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
the section file's first `## ` heading). A region is repaired only when ALL hold:

  - the heading occurs exactly once in the memo;
  - the section's research file defines each key once (a key defined twice
    means the keys were already collapsed, the older cascading-renumber bug,
    and a local key no longer identifies a source);
  - every key the section cites has a definition (research, or the section);
  - the region has the same number of markers as the section file, and pairing
    them in order is one-to-one. Anything else means the region was edited after
    assembly; it is never matched by surrounding text.

A refused region stays byte-identical, keeping its numbered keys and their
definitions. Text with no research file (title, Executive Summary, Closing,
scorecard, anything added after assembly) keeps pointing at the source it points
to now, converted to hex, and is reported as unverified: there is no local key
to recover. `prose()` checks that nothing but markers and the block changed.

Used by cli/repair_citations.py; importable so a connector tool can call it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

from .agents.citation_assembly import _source_identity
from .citation_keys import assign_keys

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


def _plan_region(vd: Path, section_file: Path, body: str, heads, entry: Dict[str, Any]):
    """Decide one section's region. Returns (start, end, local_keys, known) to
    repair, or None; fills `entry` with the status, and `bounds` when refused
    with a known span."""
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
    research = definitions_with_duplicates(research_file.read_text())
    research_keys = [k for k, _ in research]
    dup = sorted({k for k in research_keys if research_keys.count(k) > 1})
    section_defs = dict(definitions_with_duplicates(section_text))
    section_body = "\n".join(line for line in section_text.splitlines() if not DEF_LINE.match(line))
    local = MARK.findall(section_body)
    found = MARK.findall(region)
    entry.update(markers_memo=len(found), markers_section=len(local))

    def refuse(reason):
        entry.update(status="unrepairable", reason=reason)
        entry["_bounds"] = (start, end)
        return None

    if dup:
        return refuse(
            f"research file defines {', '.join('[^%s]' % k for k in dup)} more than once "
            f"({len(research)} definitions, {len(set(research_keys))} distinct keys): "
            "local keys do not identify sources"
        )
    known = dict(research)
    known.update(section_defs)
    undefined = sorted({k for k in local if k not in known})
    if undefined:
        return refuse(
            f"section cites {', '.join('[^%s]' % k for k in undefined)} with no definition in its research file"
        )
    if len(found) != len(local):
        return refuse("marker count differs between memo region and section file: edited after assembly")
    forward: Dict[str, str] = {}
    back: Dict[str, str] = {}
    for memo_key, local_key in zip(found, local):
        if forward.setdefault(memo_key, local_key) != local_key or back.setdefault(local_key, memo_key) != memo_key:
            return refuse(f"memo [^{memo_key}] pairs with more than one local key: markers edited or reordered")
    if not local:
        entry.update(status="no-citations")
        return None
    entry.update(status="repaired")
    return start, end, local, known


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
    spans = []  # (start, end, kind, local_keys, known, stem)
    for section_file in sorted((vd / "2-sections").glob("*.md")):
        if not (vd / "1-research" / f"{section_file.stem}-research.md").exists():
            continue
        entry: Dict[str, Any] = {"section": section_file.stem}
        report["regions"].append(entry)
        plan = _plan_region(vd, section_file, body, heads, entry)
        if plan:
            start, end, local, known = plan
            spans.append((start, end, "repaired", local, known, section_file.stem))
        elif "_bounds" in entry:
            start, end = entry.pop("_bounds")
            spans.append((start, end, "refused", None, None, section_file.stem))

    if not any(r.get("status") == "repaired" for r in report["regions"]):
        report["result"] = "nothing repairable; memo left unchanged"
        return RepairResult(memo_path, original, original, False, report)

    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if a[1] > b[0]:
            raise ValueError(f"regions {a[5]} and {b[5]} overlap")

    # Partition the body: repaired regions read local keys against their own
    # research; refused regions are kept as they are; the rest is unverified
    # and resolves through the memo's own block.
    chunks = []  # (text, kind, keys or None, known)
    pos = 0
    for start, end, kind, local, known, _stem in spans:
        if start > pos:
            chunks.append((body[pos:start], "unverified", None, memo_defs))
        chunks.append((body[start:end], kind, local, known))
        pos = end
    if pos < len(body):
        chunks.append((body[pos:], "unverified", None, memo_defs))

    # Every (chunk, key) that resolves to a definition gets a pseudo-key; hex
    # keys are assigned across all of them at once, so one source is one key.
    resolved: Dict[str, str] = {}
    marker_keys: List[List[str]] = []
    missing: List[str] = []
    for index, (text, kind, local, known) in enumerate(chunks):
        keys = list(local) if local is not None else MARK.findall(text)
        marker_keys.append(keys)
        if kind == "refused":
            continue
        for key in keys:
            if key in known:
                resolved[f"{index}:{key}"] = known[key]
            elif f"{index}:{key}" not in missing:
                missing.append(f"{index}:{key}")
    hex_of = assign_keys(resolved)

    kept_keys = {k for i, c in enumerate(chunks) if c[1] == "refused" for k in marker_keys[i]}
    clash = kept_keys & set(hex_of.values())
    if clash:
        raise ValueError(f"a new hex key equals a key kept in a refused region: {sorted(clash)}")

    new_texts: List[str] = []
    order: List[str] = []
    definition_of: Dict[str, str] = {}
    for index, (text, kind, _local, known) in enumerate(chunks):
        keys = marker_keys[index]
        if kind == "refused":
            new_texts.append(text)
            for key in keys:
                if key not in definition_of and key in memo_defs:
                    definition_of[key] = memo_defs[key]
                    order.append(key)
            continue
        new_keys = [hex_of.get(f"{index}:{key}", key) for key in keys]
        it = iter(new_keys)
        new_texts.append(MARK.sub(lambda _m: f"[^{next(it)}]", text))
        for key, new in zip(keys, new_keys):
            if new not in definition_of and f"{index}:{key}" in resolved:
                definition_of[new] = resolved[f"{index}:{key}"]
                order.append(new)
        if kind == "unverified" and keys:
            report["unverified"].append(
                {
                    "headings": [m.group(0).strip() for m in HEAD.finditer(text)],
                    "markers": len(keys),
                    "reason": "no research file: kept pointing at the source it points to now",
                }
            )

    if missing:
        report["notes"].append(
            "markers with no definition anywhere (kept as they were, unlinked): "
            + ", ".join(f"[^{m.split(':', 1)[1]}]" for m in missing)
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
    for rf in research_files:
        keys = [k for k, _ in definitions_with_duplicates(rf.read_text())]
        if len(keys) != len(set(keys)):
            collapsed.append(rf.name)
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
    return ScanRow(memo, wrong, checked, per, collapsed)


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
