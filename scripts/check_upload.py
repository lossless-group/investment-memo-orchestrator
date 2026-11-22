#!/usr/bin/env python3
"""Check every uploaded deal on the server against its local deal folder.

Spec: ``context-v/specs/Upload-Deal-Folders-With-a-Binaries-Manifest.md``; plan
``context-v/plans/Apply-the-Deal-Folder-Uploader.md``, step 4. Two halves:

``snapshot`` runs on the server and reads only. It prints, as JSON, what each deal
holds: its sections, which have drafts, the compiled label, and every material
(with whether its text file exists and whether its bucket object does)::

    railway ssh --service connector -- sh -c 'cd /app && runuser -u memopop -- \\
      env HOME=/home/memopop /opt/venv/bin/python - snapshot <firm>' \\
      < scripts/check_upload.py > snapshot.json

``compare`` runs on the laptop, against the local firm folder (whose deal folders
hold the ``binaries-on-server.yaml`` manifests ``--apply`` copied home)::

    uv run python scripts/check_upload.py compare io/<firm> --snapshot snapshot.json

Per deal it reports the compiled label against the newest local ``7-``/``6-``
memo, the sections against the local outline, and the materials against the
manifest. It exits 1 if any deal differs. ``snapshot`` also works on a staging
folder (``<out>/firms/<firm>``) to check what is about to go up.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

MANIFEST = "binaries-on-server.yaml"


# ------------------------------------------------------------------ server side


def outline_keys(path: Path) -> list[str]:
    """Section keys as the connector derives them (templates.load_sections)."""
    import re

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    keys = []
    for index, section in enumerate(data.get("sections") or []):
        filename = str(section.get("filename") or "")
        slug = re.sub(r"[^a-z0-9]+", "-", str(section.get("name", "")).lower()).strip("-")
        keys.append(
            filename[:-3] if filename.endswith(".md") else f"{index + 1:02d}-{slug or 'section'}"
        )
    return keys


def snapshot(firm_root: Path, bucket=None) -> dict:
    """What the server (or a staging folder) holds for each deal. Reads only."""
    deals: dict[str, dict] = {}
    for deal_json in sorted((firm_root / "deals").glob("*/deal.json")):
        state = json.loads(deal_json.read_text(encoding="utf-8"))
        deal_dir = deal_json.parent
        template = state.get("template")
        outline = firm_root / "templates" / "outlines" / f"{template}.yaml"
        materials = []
        for m in state.get("materials", []):
            key = m.get("bucket_key")
            materials.append(
                {
                    "material_id": m.get("material_id"),
                    "status": m.get("status"),
                    "source": m.get("source"),
                    "filename": m.get("filename"),
                    "local_path": m.get("local_path"),
                    "sha256": m.get("sha256"),
                    "bucket_key": key,
                    "has_text": (deal_dir / "materials" / f"{m.get('material_id')}.md").is_file(),
                    "in_bucket": (bucket.exists(key) if bucket is not None and key else None),
                }
            )
        artifacts = state.get("artifacts", {})
        deals[deal_dir.name] = {
            "template": template,
            "outline_keys": outline_keys(outline) if outline.is_file() else None,
            "sections": [s["key"] for s in state.get("sections", [])],
            "drafted": [
                s["key"]
                for s in state.get("sections", [])
                if f"draft.section:{s['key']}" in artifacts
            ],
            "compiled": (state.get("compiled") or {}).get("label"),
            "materials": materials,
        }
    return {"firm": firm_root.name, "deals": deals}


# ------------------------------------------------------------------ laptop side


def _uploader():
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    import upload_firm

    return upload_firm


def compare(firm_dir: Path, snap: dict, manifests: Path | None = None) -> list[dict]:
    """One row per local deal folder with a config: what matches and what doesn't."""
    up = _uploader()
    manifests = manifests or firm_dir
    rows = []
    for deal_dir in sorted(p for p in (firm_dir / "deals").iterdir() if p.is_dir()):
        cfg_path = deal_dir / f"{deal_dir.name}.json"
        if not cfg_path.is_file():
            continue
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        local_rel = deal_dir.relative_to(firm_dir)
        manifest_doc = {}
        if (manifests / local_rel / MANIFEST).is_file():
            manifest_doc = (
                yaml.safe_load((manifests / local_rel / MANIFEST).read_text("utf-8")) or {}
            )
        slug = manifest_doc.get("deal") or up.server_slug(cfg, deal_dir)
        server = snap["deals"].get(slug)
        row: dict = {"local": deal_dir.name, "deal": slug, "server": server}
        if server is None:
            row.update(ok=False, problem="not on the server")
            rows.append(row)
            continue

        final = up.final_memo(deal_dir)
        local_label = final[0].name.rsplit("-", 1)[-1] if final else None
        compiled = {"local": local_label, "server": server["compiled"]}
        compiled["ok"] = compiled["local"] == compiled["server"]

        template = cfg.get("outline") or cfg.get("template") or up.DEFAULT_TEMPLATE
        opath = up.outline_path(firm_dir, template)
        local_keys = [s["key"] for s in up.load_sections(opath)] if opath else None
        missing_drafts = [k for k in server["sections"] if k not in server["drafted"]]
        sections = {
            "outline": len(local_keys) if local_keys is not None else None,
            "server": len(server["sections"]),
            "drafted": len(server["drafted"]),
            "missing_drafts": missing_drafts,
            "outline_differs": local_keys != server["sections"],
            "server_outline_differs": (
                server["outline_keys"] is not None and server["outline_keys"] != local_keys
            ),
        }
        # an unfinished local deal legitimately has sections left to draft
        sections["ok"] = not sections["outline_differs"] and not (final and missing_drafts)

        entries = {
            path: e
            for path, e in (manifest_doc.get("files") or {}).items()
            if not e.get("local_missing")
        }
        by_path = {m["local_path"]: m for m in server["materials"] if m.get("local_path")}
        matched, missing, not_in_bucket, no_text = [], [], [], []
        for path, entry in sorted(entries.items()):
            m = by_path.get(path)
            if m is None or m.get("sha256") != entry.get("sha256"):
                missing.append(path)
                continue
            matched.append(path)
            if m.get("in_bucket") is False:
                not_in_bucket.append(path)
            if m.get("status") == "ready" and not m.get("has_text"):
                no_text.append(path)
        extra = sorted(p for p in by_path if p not in entries)
        materials = {
            "manifest": len(entries),
            "matched": len(matched),
            "missing": missing,
            "extra": extra,
            "not_in_bucket": not_in_bucket,
            "ready_without_text": no_text,
        }
        materials["ok"] = not (missing or extra or not_in_bucket or no_text)

        row.update(
            compiled=compiled,
            sections=sections,
            materials=materials,
            ok=compiled["ok"] and sections["ok"] and materials["ok"],
        )
        rows.append(row)
    return rows


def render(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        mark = "ok  " if r["ok"] else "DIFF"
        if r.get("server") is None:
            lines.append(f"{mark} {r['local']} -> {r['deal']}: {r.get('problem')}")
            continue
        c, s, m = r["compiled"], r["sections"], r["materials"]
        lines.append(f"{mark} {r['local']} -> {r['deal']}")
        lines.append(f"     compiled: server {c['server'] or 'none'}, local {c['local'] or 'none'}")
        lines.append(
            f"     sections: {s['server']} on the server, {s['outline']} in the local outline, "
            f"{s['drafted']} drafted"
        )
        if s["outline_differs"]:
            lines.append("       the server's section keys differ from the local outline's")
        if s["server_outline_differs"]:
            lines.append("       the firm's outline on the server differs from the local one")
        if s["missing_drafts"]:
            lines.append(f"       no draft: {', '.join(s['missing_drafts'])}")
        lines.append(
            f"     materials: {m['matched']}/{m['manifest']} manifest entries on the server"
        )
        for label, key in (
            ("missing on the server", "missing"),
            ("on the server, not in the manifest", "extra"),
            ("not in the bucket", "not_in_bucket"),
            ("ready but no text file", "ready_without_text"),
        ):
            if m[key]:
                lines.append(f"       {label}: {', '.join(m[key])}")
    bad = sum(1 for r in rows if not r["ok"])
    lines.append("")
    lines.append(
        f"{len(rows) - bad}/{len(rows)} deals match" + ("" if not bad else f"; {bad} differ")
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check uploaded deals against the local folder.")
    sub = parser.add_subparsers(dest="command", required=True)
    snap_p = sub.add_parser("snapshot", help="on the server: print each deal's state as JSON")
    snap_p.add_argument("firm", help="the firm's slug on the server")
    snap_p.add_argument("--root", type=Path, help="a firm folder to read instead (e.g. a staging)")
    cmp_p = sub.add_parser("compare", help="on the laptop: compare a snapshot to io/<firm>")
    cmp_p.add_argument("firm_dir", type=Path)
    cmp_p.add_argument("--snapshot", type=Path, required=True)
    cmp_p.add_argument("--manifests", type=Path, help="read manifests here (e.g. <out>/manifests)")
    cmp_p.add_argument("--json", action="store_true", help="print the rows as JSON")
    args = parser.parse_args(argv)

    if args.command == "snapshot":
        if args.root:
            print(json.dumps(snapshot(args.root), indent=2))
            return 0
        sys.path.insert(0, "/app")
        from src.connector.bucket import bucket_for
        from src.connector.config import ConnectorSettings

        settings = ConnectorSettings.from_env()
        root = Path(settings.io_root) / args.firm
        print(json.dumps(snapshot(root, bucket_for(settings, args.firm)), indent=2))
        return 0

    snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    rows = compare(args.firm_dir.resolve(), snap, args.manifests)
    if args.json:
        print(json.dumps([{k: v for k, v in r.items() if k != "server"} for r in rows], indent=2))
    else:
        print(render(rows), end="")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
