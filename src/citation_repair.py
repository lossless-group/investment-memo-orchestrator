"""Repair finished memos whose citations link to another section's source.

Memos assembled before the fix in
context-v/issues/Final-Draft-Citations-Collide-Across-Sections.md carry one
global numbering: each section's research numbered its sources from 1, the old
assembler treated keys as global, and most markers in the finished memo
(`7-<Deal>-<version>.md`) link to whichever section defined that number first.

This rewrites only the markers and the definitions block of the finished memo,
so prose, later passes and hand edits survive. Output keys are hex keys from
source_key(), so a repaired memo cannot collide again. It repairs only what it
can prove, region by region (a region is a section's span in the memo, found by
the section file's first `## ` heading), footnote by footnote:

  - the heading must occur exactly once in the memo, or the region is refused;
  - a research file with no appended blocks that defines a key twice with
    different sources (the older cascading-renumber bug) refuses the region;
  - each memo marker is paired with a section-file marker: in order across the
    whole region when that is still one-to-one, as assembled; otherwise only on
    lines whose prose is byte-identical to the section file, markers in the same
    places. Markers on other lines were edited after assembly and are kept. It
    never matches by surrounding text;
  - a paired key is read in its research file block by block
    (src/research_blocks.py): a section part drafted from a block reads that
    block, otherwise the block that defines the key. A key the blocks define
    differently, or nothing defines, is kept.

A kept marker stays as it was, with its key and its definition, so a refused
region stays byte-identical. Text with no research file (title, Executive Summary, Closing,
scorecard, anything added after assembly) keeps pointing at the source it points
to now, converted to hex, and is reported as unverified: there is no local key
to recover. `prose()` checks that nothing but markers and the block changed.

Used by cli/repair_citations.py; importable so a connector tool can call it.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

from .agents.citation_assembly import _source_identity
from .citation_keys import assign_keys
from .research_blocks import COLLAPSED, part_block, read_research_keys, section_parts

MARK = re.compile(r"\[\^([a-zA-Z0-9_-]+)\](?!:)")
ANY_MARK = re.compile(r"\[\^[a-zA-Z0-9_-]+\]")
DEF_LINE = re.compile(r"^\[\^([a-zA-Z0-9_-]+)\]:[ \t]?(.*)$")
HEAD = re.compile(r"^#{1,2} .+$", re.M)
DEFAULT_LEAD = ["***", "", "### Citations", ""]


class ProseChangedError(RuntimeError):
    """The repaired text differs from the original in more than citations."""


@dataclass
class RepairResult:
    memo_path: Path
    original: str
    text: str
    changed: bool
    report: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Block:
    body: str
    lead: List[str]
    definitions: List[Tuple[str, str]]
    tail: List[str]
    found: bool


def definitions_with_duplicates(text: str) -> List[Tuple[str, str]]:
    """[(key, definition)] for every `[^k]:` line, duplicates kept."""
    out = []
    for line in text.splitlines():
        m = DEF_LINE.match(line)
        if m:
            out.append((m.group(1), m.group(2).strip()))
    return out


def split_block(memo: str) -> Block:
    """Split the memo into body, block lead-in, definitions, and tail.

    The block is the contiguous run of `[^k]:` lines (blank lines allowed), with
    an optional `***`/`---` and `### Citations` lead-in just before it. Anything
    after it (such as `## Background Sources`) is the tail, kept verbatim.
    """
    lines = memo.split("\n")
    idx = [i for i, line in enumerate(lines) if DEF_LINE.match(line)]
    if not idx:
        return Block(memo, [], [], [], False)
    first, last = idx[0], idx[-1]
    for i in range(first, last + 1):
        if lines[i].strip() and not DEF_LINE.match(lines[i]):
            raise ValueError(f"definitions are not contiguous (line {i + 1}: {lines[i][:60]!r})")
    start = first
    j = first - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    if j >= 0 and lines[j].strip() == "### Citations":
        start = j
        k = j - 1
        while k >= 0 and not lines[k].strip():
            k -= 1
        if k >= 0 and lines[k].strip() in ("***", "---"):
            start = k
    return Block(
        body="\n".join(lines[:start]),
        lead=lines[start:first],
        definitions=definitions_with_duplicates("\n".join(lines[first : last + 1])),
        tail=lines[last + 1 :],
        found=True,
    )


def prose(text: str) -> str:
    """The memo with its citation markers and definitions block removed."""
    block = split_block(text)
    return ANY_MARK.sub("", block.body.rstrip() + "\n" + "\n".join(block.tail).strip())


def find_memo(version_dir: Path, memo: Optional[str] = None) -> Path:
    """The finished memo. A version dir can hold a memo named for another
    version, so with more than one `7-*.md` the caller must name it."""
    version_dir = Path(version_dir)
    if memo:
        path = version_dir / memo
        if not path.exists():
            raise ValueError(f"{path} does not exist")
        return path
    candidates = sorted(version_dir.glob("7-*.md"))
    if not candidates:
        raise ValueError(f"no finished memo (7-*.md) in {version_dir}")
    if len(candidates) > 1:
        raise ValueError(
            f"{len(candidates)} finished memos in {version_dir} "
            f"({', '.join(c.name for c in candidates)}); pass --memo to choose one"
        )
    return candidates[0]


def _region_bounds(body: str, heads, start_i: int, section_text: str) -> Tuple[int, int]:
    """From heading start_i to the next h1/h2 that is not one of the section's own."""
    own = [line.strip() for line in section_text.splitlines() if re.match(r"^#{1,2} ", line)][1:]
    j = start_i + 1
    while j < len(heads) and own and heads[j][1].strip() == own[0]:
        own.pop(0)
        j += 1
    return heads[start_i][0], heads[j][0] if j < len(heads) else len(body)


EDITED = "line edited after assembly"


def _strip_markers(line: str) -> Tuple[str, List[int]]:
    """The line without markers, and where each marker stood in that text."""
    positions: List[int] = []
    removed = 0
    for m in ANY_MARK.finditer(line):
        positions.append(m.start() - removed)
        removed += m.end() - m.start()
    return ANY_MARK.sub("", line), positions


def _pair_lines(region_lines: List[str], section_lines: List[str]) -> Dict[int, int]:
    """Region line index -> section line index, for lines whose prose is
    byte-identical and whose markers stand in the same places."""
    region = [_strip_markers(line) for line in region_lines]
    section = [_strip_markers(line) for line in section_lines]
    matcher = difflib.SequenceMatcher(None, [p for p, _ in region], [p for p, _ in section], autojunk=False)
    pairs: Dict[int, int] = {}
    for tag, a0, a1, b0, _b1 in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(a1 - a0):
            i, j = a0 + offset, b0 + offset
            if region[i][1] == section[j][1]:
                pairs[i] = j
    return pairs


def _one_to_one(memo_keys: List[str], local_keys: List[str]) -> bool:
    """Same number of markers, and pairing them in order is one-to-one."""
    if not memo_keys or len(memo_keys) != len(local_keys):
        return False
    forward: Dict[str, str] = {}
    back: Dict[str, str] = {}
    for memo_key, local_key in zip(memo_keys, local_keys):
        if forward.setdefault(memo_key, local_key) != local_key or back.setdefault(local_key, memo_key) != memo_key:
            return False
    return True


def _summary(refused: Dict[str, int]) -> str:
    return "; ".join(f"{n} refused: {reason}" for reason, n in refused.items())


def _plan_region(vd: Path, section_file: Path, body: str, heads, entry: Dict[str, Any]):
    """Decide one section's region, marker by marker.

    Returns (start, end, decisions), one decision per memo marker in the region
    in order: ("def", definition) to repair it, or ("keep", reason) to leave it
    as it is. Returns None when the region can't be located or cites nothing.
    Fills `entry` with the status and counts.
    """
    research_file = vd / "1-research" / f"{section_file.stem}-research.md"
    section_text = section_file.read_text()
    heading = next((line for line in section_text.splitlines() if line.startswith("## ")), None)
    if not heading:
        entry.update(status="unrepairable", reason="section file has no ## heading")
        return None
    entry["heading"] = heading.strip()
    hits = [i for i, (_, title) in enumerate(heads) if title.strip() == heading.strip()]
    if len(hits) != 1:
        entry.update(status="unrepairable", reason=f"heading found {len(hits)} times in memo")
        return None
    start, end = _region_bounds(body, heads, hits[0], section_text)
    region = body[start:end]
    research_text = research_file.read_text()
    research = read_research_keys(research_text)
    section_defs = dict(definitions_with_duplicates(section_text))
    all_lines = section_text.splitlines()
    all_parts = section_parts(all_lines)
    parts = (all_parts[-1] + 1) if all_parts else 1
    kept = [(line, p) for line, p in zip(all_lines, all_parts) if not DEF_LINE.match(line)]
    section_lines = [line for line, _ in kept]
    line_parts = [p for _, p in kept]
    local = MARK.findall("\n".join(section_lines))
    region_lines = region.split("\n")
    found = MARK.findall(region)
    entry.update(markers_memo=len(found), markers_section=len(local))
    if research.appended:
        entry.update(research_blocks=len(research.blocks), section_parts=parts)

    if research.collapsed and not research.appended:
        # The older bug: the file defines a key twice, so a local key no longer
        # names one source anywhere in this section. In a file with appended
        # blocks, a key one block defines twice is refused on its own below.
        research_keys = [k for k, _ in definitions_with_duplicates(research_text)]
        entry.update(
            status="unrepairable",
            reason=f"research file defines {', '.join('[^%s]' % k for k in research.collapsed)} more than once "
            f"({len(research_keys)} definitions, {len(set(research_keys))} distinct keys): "
            "local keys do not identify sources",
            repaired=0,
            refused={COLLAPSED: len(found)} if found else {},
        )
        return start, end, [("keep", COLLAPSED)] * len(found)

    if not found and not local:
        entry.update(status="no-citations")
        return None

    # Each memo marker is paired with a section marker (key, part) or None.
    local_marks = [(key, line_parts[j]) for j, line in enumerate(section_lines) for key in MARK.findall(line)]
    paired: List[Optional[Tuple[str, int]]] = []
    if _one_to_one(found, [key for key, _ in local_marks]):
        # The whole region still pairs one for one with the section file, as
        # assembled: every marker is proven in order, edited wording or not.
        paired = list(local_marks)
    else:
        # Otherwise pair markers only on lines whose prose is byte-identical to
        # the section file, so a few edited lines don't block the region.
        pairs = _pair_lines(region_lines, section_lines)
        for i, line in enumerate(region_lines):
            memo_keys = MARK.findall(line)
            if i in pairs:
                paired += [(key, line_parts[pairs[i]]) for key in MARK.findall(section_lines[pairs[i]])]
            else:
                paired += [None] * len(memo_keys)

    decisions: List[Tuple[str, str]] = []
    refused_keys: Dict[str, List[str]] = {}
    for pair in paired:
        if pair is None:
            decisions.append(("keep", EDITED))
            continue
        key, part = pair
        if key in section_defs:
            decisions.append(("def", section_defs[key]))
            continue
        definition, _, reason = research.resolve(key, part_block(part, parts, len(research.blocks)))
        if definition is None:
            decisions.append(("keep", reason))
            listed = refused_keys.setdefault(reason, [])
            if f"[^{key}]" not in listed:
                listed.append(f"[^{key}]")
        else:
            decisions.append(("def", definition))

    repaired = sum(1 for kind, _ in decisions if kind == "def")
    refused: Dict[str, int] = {}
    for kind, value in decisions:
        if kind == "keep":
            refused[value] = refused.get(value, 0) + 1
    entry.update(repaired=repaired, refused=refused)
    if refused_keys:
        entry["refused_keys"] = refused_keys
    if not refused:
        entry.update(status="repaired")
    elif repaired:
        entry.update(status="partial", reason=_summary(refused))
    elif len(found) != len(local):
        entry.update(
            status="unrepairable",
            reason="marker count differs between memo region and section file: edited after assembly",
        )
    else:
        entry.update(status="unrepairable", reason=_summary(refused))
    return start, end, decisions


def repair_memo(version_dir: Path, memo: Optional[str] = None) -> RepairResult:
    """Repair one finished memo in memory. Never writes."""
    vd = Path(version_dir)
    memo_path = find_memo(vd, memo)
    original = memo_path.read_text()
    block = split_block(original)
    body = block.body
    report: Dict[str, Any] = {"memo": str(memo_path), "regions": [], "unverified": [], "notes": []}

    memo_defs: Dict[str, str] = {}
    for key, definition in block.definitions:
        if key in memo_defs and _source_identity(memo_defs[key]) != _source_identity(definition):
            report["notes"].append(f"memo block defines [^{key}] twice with different sources; first kept")
        memo_defs.setdefault(key, definition)

    heads = [(m.start(), m.group(0)) for m in HEAD.finditer(body)]
    spans = []  # (start, end, decisions, stem)
    for section_file in sorted((vd / "2-sections").glob("*.md")):
        if not (vd / "1-research" / f"{section_file.stem}-research.md").exists():
            continue
        entry: Dict[str, Any] = {"section": section_file.stem}
        report["regions"].append(entry)
        plan = _plan_region(vd, section_file, body, heads, entry)
        if plan:
            spans.append((*plan, section_file.stem))

    counts: Dict[str, Any] = {"repaired": 0, "refused": {}}
    for region in report["regions"]:
        counts["repaired"] += region.get("repaired", 0)
        for reason, n in region.get("refused", {}).items():
            counts["refused"][reason] = counts["refused"].get(reason, 0) + n
    report["counts"] = counts

    if not counts["repaired"]:
        report["result"] = "nothing repairable; memo left unchanged"
        return RepairResult(memo_path, original, original, False, report)

    spans.sort(key=lambda s: (s[0], s[1]))
    for a, b in zip(spans, spans[1:]):
        if a[1] > b[0]:
            raise ValueError(f"regions {a[3]} and {b[3]} overlap")

    # Partition the body into regions and the unverified text between them.
    # Region markers follow their decisions; unverified markers resolve through
    # the memo's own block.
    chunks: List[Tuple[str, Optional[List[Tuple[str, str]]]]] = []
    pos = 0
    for start, end, decisions, _stem in spans:
        if start > pos:
            chunks.append((body[pos:start], None))
        chunks.append((body[start:end], decisions))
        pos = end
    if pos < len(body):
        chunks.append((body[pos:], None))

    # Every marker that resolves to a definition gets a pseudo-key; hex keys are
    # assigned across all of them at once, so one source is one key.
    resolved: Dict[str, str] = {}
    plans: List[List[Tuple[str, str]]] = []  # per chunk: ("tag", tag) or ("keep", memo key)
    missing: List[str] = []
    kept_keys: set = set()
    for text, decisions in chunks:
        plan: List[Tuple[str, str]] = []
        for n, key in enumerate(MARK.findall(text)):
            if decisions is not None:
                decision = decisions[n]
            else:
                decision = ("def", memo_defs[key]) if key in memo_defs else ("keep", "missing")
            if decision[0] == "def":
                tag = f"m{len(resolved)}"
                resolved[tag] = decision[1]
                plan.append(("tag", tag))
                continue
            plan.append(("keep", key))
            if decisions is not None:
                kept_keys.add(key)
            elif f"[^{key}]" not in missing:
                missing.append(f"[^{key}]")
        plans.append(plan)
    hex_of = assign_keys(resolved)

    # A kept key may equal a new hex key only when both name one source.
    for tag, new in hex_of.items():
        if new in kept_keys and (
            new not in memo_defs or _source_identity(memo_defs[new]) != _source_identity(resolved[tag])
        ):
            raise ValueError(f"a new hex key equals a key kept in a refused region: [^{new}]")

    new_texts: List[str] = []
    order: List[str] = []
    definition_of: Dict[str, str] = {}
    for (text, decisions), plan in zip(chunks, plans):
        new_keys = []
        for kind, value in plan:
            if kind == "tag":
                new = hex_of[value]
                definition_of.setdefault(new, resolved[value])
            else:
                new = value
                if new in memo_defs:
                    definition_of.setdefault(new, memo_defs[new])
            if new in definition_of and new not in order:
                order.append(new)
            new_keys.append(new)
        it = iter(new_keys)
        new_texts.append(MARK.sub(lambda _m: f"[^{next(it)}]", text))
        if decisions is None and plan:
            report["unverified"].append(
                {
                    "headings": [m.group(0).strip() for m in HEAD.finditer(text)],
                    "markers": len(plan),
                    "reason": "no research file: kept pointing at the source it points to now",
                }
            )

    if missing:
        report["notes"].append(
            "markers with no definition anywhere (kept as they were, unlinked): " + ", ".join(missing)
        )

    new_body = "".join(new_texts)
    def_lines: List[str] = []
    for key in order:
        if def_lines:
            def_lines.append("")
        def_lines.append(f"[^{key}]: {definition_of[key]}")
    if block.found:
        lines = new_body.split("\n") + block.lead + def_lines + block.tail
        text = "\n".join(lines)
    else:
        text = new_body.rstrip("\n") + "\n\n" + "\n".join(DEFAULT_LEAD + def_lines) + "\n"

    cited_before = set(MARK.findall(body))
    report.update(
        old_block_definitions=len(block.definitions),
        old_uncited_definitions_dropped=len([k for k in memo_defs if k not in cited_before]),
        new_sources=len(order),
        kept_numbered_keys=sorted(kept_keys, key=lambda k: (len(k), k)),
        result="repaired",
    )
    return RepairResult(memo_path, original, text, True, report)


def check_prose(result: RepairResult) -> None:
    """Raise ProseChangedError unless only markers and the block changed."""
    if prose(result.original) != prose(result.text):
        raise ProseChangedError("prose changed: repair not trusted; nothing written")


# ------------------------------------------------------------------- scan

_URL = re.compile(r"\((https?://[^)\s]+|file://[^)\s]+)\)")


def _url_definitions(text: str) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for m in re.finditer(r"^\[\^([^\]]+)\]:\s*(.+)$", text, re.M):
        urls = _URL.findall(m.group(2))
        out[m.group(1)] = unquote(urls[0]).rstrip("/").lower() if urls else None
    return out


@dataclass
class ScanRow:
    memo: Path
    wrong: int
    checked: int
    per_section: Dict[str, int]
    collapsed: List[str]
    ambiguous: bool = False
    duplicate_of: List[str] = field(default_factory=list)
    # Research files whose appended blocks reuse keys (repairable block by
    # block), as opposed to `collapsed`: one block defining a key twice.
    appended: List[str] = field(default_factory=list)

    @property
    def share(self) -> Optional[float]:
        return self.wrong / self.checked if self.checked else None


def _scan_memo(memo: Path) -> Optional[ScanRow]:
    vd = memo.parent
    research_files = sorted((vd / "1-research").glob("*-research.md"))
    if not research_files:
        return None
    text = memo.read_text()
    block = _url_definitions(text)
    heads = [(m.start(), m.group(0)) for m in HEAD.finditer(text)]
    urls_of = {rf: {u for u in _url_definitions(rf.read_text()).values() if u} for rf in research_files}
    collapsed = []
    appended = []
    for rf in research_files:
        keys = read_research_keys(rf.read_text())
        if keys.collapsed:
            collapsed.append(rf.name)
        if keys.appended and keys.reused_keys():
            appended.append(rf.name)
    wrong = checked = 0
    per: Dict[str, int] = {}
    for sf in sorted((vd / "2-sections").glob("*.md")):
        rf = vd / "1-research" / f"{sf.stem}-research.md"
        if not rf.exists():
            continue
        heading = next((line for line in sf.read_text().splitlines() if line.startswith("## ")), None)
        if not heading:
            continue
        idx = [i for i, (_, t) in enumerate(heads) if t.strip() == heading.strip()]
        if not idx:
            continue
        i = idx[0]
        start = heads[i][0]
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        own = urls_of[rf]
        for key in MARK.findall(text[start:end]):
            url = block.get(key)
            if not url:
                continue
            checked += 1
            if url not in own and any(url in v for other, v in urls_of.items() if other != rf):
                wrong += 1
                per[sf.stem] = per.get(sf.stem, 0) + 1
    return ScanRow(memo, wrong, checked, per, collapsed, appended=appended)


def scan(io_root: Path) -> List[ScanRow]:
    """Every finished memo under io/<firm>/<deals|portfolio>/<deal>/outputs/<version>/,
    with how many of its section citations link to another section's source.

    The same firm, deal and version found under two folders (a deal copied from
    deals/ to portfolio/) is reported in both places and flagged."""
    root = Path(io_root)
    if (root / "io").is_dir():
        root = root / "io"
    rows: List[ScanRow] = []
    for memo in sorted(root.glob("*/*/*/outputs/*/7-*.md")):
        row = _scan_memo(memo)
        if row is None:
            continue
        row.ambiguous = len(list(memo.parent.glob("7-*.md"))) > 1
        rows.append(row)
    by_identity: Dict[Tuple[str, str, str, str], List[ScanRow]] = {}
    for row in rows:
        rel = row.memo.relative_to(root).parts  # firm, folder, deal, outputs, version, file
        by_identity.setdefault((rel[0], rel[2], rel[4], rel[5]), []).append(row)
    for group in by_identity.values():
        if len(group) > 1:
            for row in group:
                row.duplicate_of = [str(o.memo.relative_to(root)) for o in group if o is not row]
    return rows
