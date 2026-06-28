#!/usr/bin/env python3
"""
Sources Curation UI — a local, disposable tool for converging a Sources.md.

Binds a navigable curation UI to ONE `Sources-aggregated.md` (or any
Sources.md). Page through each source, edit metadata, delete/reorder,
preview content via Jina, fire a SearXNG search and add results back into
the list, then save a converged `inputs/Sources.md` (backed up).

Reuses the orchestrator's own parsing + fetch — adds no dependencies.

Run:
    cd apps/memopop-orchestrator
    export SEARXNG_URL=http://localhost:8080      # optional; enables search
    .venv/bin/python tools/curate_sources.py \
        --file io/humain/deals/ImmuneCo/outputs/ImmuneCo-v0.0.3/Sources-aggregated.md \
        --port 8770

See context-v/plans/Sources-Curation-UI-Tool.md for the design.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make `src.curation` importable when run as a script from anywhere.
ORCH_ROOT = Path(__file__).resolve().parent.parent
if str(ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(ORCH_ROOT))

import httpx
import uvicorn
import yaml
from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse

from src.curation.sources_md import parse_frontmatter  # noqa: E402
from src.curation.fetch import fetch_url_markdown        # noqa: E402

DEFAULT_FILE = (
    "io/humain/deals/ImmuneCo/outputs/ImmuneCo-v0.0.3/Sources-aggregated.md"
)

# Canonical per-source field order when re-serializing.
FIELD_ORDER = [
    "url", "title", "publisher", "published_date",
    "sections", "rank", "sensitivity", "verdict", "note",
]
# Top-level frontmatter keys we preserve (in this order) on save.
META_ORDER = [
    "mode", "deal", "firm",
    "date_curated_initial", "date_curated_current",
    "at_semantic_version", "curated_by", "augmented_with",
]

TARGET_FILE: Path = Path(DEFAULT_FILE)

app = FastAPI(title="Sources Curation UI")


# --------------------------------------------------------------------------- #
# Parsing                                                                      #
# --------------------------------------------------------------------------- #

def _frontmatter_text(content: str) -> str:
    """Return the raw YAML frontmatter block (between the first two '---')."""
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    return parts[1] if len(parts) >= 3 else ""


def _extract_verdicts(frontmatter_text: str) -> Dict[str, str]:
    """
    Map url -> verdict by scanning the raw frontmatter. Verdicts live as YAML
    COMMENTS (`# verdict: ...`), which yaml.safe_load discards — but they flag
    the 403/timeout/error sources the analyst most wants to prune, so we keep
    them. Strips the trailing "(informational…)" boilerplate.
    """
    verdicts: Dict[str, str] = {}
    # Split on each "- url:" entry so a verdict binds to the url above it.
    entries = re.split(r"(?m)^\s*-\s*url:\s*", frontmatter_text)
    for chunk in entries[1:]:
        url = chunk.splitlines()[0].strip()
        m = re.search(r"#\s*verdict:\s*(.+)", chunk)
        if not m:
            continue
        verdict = m.group(1)
        verdict = re.split(r"\s*\(informational", verdict)[0].strip()
        if url:
            verdicts[url] = verdict
    return verdicts


def _verdict_is_error(verdict: str) -> bool:
    v = (verdict or "").lower()
    return bool(v) and (
        "error" in v or "timed out" in v or "timeout" in v
        or "403" in v or "404" in v or "410" in v or "5" == v[:1]
        or "image/" in v
    )


def inputs_sources_path() -> Path:
    """The canonical inputs/Sources.md for this deal (the Save target)."""
    p = TARGET_FILE
    if p.name == "Sources.md" and p.parent.name == "inputs":
        return p
    # aggregated path shape: <deal>/outputs/<ver>/Sources-aggregated.md
    return p.parents[2] / "inputs" / "Sources.md"


def working_file() -> Path:
    """The file the UI READS. Prefer a saved inputs/Sources.md (work-in-progress)
    over the original aggregated worksheet, so reloads show saved progress
    instead of resetting to the pristine pipeline output."""
    try:
        cand = inputs_sources_path()
        if cand.exists():
            return cand
    except Exception:
        pass
    return TARGET_FILE


def load_doc() -> Dict[str, Any]:
    """Parse the working file into {file, meta, sources[], body}."""
    src = working_file()
    content = src.read_text()
    meta, body = parse_frontmatter(content)
    verdicts = _extract_verdicts(_frontmatter_text(content))

    sources: List[Dict[str, Any]] = []
    for raw in (meta.get("sources") or []):
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url", "")).strip()
        sections = raw.get("sections") or []
        if isinstance(sections, str):
            sections = [sections]
        try:
            rank = int(raw.get("rank", 1))
        except (TypeError, ValueError):
            rank = 1
        verdict = str(raw.get("verdict") or verdicts.get(url, ""))
        sources.append({
            "url": url,
            "title": str(raw.get("title", "") or ""),
            "publisher": str(raw.get("publisher", "") or ""),
            "published_date": str(raw.get("published_date", "") or ""),
            "sections": [str(s) for s in sections],
            "rank": rank,
            "sensitivity": str(raw.get("sensitivity", "citable_externally")),
            "verdict": verdict,
            "verdict_error": _verdict_is_error(verdict),
            "note": str(raw.get("note", "") or ""),
        })

    meta_clean = {k: _jsonable(v) for k, v in meta.items() if k != "sources"}
    return {
        "file": str(src),
        "is_working_copy": src != TARGET_FILE,
        "meta": meta_clean,
        "sources": sources,
        "body": body,
    }


def _jsonable(v: Any) -> Any:
    """YAML parses bare dates into date/datetime objects, which JSON can't
    serialize. Coerce them (and nested structures) to ISO strings."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


# --------------------------------------------------------------------------- #
# Serialization                                                                #
# --------------------------------------------------------------------------- #

def _clean_source(s: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in FIELD_ORDER:
        val = s.get(key)
        if key == "url":
            out["url"] = str(val or "").strip()
        elif key == "sections":
            secs = val or []
            if isinstance(secs, str):
                secs = [x.strip() for x in secs.split(",") if x.strip()]
            out["sections"] = [str(x).strip() for x in secs if str(x).strip()]
        elif key == "rank":
            try:
                out["rank"] = int(val)
            except (TypeError, ValueError):
                out["rank"] = 1
        else:
            sval = str(val or "").strip()
            if sval:
                out[key] = sval
    return out


def serialize_doc(meta: Dict[str, Any], sources: List[Dict[str, Any]],
                  body: str, mode: Optional[str]) -> str:
    fm: Dict[str, Any] = {}
    for key in META_ORDER:
        if key in meta and meta[key] is not None:
            fm[key] = meta[key]
    if mode:
        fm["mode"] = mode
    fm.setdefault("mode", meta.get("mode", "aggregated"))
    fm["date_curated_current"] = datetime.now().date().isoformat()
    fm["sources"] = [_clean_source(s) for s in sources if str(s.get("url", "")).strip()]

    # sort_keys=False preserves our insertion order (top-level + per-source).
    yaml_block = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False, width=4096
    )
    body = body if body.endswith("\n") else body + "\n"
    return f"---\n{yaml_block}---\n\n{body}"


# --------------------------------------------------------------------------- #
# API                                                                          #
# --------------------------------------------------------------------------- #

@app.get("/api/sources")
def api_sources() -> JSONResponse:
    try:
        return JSONResponse(load_doc())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/save")
def api_save(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    meta = payload.get("meta") or {}
    sources = payload.get("sources") or []
    body = payload.get("body") or ""
    mode = payload.get("mode")
    target_kind = payload.get("target", "inputs")  # "inputs" | "inplace"

    if target_kind == "inplace":
        target = TARGET_FILE
    else:
        target = inputs_sources_path()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        backup_path = None
        if target.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = target.with_name(target.name + f".bak-{stamp}")
            shutil.copy2(target, backup_path)
        text = serialize_doc(meta, sources, body, mode)
        target.write_text(text)
        return JSONResponse({
            "ok": True,
            "written": str(target),
            "backup": str(backup_path) if backup_path else None,
            "count": len([s for s in sources if str(s.get("url", "")).strip()]),
            "mode": mode or meta.get("mode", "aggregated"),
        })
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.post("/api/search")
def api_search(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    query = (payload.get("query") or "").strip()
    if not query:
        return JSONResponse({"ok": False, "reason": "empty query"})
    base = (os.environ.get("SEARXNG_URL") or "").rstrip("/")
    if not base:
        return JSONResponse({
            "ok": False,
            "reason": "SEARXNG_URL not set. export SEARXNG_URL=http://localhost:8080 "
                      "(instance must have JSON format enabled) and restart.",
        })
    try:
        resp = httpx.get(
            f"{base}/search",
            params={"q": query, "format": "json"},
            timeout=20,
            headers={"User-Agent": "MemoPop-Curate/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        return JSONResponse({
            "ok": False,
            "reason": f"SearXNG unreachable at {base}: {e}",
        })
    results = []
    for r in (data.get("results") or [])[:25]:
        results.append({
            "title": r.get("title") or "",
            "url": r.get("url") or "",
            "content": (r.get("content") or "")[:300],
            "engine": r.get("engine") or ", ".join(r.get("engines", []) or []),
            "published_date": (r.get("publishedDate") or "")[:10],
        })
    return JSONResponse({"ok": True, "query": query, "results": results})


@app.post("/api/fetch")
def api_fetch(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    url = (payload.get("url") or "").strip()
    if not url:
        return JSONResponse({"ok": False, "reason": "no url"})
    try:
        result = fetch_url_markdown(url, timeout=25)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "reason": str(e)})
    if not result:
        return JSONResponse({"ok": False, "reason": "fetch failed (dead / blocked / non-HTML)"})
    md = result.get("markdown") or ""
    return JSONResponse({
        "ok": True,
        "title": result.get("title") or url,
        "via": result.get("via"),
        "length": len(md),
        "markdown": md[:8000],
        "truncated": len(md) > 8000,
    })


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


# --------------------------------------------------------------------------- #
# UI                                                                           #
# --------------------------------------------------------------------------- #

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Sources Curation</title>
<style>
  :root { --bg:#0f1115; --panel:#181b22; --panel2:#1f232c; --line:#2c313c;
          --txt:#e6e8ec; --dim:#9aa3b2; --accent:#6ea8fe; --danger:#ff6b6b;
          --ok:#51cf66; --warn:#ffd43b; }
  * { box-sizing: border-box; }
  body { margin:0; font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--txt); height:100vh; display:flex; flex-direction:column; }
  header { display:flex; align-items:center; gap:.75rem; padding:.5rem .9rem;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header .title { font-weight:600; }
  header .file { color:var(--dim); font-size:12px; }
  header .spacer { flex:1; }
  button { font:inherit; background:var(--panel2); color:var(--txt);
           border:1px solid var(--line); border-radius:6px; padding:.35rem .7rem; cursor:pointer; }
  button:hover { border-color:var(--accent); }
  button.primary { background:var(--accent); color:#08111f; border-color:var(--accent); font-weight:600; }
  button.danger { color:var(--danger); }
  button.small { padding:.15rem .45rem; font-size:12px; }
  select, input, textarea { font:inherit; background:var(--panel2); color:var(--txt);
           border:1px solid var(--line); border-radius:6px; padding:.35rem .5rem; width:100%; }
  textarea { resize:vertical; min-height:3em; }
  main { flex:1; display:grid; grid-template-columns: var(--listw, 360px) 6px 1fr; min-height:0; }
  .splitter { background:var(--line); cursor:col-resize; }
  .splitter:hover, .splitter.dragging { background:var(--accent); }
  .col { min-height:0; display:flex; flex-direction:column; }
  .listcol { border-right:1px solid var(--line); }
  .list { overflow:auto; flex:1; }
  .row { padding:.5rem .7rem; border-bottom:1px solid var(--line); cursor:pointer; display:flex; gap:.5rem; align-items:flex-start; }
  .row:hover { background:var(--panel); }
  .row.active { background:var(--panel2); border-left:3px solid var(--accent); padding-left:calc(.7rem - 3px); }
  .row .idx { color:var(--dim); font-size:12px; min-width:1.6em; text-align:right; }
  .row .rtitle { flex:1; overflow:hidden; text-overflow:ellipsis; }
  .row .rpub { color:var(--dim); font-size:12px; }
  .dot { width:8px; height:8px; border-radius:50%; margin-top:.4em; flex:none; background:var(--ok); }
  .dot.err { background:var(--danger); }
  .right { overflow:auto; flex:1; padding:1rem; display:flex; flex-direction:column; gap:1rem; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:1rem; }
  .card h3 { margin:0 0 .6rem; font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--dim); }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; }
  .field { display:flex; flex-direction:column; gap:.2rem; margin-bottom:.6rem; }
  .field label { font-size:12px; color:var(--dim); }
  .verdict { font-size:12px; padding:.15rem .45rem; border-radius:5px; background:var(--panel2); }
  .verdict.err { color:var(--danger); border:1px solid var(--danger); }
  .res { border:1px solid var(--line); border-radius:6px; padding:.5rem .6rem; margin-bottom:.5rem; }
  .res a { color:var(--accent); text-decoration:none; word-break:break-all; }
  .res .meta { color:var(--dim); font-size:12px; }
  pre.preview { white-space:pre-wrap; word-break:break-word; max-height:340px; overflow:auto;
                background:var(--panel2); border:1px solid var(--line); border-radius:6px; padding:.6rem; font-size:12px; }
  .toolbar { display:flex; gap:.4rem; flex-wrap:wrap; align-items:center; }
  .muted { color:var(--dim); }
  .pill { font-size:12px; background:var(--panel2); border:1px solid var(--line); border-radius:999px; padding:.1rem .5rem; }
  a.urllink { color:var(--accent); word-break:break-all; text-decoration:none; flex:1;
              padding:.35rem .5rem; border:1px solid var(--line); border-radius:6px; background:var(--panel2); }
  a.urllink:hover { text-decoration:underline; border-color:var(--accent); }
  a.urllink.disabled { color:var(--dim); pointer-events:none; }
  .row { align-items:center; }
  .row .rtitle { flex:1; min-width:0; }
  .row .rmeta { color:var(--dim); font-size:11px; margin-top:2px; display:flex; gap:.5rem; flex-wrap:wrap; }
  .row .rmeta .rk { color:var(--accent); }
  .row.dragover { box-shadow: inset 0 2px 0 0 var(--accent); }
  .row.dragging { opacity:.4; }
  .row .rowbtns { display:flex; flex-direction:column; gap:2px; opacity:.45; flex:none; }
  .row:hover .rowbtns { opacity:1; }
  .row .rowbtns button { padding:0 .35rem; font-size:10px; line-height:1.35; }
  .row .grip { color:var(--dim); cursor:grab; flex:none; font-size:13px; }
  .filterbar input { font-size:13px; }
</style>
</head>
<body>
<header>
  <span class="title">Sources Curation</span>
  <span class="file" id="fileName"></span>
  <span class="pill" id="count"></span>
  <span class="spacer"></span>
  <label class="muted" style="font-size:12px">mode</label>
  <select id="mode" style="width:auto"><option value="aggregated">aggregated</option><option value="codified">codified</option></select>
  <label class="muted" style="font-size:12px">save to</label>
  <select id="target" style="width:auto"><option value="inputs">inputs/Sources.md</option><option value="inplace">in place</option></select>
  <button id="reload">Reload</button>
  <button id="save" class="primary">Save</button>
</header>
<main>
  <div class="col listcol">
    <div class="toolbar" style="padding:.5rem .7rem; border-bottom:1px solid var(--line)">
      <button class="small" id="addBlank">+ blank source</button>
      <span class="muted" id="saveStatus" style="font-size:12px"></span>
    </div>
    <div class="filterbar" style="padding:.4rem .7rem; border-bottom:1px solid var(--line)">
      <input id="listFilter" placeholder="filter the list… (title, publisher, url, section, note) — check coverage" />
      <div class="muted" id="filterCount" style="font-size:11px; margin-top:.25rem"></div>
    </div>
    <div class="list" id="list"></div>
  </div>
  <div class="splitter" id="splitter" title="Drag to resize"></div>
  <div class="col right" id="right"></div>
</main>

<script>
let DOC = { meta:{}, sources:[], body:"" };
let focusIdx = 0;
let listFilter = "";
let dragFrom = null;

const $ = (s, r=document) => r.querySelector(s);
const el = (tag, props={}, kids=[]) => {
  const n = document.createElement(tag);
  for (const [k,v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const kid of [].concat(kids)) n.append(kid);
  return n;
};

async function load() {
  const r = await fetch("/api/sources"); const d = await r.json();
  if (d.ok === false) { alert("Load error: " + d.error); return; }
  DOC = d; focusIdx = Math.min(focusIdx, DOC.sources.length - 1);
  const base = d.file.split('/').slice(-3).join('/');
  $("#fileName").textContent = base + (d.is_working_copy ? "  ·  working copy (your saved progress)" : "  ·  aggregated worksheet (pristine)");
  $("#mode").value = (d.meta.mode || "aggregated");
  renderList(); renderRight();
}

function rowMatches(s, q){
  if (!q) return true;
  const hay = [s.title, s.publisher, s.url, (s.sections||[]).join(" "), s.note, s.verdict]
    .filter(Boolean).join(" ").toLowerCase();
  return hay.includes(q);
}

function renderList() {
  $("#count").textContent = DOC.sources.length + " sources";
  const list = $("#list"); list.innerHTML = "";
  const q = listFilter.trim().toLowerCase();
  let shown = 0;
  DOC.sources.forEach((s, i) => {
    if (!rowMatches(s, q)) return;
    shown++;
    const dot = el("span", { class: "dot" + (s.verdict_error ? " err" : "") });

    const meta = [];
    if (s.publisher) meta.push(el("span", {}, s.publisher));
    if (s.published_date) meta.push(el("span", {}, s.published_date));
    if ((s.sections||[]).length) meta.push(el("span", {}, (s.sections||[]).join(", ")));
    meta.push(el("span", { class:"rk" }, "rank " + (s.rank ?? 1)));
    if (s.verdict_error) meta.push(el("span", { style:"color:var(--danger)" }, s.verdict));
    const title = el("div", { class:"rtitle" }, [
      el("div", {}, s.title || s.url || "(no title)"),
      el("div", { class:"rmeta" }, meta),
    ]);

    const up = el("button", { class:"small", title:"move up" }, "▲");
    up.addEventListener("click", e => { e.stopPropagation(); moveSource(i, i-1); });
    const down = el("button", { class:"small", title:"move down" }, "▼");
    down.addEventListener("click", e => { e.stopPropagation(); moveSource(i, i+1); });
    const btns = el("div", { class:"rowbtns" }, [ up, down ]);
    const grip = el("span", { class:"grip", title:"drag to reorder" }, "⠿");

    const row = el("div", { class:"row" + (i===focusIdx ? " active":""), draggable:"true",
        onclick: () => { focusIdx=i; renderList(); renderRight(); } },
      [ el("span", { class:"idx" }, String(i+1)), dot, title, grip, btns ]);

    row.addEventListener("dragstart", e => { dragFrom = i; row.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
    row.addEventListener("dragend",   () => { row.classList.remove("dragging"); });
    row.addEventListener("dragover",  e => { e.preventDefault(); row.classList.add("dragover"); });
    row.addEventListener("dragleave", () => row.classList.remove("dragover"));
    row.addEventListener("drop",      e => { e.preventDefault(); row.classList.remove("dragover");
      if (dragFrom !== null && dragFrom !== i) moveSource(dragFrom, i); dragFrom = null; });

    list.append(row);
  });
  $("#filterCount").textContent = q ? `showing ${shown} of ${DOC.sources.length}` : "";
}

function moveSource(from, to){
  if (to < 0 || to >= DOC.sources.length || from === to) return;
  const focused = DOC.sources[focusIdx];
  const [item] = DOC.sources.splice(from, 1);
  DOC.sources.splice(to, 0, item);
  focusIdx = DOC.sources.indexOf(focused);   // keep highlight on the same source
  renderList();
  $("#saveStatus").textContent = "reordered — unsaved";
}

function setField(key, val) { DOC.sources[focusIdx][key] = val; }

function renderRight() {
  const right = $("#right"); right.innerHTML = "";
  if (!DOC.sources.length) { right.append(el("div", { class:"muted" }, "No sources. Add one or run a search.")); return; }
  const s = DOC.sources[focusIdx];

  // editor
  const ed = el("div", { class:"card" });
  ed.append(el("h3", {}, `Source ${focusIdx+1} of ${DOC.sources.length}`));
  const nav = el("div", { class:"toolbar", html:"" });
  nav.append(
    el("button", { class:"small", onclick: () => { if(focusIdx>0){focusIdx--;renderList();renderRight();} } }, "‹ prev"),
    el("button", { class:"small", onclick: () => { if(focusIdx<DOC.sources.length-1){focusIdx++;renderList();renderRight();} } }, "next ›"),
    el("button", { class:"small", onclick: moveUp }, "↑ up"),
    el("button", { class:"small", onclick: moveDown }, "↓ down"),
    el("button", { class:"small danger", onclick: del }, "🗑 delete"),
  );
  if (s.verdict) nav.append(el("span", { class:"verdict" + (s.verdict_error?" err":"") }, s.verdict));
  ed.append(nav);

  ed.append(field("title", "Title", s.title, "input"));
  const g = el("div", { class:"grid2" });
  g.append(field("publisher","Publisher",s.publisher,"input"), field("published_date","Published date",s.published_date,"input"));
  ed.append(g);
  ed.append(urlField(s));
  const g2 = el("div", { class:"grid2" });
  g2.append(field("sections","Sections (comma-sep)",(s.sections||[]).join(", "),"input","sections"),
            field("rank","Rank",s.rank,"input","rank"));
  ed.append(g2);
  const g3 = el("div", { class:"grid2" });
  const sens = el("select", { onchange: e => setField("sensitivity", e.target.value) });
  ["citable_externally","internal_only"].forEach(o => sens.append(el("option", { value:o, ...(s.sensitivity===o?{selected:""}:{}) }, o)));
  g3.append(wrap("Sensitivity", sens), field("verdict","Verdict",s.verdict,"input"));
  ed.append(g3);
  ed.append(field("note","Note",s.note,"textarea"));

  const fetchBtn = el("button", { class:"small", onclick: () => doFetch(s.url) }, "Fetch & preview content (Jina)");
  ed.append(fetchBtn, el("div", { id:"previewBox" }));
  right.append(ed);

  // search
  const sc = el("div", { class:"card" });
  sc.append(el("h3", {}, "New search → SearXNG"));
  const q = el("input", { placeholder:"new search term…", id:"q",
    onkeydown: e => { if(e.key==="Enter") doSearch(); } });
  const bar = el("div", { class:"toolbar" });
  bar.append(q, el("button", { onclick: doSearch }, "Search"));
  sc.append(bar, el("div", { id:"results", style:"margin-top:.6rem" }));
  right.append(sc);

  // add-a-link card — paste any URL you find
  const lc = el("div", { class:"card" });
  lc.append(el("h3", {}, "Add a link by URL"));
  const lq = el("input", { placeholder:"paste a URL…  (title auto-fetched)", id:"addurl",
    onkeydown: e => { if(e.key==="Enter"){ const v=e.target.value; e.target.value=""; addLink(v); } } });
  const lbar = el("div", { class:"toolbar" });
  lbar.append(lq, el("button", { onclick: () => { const v=$("#addurl").value; $("#addurl").value=""; addLink(v); } }, "Add link"));
  lc.append(lbar, el("div", { class:"muted", style:"font-size:12px; margin-top:.4rem" },
    "Appends to the list, inherits this source's section tags (editable), and fetches the title."));
  right.append(lc);
}

async function addLink(url){
  url = (url || "").trim();
  if (!url) return;
  if (!/^[a-z]+:\/\//i.test(url)) url = "https://" + url;   // bare domain → https://
  const idx = DOC.sources.push({
    url, title:"", publisher:"", published_date:"",
    sections:(DOC.sources[focusIdx]?.sections || []).slice(), rank:1,
    sensitivity:"citable_externally", verdict:"", note:"Analyst-added link",
  }) - 1;
  renderList();
  $("#saveStatus").textContent = `added link → now ${DOC.sources.length} (unsaved) · fetching title…`;
  try {
    const r = await fetch("/api/fetch", { method:"POST", headers:{ "content-type":"application/json" }, body: JSON.stringify({ url }) });
    const d = await r.json();
    if (d.ok && d.title) {
      DOC.sources[idx].title = d.title;
      if (focusIdx === idx) renderRight();
      renderList();
      $("#saveStatus").textContent = `added "${d.title.slice(0,40)}" → ${DOC.sources.length} (unsaved)`;
    } else {
      $("#saveStatus").textContent = `added link (title not fetched) → ${DOC.sources.length} (unsaved)`;
    }
  } catch (e) { /* leave title blank; user can Fetch & preview later */ }
}

function wrap(label, node) { return el("div", { class:"field" }, [ el("label", {}, label), node ]); }

function urlField(s){
  // The URL renders as a CLICKABLE LINK by default (opens in a new tab) — no
  // copy-paste. A small "✎ edit" toggle swaps it for an input when you need to
  // change it. Defaults back to link view each time you focus a source.
  const box = el("div", { class:"field" });
  box.append(el("label", {}, "URL"));
  const slot = el("div", {});
  let editing = false;
  function render(){
    slot.innerHTML = "";
    const u = (s.url || "").trim();
    if (editing) {
      const input = el("input", { value: s.url || "", style:"flex:1",
        oninput: e => { s.url = e.target.value; } });
      const done = el("button", { class:"small", onclick: () => { editing = false; render(); } }, "done");
      slot.append(el("div", { style:"display:flex; gap:.4rem; align-items:stretch" }, [ input, done ]));
    } else {
      const link = el("a", { class:"urllink", href: u || "#", target:"_blank",
        rel:"noopener noreferrer", title:"Open in a new tab" }, u || "(no url)");
      if (!/^https?:\/\//i.test(u)) link.classList.add("disabled");
      const edit = el("button", { class:"small", onclick: () => { editing = true; render(); } }, "✎ edit");
      slot.append(el("div", { style:"display:flex; gap:.4rem; align-items:center" }, [ link, edit ]));
    }
  }
  render();
  box.append(slot);
  return box;
}
function field(key, label, val, kind, coerce) {
  const node = el(kind === "textarea" ? "textarea" : "input", {
    value: kind === "textarea" ? undefined : (val ?? ""),
    oninput: e => {
      let v = e.target.value;
      if (coerce === "rank") v = parseInt(v||"1",10) || 1;
      if (coerce === "sections") v = v.split(",").map(x=>x.trim()).filter(Boolean);
      setField(key, v);
    }
  });
  if (kind === "textarea") node.value = val ?? "";
  return wrap(label, node);
}

function moveUp(){ if(focusIdx>0){ const a=DOC.sources; [a[focusIdx-1],a[focusIdx]]=[a[focusIdx],a[focusIdx-1]]; focusIdx--; renderList(); renderRight(); } }
function moveDown(){ const a=DOC.sources; if(focusIdx<a.length-1){ [a[focusIdx+1],a[focusIdx]]=[a[focusIdx],a[focusIdx+1]]; focusIdx++; renderList(); renderRight(); } }
function del(){ DOC.sources.splice(focusIdx,1); if(focusIdx>=DOC.sources.length) focusIdx=Math.max(0,DOC.sources.length-1); renderList(); renderRight(); }

$("#addBlank").addEventListener("click", () => {
  DOC.sources.splice(focusIdx+1, 0, { url:"", title:"", publisher:"", published_date:"",
    sections:[], rank:1, sensitivity:"citable_externally", verdict:"", note:"" });
  focusIdx = Math.min(focusIdx+1, DOC.sources.length-1); renderList(); renderRight();
});

async function doFetch(url){
  const box = $("#previewBox"); box.innerHTML = '<div class="muted">Fetching…</div>';
  const r = await fetch("/api/fetch", { method:"POST", headers:{ "content-type":"application/json" }, body: JSON.stringify({ url }) });
  const d = await r.json();
  if (!d.ok) { box.innerHTML = '<div class="muted">'+ (d.reason||"failed") +'</div>'; return; }
  box.innerHTML = "";
  box.append(el("div", { class:"muted", style:"margin:.4rem 0" }, `via ${d.via} · ${d.length} chars${d.truncated?" (truncated)":""} · title: ${d.title}`));
  box.append(el("pre", { class:"preview" }, d.markdown));
}

async function doSearch(){
  const query = $("#q").value.trim(); const box = $("#results");
  if (!query) return;
  box.innerHTML = '<div class="muted">Searching…</div>';
  const r = await fetch("/api/search", { method:"POST", headers:{ "content-type":"application/json" }, body: JSON.stringify({ query }) });
  const d = await r.json();
  if (!d.ok) { box.innerHTML = '<div class="muted">'+ (d.reason||"search unavailable") +'</div>'; return; }
  box.innerHTML = "";
  if (!d.results.length) { box.append(el("div", { class:"muted" }, "no results")); return; }
  d.results.forEach(res => {
    const card = el("div", { class:"res" });
    const addBtn = el("button", { class:"small", style:"margin-top:.4rem" }, "+ add to sources");
    addBtn.addEventListener("click", () => {
      addFromResult(res);
      addBtn.textContent = "✓ added"; addBtn.disabled = true;
    });
    card.append(
      el("div", {}, res.title || "(untitled)"),
      el("div", {}, el("a", { href: res.url, target:"_blank" }, res.url)),
      el("div", { class:"meta" }, [res.engine, res.published_date].filter(Boolean).join(" · ")),
      res.content ? el("div", { class:"meta" }, res.content) : "",
      addBtn,
    );
    box.append(card);
  });
}

function addFromResult(res){
  // Append to the END of the list, inheriting the section tags of the source
  // you're working through (replacement semantics). Crucially: do NOT move
  // focus and do NOT re-render the right pane — that would wipe the search
  // results and pull you out of the source you're on. Only the left list
  // refreshes, so you can keep adding more results from the same search.
  const q = ($("#q") && $("#q").value.trim()) || "";
  DOC.sources.push({
    url: res.url, title: res.title || "", publisher: "", published_date: res.published_date || "",
    sections: (DOC.sources[focusIdx]?.sections || []).slice(), rank: 1,
    sensitivity: "citable_externally", verdict: "", note: "Added via SearXNG: " + q,
  });
  renderList();
  const label = (res.title || res.url || "").slice(0, 44);
  $("#saveStatus").textContent = `added "${label}" → now ${DOC.sources.length} sources (unsaved)`;
}

async function save(){
  const st = $("#saveStatus"); st.textContent = "saving…";
  const r = await fetch("/api/save", { method:"POST", headers:{ "content-type":"application/json" },
    body: JSON.stringify({ meta: DOC.meta, sources: DOC.sources, body: DOC.body,
      mode: $("#mode").value, target: $("#target").value }) });
  const d = await r.json();
  if (!d.ok) { st.textContent = "error: " + d.error; return; }
  st.textContent = `saved ${d.count} → ${d.written}` + (d.backup ? " (backup made)" : "");
}

$("#reload").addEventListener("click", load);
$("#save").addEventListener("click", save);

// List filter (coverage check).
$("#listFilter").addEventListener("input", e => { listFilter = e.target.value; renderList(); });

// Draggable column splitter, width persisted across reloads.
(function setupSplitter(){
  const sp = $("#splitter");
  const saved = localStorage.getItem("curate:listw");
  if (saved) document.documentElement.style.setProperty("--listw", saved);
  let dragging = false;
  sp.addEventListener("mousedown", e => { dragging = true; sp.classList.add("dragging"); e.preventDefault(); });
  window.addEventListener("mousemove", e => {
    if (!dragging) return;
    const w = Math.max(260, Math.min(window.innerWidth - 360, e.clientX));
    document.documentElement.style.setProperty("--listw", w + "px");
  });
  window.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false; sp.classList.remove("dragging");
    localStorage.setItem("curate:listw",
      getComputedStyle(document.documentElement).getPropertyValue("--listw").trim() || "360px");
  });
})();

load();
</script>
</body>
</html>
"""


def main() -> None:
    global TARGET_FILE
    ap = argparse.ArgumentParser(description="Local Sources.md curation UI")
    ap.add_argument("--file", default=DEFAULT_FILE, help="path to the Sources(-aggregated).md to curate")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()

    TARGET_FILE = Path(args.file).resolve()
    if not TARGET_FILE.exists():
        sys.exit(f"File not found: {TARGET_FILE}")

    searx = os.environ.get("SEARXNG_URL")
    print(f"Curating: {TARGET_FILE}")
    print(f"SearXNG:  {searx or '(not set — search disabled; export SEARXNG_URL to enable)'}")
    print(f"Open:     http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
