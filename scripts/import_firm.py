#!/usr/bin/env python3
"""Import a firm made by the local pipeline (``io/<firm>/``) into connector shape.

An operator act, run on the laptop. It writes nothing to the server: it builds a
staging folder that mirrors what the server keeps, so it can be checked locally
before anything moves::

    <out>/firms/<firm>/        # the workspace, as /data/firms/<firm>/ holds it
    <out>/buckets/<firm>/      # the bucket, as its keys (LocalBucket layout)
    <out>/report.md            # per deal: what was imported, what comes next

    uv run python scripts/import_firm.py io/humain --firm humain-vc --out /tmp/humain-import

``--firm`` is the slug on the server, which must equal the firm's didi.sh entity
slug (humain is ``humain-vc`` there); the local folder name does not matter.

For each deal it picks the newest output version with drafts (else research,
else a finished memo) and turns it into a ``deal.json`` the connector can walk:

- ``1-research/<key>-research.md`` becomes ``research/<key>.md``, recorded as
  approved (the operator ran and accepted it locally).
- ``2-sections/<key>.md`` becomes ``sections/<key>.md``.
- The deal config, deck analysis, dataroom inventory, Sources.md, and the
  finished memo become ready text materials, so Claude reads them as inputs.
- When every section has a draft and a finished memo exists, the optional
  enhancement steps are recorded as skipped: the local run already applied
  them. Required steps are never skipped; what is missing is what next_step
  will ask for.
- Every text file of that version is kept under ``imported/<version>/``; the
  originals in ``inputs/`` and the binaries in ``exports/`` and the version
  folder go to the bucket under ``imported/``.

Section files are matched to the outline's keys by key, by number plus name,
or by key prefix, because outline filenames and local filenames drifted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.connector.history import TEXT_EXTENSIONS  # noqa: E402
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
SKIP_FILES = {".DS_Store"}


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


def config_notes(cfg: dict) -> str:
    """The deal config as a notes material: what the operator told the pipeline."""
    lines = [f"# Deal notes for {cfg.get('legal_name') or cfg.get('name')} (imported)", ""]
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


class Stager:
    def __init__(self, out: Path, firm: str):
        self.ws = out / "firms" / firm
        self.bucket = out / "buckets" / firm
        self.bucket_bytes = 0

    def write_ws(self, rel: str | Path, text: str) -> None:
        p = self.ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    def copy_ws(self, src: Path, rel: str | Path) -> None:
        p = self.ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)

    def put_bucket(self, src: Path, key: str) -> None:
        p = self.bucket / key
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, p)
        self.bucket_bytes += src.stat().st_size


def import_deal(stage: Stager, firm_dir: Path, deal_dir: Path, now: str) -> dict:
    """Stage one deal; return its report line."""
    cfg_path = deal_dir / f"{deal_dir.name}.json"
    report: dict = {"local": deal_dir.name}
    if not cfg_path.is_file():
        report["skipped"] = "no deal config"
        return report
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    company = cfg.get("legal_name") or cfg.get("name") or deal_dir.name
    url = cfg.get("url")
    domain = domain_of(url)
    slug = slugify(domain) if domain else slugify(company)
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
        memos = sorted(version.glob("7-*.md"))
        if memos:
            material(
                "other",
                f"Previous memo, {version.name} (imported)",
                memos[0].read_text(encoding="utf-8"),
                memos[0],
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
    finished = version is not None and any(version.glob("7-*.md")) and len(got_drafts) == len(keys)
    if finished:
        reason = (
            f"Already applied in the local pipeline run {version.name} this deal was imported from."
        )
        skips = [("materials.brief", None)]
        skips += [(step, None) for step in ENHANCEMENTS_DEAL]
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

    # keep every text file of the version; binaries and originals go to the bucket
    if version:
        for f in version.rglob("*"):
            if not f.is_file() or f.name in SKIP_FILES:
                continue
            sub = f.relative_to(version)
            if is_text(f):
                stage.copy_ws(f, rel / "imported" / version.name / sub)
            else:
                stage.put_bucket(f, f"imported/{slug}/{version.name}/{sub.as_posix()}")
    for folder in ("inputs", "exports", "assets"):
        for f in (deal_dir / folder).rglob("*") if (deal_dir / folder).is_dir() else []:
            if f.is_file() and f.name not in SKIP_FILES:
                stage.put_bucket(
                    f, f"imported/{slug}/{folder}/{f.relative_to(deal_dir / folder).as_posix()}"
                )
    stage.copy_ws(cfg_path, rel / "imported" / cfg_path.name)

    stage.write_ws(rel / "deal.json", json.dumps(state, indent=2) + "\n")
    missing_research = [k for k in keys if k not in got_research]
    missing_drafts = [k for k in keys if k not in got_drafts]
    report.update(
        sections=len(keys),
        research=len(got_research),
        drafts=len(got_drafts),
        materials=len(state["materials"]),
        finished=finished,
        missing_research=missing_research,
        missing_drafts=missing_drafts,
    )
    return report


# ------------------------------------------------------------------ the firm


def import_firm(firm_dir: Path, firm: str, out: Path, only: list[str] | None = None) -> list[dict]:
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; pick a fresh --out")
    stage = Stager(out, firm)
    now = now_iso()
    for sub in ("templates", "configs"):
        if (firm_dir / sub).is_dir():
            for f in (firm_dir / sub).rglob("*"):
                if f.is_file() and f.name not in SKIP_FILES:
                    if is_text(f):
                        stage.copy_ws(f, f.relative_to(firm_dir))
                    else:
                        stage.put_bucket(f, f"imported/_firm/{f.relative_to(firm_dir).as_posix()}")
    if (firm_dir / "assets").is_dir():
        for f in (firm_dir / "assets").rglob("*"):
            if f.is_file() and f.name not in SKIP_FILES:
                stage.put_bucket(
                    f, f"imported/_firm/assets/{f.relative_to(firm_dir / 'assets').as_posix()}"
                )
    firm_json = {"default_template": DEFAULT_TEMPLATE}
    stage.write_ws("firm.json", json.dumps(firm_json, indent=2) + "\n")

    reports = []
    for deal_dir in sorted(p for p in (firm_dir / "deals").iterdir() if p.is_dir()):
        if only and deal_dir.name not in only:
            continue
        reports.append(import_deal(stage, firm_dir, deal_dir, now))

    slugs = [r["deal"] for r in reports if "deal" in r]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        raise SystemExit(f"two local deals map to the same slug: {sorted(dupes)}")

    lines = [f"# Import of {firm} ({now})", "", f"Bucket bytes staged: {stage.bucket_bytes:,}", ""]
    for r in reports:
        if "skipped" in r:
            lines.append(f"- **{r['local']}**: skipped ({r['skipped']})")
            continue
        lines.append(
            f"- **{r['local']}** → `{r['deal']}` ({r['template']}, {r['version']}): "
            f"research {r['research']}/{r['sections']}, drafts {r['drafts']}/{r['sections']}, "
            f"{r['materials']} materials{', finished' if r['finished'] else ''}"
        )
        if r["missing_research"]:
            lines.append(
                f"  - next_step will ask for research on: {', '.join(r['missing_research'])}"
            )
        if r["missing_drafts"] and r["missing_drafts"] != r["missing_research"]:
            lines.append(f"  - and drafts of: {', '.join(r['missing_drafts'])}")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("firm_dir", type=Path, help="the local firm folder, e.g. io/humain")
    parser.add_argument("--firm", required=True, help="the firm's slug on the server")
    parser.add_argument("--out", type=Path, required=True, help="an empty staging folder")
    parser.add_argument("--deal", action="append", help="import only this local deal (repeatable)")
    args = parser.parse_args(argv)
    import_firm(args.firm_dir.resolve(), args.firm, args.out.resolve(), args.deal)
    print((args.out / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
