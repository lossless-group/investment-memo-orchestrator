"""create_new_deal: start a deal for a company, or return the one that exists."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field

from .. import flow
from ..errors import ConnectorError
from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..templates import default_template, load_sections
from ..workspace import Workspace, is_slug


class Input(ToolInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    stage: str | None = Field(default=None, max_length=80)
    template: str | None = Field(default=None, max_length=100)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:80].strip("-")


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    host = (urlsplit(raw).hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _norm_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split())


def _find_existing(ws: Workspace, slug: str, domain: str | None, company: str) -> dict | None:
    if ws.deal_exists(slug):
        return ws.read_deal(slug)
    wanted = _norm_name(company)
    for other in ws.deal_slugs():
        state = ws.read_deal(other)
        if domain and state.get("domain") == domain:
            return state
        if _norm_name(state.get("company", "")) == wanted:
            return state
    return None


def _body(state: dict, created: bool) -> dict:
    return {
        "deal": state["deal"],
        "created": created,
        "template": state["template"],
        "sections": [{"key": s["key"], "name": s["name"]} for s in state["sections"]],
    }


def handle(ws: Workspace, params: Input) -> dict:
    domain = domain_of(params.url)
    slug = slugify(domain) if domain else slugify(params.company)
    if not is_slug(slug):
        raise ConnectorError(
            "validation_failed",
            "Can't make a deal name from that company name; add its url.",
            details={"errors": [{"field": "company", "problem": "no letters or digits"}]},
        )
    template = params.template or default_template(ws)
    sections = load_sections(ws, template)

    with ws.lock("_create"):
        existing = _find_existing(ws, slug, domain, params.company)
        if existing is not None:
            return _body(existing, created=False)
        state = flow.new_deal_state(
            slug, params.company, params.url, domain, params.stage, template, sections
        )
        with ws.transaction() as tx:
            path = tx.write_json(ws.deal_rel(slug) / "deal.json", state)
        ws.history.record(f"create_new_deal: {slug} ({template})", [path])
    return _body(state, created=True)


TOOL = ToolDef(
    name="create_new_deal",
    summary="Start a new deal for a company this firm has no record of yet.",
    when_to_use=(
        "the partner names a company to write a memo on and list_deals doesn't show it. "
        "Calling this twice for the same company is safe; it returns the existing deal."
    ),
    when_not_to_use="to continue an existing deal: call next_step with its slug instead.",
    inputs=[
        InputDoc("company", "string", "The company's name.", "Acme Robotics", required=True),
        InputDoc(
            "url",
            "string",
            "The company's website; strongly preferred, because it makes the deal slug unambiguous.",
            "https://acme.ai",
        ),
        InputDoc("stage", "string", "The round being evaluated.", "Series A"),
        InputDoc(
            "template",
            "string",
            "The memo outline to use; omit for the firm's default.",
            "direct-early-stage-12Ps",
        ),
    ],
    returns=[
        ReturnDoc("deal", "The deal's slug: from the url's domain if given, else from the name."),
        ReturnDoc("created", "true if this call created the deal; false if it already existed."),
        ReturnDoc("template", "The memo template the deal uses."),
        ReturnDoc("sections", "The memo's sections, in order, each with its key and name."),
    ],
    changes="creates the deal folder and its first history entry; nothing if it already exists.",
    duration="under a second.",
    errors=["template_not_found", "validation_failed"],
    error_next_overrides={
        "validation_failed": "`company` is empty or unusable: ask the partner for the "
        "company's name and website and call again.",
    },
    next=(
        "ask the partner for their materials and call add_materials, or call next_step to "
        "begin research without them."
    ),
    examples=[
        Example(
            title="A new company",
            request={"company": "Acme Robotics", "url": "https://acme.ai", "stage": "Seed"},
            response={
                "ok": True,
                "deal": "acme-ai",
                "created": True,
                "template": "direct-early-stage-12Ps",
                "sections": [
                    {"key": "01-executive-summary", "name": "Executive Summary"},
                    {"key": "02-origins", "name": "Origins"},
                    {"key": "03-opening", "name": "Opening"},
                    {"key": "04-organization", "name": "Organization"},
                    {"key": "05-offering", "name": "Offering"},
                    {"key": "06-opportunity", "name": "Opportunity"},
                    {"key": "07-risks", "name": "Risks & What Could Go Wrong"},
                    {"key": "08-scorecard-summary", "name": "12Ps Scorecard Summary"},
                    {"key": "09-funding-terms", "name": "Funding & Terms"},
                    {"key": "10-closing-assessment", "name": "Closing Assessment"},
                ],
                "api_version": "1",
            },
        ),
        Example(
            title="The same company again",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"company": "Acme Robotics", "url": "https://www.acme.ai/"},
            response={"ok": True, "deal": "acme-ai", "created": False, "sections": ANY},
        ),
        Example(
            title="An unknown template",
            request={"company": "Acme Robotics", "template": "no-such-outline"},
            response={
                "ok": False,
                "error": {
                    "kind": "invalid",
                    "code": "template_not_found",
                    "message": "No memo template called 'no-such-outline'.",
                    "next": "Call create_new_deal again without `template` to use the firm's default.",
                    "details": {"available": ANY},
                },
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    blocks="yes (required)",
    rest_method="POST",
    rest_path="/v1/deals",
)
