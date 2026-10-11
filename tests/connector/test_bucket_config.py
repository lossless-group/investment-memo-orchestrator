"""Per-firm S3 credentials (plan 2, found while writing the deploy guide).

Each Railway bucket has its own generated name and its own access key, so one
global key pair and a ``memopop-{firm}`` name template can't reach a second
firm's bucket. ``MEMOPOP_S3_FIRM_<FIRM>_<FIELD>`` sets a firm's bucket name,
keys, endpoint, and region; anything unset falls back to the global settings.
Not a spec ID: it is how the spec's "one bucket per firm" is met on Railway.
No network: boto3 builds clients without calling anything.
"""

from __future__ import annotations

import pytest

from src.connector.bucket import S3Bucket, bucket_for
from src.connector.config import ConnectorSettings

ENV = {
    "MEMOPOP_BUCKET_BACKEND": "s3",
    "MEMOPOP_S3_ENDPOINT": "https://global.example",
    "MEMOPOP_S3_ACCESS_KEY_ID": "GLOBALKEY",
    "MEMOPOP_S3_SECRET_ACCESS_KEY": "globalsecret",
    "MEMOPOP_S3_FIRM_TEST_FIRM_BUCKET": "test-firm-bucket-x1y2",
    "MEMOPOP_S3_FIRM_TEST_FIRM_ACCESS_KEY_ID": "TESTKEY",
    "MEMOPOP_S3_FIRM_TEST_FIRM_SECRET_ACCESS_KEY": "testsecret",
    "MEMOPOP_S3_FIRM_TEST_FIRM_ENDPOINT": "https://t3.storageapi.dev",
}


def creds(bucket: S3Bucket) -> tuple[str, str]:
    c = bucket.client._request_signer._credentials
    return c.access_key, c.secret_key


def test_a_firm_with_its_own_settings_uses_them():
    settings = ConnectorSettings.from_env(ENV)
    bucket = bucket_for(settings, "test-firm")
    assert isinstance(bucket, S3Bucket)
    assert bucket.name == "test-firm-bucket-x1y2"
    assert creds(bucket) == ("TESTKEY", "testsecret")
    assert bucket.client.meta.endpoint_url == "https://t3.storageapi.dev"


def test_a_firm_without_its_own_settings_falls_back_to_the_globals():
    settings = ConnectorSettings.from_env(ENV)
    bucket = bucket_for(settings, "other-firm")
    assert bucket.name == "memopop-other-firm"
    assert creds(bucket) == ("GLOBALKEY", "globalsecret")
    assert bucket.client.meta.endpoint_url == "https://global.example"


def test_virtual_hosted_addressing_is_the_default_and_can_be_changed():
    default = bucket_for(ConnectorSettings.from_env(ENV), "test-firm")
    assert default.client.meta.config.s3["addressing_style"] == "virtual"
    path = bucket_for(
        ConnectorSettings.from_env({**ENV, "MEMOPOP_S3_ADDRESSING_STYLE": "path"}), "test-firm"
    )
    assert path.client.meta.config.s3["addressing_style"] == "path"


def test_a_malformed_firm_variable_is_refused():
    with pytest.raises(ValueError, match="MEMOPOP_S3_FIRM_"):
        ConnectorSettings.from_env({"MEMOPOP_S3_FIRM_TEST_FIRM_COLOUR": "blue"})
