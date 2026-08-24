"""
Archive Renaming

Renames portfolio source files onto the house convention:

    portfolio/<Company>/<YYYYMMDD>_<Company>_<Collection>--<Round>/
        <YYYYMMDD>_<Company>_<DocName>--<Round>.<ext>

The dates repeat at every level on purpose. A person browsing a portfolio in
Finder or a terminal sorts by name and wants the newest thing first; a date
prefix makes name-order and time-order the same order, at every depth, without
anyone having to switch to a date column that does not survive a copy.

**This is a destructive operation on a private archive, so it is built to be
reversed.** Planning and applying are separate calls, every plan is written to a
manifest before a single file moves, and the manifest is enough to undo the
whole thing. Nothing here runs without an explicit apply.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .date_resolution import resolve_deck_date, sibling_dates_for
from .deck_lineage import _token


MANIFEST_NAME = "rename-manifest.json"

# Caps on the document token. Long enough to stay identifiable, short enough to
# read in a listing and type in a shell.
_MAX_DOC_WORDS = 7
_MAX_DOC_CHARS = 58


@dataclass
class RenamePlan:
    """One file's move, with the reasoning that produced it."""

    source: str
    target: str
    date_used: Optional[str]
    date_source: Optional[str]
    date_confidence: Optional[str]
    collection: str
    doc_name: str
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "source": self.source,
            "target": self.target,
            "date_used": self.date_used,
            "date_source": self.date_source,
            "date_confidence": self.date_confidence,
            "collection": self.collection,
            "doc_name": self.doc_name,
            "notes": self.notes,
        }


# =============================================================================
# Naming pieces
# =============================================================================

# Folder names in the existing archive, mapped to collection tokens. Anything
# unmatched keeps its own name, tokenized — the archive's own vocabulary is
# usually better than a category we would invent for it.
_COLLECTION_ALIASES = {
    "series a executed documents": "ExecutedDocuments",
    "series seed documents": "SeedDocuments",
    "vantage products - series a - transaction documents": "TransactionDocuments",
    "transaction documents": "TransactionDocuments",
    "second tranch": "SecondTranche",
    "second tranche": "SecondTranche",
    "spv": "SPV",
    "research": "Research",
    "diligence": "Diligence",
    "misc": "Misc",
    "": "Dataroom",
}

# Words to drop from a document name — they repeat what the path already says.
_DOC_NOISE = re.compile(
    r"\b(?:compressed|final|copy|v\d+|\(\d+\)|\[\d+\]|updated?|signed|executed)\b",
    re.IGNORECASE,
)


def collection_token(folder_name: str) -> str:
    """Token for the folder a document sits in."""
    key = folder_name.strip().lower()
    if key in _COLLECTION_ALIASES:
        return _COLLECTION_ALIASES[key]
    for alias, token in _COLLECTION_ALIASES.items():
        if alias and alias in key:
            return token
    return _token(folder_name) or "Dataroom"


def load_company_registry(path: Path) -> Dict[str, Dict]:
    """
    Read the portfolio's company registry, keyed by canonical token.

    A company is spelled several ways across an archive — legal entity on the
    SAFE, brand on the deck, an abbreviation in a spreadsheet, and at least one
    typo. One canonical token plus a list of aliases lets every consumer strip
    all of them while writing only one.
    """
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {c["token"]: c for c in data.get("companies", [])}


def doc_token(filename: str, company: str, keep_qualifiers: bool = True,
              aliases: Optional[Sequence[str]] = None) -> str:
    """
    Token for the document itself.

    The company name comes out — the path already carries it, and repeating it
    inside the filename is the noise that made the originals hard to scan.
    Qualifiers like "Executed" or "Updated" stay by default, appended after a
    ``--``, because signed-versus-form is exactly the distinction a reader needs
    from a filename.
    """
    stem = Path(filename).stem
    # Strip every spelling of the company, not just the canonical one. The path
    # already names the company; repeating "Meridian Systems" inside the
    # filename is the noise this exists to remove.
    company_tokens = set()
    for name in [company, *(aliases or [])]:
        company_tokens |= {t.lower() for t in re.split(r"[^A-Za-z0-9]+", name) if len(t) > 2}

    qualifiers: List[str] = []
    if keep_qualifiers:
        for word, label in (
            (r"\[?executed\]?", "Executed"),
            (r"\bsigned\b", "Signed"),
            (r"\bform of\b", "Form"),
            (r"\bdraft\b", "Draft"),
            (r"\bupdated?\b", "Updated"),
            (r"\btemplate\b", "Template"),
        ):
            if re.search(word, stem, re.IGNORECASE):
                qualifiers.append(label)

    cleaned = _DOC_NOISE.sub(" ", stem)
    cleaned = re.sub(r"\b(?:pwd|password)\s*\S+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[-_.]+", " ", cleaned)
    # Strip date-ish runs; the prefix carries the date now.
    cleaned = re.sub(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b", " ", cleaned)
    cleaned = re.sub(r"\b(?:20\d{2}|\d{6,8})\b", " ", cleaned)

    parts = [
        p for p in re.split(r"[^A-Za-z0-9]+", cleaned)
        if p and p.lower() not in company_tokens and len(p) > 1
    ]
    # Academic titles run to twenty words. A filename that long is unreadable in
    # a listing and unusable in a shell, so keep the leading words — which carry
    # the subject — and drop the tail.
    if len(parts) > _MAX_DOC_WORDS:
        parts = parts[:_MAX_DOC_WORDS]

    name = _token(" ".join(parts)) or "Document"
    if len(name) > _MAX_DOC_CHARS:
        name = name[:_MAX_DOC_CHARS]
    return f"{name}--{'-'.join(dict.fromkeys(qualifiers))}" if qualifiers else name


def round_token(round_name: Optional[str]) -> str:
    return _token(round_name) if round_name else "Unassigned"


# =============================================================================
# Planning
# =============================================================================

def plan_company_rename(
    company_dir: Path,
    company_token: str,
    round_by_path: Optional[Dict[str, str]] = None,
    default_round: str = "Unassigned",
    aliases: Optional[Sequence[str]] = None,
) -> List[RenamePlan]:
    """
    Build the rename plan for one company's folder. Moves nothing.

    Args:
        company_dir: The company's directory inside the portfolio.
        company_token: The token to use for this company in every path. Supplied
            rather than derived, because the archive spells companies several
            ways and a single canonical token has to be chosen deliberately.
        round_by_path: Optional map from a path fragment to a round name, so
            documents in different folders can carry different rounds.
        default_round: Round for anything the map does not cover.
    """
    plans: List[RenamePlan] = []
    round_by_path = round_by_path or {}

    for source in sorted(company_dir.rglob("*")):
        if not source.is_file() or source.name.startswith(".") or source.name.startswith("~$"):
            continue

        relative = source.relative_to(company_dir)
        folder = str(relative.parent) if str(relative.parent) != "." else ""
        collection = collection_token(folder)

        round_name = default_round
        for fragment, mapped in round_by_path.items():
            if fragment.lower() in str(relative).lower():
                round_name = mapped
                break

        resolved = _date_for(source)
        stamp = resolved.date_on_deck.strftime("%Y%m%d") if resolved.date_on_deck else "00000000"

        name = doc_token(source.name, company_token, aliases=aliases)
        # The folder stamp is filled in once per collection below; the file keeps
        # its own date.
        target = (
            company_dir.parent
            / company_token
            / f"{{FOLDER_STAMP}}_{company_token}_{collection}--{round_token(round_name)}"
            / f"{stamp}_{company_token}_{name}--{round_token(round_name)}{source.suffix.lower()}"
        )

        plans.append(RenamePlan(
            source=str(source),
            target=str(target),
            date_used=resolved.date_on_deck.isoformat() if resolved.date_on_deck else None,
            date_source=resolved.date_source,
            date_confidence=resolved.date_confidence,
            collection=collection,
            doc_name=name,
            notes=list(resolved.notes),
        ))

    return _deduplicate(_stamp_collections(plans))


def _stamp_collections(plans: List[RenamePlan]) -> List[RenamePlan]:
    """
    Give each collection folder one date: that of its most recent member.

    Dating the folder per-file exploded a coherent ``Research/`` folder into five
    singleton folders, one per paper, because the papers were published between
    2014 and 2024. That destroys the grouping the archive already had and buries
    a Seed-round collection under a decade-old publication date.

    Most-recent rather than earliest, because the point of the date prefix is
    newest-first browsing: a folder should sort by when it was last meaningfully
    added to.
    """
    by_folder: Dict[str, List[RenamePlan]] = {}
    for plan in plans:
        by_folder.setdefault(str(Path(plan.target).parent), []).append(plan)

    for folder, members in by_folder.items():
        dates = [m.date_used for m in members if m.date_used]
        stamp = max(dates).replace("-", "") if dates else "00000000"
        for member in members:
            member.target = str(Path(folder.replace("{FOLDER_STAMP}", stamp)) /
                                Path(member.target).name)
    return plans


def _date_for(path: Path):
    """
    Date one document with the same cascade the stenographer uses for decks.

    Only PDFs get their text and metadata read; for everything else the filename
    and the surrounding folder carry the signal. A document that yields nothing
    lands under ``00000000``, which sorts to the top and is meant to be
    conspicuous rather than tidy.
    """
    head = ""
    metadata: Dict = {}
    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf

            doc = pymupdf.open(str(path))
            if doc.needs_pass:
                from ..dataroom.document_text import _try_passwords

                _try_passwords(doc, path)
            metadata = doc.metadata or {}
            head = "\n".join(doc[i].get_text() for i in range(min(2, doc.page_count)))
            doc.close()
        except Exception:
            pass

    return resolve_deck_date(
        first_slides_text=head,
        pdf_title=metadata.get("title"),
        pdf_creation_date=metadata.get("creationDate"),
        filename=path.name,
        file_mtime=datetime.fromtimestamp(path.stat().st_mtime).date(),
        sibling_dates=sibling_dates_for(path),
    )


def _deduplicate(plans: Sequence[RenamePlan]) -> List[RenamePlan]:
    """
    Give colliding targets a numeric suffix.

    Collisions are expected, not exceptional: the archive holds a signed and an
    unsigned copy of the same agreement, and both normalize to the same name once
    the noise words come out. Renaming one over the other would destroy a file.
    """
    seen: Dict[str, int] = {}
    result: List[RenamePlan] = []

    for plan in plans:
        target = Path(plan.target)
        key = str(target).lower()
        if key in seen:
            seen[key] += 1
            plan.target = str(target.with_name(f"{target.stem}--{seen[key]}{target.suffix}"))
            plan.notes.append(
                f"name collided with an earlier file; suffixed --{seen[key]}"
            )
        else:
            seen[key] = 1
        result.append(plan)

    return result


# =============================================================================
# Applying and reversing
# =============================================================================

def write_manifest(plans: Sequence[RenamePlan], manifest_path: Path) -> Path:
    """Persist a plan. Written before anything moves, so a crash is recoverable."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "created": datetime.now().isoformat(),
                "applied": False,
                "moves": [p.as_dict() for p in plans],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def apply_manifest(manifest_path: Path, confirm: bool = False) -> Dict:
    """
    Execute a written plan.

    ``confirm`` must be passed explicitly. A default-safe apply that a caller can
    trigger by forgetting an argument is not a safe apply.
    """
    if not confirm:
        raise ValueError("apply_manifest requires confirm=True — refusing to move files")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("applied"):
        raise ValueError(f"{manifest_path} was already applied; reverse it before re-applying")

    moved, failed = 0, []
    for move in data["moves"]:
        source, target = Path(move["source"]), Path(move["target"])
        try:
            if not source.exists():
                failed.append({"source": str(source), "error": "source no longer exists"})
                continue
            if target.exists():
                failed.append({"source": str(source), "error": f"target exists: {target}"})
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            moved += 1
        except OSError as e:
            failed.append({"source": str(source), "error": str(e)})

    # Prune directories the moves emptied. Left behind, they read as surviving
    # collections — a "Research/" folder that still exists but holds nothing
    # looks like a rename that half-failed. Deepest-first so nested empties
    # collapse; only ever removes directories that are genuinely empty.
    removed_dirs = _prune_empty_dirs(
        {Path(m["source"]).parent for m in data["moves"]}
    )

    data["applied"] = True
    data["removed_empty_dirs"] = removed_dirs
    data["applied_at"] = datetime.now().isoformat()
    data["moved"] = moved
    data["failed"] = failed
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {"moved": moved, "failed": failed}


def _prune_empty_dirs(candidates) -> List[str]:
    """
    Remove directories left empty by a move, deepest first.

    Ignores dotfiles when deciding emptiness — a stray ``.DS_Store`` should not
    keep a dead folder alive — but never removes a directory holding real files.
    """
    removed: List[str] = []
    ordered = sorted(candidates, key=lambda p: len(Path(p).parts), reverse=True)

    for directory in ordered:
        directory = Path(directory)
        while directory.exists() and directory.is_dir():
            entries = [e for e in directory.iterdir() if not e.name.startswith(".")]
            if entries:
                break
            for junk in directory.iterdir():
                junk.unlink(missing_ok=True)
            try:
                directory.rmdir()
                removed.append(str(directory))
            except OSError:
                break
            directory = directory.parent

    return removed


def reverse_manifest(manifest_path: Path, confirm: bool = False) -> Dict:
    """Undo an applied plan, putting every file back where it started."""
    if not confirm:
        raise ValueError("reverse_manifest requires confirm=True — refusing to move files")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored, failed = 0, []

    for move in reversed(data["moves"]):
        source, target = Path(move["source"]), Path(move["target"])
        try:
            if not target.exists():
                failed.append({"target": str(target), "error": "not found; already reversed?"})
                continue
            source.parent.mkdir(parents=True, exist_ok=True)
            target.rename(source)
            restored += 1
        except OSError as e:
            failed.append({"target": str(target), "error": str(e)})

    data["applied"] = False
    data["reversed_at"] = datetime.now().isoformat()
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return {"restored": restored, "failed": failed}


def format_plan_preview(plans: Sequence[RenamePlan], limit: int = 0) -> str:
    """Render a plan for a human to read before approving it."""
    lines: List[str] = []
    by_folder: Dict[str, List[RenamePlan]] = {}
    for plan in plans:
        by_folder.setdefault(str(Path(plan.target).parent), []).append(plan)

    for folder in sorted(by_folder):
        lines.append(f"\n{folder}/")
        for plan in by_folder[folder][: limit or None]:
            confidence = (plan.date_confidence or "?")[:3]
            lines.append(
                f"    {Path(plan.target).name}"
                f"\n        ← {Path(plan.source).name}"
                f"   [{plan.date_used or 'no date'} · {plan.date_source or '—'} · {confidence}]"
            )
            for note in plan.notes:
                lines.append(f"        ! {note[:110]}")
    return "\n".join(lines)
