"""Connector settings, read from the environment once per app.

| Env var | Meaning | Default |
|---|---|---|
| `MEMO_IO_ROOT` | Root of the firm workspaces (`<root>/<firm>/deals/...`) | `/data/firms` |
| `MEMOPOP_PUBLIC_BASE_URL` | The public origin; every URL we publish is built from it | `https://memopop.didi.sh` |
| `MEMOPOP_AUTH_ISSUER` | The authorization server, and the tokens' `iss` | `https://id.didi.sh` |
| `MEMOPOP_JWKS_URL` | Where token signing keys are fetched | `https://id.didi.sh/.well-known/jwks.json` |
| `MEMOPOP_TOKEN_AUDIENCE` | The `aud` tokens must carry (`<aud>/mcp` is accepted too) | `https://memopop.didi.sh` |
| `MEMOPOP_STATIC_KEYS` | Interim per-firm keys, `firm=key,firm=key` (Claude Code and the health check only) | none |
| `MEMOPOP_DISABLED_STEPS` | Ops switch: comma-separated step ids to skip (optional steps only) | none |
| `MEMOPOP_COMPILE_BUDGET_SECONDS` | How long compile works before it returns a job instead | `200` |
| `MEMOPOP_LINK_SECRET` | Signs compiled-memo links served from a local bucket (S3 links are presigned) | random per process |
| `MEMOPOP_BUCKET_BACKEND` | `local` or `s3` | `local` |
| `MEMOPOP_BUCKET_LOCAL_ROOT` | Root of the local buckets (`<root>/<firm>/...`) | `<MEMO_IO_ROOT>/../buckets` |
| `MEMOPOP_S3_ENDPOINT` | S3-compatible endpoint (falls back to `AWS_ENDPOINT_URL`) | none |
| `MEMOPOP_S3_ACCESS_KEY_ID` | (falls back to `AWS_ACCESS_KEY_ID`) | none |
| `MEMOPOP_S3_SECRET_ACCESS_KEY` | (falls back to `AWS_SECRET_ACCESS_KEY`) | none |
| `MEMOPOP_S3_REGION` | (falls back to `AWS_REGION`) | `auto` |
| `MEMOPOP_S3_BUCKET_TEMPLATE` | One bucket per firm; `{firm}` is replaced | `memopop-{firm}` |
| `MEMOPOP_JJ_BIN` | The jj binary that keeps each firm's history (absent: no history kept) | `jj` |
| `MEMOPOP_FAULT_FIRMS` | Test only: firms whose own outlines may force a skip and a `down` (`src/connector/faults.py`). Only ever `test-firm` | none |
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_static_keys(raw: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        firm, sep, key = pair.partition("=")
        if not sep or not firm.strip() or not key.strip():
            raise ValueError("MEMOPOP_STATIC_KEYS must look like firm=key,firm=key")
        keys[firm.strip()] = key.strip()
    return keys


@dataclass
class ConnectorSettings:
    io_root: Path = Path("/data/firms")
    public_base_url: str = "https://memopop.didi.sh"
    auth_issuer: str = "https://id.didi.sh"
    jwks_url: str = "https://id.didi.sh/.well-known/jwks.json"
    token_audience: str = "https://memopop.didi.sh"
    #: firm -> key. Interim; removed the day didi.sh OAuth is live for every client.
    static_keys: dict[str, str] = field(default_factory=dict)
    disabled_steps: set[str] = field(default_factory=set)
    #: Test only (src/connector/faults.py): firms whose own outlines may inject faults.
    fault_firms: set[str] = field(default_factory=set)
    bucket_backend: str = "local"
    bucket_local_root: Path | None = None
    s3_endpoint: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_region: str = "auto"
    s3_bucket_template: str = "memopop-{firm}"
    #: The jj binary for per-firm history (phase 6).
    jj_bin: str = "jj"
    #: MemoPop's own outlines. A firm's own live in <firm>/templates/outlines/.
    templates_dir: Path = REPO_ROOT / "templates" / "outlines"
    default_template: str = "direct-early-stage-12Ps"
    jwks_cache_seconds: int = 300
    #: compile returns a job past this (spec: never block past 240 s; plan 5: 200 s).
    compile_budget_seconds: float = 200.0
    #: Signs local-bucket download links. Random per process unless set, so a
    #: restart invalidates them; production uses S3 presigned links instead.
    link_secret: str = field(default_factory=lambda: secrets.token_hex(32))

    def __post_init__(self) -> None:
        self.io_root = Path(self.io_root)
        self.public_base_url = self.public_base_url.rstrip("/")
        if self.bucket_local_root is None:
            self.bucket_local_root = self.io_root.parent / "buckets"
        self.bucket_local_root = Path(self.bucket_local_root)

    @property
    def mcp_url(self) -> str:
        """The connector URL partners enter, and the protected resource's id."""
        return f"{self.public_base_url}/mcp"

    @property
    def resource_metadata_url(self) -> str:
        return f"{self.public_base_url}/.well-known/oauth-protected-resource/mcp"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ConnectorSettings:
        e = os.environ if env is None else env

        def get(name: str, fallback: str | None = None, default: str | None = None):
            return e.get(name) or (e.get(fallback) if fallback else None) or default

        local_root = get("MEMOPOP_BUCKET_LOCAL_ROOT")
        return cls(
            io_root=Path(get("MEMO_IO_ROOT", default="/data/firms")),
            public_base_url=get("MEMOPOP_PUBLIC_BASE_URL", default="https://memopop.didi.sh"),
            auth_issuer=get("MEMOPOP_AUTH_ISSUER", default="https://id.didi.sh"),
            jwks_url=get("MEMOPOP_JWKS_URL", default="https://id.didi.sh/.well-known/jwks.json"),
            token_audience=get("MEMOPOP_TOKEN_AUDIENCE", default="https://memopop.didi.sh"),
            static_keys=_parse_static_keys(get("MEMOPOP_STATIC_KEYS", default="")),
            disabled_steps={
                s.strip() for s in get("MEMOPOP_DISABLED_STEPS", default="").split(",") if s.strip()
            },
            fault_firms={
                s.strip() for s in get("MEMOPOP_FAULT_FIRMS", default="").split(",") if s.strip()
            },
            bucket_backend=get("MEMOPOP_BUCKET_BACKEND", default="local"),
            bucket_local_root=Path(local_root) if local_root else None,
            s3_endpoint=get("MEMOPOP_S3_ENDPOINT", "AWS_ENDPOINT_URL"),
            s3_access_key_id=get("MEMOPOP_S3_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
            s3_secret_access_key=get("MEMOPOP_S3_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY"),
            s3_region=get("MEMOPOP_S3_REGION", "AWS_REGION", default="auto"),
            s3_bucket_template=get("MEMOPOP_S3_BUCKET_TEMPLATE", default="memopop-{firm}"),
            jj_bin=get("MEMOPOP_JJ_BIN", default="jj"),
            compile_budget_seconds=float(get("MEMOPOP_COMPILE_BUDGET_SECONDS", default="200")),
            **({"link_secret": secret} if (secret := get("MEMOPOP_LINK_SECRET")) else {}),
        )
