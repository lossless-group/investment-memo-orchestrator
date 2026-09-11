"""Revise one section's prose against an operator's angle, without losing what it said.

The pipeline could already research a section again (`improve_section.py`,
`refocus_section.py`, both via Perplexity) and could re-synthesise prose from
research (`writer.polish_section_research`). Neither does the thing an analyst
actually asks for: *keep this section's facts, change how it argues.*

So this composes the two halves that already existed and were never joined:

* `writer.polish_section_research` proved the pattern — count the citations
  going in, tell the model, count them coming out, and revert if any are gone.
* `src/grounding.extract_evidence` knows how to pull every quote and figure a
  `[^N]` marker vouches for. Nothing had ever used it to guard a rewrite.

**No web search.** The section's claims are already grounded; re-researching is
how a revision turns into a different section. The only new input is the angle.

**Losses are itemised, not summarised.** A rewrite that drops a figure is told
exactly which figure, once, with its own draft in front of it — the same
correction shape `codified_section_researcher` uses for grounding failures, and
for the same reason: "keep what was correct" is unfollowable without the thing
being changed.

**Every attempt is archived.** A gate that silently reverts is as opaque as one
that silently drops. `_revisions/<section>/<timestamp>/` holds the angle, the
before, each attempt, the verdict and a machine-readable report, so any revision
is traceable and diffable after the fact. Archives live in a subdirectory
because assembly globs `2-sections/*.md` non-recursively — a sibling file would
be assembled into the memo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..llm_provider import complete

# The preservation primitives are shared with revise_summary_sections,
# improve_section and refocus_section. They were written here first; keeping a
# private second copy is exactly how this pipeline ended up with two
# implementations of every other contract it has.
from ..preservation import (
    BODY,
    Losses,
    Preservation,
    compare as _compare,
    correction as _build_correction_block,
    instructions as _preservation_instructions,
)

# A revision reasons over a whole section and returns a whole section.
_TIMEOUT = 600
_MAX_ATTEMPTS = 2

# The model's way of saying "your angle needs something this section does not
# contain" without inventing it. A note to the operator, so it must never reach
# the memo — AGENTS.md §6. Lifted out of the prose on accept and reported.
_GAP_RE = re.compile(r"^\s*REVISION-GAP:\s*(.+?)\s*$", re.MULTILINE)


def split_gaps(text: str) -> Tuple[str, List[str]]:
    """Separate the revised prose from the model's notes to the operator."""
    gaps = [g.strip() for g in _GAP_RE.findall(text)]
    cleaned = _GAP_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned, gaps


@dataclass
class RevisionResult:
    accepted: bool
    reason: str
    before: str
    after: Optional[str]
    attempts: List[str]
    losses: List[Losses]
    archive_dir: Optional[Path]
    section_path: Path
    gaps: List[str] = field(default_factory=list)


def _build_prompt(section_name: str, prose: str, angle: str, keep: Preservation) -> str:
    """The revision ask, plus the evidence discipline the result is checked against."""
    return f"""You are revising one section of an investment memo. You are changing HOW IT
ARGUES, not what it knows.

THE ANALYST'S REQUEST:
{angle}

THE SECTION AS IT STANDS ("{section_name}"):
---
{prose}
---

{_preservation_instructions(keep, mode=BODY)}

RULES:
- Do NOT introduce a fact, number, date, entity or citation that is not already
  in the section above. You have no research tool and no new sources. If the
  request needs something the section does not contain, say so in one line at
  the end prefixed `REVISION-GAP:` and revise everything else.
- Do NOT add meta-commentary, apologies, or notes addressed to the reader about
  the revision. The reader is an investment partner who does not know a revision
  happened.
- Keep the section's heading exactly as it is.
- Return ONLY the revised section in markdown. No preamble.

Your output will be checked against the lists above. Anything missing will be
itemised back to you."""


def _build_correction(prompt: str, draft: str, losses: Losses) -> str:
    return f"{prompt}\n\n{_build_correction_block(draft, losses)}"


def revise_section(
    section_path: Path,
    angle: str,
    *,
    max_attempts: int = _MAX_ATTEMPTS,
    model: Optional[str] = None,
    archive: bool = True,
) -> RevisionResult:
    """Revise the prose at `section_path` per `angle`, or leave it alone.

    Never writes on a failed gate. The original stands and the archive explains
    why, which is the only outcome an analyst can act on — a half-revised
    section with two citations missing is worse than no revision at all.
    """
    section_path = Path(section_path)
    before_text = section_path.read_text()
    section_name = _section_name(before_text, section_path)
    keep = Preservation.of(before_text)

    print(f"  ✏️  Revising {section_path.name} — {keep.words} words, "
          f"{len(keep.citations)} citation(s), {len(keep.figures)} figure(s)")

    prompt = _build_prompt(section_name, before_text, angle, keep)
    attempts: List[str] = []
    losses_log: List[Losses] = []
    accepted_text: Optional[str] = None
    reason = ""

    current_prompt = prompt
    gaps: List[str] = []
    for attempt in range(1, max_attempts + 1):
        completion = complete(
            current_prompt, max_tokens=8000, model=model, timeout=_TIMEOUT
        )
        if not completion.ok:
            reason = (f"model call failed: {completion.error or 'empty response'} "
                      f"(provider={completion.provider})")
            print(f"     ❌ {reason}")
            break

        draft, draft_gaps = split_gaps(completion.text.strip())
        attempts.append(draft)
        # Measured on the cleaned prose: a gap line naming "$9,800" would
        # otherwise satisfy the check for a figure the prose actually dropped.
        losses = _compare(keep, Preservation.of(draft))
        losses_log.append(losses)

        if not losses.any:
            accepted_text = draft
            gaps = draft_gaps
            reason = f"accepted on attempt {attempt}"
            print(f"     ✓ attempt {attempt}: nothing lost — accepted "
                  f"({len(draft.split())} words)")
            break

        print(f"     ⚠️  attempt {attempt} lost {losses.summary()}")
        if attempt < max_attempts:
            print("     ↺ re-prompting with an itemised list of what it dropped")
            current_prompt = _build_correction(prompt, draft, losses)
        else:
            reason = f"rejected — still lost {losses.summary()} after {attempt} attempts"
            print(f"     ❌ {reason}; keeping the original")

    if gaps:
        print(f"     ⓘ  {len(gaps)} gap(s) the section could not support — "
              "reported, not written into the memo:")
        for g in gaps:
            print(f"        · {g}")

    archive_dir = None
    if archive:
        archive_dir = _archive(
            section_path, angle, before_text, attempts, losses_log,
            accepted_text is not None, reason, keep, gaps,
        )

    if accepted_text is not None:
        section_path.write_text(accepted_text)

    return RevisionResult(
        accepted=accepted_text is not None,
        reason=reason,
        before=before_text,
        after=accepted_text,
        attempts=attempts,
        losses=losses_log,
        archive_dir=archive_dir,
        section_path=section_path,
        gaps=gaps,
    )


def _section_name(content: str, path: Path) -> str:
    for line in content.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def _archive(
    section_path: Path,
    angle: str,
    before: str,
    attempts: List[str],
    losses: List[Losses],
    accepted: bool,
    reason: str,
    keep: Preservation,
    gaps: List[str],
) -> Path:
    """Write a traceable, diffable record of one revision.

    Lives under `2-sections/_revisions/` because assembly globs `*.md`
    non-recursively — a sibling file would end up inside the memo.
    """
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    root = section_path.parent / "_revisions" / section_path.stem / stamp
    root.mkdir(parents=True, exist_ok=True)

    (root / "angle.md").write_text(angle.strip() + "\n")
    if gaps:
        (root / "gaps.md").write_text(
            "# What this section could not support\n\n"
            "The revision was asked for something the section does not contain. "
            "Rather than invent it, the model said so. Each line is a candidate "
            "for research, not a defect in the prose.\n\n"
            + "\n".join(f"- {g}" for g in gaps) + "\n"
        )
    (root / "before.md").write_text(before)
    for i, draft in enumerate(attempts, start=1):
        (root / f"attempt-{i}.md").write_text(draft)
    if accepted and attempts:
        (root / "accepted.md").write_text(attempts[-1])

    (root / "report.json").write_text(json.dumps({
        "section": section_path.name,
        "timestamp": stamp,
        "accepted": accepted,
        "reason": reason,
        "angle": angle.strip(),
        "gaps": gaps,
        "before": {
            "words": keep.words,
            "citations": sorted(keep.citations),
            "figures": sorted(keep.figures),
            "markers": sorted(keep.markers),
        },
        "attempts": [
            {
                "n": i,
                "words": len(attempts[i - 1].split()),
                "lost_citations": lo.citations,
                "lost_figures": lo.figures,
                "lost_quotes": lo.quotes,
            }
            for i, lo in enumerate(losses, start=1)
        ],
    }, indent=2) + "\n")

    print(f"     🗄  archived to {root.relative_to(section_path.parent.parent)}")
    return root
