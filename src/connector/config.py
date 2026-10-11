"""Connector settings (TDD floor stub)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConnectorSettings:
    io_root: Path = Path("/data/firms")
    public_base_url: str = "https://memopop.didi.sh"
    auth_issuer: str = "https://id.didi.sh"
    jwks_url: str = "https://id.didi.sh/.well-known/jwks.json"
    token_audience: str = "https://memopop.didi.sh"
    static_keys: dict[str, str] = field(default_factory=dict)
    bucket_backend: str = "local"
    bucket_local_root: Path | None = None
    disabled_steps: set[str] = field(default_factory=set)
