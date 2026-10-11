"""The error envelope and the full code catalogue.

Every failure, on both transports, is one envelope::

    {"ok": false,
     "error": {"kind", "code", "message", "next", "retry_after_seconds", "details"},
     "api_version": "1"}

Three kinds (context-v/decisions: Three-Kinds-of-Error-and-Optional-Steps-Never-Block):

- ``down``: our side is broken. REST 503 (with Retry-After) or 504.
- ``invalid``: the call was wrong. REST 4xx.
- ``skipped``: an optional step did not run. Reported inside a successful
  response (``skipped_since_last_call``, a compile report), never raised.

Adding a code is additive (it stays in v1); give it every field below, and the
registry lint (CONN-REG-03) checks it is documented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import API_VERSION

DOWN = "down"
INVALID = "invalid"
SKIPPED = "skipped"


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    kind: str
    status: int
    #: Default message, shown to the partner by Claude.
    message: str
    #: What the caller should do next. Every error says this.
    next: str
    #: The docs entry for /docs/errors: when it happens and why.
    docs: str
    retry_after_seconds: int | None = None


_SPECS = [
    # ---------------------------------------------------------------- down
    ErrorSpec(
        "service_unavailable",
        DOWN,
        503,
        "MemoPop is unavailable right now.",
        "Tell the partner MemoPop is down and try again in a minute. Do not retry in a loop.",
        "The server is starting, restarting, or overloaded. Nothing was changed.",
        30,
    ),
    ErrorSpec(
        "storage_unavailable",
        DOWN,
        503,
        "MemoPop could not read or write this firm's workspace.",
        "Tell the partner their work is safe but this step was not saved, and try again shortly.",
        "The workspace volume or the firm's bucket failed mid-call. Every write in the call "
        "was rolled back, so nothing was saved.",
        30,
    ),
    ErrorSpec(
        "timeout",
        DOWN,
        504,
        "The request took too long and was stopped.",
        "Try the same call once more. If it times out again, tell the partner and stop.",
        "The call ran past its time budget. Long work such as compile returns a job instead.",
        10,
    ),
    ErrorSpec(
        "internal_error",
        DOWN,
        503,
        "Something went wrong inside MemoPop.",
        "Tell the partner something went wrong on MemoPop's side and stop; it has been logged.",
        "An unexpected failure on the server. It is a bug: report it with the time it happened.",
        60,
    ),
    # ---------------------------------------------------------------- invalid
    ErrorSpec(
        "unauthenticated",
        INVALID,
        401,
        "This request has no valid MemoPop sign-in.",
        "Ask the partner to reconnect MemoPop in Claude's connector settings and sign in "
        "with didi.sh.",
        "No credential, or a token that is expired, for another audience, or signed by an "
        "unknown key. The WWW-Authenticate header points at the protected-resource document.",
    ),
    ErrorSpec(
        "forbidden_firm",
        INVALID,
        403,
        "This sign-in can't act for that firm.",
        "Call again without `firm` to use the firm you signed in as, or ask the partner which "
        "of their firms to use.",
        "The call named a firm the credential does not belong to. The response is the same "
        "whether or not that firm exists, so it reveals nothing about other firms.",
    ),
    ErrorSpec(
        "deal_not_found",
        INVALID,
        404,
        "No deal by that name in this workspace.",
        "Call list_deals to see this firm's deals, or create_new_deal to start one.",
        "The deal slug does not exist in the signed-in firm's workspace.",
    ),
    ErrorSpec(
        "artifact_not_found",
        INVALID,
        404,
        "No artifact or material with that id on this deal.",
        "Use an artifact_id returned by next_step or submit_artifact, or call next_step to see "
        "what the deal has.",
        "The artifact, material, or version asked for does not exist on this deal.",
    ),
    ErrorSpec(
        "template_not_found",
        INVALID,
        404,
        "No memo template by that name.",
        "Call create_new_deal again without `template` to use the firm's default.",
        "The template name matched neither the firm's outlines nor MemoPop's. "
        "`details.available` lists the names that exist.",
    ),
    ErrorSpec(
        "validation_failed",
        INVALID,
        422,
        "The request's inputs are not valid.",
        "Fix the inputs listed in `details.errors` and call again.",
        "An input is missing, has the wrong type, or is out of range. Nothing was changed.",
    ),
    ErrorSpec(
        "checks_failed",
        INVALID,
        422,
        "The artifact failed its checks and was not saved.",
        "Fix each failure in `details.failures` and submit the whole artifact again.",
        "The submitted content did not pass the checks its step declares (length, citations, "
        "headings). Every failure is listed; nothing was saved.",
    ),
    ErrorSpec(
        "step_out_of_order",
        INVALID,
        409,
        "That step has not been handed out yet.",
        "Call next_step and do the step it returns.",
        "An artifact was submitted for a step next_step has not handed out. The server owns "
        "the order of the method.",
    ),
    ErrorSpec(
        "research_not_approved",
        INVALID,
        409,
        "This section's research has not been approved by the partner.",
        "Show the partner the section's research, and once they approve it, submit it again "
        "with partner_approved: true.",
        "A section can't be drafted until its research is partner-approved.",
    ),
    ErrorSpec(
        "material_too_large",
        INVALID,
        413,
        "That material is too large to add this way.",
        "Send it as a file upload (an item with only `filename`) instead of inline text.",
        "Inline material text is limited to 100,000 characters.",
    ),
    ErrorSpec(
        "link_unreachable",
        INVALID,
        422,
        "MemoPop could not fetch that link.",
        "Check the link with the partner, or ask them to upload the file instead.",
        "A material link could not be fetched (not found, private, or timed out).",
    ),
    ErrorSpec(
        "unsupported_version",
        INVALID,
        400,
        "That API version is not supported.",
        "Use the v1 routes under /v1/ and MCP server version 1.x.",
        "The client asked for an API version this server does not serve.",
    ),
    ErrorSpec(
        "not_implemented",
        INVALID,
        400,
        "This tool is not available on this server yet.",
        "Tell the partner this part of MemoPop is not live yet, and continue with next_step.",
        "Plan 1 registers all eight tools with full docs; add_materials, save_snapshot, and "
        "compile return this until their phases land. Additive to the spec's starting codes.",
    ),
    ErrorSpec(
        "drafts_incomplete",
        INVALID,
        409,
        "Not every section has a draft yet, so the memo can't be compiled.",
        "Call next_step and finish the drafts it hands out, then call compile again.",
        "compile needs a draft of every section in the deal's template. `details.missing` "
        "lists the sections without one. Added in plan 5 (additive).",
    ),
    ErrorSpec(
        "link_expired",
        INVALID,
        410,
        "That download link has expired or is not valid.",
        "Call compile again for the deal to get fresh links; they last seven days.",
        "A compiled memo's signed link was past its expiry, or its signature did not match. "
        "Added in plan 5 (additive).",
    ),
    # ---------------------------------------------------------------- skipped
    ErrorSpec(
        "step_disabled",
        SKIPPED,
        200,
        "An optional step is turned off and was skipped.",
        "Tell the partner in one line which step was skipped, then continue with next_step.",
        "An operator disabled an optional step. The memo still completes; the skip is listed "
        "and the step can be re-run once it is enabled.",
    ),
    ErrorSpec(
        "step_failed",
        SKIPPED,
        200,
        "An optional step failed and was skipped.",
        "Tell the partner in one line which step was skipped, then continue with next_step.",
        "An optional server step raised. Optional steps never block the memo.",
    ),
    ErrorSpec(
        "step_skipped",
        SKIPPED,
        200,
        "An optional step was skipped by Claude, with a reason.",
        "Tell the partner in one line which step was skipped and why, then continue with "
        "next_step.",
        "Claude could not do an optional step well with what it had and skipped it through "
        "submit_artifact with skip: true and a reason. The memo still completes. Added in "
        "plan 5 (additive).",
    ),
    ErrorSpec(
        "material_unreadable",
        SKIPPED,
        200,
        "A material could not be read and was skipped.",
        "Tell the partner which material was skipped and ask for another copy; continue "
        "meanwhile.",
        "A material's text could not be extracted, or its link could not be fetched.",
    ),
]

CATALOGUE: dict[str, ErrorSpec] = {spec.code: spec for spec in _SPECS}


class ConnectorError(Exception):
    """A typed failure. Tools raise it; transports turn it into the envelope."""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        next: str | None = None,
        details: dict[str, Any] | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        spec = CATALOGUE[code]
        self.code = code
        self.kind = spec.kind
        self.status = spec.status
        self.message = message or spec.message
        self.next = next or spec.next
        self.details = details or {}
        self.retry_after_seconds = (
            retry_after_seconds if retry_after_seconds is not None else spec.retry_after_seconds
        )
        super().__init__(f"{code}: {self.message}")


def envelope(err: ConnectorError) -> dict[str, Any]:
    """The one failure body, identical over MCP and REST."""
    return {
        "ok": False,
        "error": {
            "kind": err.kind,
            "code": err.code,
            "message": err.message,
            "next": err.next,
            "retry_after_seconds": err.retry_after_seconds,
            "details": err.details,
        },
        "api_version": API_VERSION,
    }


def success(body: dict[str, Any]) -> dict[str, Any]:
    """A success body: the tool's output plus ``ok`` and ``api_version``."""
    return {"ok": True, **body, "api_version": API_VERSION}
