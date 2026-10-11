"""compile's server steps: assemble the memo from the saved sections, then export it.

No model is called. Each stage reuses the existing agents' pure functions
(spec §First mapping, ``compile.assemble``):

| Stage | Required | Reuses |
|---|---|---|
| ``compile.sections`` | yes | the deal's current section texts (``flow.current_section_key``), the revised summaries, the scorecard |
| ``compile.citations`` | yes | ``citation_assembly.consolidate_citations`` |
| ``compile.spacing`` | no | ``citation_spacing.fix_citation_spacing`` |
| ``compile.toc`` | no | ``toc_generator`` (``extract_headers``, ``generate_toc_markdown``, ``insert_toc_after_executive_summary``) |
| ``compile.deck_images`` | no | ``inject_deck_images._insert_after_best_header`` |
| ``compile.diagrams`` | no | ``diagram_generator`` (``render_tam_sam_som``, ``insert_after_first_paragraph``) |
| ``compile.finalize`` | yes | (tidies whitespace) |
| ``compile.html`` / ``compile.pdf`` | yes, when asked for | ``cli.export_branded.render_branded_html``, WeasyPrint |

An optional stage that is switched off (``MEMOPOP_DISABLED_STEPS``) is skipped
with ``step_disabled``; one that raises is skipped with ``step_failed`` and the
memo is still produced (CONN-ENH-03). A required stage that raises fails the
compile. Stages look themselves up in :data:`STAGE_IMPLS` at run time, which is
also the seam tests use to make one fail or run slowly.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from .. import flow
from ..config import REPO_ROOT
from ..errors import ConnectorError
from ..registry import Registry
from ..workspace import Workspace

log = logging.getLogger("memopop.connector.compile")

BASE_CSS = REPO_ROOT / "templates" / "base-style.css"


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    required: bool


STAGES = [
    Stage("compile.sections", "Gather the sections", True),
    Stage("compile.citations", "Consolidate and renumber citations", True),
    Stage("compile.spacing", "Fix citation spacing", False),
    Stage("compile.toc", "Add the table of contents", False),
    Stage("compile.deck_images", "Place the deck's images", False),
    Stage("compile.diagrams", "Draw the market-sizing diagram", False),
    Stage("compile.finalize", "Finalize the memo", True),
]


@dataclass
class Context:
    ws: Workspace
    registry: Registry
    state: dict
    #: Per section, in outline order: key, name, text, and which artifact it came from.
    sections: list[dict] = field(default_factory=list)
    #: Whole-memo additions after the last section (the scorecard).
    extras: list[str] = field(default_factory=list)
    memo: str = ""
    citations: dict = field(default_factory=dict)
    skipped: list[dict] = field(default_factory=list)

    def text(self, artifact_id: str) -> str | None:
        record = self.state["artifacts"].get(artifact_id)
        if record is None:
            return None
        return self.ws.read_text(f"deals/{self.state['deal']}/{record['path']}")


# ------------------------------------------------------------------ stages

_H2 = re.compile(r"^##\s+(?!#)(.+?)\s*$", re.MULTILINE)


def _split_h2(text: str) -> list[tuple[str, str]]:
    """Split markdown into (heading, block) pairs at each level-2 heading."""
    marks = list(_H2.finditer(text))
    return [
        (m.group(1).strip(), text[m.start() : marks[i + 1].start() if i + 1 < len(marks) else None])
        for i, m in enumerate(marks)
    ]


_CITATION_BLOCK = re.compile(r"\n-{3,}[ \t]*\n+###\s+Citations\b")


def _split_citations(text: str) -> tuple[str, str]:
    """(everything before the consolidated citation block, the block itself)."""
    match = _CITATION_BLOCK.search(text)
    return (text[: match.start()], text[match.start() :]) if match else (text, "")


def gather_sections(ctx: Context) -> None:
    state = ctx.state
    for section in state["sections"]:
        key = flow.current_section_key(ctx.registry, state, section["key"])
        text = ctx.text(key) if key else None
        if text is None:  # compile refuses this before any stage runs
            raise ConnectorError("drafts_incomplete", details={"missing": [section["key"]]})
        if not _H2.search(text.split("\n", 3)[0] if text else ""):
            text = f"## {section['name']}\n\n{text}"
        ctx.sections.append(
            {"key": section["key"], "name": section["name"], "text": text, "from": key}
        )

    # The revised bookend sections replace theirs, matched by heading.
    summaries = ctx.text("enhance.summaries")
    if summaries:
        from src.agents.citation_assembly import extract_citation_definitions

        definitions = extract_citation_definitions(summaries)
        block = "\n".join(f"[^{k}]: {v}" for k, v in definitions.items())
        by_name = {s["name"].strip().lower(): s for s in ctx.sections}
        for heading, part in _split_h2(summaries):
            target = by_name.get(heading.lower())
            if target is not None:
                body = re.sub(r"^\[\^[^\]\s]+\]:.*$", "", part, flags=re.MULTILINE)
                body = re.sub(r"\n#{2,3}\s*Citations\s*$", "", body.rstrip()).rstrip()
                target["text"] = f"{body}\n\n### Citations\n\n{block}\n"
                target["from"] = "enhance.summaries"

    scorecard = ctx.text("enhance.scorecard")
    if scorecard:
        ctx.extras.append(scorecard)


def consolidate(ctx: Context) -> None:
    from src.agents.citation_assembly import consolidate_citations

    texts = [s["text"] for s in ctx.sections] + ctx.extras
    bodies, block, stats = consolidate_citations(texts)
    title = f"# Investment Memo: {ctx.state['company']}"
    ctx.memo = "\n\n".join([title, *[b.strip() for b in bodies]]) + "\n" + block
    ctx.citations = {"sources": stats["sources"], "missing": len(stats["missing"])}


def spacing(ctx: Context) -> None:
    from src.agents.citation_spacing import fix_citation_spacing

    ctx.memo = fix_citation_spacing(ctx.memo)


def toc(ctx: Context) -> None:
    from src.agents.toc_generator import (
        extract_headers,
        generate_toc_markdown,
        insert_toc_after_executive_summary,
        remove_existing_toc,
    )

    body, citations = _split_citations(remove_existing_toc(ctx.memo))
    contents = generate_toc_markdown(extract_headers(body))
    if not contents:
        return
    if re.search(r"^##\s+.*executive summary", body, re.IGNORECASE | re.MULTILINE):
        body = insert_toc_after_executive_summary(body, contents)
    else:  # no executive summary: right after the title
        title, _, rest = body.partition("\n\n")
        body = f"{title}\n\n{contents}\n{rest}"
    ctx.memo = body + citations


def _edit_section(memo: str, name: str, edit: Callable[[str], str]) -> str:
    """Apply ``edit`` to one section of the joined memo, found by its heading."""
    for heading, block in _split_h2(memo):
        if heading.strip().lower() == name.strip().lower():
            body, rest = _split_citations(block)
            start = memo.index(block)
            return memo[:start] + edit(body) + rest + memo[start + len(block) :]
    raise ValueError(f"no section headed {name!r} in the memo")


def deck_images(ctx: Context) -> None:
    """Place deck images listed by the materials step, if it listed any.

    Contract (pending phase 4): ``materials/deck-images.json`` in the deal, a list
    of ``{"url", "section", "alt", "category", "slug"}``. No file, nothing to do.
    """
    from src.agents.inject_deck_images import _insert_after_best_header

    path = ctx.ws.root / "deals" / ctx.state["deal"] / "materials" / "deck-images.json"
    if not path.is_file():
        return
    for image in json.loads(path.read_text(encoding="utf-8")):
        info = flow.section_info(ctx.state, flow.resolve_section(ctx.state, image["section"]))
        if info is None:
            continue
        embed = f"![{image.get('alt') or 'Deck slide'}]({image['url']})"
        ctx.memo = _edit_section(
            ctx.memo,
            info["name"],
            lambda text, img=image, e=embed: _insert_after_best_header(
                text, e, img.get("category", ""), img.get("slug", "")
            ),
        )


_FENCED_YAML = re.compile(r"^```ya?ml[ \t]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def diagrams(ctx: Context) -> None:
    """Draw the TAM/SAM/SOM diagram from enhance.diagrams' data into its section."""
    text = ctx.text("enhance.diagrams")
    if not text:
        return
    from src.agents.diagram_generator import (
        _parse_dollar_value,
        insert_after_first_paragraph,
        render_tam_sam_som,
    )

    data = yaml.safe_load(_FENCED_YAML.search(text).group(1))
    info = flow.section_info(ctx.state, flow.resolve_section(ctx.state, str(data["section"])))
    if info is None:
        raise ValueError(f"enhance.diagrams names an unknown section {data['section']!r}")
    values = {k: _parse_dollar_value(str(data[k])) for k in ("tam", "sam", "som")}
    if None in values.values():
        raise ValueError("enhance.diagrams has a figure that is not a dollar amount")
    growth = {f"{k}_growth": str(data[f"{k}_growth"]) for k in values if data.get(f"{k}_growth")}
    with tempfile.TemporaryDirectory(prefix="memopop-diagram-") as tmp:
        svg, _png = render_tam_sam_som(
            values["tam"], values["sam"], values["som"], Path(tmp), growth, ctx.state["company"]
        )
        encoded = base64.b64encode(svg.read_bytes()).decode()
    image = f"\n![Market sizing: TAM, SAM, and SOM](data:image/svg+xml;base64,{encoded})\n"
    ctx.memo = _edit_section(
        ctx.memo, info["name"], lambda body: insert_after_first_paragraph(body, image)
    )


def finalize(ctx: Context) -> None:
    ctx.memo = re.sub(r"\n{3,}", "\n\n", ctx.memo).strip() + "\n"


STAGE_IMPLS: dict[str, Callable[[Context], None]] = {
    "compile.sections": gather_sections,
    "compile.citations": consolidate,
    "compile.spacing": spacing,
    "compile.toc": toc,
    "compile.deck_images": deck_images,
    "compile.diagrams": diagrams,
    "compile.finalize": finalize,
}


def assemble(ctx: Context) -> None:
    """Run every stage in order; record skips for optional ones."""
    disabled = ctx.ws.settings.disabled_steps
    for stage in STAGES:
        if not stage.required and stage.id in disabled:
            ctx.skipped.append(
                {
                    "step_id": stage.id,
                    "section": None,
                    "code": "step_disabled",
                    "reason": f"{stage.title} is turned off on this server.",
                }
            )
            continue
        if stage.required:
            STAGE_IMPLS[stage.id](ctx)
            continue
        before = ctx.memo
        try:
            STAGE_IMPLS[stage.id](ctx)
        except Exception as exc:  # an optional step never blocks the memo
            log.warning("optional compile stage %s failed", stage.id, exc_info=True)
            ctx.memo = before
            ctx.skipped.append(
                {
                    "step_id": stage.id,
                    "section": None,
                    "code": "step_failed",
                    "reason": f"{stage.title} failed ({exc.__class__.__name__}).",
                }
            )


# ------------------------------------------------------------------ export


def _brand(ws: Workspace):
    from src.branding import BrandConfig

    for name in (f"brand-{ws.firm}-config.yaml", "brand-config.yaml"):
        path = ws.root / "configs" / name
        if path.is_file():
            return BrandConfig.load(config_path=path)
    return BrandConfig.get_default_config()


def render_html(ws: Workspace, state: dict, memo: str) -> str:
    from cli.export_branded import render_branded_html

    return render_branded_html(
        memo,
        title=f"{state['company']} - Investment Memo",
        company=state["company"],
        brand=_brand(ws),
        css_path=BASE_CSS,
        memo_date=datetime.now(UTC).strftime("%Y-%m-%d"),
    )


def render_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except OSError as exc:  # its system libraries are missing
        raise ConnectorError(
            "service_unavailable", "PDF export is unavailable on this server right now."
        ) from exc
    return HTML(string=html, base_url=str(BASE_CSS.parent)).write_pdf()


def report_for(registry: Registry, state: dict, ctx: Context, skips: list[dict]) -> dict:
    """What compile tells the partner: kept small, since MCP carries it twice."""
    enhance = [s for s in registry.steps if s.phase == "enhance" and s.runs_on == "claude"]
    run, not_run = [], []
    for step in enhance:
        keys = flow.section_keys(state) if step.scope == "section" else [None]
        insts = [flow.Instance(step, k) for k in keys]
        if any(i.key in state["artifacts"] for i in insts):
            run.append(step.id)
        elif not all(flow.is_skipped(i, state) for i in insts):
            not_run.append(step.id)
    return {
        "sections": [{"key": s["key"], "name": s["name"]} for s in ctx.sections],
        "enhancements_run": run,
        "skipped": [{k: s.get(k) for k in ("step_id", "section", "code", "reason")} for s in skips],
        "not_run": not_run,
        "citations": ctx.citations,
    }
