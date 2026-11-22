"""preview: render a section, the memo, or an artifact as the partner will see it.

Agents in Claude, ChatGPT or Claude Code must never render a memo's markdown
themselves: each would render it differently, and none numbers hex-code
citations the way the firm's site does. This renders on the server with
Lossless Flavored Markdown (:mod:`..render.lfm`) inside the firm's branded page,
and returns a signed link to it and the HTML.

It works before compile: ``memo`` assembles the current sections the way
compile would, without saving a version. Nothing in the deal changes; the
rendered page is stored in the firm's bucket under ``previews/<deal>/`` so the
link can serve it.
"""

from __future__ import annotations

import hashlib

from pydantic import Field

from .. import flow
from ..compile import links, pipeline
from ..errors import ConnectorError
from ..registry import load_registry
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace
from .submit_artifact import EXAMPLE_RESEARCH

#: The whole memo, assembled from the current sections as compile would.
MEMO = "memo"


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    artifact: str = Field(min_length=1, max_length=300)


def _missing_drafts(state: dict) -> list[str]:
    return [k for k in flow.section_keys(state) if f"draft.section:{k}" not in state["artifacts"]]


def _assembled_memo(ws: Workspace, state: dict) -> str:
    missing = _missing_drafts(state)
    if missing:
        raise ConnectorError(
            "drafts_incomplete",
            f"{len(missing)} of {len(state['sections'])} sections have no draft yet, so there "
            "is no memo to preview. Preview a section or an artifact instead.",
            details={"missing": missing},
        )
    ctx = pipeline.Context(ws=ws, registry=load_registry(), state=state)
    pipeline.assemble(ctx)
    return ctx.memo


def _resolve(ws: Workspace, state: dict, wanted: str) -> tuple[str, str, str]:
    """(markdown, title, source) for what the caller asked to see."""
    base = f"deals/{state['deal']}"
    if wanted == MEMO:
        return _assembled_memo(ws, state), "The memo, from its current sections", "sections"

    record = state["artifacts"].get(wanted)
    if record is not None:
        section = flow.section_info(state, record.get("section")) or {}
        title = record["step_id"] + (f": {section.get('name')}" if section else "")
        return ws.read_text(f"{base}/{record['path']}"), title, wanted

    key = flow.resolve_section(state, wanted)
    if key is not None:
        current = flow.current_section_key(load_registry(), state, key)
        if current is not None:
            name = flow.section_info(state, key)["name"]
            text = ws.read_text(f"{base}/{state['artifacts'][current]['path']}")
            return text, f"Section: {name}", current
        raise ConnectorError(
            "artifact_not_found",
            f"Section '{wanted}' has no draft yet. Preview its research instead.",
            details={"available": [MEMO, *sorted(state["artifacts"])]},
        )

    raise ConnectorError(
        "artifact_not_found",
        f"Nothing called '{wanted}' on this deal to preview.",
        details={"available": [MEMO, *sorted(state["artifacts"])]},
    )


def handle(ws: Workspace, params: Input) -> dict:
    state = ws.read_deal(params.deal)
    markdown, title, source = _resolve(ws, state, params.artifact.strip())
    html = pipeline.render_html(ws, state, markdown, renderer="lfm")
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
    key = f"previews/{params.deal}/{digest}.html"
    if not ws.bucket.exists(key):
        ws.bucket.put(key, html.encode("utf-8"), links.CONTENT_TYPES[".html"])
    return {
        "deal": params.deal,
        "artifact": params.artifact,
        "title": title,
        "source": source,
        "html_url": links.signed_url(ws, key),
        "html": html,
    }


TOOL = ToolDef(
    name="preview",
    summary=(
        "Show a section, the whole memo, or an artifact as the partner will see it: rendered "
        "on the server, with the firm's branding and numbered citations."
    ),
    when_to_use=(
        "the partner wants to see a draft, a rewritten section, research, or the memo as it "
        "will look, before or after compile. Give them html_url, or show the returned html as "
        "a work artifact if your client supports one."
    ),
    when_not_to_use=(
        "to read an artifact's text (use get_artifact), or to publish: preview saves no "
        "version; call compile for the memo's next version and its exports. Never render the "
        "markdown yourself and never number citations yourself; call preview."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "artifact",
            "string",
            "What to show: `memo` (the whole memo, assembled from the current sections as "
            "compile would; every section needs a draft), a section's key, name or number (its "
            "current text), or an artifact id from next_step or submit_artifact (for example "
            "compile.assemble, the last compiled memo).",
            "01-executive-summary",
            required=True,
        ),
    ],
    returns=[
        ReturnDoc("title", "What was rendered, e.g. Section: Executive Summary."),
        ReturnDoc(
            "source",
            "The artifact id the text came from, or `sections` for an assembled memo.",
        ),
        ReturnDoc("html_url", "A signed link to the rendered page, valid for seven days."),
        ReturnDoc(
            "html",
            "The rendered page: the firm's branded HTML with the body rendered by Lossless "
            "Flavored Markdown, citations numbered in the order they are first cited. Long "
            "for a whole memo; prefer giving the partner html_url.",
        ),
    ],
    changes=(
        "nothing in the deal. The rendered page is stored in the firm's bucket so the link "
        "can serve it."
    ),
    duration="a few seconds; a whole memo can take longer.",
    errors=[
        "deal_not_found",
        "artifact_not_found",
        "drafts_incomplete",
        "validation_failed",
        "service_unavailable",
    ],
    error_next_overrides={
        "service_unavailable": "Rendering is down on the server. Tell the partner the preview "
        "isn't available right now; don't render the markdown yourself.",
    },
    next="give the partner html_url (or show html as a work artifact), and ask what to change.",
    examples=[
        Example(
            title="Preview approved research",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("next_step", {"deal": "acme-ai"}),
                (
                    "submit_artifact",
                    {
                        "deal": "acme-ai",
                        "step_id": "research.section",
                        "section": "01-executive-summary",
                        "content": EXAMPLE_RESEARCH,
                        "partner_approved": True,
                    },
                ),
            ],
            request={"deal": "acme-ai", "artifact": "research.section:01-executive-summary"},
            response={
                "ok": True,
                "deal": "acme-ai",
                "artifact": "research.section:01-executive-summary",
                "title": "research.section: Executive Summary",
                "source": "research.section:01-executive-summary",
                "html_url": ANY,
                "html": ANY,
                "api_version": "1",
            },
        ),
        Example(
            title="The whole memo before every section has a draft",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai", "artifact": "memo"},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "drafts_incomplete", "details": ANY},
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=True,
    destructive=False,
    rest_method="GET",
    rest_path="/v1/deals/{deal}/preview",
)
