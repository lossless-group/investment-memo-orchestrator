"""One bucket per firm, behind one interface.

Production uses S3-compatible buckets (Railway buckets); tests and local runs use
a directory. Keys are relative (``materials/<id>/deck.pdf``,
``compiled/<version>/memo.pdf``, ``snapshots/<id>.tar.gz``); the bucket itself is
the firm boundary, so a key can never name another firm's object.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Protocol

from .config import ConnectorSettings
from .errors import ConnectorError


class Bucket(Protocol):
    def put(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def list(self, prefix: str = "") -> list[str]: ...


def _clean_key(key: str) -> str:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ConnectorError("validation_failed", f"Bad bucket key: {key!r}")
    return str(path)


class LocalBucket:
    """A directory standing in for a bucket."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / _clean_key(key)

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        except OSError as exc:
            raise ConnectorError("storage_unavailable", details={"bucket": "local"}) from exc

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ConnectorError("artifact_not_found")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ConnectorError("storage_unavailable") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        if not self.root.exists():
            return []
        keys = [
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and not p.name.endswith(".part")
        ]
        return sorted(k for k in keys if k.startswith(prefix))


class S3Bucket:
    """An S3-compatible bucket (Railway buckets in production)."""

    def __init__(self, client, name: str):
        self.client = client
        self.name = name

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        try:
            self.client.put_object(Bucket=self.name, Key=_clean_key(key), Body=data, **extra)
        except Exception as exc:  # botocore raises many types
            raise ConnectorError("storage_unavailable", details={"bucket": "s3"}) from exc

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.name, Key=_clean_key(key))["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise ConnectorError("artifact_not_found") from exc
        except Exception as exc:
            raise ConnectorError("storage_unavailable") from exc

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.name, Key=_clean_key(key))
            return True
        except Exception:
            return False

    def list(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.name, Prefix=prefix):
                keys += [obj["Key"] for obj in page.get("Contents", [])]
        except Exception as exc:
            raise ConnectorError("storage_unavailable") from exc
        return sorted(keys)


def bucket_for(settings: ConnectorSettings, firm: str) -> Bucket:
    """The firm's bucket. Firms never share one."""
    if settings.bucket_backend == "s3":
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )
        return S3Bucket(client, settings.s3_bucket_template.format(firm=firm))
    if settings.bucket_backend == "local":
        assert settings.bucket_local_root is not None
        return LocalBucket(settings.bucket_local_root / firm)
    raise ValueError(f"Unknown MEMOPOP_BUCKET_BACKEND {settings.bucket_backend!r}")
