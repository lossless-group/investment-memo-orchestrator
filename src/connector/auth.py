"""Who is calling, and for which firm.

Two credentials, both sent as ``Authorization: Bearer <credential>``:

1. **id.didi.sh access tokens** (the real path). EdDSA (Ed25519) JWTs, header
   ``{"alg": "EdDSA", "kid": ..., "typ": "at+jwt"}``, verified against the JWKS
   at ``MEMOPOP_JWKS_URL``. Required claims: ``iss`` (``MEMOPOP_AUTH_ISSUER``),
   ``sub``, ``aud`` (``https://memopop.didi.sh`` or ``https://memopop.didi.sh/mcp``;
   a list containing either is fine), ``exp``, ``iat``. The firm comes from
   ``entity``: ``{"id": ..., "slug": ...}``, mapped by ``entity.slug``. Also
   accepted, for robustness: ``entity`` as a bare slug string, an ``entity`` with
   only ``id`` (matched against ``entity_id`` in a firm's ``firm.json``), and an
   ``entities`` list of either form for people in several firms. ``scope``,
   ``client_id`` and ``jti`` are carried but not enforced yet.
2. **Static per-firm keys** (``MEMOPOP_STATIC_KEYS``), interim, for Claude Code
   and the health check only, never given to a client. ``X-MemoPop-Key`` works
   too. Remove this path the day didi.sh OAuth serves every client.

A request without a valid credential is ``unauthenticated`` (401) with
``WWW-Authenticate: Bearer resource_metadata="<base>/.well-known/oauth-protected-resource/mcp"``.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import jwt

from .config import ConnectorSettings
from .errors import ConnectorError
from .workspace import is_slug

ACCESS_TOKEN_TYPES = {"at+jwt", "application/at+jwt"}
#: Don't refetch the JWKS for an unknown kid more often than this.
JWKS_REFETCH_SECONDS = 30


@dataclass(frozen=True)
class Principal:
    firms: tuple[str, ...]
    via: str  # "token" or "static_key"
    subject: str
    claims: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


class JwksCache:
    def __init__(self, settings: ConnectorSettings, client: httpx.Client):
        self.settings = settings
        self.client = client
        self._keys: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def _fetch(self) -> None:
        try:
            response = self.client.get(self.settings.jwks_url, timeout=10)
            response.raise_for_status()
            keys = response.json().get("keys", [])
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(
                "service_unavailable", "MemoPop could not reach the sign-in service's keys."
            ) from exc
        parsed = {}
        for jwk in keys:
            if jwk.get("kid") and jwk.get("kty") == "OKP" and jwk.get("crv") == "Ed25519":
                parsed[jwk["kid"]] = jwt.PyJWK(jwk, algorithm="EdDSA").key
        self._keys = parsed
        self._fetched_at = time.monotonic()

    def key(self, kid: str):
        with self._lock:
            age = time.monotonic() - self._fetched_at
            if not self._keys or age > self.settings.jwks_cache_seconds:
                self._fetch()
            elif kid not in self._keys and age > JWKS_REFETCH_SECONDS:
                self._fetch()  # the issuer may have rotated keys
            return self._keys.get(kid)


class Authenticator:
    def __init__(self, settings: ConnectorSettings, client: httpx.Client):
        self.settings = settings
        self.jwks = JwksCache(settings, client)

    def challenge(self, error: str | None = None) -> str:
        value = f'Bearer resource_metadata="{self.settings.resource_metadata_url}"'
        if error:
            value += f', error="{error}"'
        return value

    def authenticate(self, headers) -> Principal:
        credential = None
        auth = headers.get("authorization") or ""
        if auth[:7].lower() == "bearer ":
            credential = auth[7:].strip()
        credential = credential or (headers.get("x-memopop-key") or "").strip() or None
        if not credential:
            raise ConnectorError("unauthenticated")
        firm = self._static_firm(credential)
        if firm:
            return Principal((firm,), "static_key", f"static:{firm}")
        return self._verify_token(credential)

    def _static_firm(self, credential: str) -> str | None:
        found = None
        for firm, key in self.settings.static_keys.items():
            if hmac.compare_digest(credential.encode(), key.encode()):
                found = firm
        return found

    def _verify_token(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise ConnectorError("unauthenticated", "That sign-in token is not readable.") from None
        if (
            header.get("alg") != "EdDSA"
            or str(header.get("typ", "")).lower() not in ACCESS_TOKEN_TYPES
        ):
            raise ConnectorError("unauthenticated", "That token is not a didi.sh access token.")
        key = self.jwks.key(str(header.get("kid") or ""))
        if key is None:
            raise ConnectorError("unauthenticated", "That token was signed by an unknown key.")
        audience = self.settings.token_audience.rstrip("/")
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                audience=[audience, f"{audience}/mcp"],
                issuer=self.settings.auth_issuer,
                leeway=30,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise ConnectorError("unauthenticated", "That sign-in has expired.") from None
        except jwt.PyJWTError:
            raise ConnectorError(
                "unauthenticated", "That sign-in token is not valid here."
            ) from None
        firms = self._firms_from_claims(claims)
        if not firms:
            raise ConnectorError("unauthenticated", "That sign-in names no MemoPop firm.")
        return Principal(tuple(firms), "token", str(claims["sub"]), claims)

    def _firms_from_claims(self, claims: dict) -> list[str]:
        entities = []
        if "entity" in claims:
            entities.append(claims["entity"])
        if isinstance(claims.get("entities"), list):
            entities += claims["entities"]
        firms: list[str] = []
        for entity in entities:
            firm = self._firm_for_entity(entity)
            if firm and firm not in firms:
                firms.append(firm)
        return firms

    def _firm_for_entity(self, entity: Any) -> str | None:
        if isinstance(entity, str):
            return entity if is_slug(entity) else None
        if not isinstance(entity, dict):
            return None
        slug = entity.get("slug")
        if isinstance(slug, str) and is_slug(slug):
            return slug
        entity_id = entity.get("id")
        if isinstance(entity_id, str) and entity_id:
            return self._firm_by_entity_id(entity_id)
        return None

    def _firm_by_entity_id(self, entity_id: str) -> str | None:
        root = Path(self.settings.io_root)
        if not root.is_dir():
            return None
        for config in root.glob("*/firm.json"):
            try:
                if json.loads(config.read_text() or "{}").get("entity_id") == entity_id:
                    return config.parent.name
            except (OSError, ValueError, AttributeError):
                continue
        return None


def select_firm(principal: Principal, requested: str | None) -> str:
    """The firm to act for. Naming a firm the credential lacks is ``forbidden_firm``,
    with the same answer whether or not that firm exists."""
    if requested is not None:
        if requested in principal.firms:
            return requested
        raise ConnectorError("forbidden_firm")
    if len(principal.firms) == 1:
        return principal.firms[0]
    raise ConnectorError(
        "validation_failed",
        "This sign-in belongs to more than one firm; pass `firm`.",
        details={"errors": [{"field": "firm", "allowed": list(principal.firms)}]},
    )


def protected_resource_document(settings: ConnectorSettings) -> dict:
    """RFC 9728 metadata. Built from the configured base URL, never the request,
    so a proxy forwarding plain http can't turn these URLs into http (CONN-AUTH-02)."""
    return {
        "resource": settings.mcp_url,
        "authorization_servers": [settings.auth_issuer],
        "bearer_methods_supported": ["header"],
        "resource_name": "MemoPop",
        "resource_documentation": f"{settings.public_base_url}/docs",
    }
