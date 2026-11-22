"""Read a research file block by block, so a key means the source its own block gave it.

A reused research file can carry appended blocks (src/research_append.py): the
original findings, then one block per later run under `## Added from N new
sources`, `## Added under thesis frame: …` or `## Refreshed under thesis frame:
…`, each opened by a `<!-- research-block: … -->` stamp. Before
context-v/issues/Appended-Research-Blocks-Reuse-Footnote-Keys.md was fixed, each
appended block numbered its footnotes from 1 again, so one file can define
`[^1]` once per block, each time for a different source. Reading such a file as
one dict (last definition wins) links the original block's footnotes to the
appended block's sources.

This module is the shared reading of those files for final assembly
(src/agents/citation_assembly.py) and the repair tool (src/citation_repair.py):

- `split_blocks()` cuts a research file at its block boundaries.
- `ResearchKeys.resolve()` gives a key's definition: in the block a section part
  was drafted from when that is known, else in the one block that defines it,
  else (several blocks agree on the source) that source. A key two blocks define
  with different sources is refused, never guessed.
- `section_parts()` cuts a section the same way, at its `### Added from …`
  headings, so part *i* can be read against block *i*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .citation_keys import source_identity

_LABEL = r"(?:Added from \d+ new sources?|Added under thesis frame:|Refreshed under thesis frame:)"
BLOCK_HEAD = re.compile(rf"^## {_LABEL}")
PART_HEAD = re.compile(rf"^### {_LABEL}")
STAMP = re.compile(r"^<!--\s*research-block:")
_BREAK = re.compile(r"^(?:\*\*\*|---)\s*$")
_DEF_LINE = re.compile(r"^\[\^([a-zA-Z0-9_-]+)\]:[ \t]?(.*)$")

# Reasons a key is not resolved, as they appear in reports.
UNDEFINED = "no definition in its research file"
CONFLICT = "research blocks define this key differently"
COLLAPSED = "research file defines this key more than once in one block"


def split_blocks(text: str) -> List[str]:
    """The research file cut at each appended block's start.

    A block starts at its stamp, or at its `## Added …` heading when no stamp
    precedes it. The `***` break before a block is dropped from the block above,
    so the last definition there does not run into it.
    """
    lines = text.split("\n")
    starts = [0]
    for i, line in enumerate(lines):
        if STAMP.match(line):
            starts.append(i)
        elif BLOCK_HEAD.match(line):
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if not (j >= 0 and STAMP.match(lines[j])):
                starts.append(i)
    starts = sorted(set(starts))
    blocks = []
    for a, b in zip(starts, starts[1:] + [len(lines)]):
        chunk = lines[a:b]
        while chunk and not chunk[-1].strip():
            chunk.pop()
        if chunk and _BREAK.match(chunk[-1]) and b != len(lines):
            chunk.pop()
        blocks.append("\n".join(chunk))
    if len(blocks) > 1 and not blocks[0].strip():
        blocks = blocks[1:]
    return blocks


def line_definitions(text: str) -> List[Tuple[str, str]]:
    """[(key, definition)] for every `[^k]:` line, duplicates kept."""
    out = []
    for line in text.splitlines():
        m = _DEF_LINE.match(line)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


@dataclass
class ResearchKeys:
    """A research file's definitions, one dict per block.

    A key defined twice in one block with different sources (the older
    collapsed-keys bug) is recorded in `collapsed` and maps to None there.
    """

    blocks: List[Dict[str, Optional[str]]] = field(default_factory=list)
    collapsed: List[str] = field(default_factory=list)

    @property
    def appended(self) -> bool:
        return len(self.blocks) > 1

    def conflicts(self) -> List[str]:
        """Keys two blocks define with different sources."""
        out = []
        for key in self.keys():
            identities = {source_identity(b[key]) for b in self.blocks if b.get(key) is not None}
            if len(identities) > 1:
                out.append(key)
        return out

    def reused_keys(self) -> List[str]:
        """Keys defined in more than one block, whatever their sources."""
        return [k for k in self.keys() if sum(1 for b in self.blocks if k in b) > 1]

    def keys(self) -> List[str]:
        seen: List[str] = []
        for block in self.blocks:
            for key in block:
                if key not in seen:
                    seen.append(key)
        return seen

    def resolve(
        self, key: str, block: Optional[int] = None
    ) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """(definition, block index, None), or (None, None, reason).

        With `block`, the key is read in that block first (a section part drafted
        from it). Otherwise, or when that block does not define it, it is read in
        whichever block defines it, provided every such block names one source.
        """
        if block is not None and 0 <= block < len(self.blocks) and key in self.blocks[block]:
            definition = self.blocks[block][key]
            if definition is None:
                return None, None, COLLAPSED
            return definition, block, None
        found = [(i, b[key]) for i, b in enumerate(self.blocks) if key in b]
        if not found:
            return None, None, UNDEFINED
        if any(d is None for _, d in found):
            return None, None, COLLAPSED
        if len({source_identity(d) for _, d in found}) > 1:
            return None, None, CONFLICT
        return found[0][1], found[0][0], None

    def merged(self) -> Dict[str, str]:
        """Every key that resolves without a section part, to its definition."""
        out = {}
        for key in self.keys():
            definition, _, _ = self.resolve(key)
            if definition is not None:
                out[key] = definition
        return out

    def all_definitions(self) -> List[str]:
        return [d for b in self.blocks for d in b.values() if d is not None]


def read_research_keys(
    text: str, parse: Optional[Callable[[str], Sequence[Tuple[str, str]]]] = None
) -> ResearchKeys:
    """Split `text` into blocks and read each block's definitions.

    `parse` returns a block's (key, definition) pairs, duplicates kept; the
    default reads one `[^k]:` line per definition.
    """
    parse = parse or line_definitions
    result = ResearchKeys()
    for block_text in split_blocks(text):
        block: Dict[str, Optional[str]] = {}
        for key, definition in parse(block_text):
            if key in block:
                prior = block[key]
                if prior is not None and source_identity(prior) != source_identity(definition):
                    block[key] = None
                    if key not in result.collapsed:
                        result.collapsed.append(key)
                continue
            block[key] = definition
        result.blocks.append(block)
    return result


def section_parts(lines: Sequence[str]) -> List[int]:
    """The part index of each section line: 0, then +1 at each `### Added …` heading."""
    part = 0
    out = []
    for line in lines:
        if PART_HEAD.match(line):
            part += 1
        out.append(part)
    return out


def part_block(part: int, parts: int, blocks: int) -> Optional[int]:
    """The block a section part was drafted from, when the section says so.

    Only when the section has more than one part and exactly one per block;
    a one-part section was redrafted from the whole file and names no block.
    """
    if parts > 1 and parts == blocks:
        return part
    return None
