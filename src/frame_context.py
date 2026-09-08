"""
Render a thesis frame into the prompt blocks the agents inject.

Both the researcher and the writer need the frame, and they need it to say the
same thing. Building the text here — rather than formatting it inline in each
agent — is what keeps a frame a *variable*: agents read state, call one of these
functions, and never contain frame text as a literal.

The two blocks differ because the jobs differ. The researcher is told what to go
find and what qualifications to record alongside it; the writer is told what
argument the section must be consistent with and what it may not overstate.
Both carry the caveats verbatim, because a qualification that reaches only the
prose can be stripped by the next assembly, while one that reaches the research
file is durable.
"""

from __future__ import annotations

from typing import List, Optional

from .schemas.frame_schema import ThesisFrame

_DIRECTIVE_GUIDANCE = {
    "rewrite": (
        "Regenerate this section from the research base under the frame. You are not "
        "editing the prior draft; write the section this evidence and this thesis support."
    ),
    "amend": (
        "The existing section is not wrong, only narrow. Make the MINIMUM change that "
        "makes it consistent with the frame. Preserve existing sentences and their "
        "citations wherever they remain accurate — do not rewrite for style."
    ),
    "re-score": (
        "Re-evaluate with the frame in context. Expect movement only on dimensions the "
        "frame actually bears on; do not manufacture movement elsewhere."
    ),
}


def _caveat_block(caveats: List[str]) -> str:
    if not caveats:
        return ""
    lines = "\n".join(f"- {c}" for c in caveats)
    return (
        "\nNON-NEGOTIABLE QUALIFICATIONS — carry these wherever the underlying claim "
        f"appears. They are not optional context; a claim that loses its qualification "
        f"becomes false:\n{lines}\n"
    )


def research_block(frame: Optional[ThesisFrame], section_filename: str) -> str:
    """
    The block injected into the codified researcher's prompt.

    Empty string when there is no frame, so a frameless run is byte-identical to
    today's behaviour.
    """
    if frame is None:
        return ""
    directive = frame.directive_for(section_filename)
    if not directive.researches:
        return ""

    extra_questions = frame.questions_for(section_filename)
    questions_text = (
        "\nThe active thesis additionally requires these be answered, IN ADDITION TO the "
        "section's standing guiding questions (never instead of them):\n"
        + "\n".join(f"- {q}" for q in extra_questions)
        + "\n"
    ) if extra_questions else ""

    additive = (
        "\nThis section's research is ADDITIVE. Findings already recorded for this section "
        "remain valid and are not being replaced — you are extending the evidence base, not "
        "regathering it. Do not restate what is already recorded; contribute what is new.\n"
        if directive.research == "extend" else
        "\nThis section's research is being REFRESHED: extend the evidence base with new "
        "findings, and explicitly flag any existing claim the new evidence contradicts.\n"
    )

    return (
        f"\nACTIVE THESIS FRAME: {frame.name} ({frame.stance})\n\n"
        f"{frame.premise}\n"
        f"{additive}"
        f"{questions_text}"
        f"{_caveat_block(frame.caveats)}"
    )


def writer_block(frame: Optional[ThesisFrame], section_filename: str) -> str:
    """The block injected into write_single_section's prompt, beside mode_guidance."""
    if frame is None:
        return ""
    directive = frame.directive_for(section_filename)
    if not directive.writes and directive.prose != "re-score":
        return ""

    guidance = _DIRECTIVE_GUIDANCE.get(directive.prose, "")
    note = frame.note_for(section_filename)

    return (
        f"\nACTIVE THESIS FRAME: {frame.name} ({frame.stance})\n\n"
        f"{frame.premise}\n\n"
        f"THIS SECTION'S DIRECTIVE: {directive.prose}\n"
        f"{guidance}\n"
        + (f"{note}\n" if note else "")
        + _caveat_block(frame.caveats)
        + (
            "\nSTANCE NOTE: this is a re-sequencing, not a pivot. The prior thesis is not "
            "abandoned or failed — it is being reordered. Do not describe it as dropped.\n"
            if frame.stance == "re-sequencing" else ""
        )
    )


def evidence_paths(frame: Optional[ThesisFrame]) -> List[str]:
    """Deal-relative paths of the documents a frame introduces."""
    return [e.path for e in frame.evidence] if frame else []
