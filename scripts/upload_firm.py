#!/usr/bin/env python3
"""Upload a firm made by the local pipeline (``io/<firm>/``) to the connector.

Spec: ``context-v/specs/Upload-Deal-Folders-With-a-Binaries-Manifest.md``.

Run on the laptop. It stages first and writes nothing to the server::

    uv run python scripts/upload_firm.py io/humain --firm humain-vc --out /tmp/humain-upload

    <out>/firms/<firm>/        # deal folders and firm files, as /data/firms/<firm>/ holds them
    <out>/blobs/<sha256>       # each binary once, by content
    <out>/manifests/<path>/binaries-on-server.yaml   # one per local deal folder and the firm root
    <out>/plan.json            # what apply_upload.py does on the server
    <out>/apply_upload.py      # the server-side step, shipped with the staging
    <out>/report.md            # per deal: what goes up, what next_step will ask for

``--apply`` then streams the staging to the server over ``railway ssh``, runs
the apply step as the service user (it backs the firm up first), and copies the
manifests into the local deal folders.

``--firm`` is the slug on the server, which must equal the firm's didi.sh entity
slug; the local folder name does not matter. A deal's server name comes from
``memopop_deal`` in its config, else from its domain.

For each deal:

- Research and section drafts of the newest version that has them become
  ``research/<key>.md`` and ``sections/<key>.md``, research recorded as approved.
- The newest finished memo (``7-<Deal>-v*.md``, else ``6-<Deal>-v*.md``) becomes
  compiled version 1, labelled with its local version, so a site can show it.
- Every other text file in the deal folder is kept under ``local/<path>``.
- Every binary goes to the bucket once, as ``blobs/<sha256>``, and is recorded
  both as a material in ``deal.json`` and in the deal folder's
  ``binaries-on-server.yaml``. The same bytes at several paths in one deal are
  one material listing every path (``local_paths``); the manifest, keyed by
  path, points each of them at that material. A binary already in that manifest with the same
  hash is not staged again, nor is one whose hash is in ``--known-blobs <file>``
  (the hash list ``scripts/fold_imported_blobs.py`` prints on the server).
- Each binary's text is extracted here, with the connector's own reader, into
  ``materials/<material_id>.md``, so the material is ``ready`` as one added with
  ``add_materials`` would be. A binary with no text (an image, a scan with no
  text layer) is recorded ``skipped`` with the reason, as the server would.
- When every section has a draft and a finished memo exists, the optional
  enhancement steps are recorded as skipped: the local run already applied them.

Section files are matched to the outline's keys by key, by number plus name,
or by key prefix, because outline filenames and local filenames drifted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.connector.history import TEXT_EXTENSIONS  # noqa: E402
from src.connector.materials.extract import Unextractable, extract  # noqa: E402
from src.connector.tools.create_new_deal import domain_of, slugify  # noqa: E402

REPO_OUTLINES = Path(__file__).resolve().parents[1] / "templates" / "outlines"
DEFAULT_TEMPLATE = "direct-early-stage-12Ps"
ENHANCEMENTS_DEAL = [
    "enhance.diagrams",
    "enhance.one_pager",
    "enhance.scorecard",
    "enhance.summaries",
]
ENHANCEMENTS_SECTION = ["enhance.citations", "enhance.fact_check", "enhance.tables"]
SKIP_FILES = {".DS_Store", "binaries-on-server.yaml"}


def is_macos_metadata(name: str) -> bool:
    """A Finder or AppleDouble file (``._x``, ``.DS_Store``): never content, never sent."""
    return name.startswith("._") or name == ".DS_Store"


MANIFEST = "binaries-on-server.yaml"
FINAL_MEMO = re.compile(r"^([67])-.+-v\d+(\.\d+)+\.md$")
FIRM_DIRS = ("configs", "templates", "assets")
HASH_LINE = re.compile(r"^[0-9a-f]{64}$")
EXTRACT_STEP = "materials.extract"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def material_id(*parts: str) -> str:
    return "mat-" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def is_text(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in TEXT_EXTENSIONS


def version_key(path: Path) -> list[int]:
    return [int(x) for x in re.findall(r"\d+", path.name.rsplit("-v", 1)[-1])]


def norm(text: str) -> str:
    return re.sub(r"-+", "-", text.lower()).strip("-")


def name_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ------------------------------------------------------------------ outlines


def outline_path(firm_dir: Path, name: str) -> Path | None:
    for d in (firm_dir / "templates" / "outlines", REPO_OUTLINES):
        p = d / f"{name}.yaml"
        if p.is_file():
            return p
    return None


def load_sections(path: Path) -> list[dict]:
    """The same section list the connector's templates.load_sections builds."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sections = []
    for index, section in enumerate(data.get("sections") or []):
        filename = str(section.get("filename") or "")
        key = (
            filename[:-3]
            if filename.endswith(".md")
            else f"{index + 1:02d}-{name_slug(str(section.get('name', ''))) or 'section'}"
        )
        questions = section.get("guiding_questions") or []
        if isinstance(questions, dict):
            questions = [q for group in questions.values() for q in (group or [])]
        sections.append(
            {
                "key": key,
                "name": str(section.get("name") or f"Section {index + 1}"),
                "number": section.get("number", index + 1),
                "description": str(section.get("description") or "").strip(),
                "guiding_questions": [str(q) for q in questions if isinstance(q, str)],
                "target_length": section.get("target_length") or {},
            }
        )
    return sections


def match_file(section: dict, files: dict[str, Path]) -> Path | None:
    """The local file for an outline section: by key, number plus name, or key prefix."""
    key = norm(section["key"])
    number = key.split("-", 1)[0]
    by_name = f"{number}-{name_slug(section['name'])}"
    normed = {norm(stem): p for stem, p in files.items()}
    for candidate in (key, by_name):
        if candidate in normed:
            return normed[candidate]
    prefixed = [p for stem, p in normed.items() if stem.startswith(key + "-")]
    return prefixed[0] if len(prefixed) == 1 else None


# ------------------------------------------------------------------ one deal


def pick_version(deal_dir: Path) -> Path | None:
    outputs = deal_dir / "outputs"
    if not outputs.is_dir():
        return None
    versions = sorted(
        (p for p in outputs.iterdir() if p.is_dir() and "-v" in p.name),
        key=version_key,
        reverse=True,
    )

    def has(p: Path, sub: str) -> bool:
        return (p / sub).is_dir() and any((p / sub).glob("*.md"))

    for test in (
        lambda p: has(p, "2-sections"),
        lambda p: has(p, "1-research"),
        lambda p: any(p.glob("7-*.md")),
    ):
        for p in versions:
            if test(p):
                return p
    return None


def final_memo(deal_dir: Path) -> tuple[Path, Path] | None:
    """The newest finished memo: (version folder, memo file). 7- beats 6- in a version."""
    outputs = deal_dir / "outputs"
    if not outputs.is_dir():
        return None
    versions = sorted(
        (p for p in outputs.iterdir() if p.is_dir() and "-v" in p.name),
        key=version_key,
        reverse=True,
    )
    for v in versions:
        memos = sorted(
            (p for p in v.glob("*.md") if FINAL_MEMO.match(p.name)),
            key=lambda p: p.name[0],
            reverse=True,
        )
        if memos:
            return v, memos[0]
    return None


def binary_kind(rel: Path) -> str:
    parts = [p.lower() for p in rel.parts]
    name = rel.name.lower()
    if any("dataroom" in p or "data-room" in p for p in parts):
        return "dataroom"
    if "exports" in parts or "outputs" in parts:
        return "export"
    if "deck" in name or rel.suffix.lower() in (".key", ".pptx", ".ppt"):
        return "deck"
    if rel.suffix.lower() in (".xlsx", ".xls", ".csv", ".numbers"):
        return "financials"
    if rel.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
        return "image"
    return "other"


def read_manifest(folder: Path) -> dict:
    p = folder / MANIFEST
    if not p.is_file():
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("files") or {}


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_known_blobs(path: Path) -> set[str]:
    """Hashes already in the bucket as ``blobs/<sha256>``: every line that is exactly one.

    Anything else on a line (progress output, a comment) makes it not count.
    """
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if HASH_LINE.match(line.strip())
    }


def trading_name(cfg: dict) -> str | None:
    """The name the company trades under: trading_name, then name, then legal_name."""
    for field in ("trading_name", "name", "legal_name"):
        value = cfg.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def write_brief(state: dict, final: tuple[Path, Path], version: Path | None) -> str:
    """The materials brief for a finished deal: what it has and where it came from.

    The local run already read these materials, so this lists them instead of
    summarizing them again. Steps that read ``materials.brief`` then get something
    real rather than nothing (CONN-PT-05).
    """
    memo_version = final[0].name.rsplit("-", 1)[-1]
    lines = [
        f"# Materials brief: {state['company']} (imported)",
        "",
        f"This deal was finished in the local pipeline and imported. Its finished memo is "
        f"{memo_version}, from the local run {final[0].name} (`{final[1].name}`); it is "
        "compiled version 1 here and is also among the materials.",
    ]
    if version is not None and version != final[0]:
        lines.append(f"The research and section drafts come from the local run {version.name}.")
    lines += [
        "",
        "The local run read these materials and applied the enhancements, so this brief "
        "lists them rather than summarizing them again. Read a text material with "
        "get_artifact; binaries are in the firm's bucket.",
        "",
        "## Materials",
        "",
    ]
    for m in state["materials"]:
        what = m.get("title") or m.get("filename") or m["material_id"]
        size = f", {m['bytes']:,} bytes" if m.get("bytes") else ""
        where = "in the bucket" if m.get("bucket_key") else "text"
        lines.append(f"- `{m['material_id']}` ({m.get('kind')}, {where}{size}): {what}")
    return "\n".join(lines) + "\n"


def config_notes(cfg: dict) -> str:
    """The deal config as a notes material: what the operator told the pipeline."""
    lines = [f"# Deal notes for {trading_name(cfg) or 'this deal'} (imported)", ""]
    for field in ("description", "url", "stage", "type", "mode"):
        if cfg.get(field):
            lines.append(f"- **{field}:** {cfg[field]}")
    for field in ("notes", "research_focus"):
        if cfg.get(field):
            lines += ["", f"## {field.replace('_', ' ').title()}", "", str(cfg[field])]
    for field in (
        "proposed_terms",
        "founders",
        "known_competitors",
        "disambiguation",
        "search_variants",
    ):
        if cfg.get(field):
            lines += [
                "",
                f"## {field.replace('_', ' ').title()}",
                "",
                "```json",
                json.dumps(cfg[field], indent=2),
                "```",
            ]
    return "\n".join(lines) + "\n"


def server_slug(cfg: dict, deal_dir: Path) -> str:
    """The deal's name on the server: memopop_deal, else its domain, else its company."""
    named = (cfg.get("memopop_deal") or {}).get("deal")
    if named:
        return named
    domain = cfg.get("domain") or domain_of(cfg.get("url"))
    return slugify(domain) if domain else slugify(trading_name(cfg) or deal_dir.name)


class Stager:
    def __init__(self, out: Path, firm: str, known_blobs: set[str] | None = None):
        self.out = out
        self.firm = firm
        self.ws = out / "firms" / firm
        self.blobs = out / "blobs"
        self.bucket_bytes = 0
        self.blob_hashes: set[str] = set()
        self.reused = 0
        self.known = set(known_blobs or ())
        self.known_used: set[str] = set()
        self.texts: dict[str, tuple[str | None, str | None]] = {}

    def text_of(self, src: Path, digest: str) -> tuple[str | None, str | None]:
        """(text, None) or (None, why not), extracted once per distinct content."""
        if digest not in self.texts:
            try:
                self.texts[digest] = (extract(src.read_bytes(), src.name), None)
            except Unextractable as exc:
                self.texts[digest] = (None, str(exc))
        return self.texts[digest]

    def put_blob(
        self, src: Path, rel: Path, manifest: dict, entries: dict, now: str, deal: str | None
    ) -> dict:
        """Stage a binary once by content; return its manifest entry."""
        digest = file_sha(src)
        key = f"blobs/{digest}"
        known = manifest.get(rel.as_posix())
        if known and known.get("sha256") == digest:
            self.reused += 1
            entry = dict(known)
        else:
            if digest in self.known:
                self.known_used.add(digest)  # already in the bucket; nothing to send
            elif digest not in self.blob_hashes:
                self.blobs.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, self.blobs / digest)
                self.blob_hashes.add(digest)
                self.bucket_bytes += src.stat().st_size
            entry = {
                "sha256": digest,
                "bytes": src.stat().st_size,
                "kind": binary_kind(rel),
                "bucket_key": key,
                "uploaded_at": now,
            }
            if deal:
                entry["material_id"] = material_id(deal, "binary", digest)
        entries[rel.as_posix()] = entry
        return entry

    def write_manifest(self, local_rel: Path, deal: str | None, entries: dict) -> None:
        p = self.out / "manifests" / local_rel / MANIFEST
        p.parent.mkdir(parents=True, exist_ok=True)
        doc = {"firm": self.firm, "deal": deal, "files": dict(sorted(entries.items()))}
        p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def write_ws(self, rel: str | Path, text: str) -> None:
        p = self.ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def copy_ws(self, src: Path, rel: str | Path) -> None:
        p = self.ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)


def import_deal(stage: Stager, firm_dir: Path, deal_dir: Path, now: str) -> dict:
    """Stage one deal; return its report line."""
    cfg_path = deal_dir / f"{deal_dir.name}.json"
    report: dict = {"local": deal_dir.name, "local_path": deal_dir.relative_to(firm_dir).as_posix()}
    if not cfg_path.is_file():
        report["skipped"] = "no deal config"
        return report
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    company = trading_name(cfg) or deal_dir.name
    url = cfg.get("url")
    domain = cfg.get("domain") or domain_of(url)
    slug = server_slug(cfg, deal_dir)
    template = cfg.get("outline") or cfg.get("template") or DEFAULT_TEMPLATE
    opath = outline_path(firm_dir, template)
    if opath is None:
        report["skipped"] = f"outline '{template}' not found"
        return report
    sections = load_sections(opath)
    if opath.parent != firm_dir / "templates" / "outlines":
        stage.copy_ws(opath, Path("templates") / "outlines" / opath.name)  # pin it to the firm

    version = pick_version(deal_dir)
    rel = Path("deals") / slug
    state = {
        "deal": slug,
        "company": company,
        "legal_name": cfg.get("legal_name"),
        "url": url,
        "domain": domain,
        "stage": cfg.get("stage"),
        "template": template,
        "sections": sections,
        "created_at": now,
        "updated_at": now,
        "materials": [],
        "artifacts": {},
        "handed_out": [],
        "skips": [],
        "skips_reported": 0,
        "compiled": None,
        "log": [{"at": now, "event": "created"}],
        "imported_from": {
            "path": str(deal_dir.relative_to(firm_dir.parent)),
            "version": version.name if version else None,
            "at": now,
        },
    }
    report.update(deal=slug, template=template, version=version.name if version else None)

    def artifact(
        step_id: str, section: str | None, path: str, kind: str, text: str, approved: bool
    ):
        stage.write_ws(rel / path, text)
        state["artifacts"][f"{step_id}:{section}" if section else step_id] = {
            "step_id": step_id,
            "section": section,
            "path": path,
            "kind": kind,
            "version": 1,
            "sha256": sha(text),
            "chars": len(text),
            "partner_approved": approved,
            "partner_notes": (
                f"Imported from the local pipeline run {version.name if version else '-'}."
                if approved
                else None
            ),
            "instruction_version": "1",
            "saved_at": now,
        }
        state["log"].append(
            {"at": now, "event": "imported", "step": step_id, "section": section, "version": 1}
        )

    def material(kind: str, title: str, text: str, src: Path | None = None) -> None:
        mid = material_id(slug, title)
        stage.write_ws(rel / "materials" / f"{mid}.md", text)
        record = {
            "material_id": mid,
            "kind": kind,
            "status": "ready",
            "source": "import",
            "title": title,
            "filename": src.name if src else None,
            "chars": len(text),
            "added_at": now,
            "ready_at": now,
        }
        state["materials"].append(record)

    # materials: what the operator told the pipeline, and what the pipeline read
    material("notes", "Deal notes (imported deal config)", config_notes(cfg), cfg_path)
    if version:
        for name, kind, title in (
            ("0-deck-analysis.md", "deck", "Deck analysis (imported)"),
            ("0-dataroom-inventory.md", "dataroom", "Dataroom inventory (imported)"),
        ):
            if (version / name).is_file():
                material(kind, title, (version / name).read_text(encoding="utf-8"), version / name)
    final = final_memo(deal_dir)
    if final:
        material(
            "other",
            f"Previous memo, {final[0].name} (imported)",
            final[1].read_text(encoding="utf-8"),
            final[1],
        )
    sources_md = deal_dir / "inputs" / "Sources.md"

    # research and drafts
    research_files = {}
    draft_files = {}
    if version:
        if (version / "1-research").is_dir():
            research_files = {
                p.stem.removesuffix("-research"): p for p in (version / "1-research").glob("*.md")
            }
        if (version / "2-sections").is_dir():
            draft_files = {p.stem: p for p in (version / "2-sections").glob("*.md")}
    got_research, got_drafts = [], []
    for s in sections:
        p = match_file(s, research_files)
        if p:
            artifact(
                "research.section",
                s["key"],
                f"research/{s['key']}.md",
                "research",
                p.read_text("utf-8"),
                True,
            )
            got_research.append(s["key"])
        p = match_file(s, draft_files)
        if p:
            artifact(
                "draft.section",
                s["key"],
                f"sections/{s['key']}.md",
                "section",
                p.read_text("utf-8"),
                False,
            )
            got_drafts.append(s["key"])
    if sources_md.is_file() and got_research:
        artifact(
            "research.sources",
            None,
            "research/_sources.md",
            "sources",
            sources_md.read_text("utf-8"),
            True,
        )

    keys = [s["key"] for s in sections]
    finished = version is not None and final is not None and len(got_drafts) == len(keys)
    if finished:
        reason = (
            f"Already applied in the local pipeline run {version.name} this deal was imported from."
        )
        # materials.brief is written below, once every material is recorded, not skipped
        skips = [(step, None) for step in ENHANCEMENTS_DEAL]
        skips += [(step, k) for step in ENHANCEMENTS_SECTION for k in keys]
        if "research.sources" not in state["artifacts"]:
            skips.append(("research.sources", None))
        for step, section in skips:
            state["skips"].append(
                {
                    "step_id": step,
                    "section": section,
                    "code": "step_skipped",
                    "reason": reason,
                    "at": now,
                }
            )
        state["skips_reported"] = len(state["skips"])  # nothing new to tell the partner

    # the newest finished memo is compiled version 1, labelled with its local version
    if final:
        memo = final[1].read_text(encoding="utf-8")
        label = final[0].name.rsplit("-", 1)[-1]
        digest = sha(memo)
        stage.write_ws(rel / "compiled" / "1" / "memo.md", memo)
        state["compiled"] = {"version": 1, "label": label, "sha256": digest, "keys": {}, "at": now}
        state["artifacts"]["compile.assemble"] = {
            "step_id": "compile.assemble",
            "section": None,
            "path": "compiled/1/memo.md",
            "kind": "compiled",
            "version": 1,
            "sha256": digest,
            "chars": len(memo),
            "partner_approved": False,
            "partner_notes": f"Imported from the local pipeline run {final[0].name}.",
            "instruction_version": "1",
            "saved_at": now,
        }
        state["log"].append({"at": now, "event": "compiled", "version": 1, "label": label})

    # the whole deal folder: text under local/, binaries to the bucket once, recorded
    manifest = read_manifest(deal_dir)
    entries: dict = {}
    binaries = 0
    unreadable = 0
    by_sha: dict[str, dict] = {}  # one material per distinct content in the deal
    for f in sorted(deal_dir.rglob("*")):
        if not f.is_file() or f.name in SKIP_FILES or "/." in f.as_posix():
            continue
        sub = f.relative_to(deal_dir)
        if is_text(f):
            stage.copy_ws(f, rel / "local" / sub)
            continue
        entry = stage.put_blob(f, sub, manifest, entries, now, slug)
        binaries += 1
        shared = by_sha.get(entry["sha256"])
        if shared is not None:  # same bytes at another path: same material, one more path
            shared["local_paths"].append(sub.as_posix())
            entry["material_id"] = shared["material_id"]
            continue
        mid = entry.get("material_id") or material_id(slug, "binary", entry["sha256"])
        entry["material_id"] = mid
        record = {
            "material_id": mid,
            "kind": entry["kind"],
            "source": "upload",
            "title": sub.as_posix(),
            "filename": f.name,
            "bucket_key": entry["bucket_key"],
            "sha256": entry["sha256"],
            "bytes": entry["bytes"],
            "local_path": sub.as_posix(),  # the first path; local_paths has them all
            "local_paths": [sub.as_posix()],
            "added_at": now,
        }
        # the text the materials pipeline would extract on the server, extracted here
        text, why_not = stage.text_of(f, entry["sha256"])
        if text is not None:
            stage.write_ws(rel / "materials" / f"{mid}.md", text)
            record.update(status="ready", chars=len(text), ready_at=now, error=None)
        else:
            record.update(status="skipped", error=why_not)
            unreadable += 1
            state["skips"].append(
                {
                    "step_id": EXTRACT_STEP,
                    "section": None,
                    "code": "material_unreadable",
                    "reason": f"{sub.as_posix()}: {why_not}",
                    "material_id": mid,
                    "at": now,
                }
            )
        state["materials"].append(record)
        by_sha[entry["sha256"]] = record
    stage.write_manifest(deal_dir.relative_to(firm_dir), slug, entries)

    if finished:
        artifact(
            "materials.brief",
            None,
            "materials/brief.md",
            "brief",
            write_brief(state, final, version),
            False,
        )
        state["skips_reported"] = len(state["skips"])  # the local run already read them

    stage.write_ws(rel / "deal.json", json.dumps(state, indent=2) + "\n")
    missing_research = [k for k in keys if k not in got_research]
    missing_drafts = [k for k in keys if k not in got_drafts]
    report.update(
        sections=len(keys),
        research=len(got_research),
        drafts=len(got_drafts),
        materials=len(state["materials"]),
        binaries=binaries,
        unreadable=unreadable,
        compiled=state["compiled"]["label"] if state["compiled"] else None,
        finished=finished,
        missing_research=missing_research,
        missing_drafts=missing_drafts,
    )
    return report


# ------------------------------------------------------------------ the firm


def upload_firm(
    firm_dir: Path,
    firm: str,
    out: Path,
    only: list[str] | None = None,
    known_blobs: set[str] | None = None,
) -> list[dict]:
    """Stage the firm for upload; write plan.json, report.md and the apply step.

    ``known_blobs`` are hashes already in the bucket as ``blobs/<sha256>``: they are
    recorded like any other binary but not staged.
    """
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; pick a fresh --out")
    stage = Stager(out, firm, known_blobs)
    now = now_iso()

    # the firm's own files: configs, outlines, scorecards, assets
    firm_paths: list[str] = []
    manifest = read_manifest(firm_dir)
    entries: dict = {}
    for sub in FIRM_DIRS:
        for f in sorted((firm_dir / sub).rglob("*")) if (firm_dir / sub).is_dir() else []:
            if not f.is_file() or f.name in SKIP_FILES or is_macos_metadata(f.name):
                continue
            rel = f.relative_to(firm_dir)
            if is_text(f):
                stage.copy_ws(f, rel)
                firm_paths.append(rel.as_posix())
            else:
                stage.put_blob(f, rel, manifest, entries, now, None)
    stage.write_manifest(Path("."), None, entries)

    reports = []
    for deal_dir in sorted(p for p in (firm_dir / "deals").iterdir() if p.is_dir()):
        if only and deal_dir.name not in only:
            continue
        reports.append(import_deal(stage, firm_dir, deal_dir, now))
    # outlines pinned from the repo by import_deal are firm files too
    for p in sorted((stage.ws / "templates" / "outlines").glob("*.yaml")):
        rel = p.relative_to(stage.ws).as_posix()
        if rel not in firm_paths:
            firm_paths.append(rel)

    slugs = [r["deal"] for r in reports if "deal" in r]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise SystemExit(f"two local deals map to the same server deal: {sorted(dupes)}")

    plan = {
        "firm": firm,
        "at": now,
        "deals": slugs,
        "firm_paths": firm_paths,
        "blobs": sorted(stage.blob_hashes),
        "known_blobs": sorted(stage.known_used),
        "local": {r["deal"]: r["local_path"] for r in reports if "deal" in r},
    }
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(Path(__file__).with_name("apply_upload.py"), out / "apply_upload.py")

    lines = [
        f"# Upload of {firm} ({now})",
        "",
        f"- Deals: {len(slugs)}",
        f"- Firm files: {len(firm_paths)}",
        f"- Binaries to send: {len(stage.blob_hashes)} ({stage.bucket_bytes / 1e6:,.0f} MB); "
        f"already uploaded per manifests: {stage.reused}; "
        f"already in the bucket per the known-blobs list: {len(stage.known_used)}",
        "",
    ]
    for r in reports:
        if "skipped" in r:
            lines.append(f"- **{r['local']}**: skipped ({r['skipped']})")
            continue
        lines.append(
            f"- **{r['local']}** → `{r['deal']}` ({r['template']}, sections from {r['version']}): "
            f"research {r['research']}/{r['sections']}, drafts {r['drafts']}/{r['sections']}, "
            f"compiled {r['compiled'] or 'none'}, {r['binaries']} binaries"
            + (f" ({r['unreadable']} with no text, recorded skipped)" if r["unreadable"] else "")
        )
        if r["missing_research"]:
            lines.append(
                f"  - next_step will ask for research on: {', '.join(r['missing_research'])}"
            )
        if r["missing_drafts"] and r["missing_drafts"] != r["missing_research"]:
            lines.append(f"  - and drafts of: {', '.join(r['missing_drafts'])}")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return reports


def apply(out: Path, firm_dir: Path, service: str) -> None:
    """Stream the staging to the server, run apply_upload.py there, then copy the manifests home."""
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    remote = (
        "set -e; rm -rf /tmp/upload; mkdir -p /tmp/upload; tar -xf - -C /tmp/upload; "
        "chown -R memopop:memopop /tmp/upload; cd /app; "
        f"runuser -u memopop -- env HOME=/home/memopop /opt/venv/bin/python /tmp/upload/apply_upload.py "
        f"{plan['firm']} /tmp/upload; rm -rf /tmp/upload"
    )
    # macOS tar adds a ._ AppleDouble entry beside every file with extended
    # attributes unless COPYFILE_DISABLE is set; the excludes catch any on disk.
    tar = subprocess.Popen(
        ["tar", "-cf", "-", "--no-xattrs", "--exclude=._*", "--exclude=.DS_Store", "-C", str(out), "."],
        stdout=subprocess.PIPE,
        env={**os.environ, "COPYFILE_DISABLE": "1"},
    )
    ssh = subprocess.run(
        ["railway", "ssh", "--service", service, "--", "sh", "-c", remote], stdin=tar.stdout
    )
    tar.stdout.close()
    if tar.wait() != 0 or ssh.returncode != 0:
        raise SystemExit("apply failed on the server; nothing copied home (see the output above)")
    for src in (out / "manifests").rglob(MANIFEST):
        dest = firm_dir / src.parent.relative_to(out / "manifests") / MANIFEST
        if dest.parent.is_dir():
            shutil.copy2(src, dest)
    print("manifests copied into the local deal folders")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("firm_dir", type=Path, help="the local firm folder, e.g. io/humain")
    parser.add_argument("--firm", required=True, help="the firm's slug on the server")
    parser.add_argument("--out", type=Path, required=True, help="an empty staging folder")
    parser.add_argument("--deal", action="append", help="only this local deal (repeatable)")
    parser.add_argument(
        "--known-blobs",
        type=Path,
        help="a hash list (fold_imported_blobs.py's output): blobs already in the bucket",
    )
    parser.add_argument("--apply", action="store_true", help="send the staging to the server")
    parser.add_argument("--service", default="connector", help="the Railway service to apply on")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if args.apply and (out / "plan.json").is_file():
        apply(out, args.firm_dir.resolve(), args.service)
        return 0
    known = read_known_blobs(args.known_blobs) if args.known_blobs else None
    upload_firm(args.firm_dir.resolve(), args.firm, out, args.deal, known)
    print((out / "report.md").read_text(encoding="utf-8"))
    if args.apply:
        apply(out, args.firm_dir.resolve(), args.service)
    return 0


if __name__ == "__main__":
    sys.exit(main())
