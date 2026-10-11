"""The API changelog, served at /docs/changelog. Newest first; add, never edit.

Additive changes (a new optional input, output field, tool, or error code) land
here and stay in v1. Breaking changes need /v2/ (spec §Versioning).
"""

from __future__ import annotations

API_CHANGELOG: list[dict] = [
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
