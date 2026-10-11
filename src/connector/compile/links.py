"""Signed links to a compiled memo, valid for seven days.

An S3 bucket (production) gets an S3 presigned URL. A local bucket (tests, local
runs) gets a link to this server, ``/v1/files/<firm>/<key>?expires=&signature=``,
signed with HMAC-SHA256 over the firm, key, and expiry using
``MEMOPOP_LINK_SECRET``. The signature is the credential: the link works without
a sign-in, for exactly that object, until it expires.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from ..bucket import S3Bucket
from ..config import ConnectorSettings
from ..errors import ConnectorError, envelope
from ..workspace import Workspace, is_slug, open_workspace

#: Seven days, which is also S3 SigV4's longest presigned URL.
LINK_TTL_SECONDS = 7 * 24 * 3600

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
}


def _signature(settings: ConnectorSettings, firm: str, key: str, expires: int) -> str:
    message = f"{firm}\n{key}\n{expires}".encode()
    return hmac.new(settings.link_secret.encode(), message, hashlib.sha256).hexdigest()


def signed_url(ws: Workspace, key: str) -> str:
    if isinstance(ws.bucket, S3Bucket):
        return ws.bucket.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": ws.bucket.name, "Key": key},
            ExpiresIn=LINK_TTL_SECONDS,
        )
    expires = int(time.time()) + LINK_TTL_SECONDS
    signature = _signature(ws.settings, ws.firm, key, expires)
    return (
        f"{ws.settings.public_base_url}/v1/files/{ws.firm}/{quote(key)}"
        f"?expires={expires}&signature={signature}"
    )


def files_router(settings: ConnectorSettings) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/files/{firm}/{key:path}", include_in_schema=False)
    def download(firm: str, key: str, expires: int = 0, signature: str = "") -> Response:
        try:
            expected = _signature(settings, firm, key, expires) if is_slug(firm) else ""
            if (
                not expected
                or not hmac.compare_digest(expected, signature)
                or expires < time.time()
            ):
                raise ConnectorError("link_expired")
            data = open_workspace(settings, firm).bucket.get(key)
        except ConnectorError as err:
            return JSONResponse(envelope(err), status_code=err.status)
        suffix = "." + key.rsplit(".", 1)[-1] if "." in key else ""
        return Response(data, media_type=CONTENT_TYPES.get(suffix, "application/octet-stream"))

    return router
