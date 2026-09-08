"""
Thesis frame schema.

A frame is the deal's *angle* — the thesis every affected section must be
consistent with. It is deliberately orthogonal to the outline: the outline owns
the section taxonomy (which sections exist, what each is for), the frame owns
what this run argues inside them. A frame that renames or reorders sections is
out of contract and the loader rejects it.

The design rule that shapes this whole module:

    1-research/ accumulates. 2-sections/ is regenerated from it.

A new thesis is almost always *new evidence about the same company* rather than
a replacement for what was already gathered, so research directives are additive
by default and are a separate axis from what happens to the prose. See
context-v/specs/Thesis-Frames-And-The-Re-Angle-Run.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# --- Directive vocabularies --------------------------------------------------
#
# Two axes, because they answer different questions. Research asks "what do we
# know"; prose asks "how do we say it". A section can grow its evidence base and
# keep its prose untouched, or reuse its evidence and be re-synthesised entirely.

RESEARCH_DIRECTIVES = frozenset({
    "extend",   # research the frame's questions, APPEND findings; never rewrite
    "refresh",  # extend, plus re-verify existing claims against the new evidence
    "reuse",    # carry the file forward untouched; no research call at all
})

PROSE_DIRECTIVES = frozenset({
    "rewrite",    # regenerate from the (now larger) research base under the frame
    "amend",      # show existing prose, ask for the minimum consistent change
    "re-score",   # rerun the scorecard evaluator with the frame in context
    "unchanged",  # not regenerated, not shown, not touched
})

STANCES = frozenset({"re-sequencing", "replacement", "dual-thesis"})

# A section absent from `affects` is inert: its evidence is carried forward and
# its prose is left alone. Silence means "don't touch it", never "regenerate it".
DEFAULT_DIRECTIVE = ("reuse", "unchanged")


@dataclass
class EvidenceDoc:
    """A source document the frame introduces, deal-relative."""
    path: str
    note: str = ""


@dataclass
class SectionDirective:
    """What a framed run does to one section, on both axes."""
    research: str = DEFAULT_DIRECTIVE[0]
    prose: str = DEFAULT_DIRECTIVE[1]

    @property
    def researches(self) -> bool:
        """True when this section needs a research call at all."""
        return self.research in ("extend", "refresh")

    @property
    def writes(self) -> bool:
        """True when the writer regenerates or edits this section's prose."""
        return self.prose in ("rewrite", "amend")

    @property
    def is_inert(self) -> bool:
        return not self.researches and self.prose == "unchanged"


@dataclass
class ThesisFrame:
    """
    A deal's thesis, loaded from io/<firm>/deals/<Deal>/frames/<slug>.yaml.

    Carried on MemoState as a run variable, exactly like memo_mode. No agent
    imports a frame file and no prompt contains frame text as a literal.
    """
    name: str
    slug: str
    stance: str
    premise: str
    evidence: List[EvidenceDoc] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    questions: Dict[str, List[str]] = field(default_factory=dict)
    affects: Dict[str, SectionDirective] = field(default_factory=dict)
    directive_notes: Dict[str, str] = field(default_factory=dict)
    source_path: Optional[str] = None

    # --- lookups the agents use ---------------------------------------------

    def directive_for(self, section_filename: str) -> SectionDirective:
        """
        The directive for a section. Absent sections default to inert rather
        than raising — a frame is allowed to be silent about sections it does
        not touch, and silence must be the safe answer.
        """
        return self.affects.get(section_filename, SectionDirective())

    def questions_for(self, section_filename: str) -> List[str]:
        """
        Frame questions for a section. These are MERGED with the outline's
        guiding_questions by the caller, never substituted for them.
        """
        return list(self.questions.get(section_filename, []))

    def note_for(self, section_filename: str) -> str:
        return self.directive_notes.get(section_filename, "")

    def sections_in_scope(self) -> List[str]:
        """Sections a framed run touches on either axis, in declared order."""
        return [k for k, d in self.affects.items() if not d.is_inert]
