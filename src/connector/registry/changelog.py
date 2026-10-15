"""The API changelog, served at /docs/changelog. Newest first; add, never edit.

Additive changes (a new optional input, output field, tool, or error code) land
here and stay in v1. Breaking changes need /v2/ (spec §Versioning).
"""

from __future__ import annotations

API_CHANGELOG: list[dict] = [
    {
        "date": "2026-10-15",
        "version": "1.4.0",
        "changes": [
            "New tool `start_revision` (additive): reopen one or more sections of a drafted or "
            "compiled memo, with the partner's `angle`, optional `material_ids`, and `start` "
            "(research or draft). next_step then hands the reopened steps out again.",
            "New tool `cancel_revision` (additive): drop the open revision and restore each "
            "reopened artifact's earlier text as a new version.",
            "next_step returns a new field, `revision` (additive): null, or the open revision "
            "when the step was reopened by it. The step's `instruction` opens with the request.",
            "compile returns a new field, `label` (additive): the memo's version as the "
            "partner says it, the next patch after the last compile or the imported local run.",
            "list_deals returns `memo_version` and `revision` per deal (additive).",
            "New error codes (additive): `revision_open`, `revision_incomplete`, "
            "`no_open_revision`, `section_not_drafted`.",
            "An unchanged recompile of a memo with diagrams keeps its version: diagrams now "
            "render to the same bytes every time.",
        ],
    },
    {
        "date": "2026-10-11",
        "version": "1.3.0",
        "changes": [
            "next_step returns a new field, `tell_partner` (additive): one plain sentence "
            "naming each step in `skipped_since_last_call` and why, for Claude to send the "
            "partner word for word before doing the step; null when nothing was skipped. "
            'It reads "Skipped: <step title> (<sections>), because <why>.", one clause per '
            "skipped step, joined by semicolons.",
            "On the call that reports a skip, the step's `instruction` opens with the same "
            "sentence and asks Claude to send it first. Later calls for the same step don't "
            "repeat it.",
        ],
    },
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
            "save_snapshot works: it archives the firm's whole workspace, history included, to "
            "the firm's bucket under snapshots/ and returns change counts against the previous "
            "snapshot. It no longer returns `not_implemented`.",
            "save_snapshot returns a new field, `previous_snapshot_id` (additive).",
            "Every saved artifact is now kept in the firm's history, so get_artifact with an "
            "earlier `version` returns that version's text instead of `artifact_not_found`.",
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
