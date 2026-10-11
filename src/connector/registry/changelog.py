"""The API changelog, served at /docs/changelog. Newest first; add, never edit.

Additive changes (a new optional input, output field, tool, or error code) land
here and stay in v1. Breaking changes need /v2/ (spec §Versioning).
"""

from __future__ import annotations

API_CHANGELOG: list[dict] = [
    {
        "date": "2026-10-10",
        "version": "1.1.0",
        "changes": [
            "add_materials works: inline text (up to 100,000 characters) is ready at once; "
            "links are fetched in the background (Google Drive and Dropbox share links "
            "rewritten, DocSend not yet); an item with only a filename returns a one-time "
            "`upload_url` (single use, one hour) and `upload_expires_at`.",
            "add_materials `accepted` entries now carry `kind` (additive).",
            "A link or file that can't be read is recorded as a `material_unreadable` skip, "
            "reported by next_step and list_deals; the deal continues.",
            "New page outside the API: GET and POST /upload/{token}, the one-time upload form.",
            "add_materials no longer returns `not_implemented`.",
        ],
    },
    {
        "date": "2026-10-10",
        "version": "1.0.0",
        "changes": [
            "v1 of the MemoPop connector: MCP at /mcp and REST under /v1/.",
            "list_deals, create_new_deal, next_step, submit_artifact, and get_artifact work.",
            "add_materials, save_snapshot, and compile are declared with full docs and "
            "return `not_implemented` until their phases ship.",
            "Error code `not_implemented` added to the catalogue (additive).",
            "Sign-in with didi.sh access tokens (EdDSA, typ at+jwt); interim static keys "
            "for Claude Code and the health check.",
        ],
    },
]
