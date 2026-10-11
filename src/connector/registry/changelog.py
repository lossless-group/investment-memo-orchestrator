"""The API changelog, served at /docs/changelog. Newest first; add, never edit.

Additive changes (a new optional input, output field, tool, or error code) land
here and stay in v1. Breaking changes need /v2/ (spec §Versioning).
"""

from __future__ import annotations

API_CHANGELOG: list[dict] = [
    {
        "date": "2026-10-10",
        "version": "1.2.0",
        "changes": [
            "compile works: it assembles the sections in outline order, consolidates and "
            "renumbers citations, adds the table of contents and the market-sizing diagram, "
            "and returns signed HTML and PDF links that last seven days. Past about 200 seconds "
            "it returns a job_id instead, and list_deals reports the job.",
            "submit_artifact takes `skip` and `reason` (optional inputs): Claude skips an "
            "optional step it can't do well, and the skip is listed like any other. `content` "
            "is now required only without `skip`. New output field `skipped`.",
            "list_deals adds `compile` to each deal: the last compile's job, status, version, "
            "and links.",
            "The enhancement steps (tables, diagrams, citations, fact check, scorecard, "
            "summaries, one-pager) and research.sources carry full instructions.",
            "Error codes `drafts_incomplete` (invalid, 409), `link_expired` (invalid, 410), and "
            "`step_skipped` (skipped) added (additive).",
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
