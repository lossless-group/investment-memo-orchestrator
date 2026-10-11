"""compile: assemble the memo and export HTML and PDF.

Plan 1 declares the tool with its full docs; plan 5 implements it (assembly,
citation consolidation, export, signed links, the job fallback past 240 s).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..errors import ConnectorError
from ..registry.types import Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace


class Input(ToolInput):
    deal: str = Field(min_length=1, max_length=100)
    formats: list[Literal["html", "pdf"]] | None = Field(default=None, min_length=1)


def handle(ws: Workspace, params: Input) -> dict:
    ws.read_deal(params.deal)
    raise ConnectorError("not_implemented", "compile is not live on this server yet.")


TOOL = ToolDef(
    name="compile",
    summary="Assemble a deal's sections into the finished memo and export it as HTML and PDF.",
    when_to_use=(
        "next_step says done and compile_ready, or the partner wants to see the memo as it "
        "stands once every section has a draft."
    ),
    when_not_to_use=(
        "before every section has a draft (it is refused); call next_step and finish the "
        "drafts first."
    ),
    inputs=[
        InputDoc("deal", "string", "The deal's slug.", "acme-ai", required=True),
        InputDoc(
            "formats",
            "array",
            "Which exports to make: html, pdf, or both (the default).",
            ["html", "pdf"],
        ),
    ],
    returns=[
        ReturnDoc("html_url", "A signed link to the HTML memo, valid for seven days."),
        ReturnDoc("pdf_url", "A signed link to the PDF memo, valid for seven days."),
        ReturnDoc("version", "The compiled memo's version."),
        ReturnDoc("report", "The sections included, the enhancements run, and the skips."),
        ReturnDoc(
            "job_id",
            "Only when compiling takes longer than 240 seconds; list_deals reports when it finishes.",
        ),
    ],
    changes="writes the compiled memo to the workspace and copies the exports to the firm's bucket.",
    duration="typically under a minute; past 240 seconds it returns a job instead.",
    errors=["deal_not_found", "not_implemented"],
    error_next_overrides={
        "not_implemented": "Compiling isn't live yet: tell the partner the sections are saved "
        "and can be read with get_artifact.",
    },
    next="give the partner the links and the report's skips, one line each.",
    examples=[
        Example(
            title="Compile a deal (until compile ships, this returns not_implemented)",
            setup=[("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"})],
            request={"deal": "acme-ai"},
            response={
                "ok": False,
                "error": {"kind": "invalid", "code": "not_implemented"},
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
    rest_path="/v1/deals/{deal}/compile",
    implemented=False,
)
