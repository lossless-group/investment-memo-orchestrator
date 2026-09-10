#!/usr/bin/env python3
"""
Generate docs/PIPELINE-REFERENCE.md from the code itself.

The reference this replaces was hand-maintained in four places (README's two
tables, docs/COMMANDS_CHEAT_SHEET.md, WARP.md) and all four drifted: the README
agent table documented 27 of the graph's 35 nodes and omitted `aggregate_sources`,
the curation halt that codified mode turns on. A table nobody regenerates is a
table that lies, so this reads the AST instead:

  * `src/workflow.py`  → nodes, edges, entry point, conditional branches, and the
                         module each node's agent function lives in
  * agent modules      → whether each one routes through `src/llm_provider.py` or
                         constructs an Anthropic client directly (the live
                         inventory for the CLI-first-provider issue)
  * `src/main.py`      → every flag on the main entry point
  * `cli/`, `src/cli/` → every standalone tool, its docstring, and its flags

Everything a machine cannot infer — what stage a node belongs to for `--from`,
which AGENTS.md principles it operates under, what it writes to disk — lives in
`docs/pipeline-reference.overlay.yaml` and is merged in. A node with no overlay
entry is reported, and `tests/test_pipeline_reference.py` fails on it, so adding
a node to the graph forces a decision about how it is documented.

Usage:
    .venv/bin/python scripts/gen_pipeline_reference.py            # write the doc
    .venv/bin/python scripts/gen_pipeline_reference.py --check    # exit 1 on drift
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / "src" / "workflow.py"
MAIN = REPO / "src" / "main.py"
OVERLAY = REPO / "docs" / "pipeline-reference.overlay.yaml"
OUTPUT = REPO / "docs" / "PIPELINE-REFERENCE.md"

CLI_DIRS = [REPO / "cli", REPO / "cli" / "utils", REPO / "src" / "cli"]


# ---------------------------------------------------------------- graph parsing


@dataclass
class Node:
    name: str
    func: str
    comment: str = ""
    module: str = ""
    order: int = 0
    routing: str = ""
    routing_detail: str = ""
    overlay: dict = field(default_factory=dict)


def _trailing_comment(lines: list[str], lineno: int) -> str:
    """AST drops comments; the node-order commentary in workflow.py lives in them."""
    raw = lines[lineno - 1]
    # Ignore a '#' inside a string literal — every add_node line here is simple,
    # but a naive split would still corrupt one that is not.
    in_str = None
    for i, ch in enumerate(raw):
        if in_str:
            if ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "#":
            return raw[i + 1 :].strip()
    return ""


def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _rel_module_path(module: str, level: int) -> str:
    """`.agents.deck_analyst` (level 1, inside src/) -> src/agents/deck_analyst.py"""
    if level == 0:
        return ""
    base = REPO / "src"
    for _ in range(level - 1):
        base = base.parent
    target = base.joinpath(*module.split(".")) if module else base
    if target.with_suffix(".py").exists():
        return str(target.with_suffix(".py").relative_to(REPO))
    if target.is_dir():
        return str(target.relative_to(REPO)) + "/"
    return ""


def parse_graph() -> tuple[list[Node], str, dict, list[tuple[str, str, dict]]]:
    src = WORKFLOW.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)

    # imported name -> file it came from
    origins: dict[str, str] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom):
            path = _rel_module_path(stmt.module or "", stmt.level)
            for alias in stmt.names:
                origins[alias.asname or alias.name] = path
        elif isinstance(stmt, ast.FunctionDef):
            origins[stmt.name] = "src/workflow.py"

    build = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_workflow"),
        None,
    )
    if build is None:
        raise SystemExit("build_workflow() not found in src/workflow.py")

    # `research_fn = research_agent_enhanced if ... else research_agent`
    aliases: dict[str, list[str]] = {}
    for stmt in ast.walk(build):
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
            tgt = stmt.targets[0]
            if not isinstance(tgt, ast.Name):
                continue
            val = stmt.value
            if isinstance(val, ast.IfExp):
                names = [n.id for n in (val.body, val.orelse) if isinstance(n, ast.Name)]
                if names:
                    aliases[tgt.id] = names
            elif isinstance(val, ast.Name):
                aliases[tgt.id] = [val.id]

    nodes: list[Node] = []
    edges: dict[str, str] = {}
    conditionals: list[tuple[str, str, dict]] = []
    entry = ""

    for call in ast.walk(build):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        method = call.func.attr
        args = call.args

        if method == "add_node" and len(args) >= 2:
            name = _const(args[0])
            func = args[1].id if isinstance(args[1], ast.Name) else ast.unparse(args[1])
            if name:
                nodes.append(
                    Node(name=name, func=func, comment=_trailing_comment(lines, call.lineno))
                )
        elif method == "set_entry_point" and args:
            entry = _const(args[0]) or entry
        elif method == "add_edge" and len(args) >= 2:
            a = _const(args[0])
            b = _const(args[1]) or (args[1].id if isinstance(args[1], ast.Name) else "")
            if a:
                edges[a] = b
        elif method == "add_conditional_edges" and len(args) >= 3:
            source = _const(args[0])
            router = args[1].id if isinstance(args[1], ast.Name) else ast.unparse(args[1])
            mapping = {}
            if isinstance(args[2], ast.Dict):
                for k, v in zip(args[2].keys, args[2].values):
                    kk, vv = _const(k), _const(v)
                    if kk and vv:
                        mapping[kk] = vv
            if source:
                conditionals.append((source, router, mapping))

    # resolve each node's defining file, expanding the conditional alias
    for node in nodes:
        funcs = aliases.get(node.func, [node.func])
        paths = sorted({origins.get(f, "") for f in funcs if origins.get(f)})
        node.module = " / ".join(paths)
        if len(funcs) > 1:
            node.func = " | ".join(funcs)

    by_name = {n.name: n for n in nodes}
    order = _linearize(entry, edges, conditionals, set(by_name))
    for i, name in enumerate(order, start=1):
        by_name[name].order = i

    return nodes, entry, edges, conditionals


def _linearize(entry: str, edges: dict, conditionals: list, known: set) -> list[str]:
    """Walk the graph from the entry point so node numbering matches execution."""
    cond_targets = {src: list(m.values()) for src, _, m in conditionals}
    order: list[str] = []
    seen: set[str] = set()
    queue = [entry] if entry else []
    while queue:
        current = queue.pop(0)
        if current in seen or current not in known:
            continue
        seen.add(current)
        order.append(current)
        nxt = edges.get(current)
        if nxt and nxt in known:
            queue.append(nxt)
        queue.extend(t for t in cond_targets.get(current, []) if t in known)
    # anything unreachable still gets documented, at the end
    order.extend(sorted(n for n in known if n not in seen))
    return order


# ------------------------------------------------------- llm routing detection

# An Anthropic client constructed outside src/llm_provider.py cannot use the
# Claude Code seat and bills the metered API unconditionally.
#
# Matched on the AST, not on the source text. A regex over raw bytes counts the
# word "Anthropic()" inside a comment explaining that the module no longer calls
# it — which is exactly what happened the first time deck_analyst.py was fixed,
# and it reported the file as still bypassing.
_BYPASS_CALLS = {
    "ChatAnthropic": "ChatAnthropic()",
    "Anthropic": "Anthropic()",
}

# Non-Anthropic model and retrieval clients. Without these a Perplexity-only
# agent reads as "no LLM", which is wrong in the way that matters — it has a
# metered dependency, just not one llm_provider can route.
_OTHER_CALLS = {
    "OpenAI": "Perplexity/OpenAI",
    "TavilyClient": "Tavily",
    "FirecrawlApp": "Firecrawl",
}


def _called_name(node: ast.Call) -> str | None:
    """`Anthropic(...)` -> 'Anthropic'; `anthropic.Anthropic(...)` -> 'Anthropic'."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _py_files(path_str: str) -> list[Path]:
    if not path_str:
        return []
    p = REPO / path_str
    if path_str.endswith("/"):
        return sorted(f for f in p.rglob("*.py") if "__pycache__" not in f.parts)
    return [p] if p.exists() else []


def scan_file(path: Path) -> dict:
    """Classify one module's model access. The provider layer itself is exempt."""
    result = {"bypass": {}, "routed": False, "others": []}
    if path.name == "llm_provider.py":
        return result
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return result

    others: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _called_name(node)
            if name in _BYPASS_CALLS:
                label = _BYPASS_CALLS[name]
                result["bypass"][label] = result["bypass"].get(label, 0) + 1
            elif name in _OTHER_CALLS:
                others.add(_OTHER_CALLS[name])
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[-1] == "llm_provider":
                result["routed"] = True
        elif isinstance(node, ast.Import):
            if any(a.name.split(".")[-1] == "llm_provider" for a in node.names):
                result["routed"] = True

    result["others"] = sorted(others)
    return result


def scan_routing(module: str) -> tuple[str, str]:
    """Does this node's code route through llm_provider, or bill the API directly?

    A node backed by a package (`src/agents/dataroom/`) is scanned recursively,
    so one bypassing extractor marks the whole node. Modules a node calls but
    does not contain are NOT counted here — see the repo-wide inventory for that.
    """
    files = [f for part in module.split(" / ") for f in _py_files(part.strip())]
    if not files:
        return "—", ""
    bypass: dict[str, int] = {}
    routed = False
    others: set[str] = set()
    for f in files:
        r = scan_file(f)
        routed = routed or r["routed"]
        others.update(r["others"])
        for label, n in r["bypass"].items():
            bypass[label] = bypass.get(label, 0) + n

    total = sum(bypass.values())
    detail_bits = [f"{n}× `{lbl}`" for lbl, n in sorted(bypass.items())]
    if others:
        detail_bits.append("via " + ", ".join(sorted(others)))
    detail = ", ".join(detail_bits)

    if total and routed:
        label = "mixed"
    elif total:
        label = "bypasses"
    elif routed:
        label = "routed"
    elif others:
        label = "other provider"
    else:
        label = "no model call"
    return label, detail


def repo_inventory() -> tuple[list[tuple[str, int, str]], list[str]]:
    """Every module under src/ that builds an Anthropic client, and every one
    that routes. This is the list the CLI-first-provider refactor works through;
    unlike the per-node column it catches modules a node calls rather than owns.
    """
    bypassing: list[tuple[str, int, str]] = []
    routing: list[str] = []
    for f in sorted((REPO / "src").rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        r = scan_file(f)
        rel = str(f.relative_to(REPO))
        total = sum(r["bypass"].values())
        if total:
            detail = ", ".join(f"{n}× `{lbl}`" for lbl, n in sorted(r["bypass"].items()))
            bypassing.append((rel, total, detail))
        elif r["routed"]:
            routing.append(rel)
    return bypassing, routing


# --------------------------------------------------------------- argparse scan


def parse_argparse(path: Path) -> list[dict]:
    """Pull flags out of a script's add_argument() calls without importing it."""
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return []
    out = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "add_argument"):
            continue
        names = [c for c in (_const(a) for a in call.args) if c]
        entry = {"names": names, "help": "", "choices": None, "default": None, "action": None}
        for kw in call.keywords:
            if kw.arg == "help":
                entry["help"] = _const(kw.value) or (
                    " ".join(
                        v for v in (_const(x) for x in getattr(kw.value, "values", [])) if v
                    )
                    if isinstance(kw.value, ast.JoinedStr)
                    else _flatten_str(kw.value)
                )
            elif kw.arg == "choices" and isinstance(kw.value, (ast.List, ast.Tuple)):
                entry["choices"] = [c for c in (_const(e) for e in kw.value.elts) if c]
            elif kw.arg == "default":
                entry["default"] = _const(kw.value)
            elif kw.arg == "action":
                entry["action"] = _const(kw.value)
        if names:
            out.append(entry)
    return out


def _flatten_str(node) -> str:
    """help= is sometimes a parenthesised implicit concatenation of literals."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _flatten_str(node.left) + _flatten_str(node.right)
    return ""


def docstring_summary(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return ""
    doc = ast.get_docstring(tree) or ""
    for line in doc.splitlines():
        line = line.strip()
        if line and not line.lower().startswith(("usage", "example")):
            return line
    return ""


def shell_summary(path: Path) -> str:
    for line in path.read_text(errors="replace").splitlines()[:15]:
        line = line.strip()
        if line.startswith("#") and not line.startswith("#!"):
            text = line.lstrip("#").strip()
            if text:
                return text
    return ""


# ----------------------------------------------------------------- md emission


def esc(text: str) -> str:
    return text.replace("|", "\\|").strip()


def render(nodes, entry, edges, conditionals, overlay) -> str:
    nodes_sorted = sorted(nodes, key=lambda n: n.order)
    stages = overlay.get("stages", {})
    node_overlay = overlay.get("nodes", {})

    out: list[str] = []
    w = out.append

    w("<!-- GENERATED FILE — DO NOT EDIT BY HAND.")
    w("     Regenerate:  .venv/bin/python scripts/gen_pipeline_reference.py")
    w("     Prose that is not derivable from code belongs in")
    w("     docs/pipeline-reference.overlay.yaml, which this file merges in. -->")
    w("")
    w("# MemoPop Orchestrator — Pipeline Reference")
    w("")
    w(
        "The single current answer to *what agents run, in what order, and what "
        "can I type at a shell*. Generated from `src/workflow.py`, `src/main.py`, "
        "and `cli/` by `scripts/gen_pipeline_reference.py`; "
        "`tests/test_pipeline_reference.py` fails when it drifts from them."
    )
    w("")
    w(
        "This file says what the pipeline **does**. `AGENTS.md` says how each agent "
        "must **behave** — the §1–§12 contract prepended to agent system prompts. "
        "The §-references in the table below point into it."
    )
    w("")

    # ---- graph
    total = len(nodes_sorted)
    w(f"## The graph — {total} nodes")
    w("")
    w(f"Entry point: **`{entry}`**. Every node runs on every invocation; see the")
    w("`--from` discussion below for why that is a problem and what is planned.")
    w("")
    w("| # | Node | Stage | Module | LLM routing | Purpose | AGENTS.md |")
    w("|---|------|-------|--------|-------------|---------|-----------|")
    for n in nodes_sorted:
        ov = node_overlay.get(n.name, {})
        purpose = ov.get("purpose") or n.comment or ""
        stage = ov.get("stage", "—")
        principles = ", ".join(ov.get("agents_md", [])) or "—"
        mod = f"`{n.module}`" if n.module else "—"
        routing = n.routing if n.routing != "—" else "—"
        if n.routing_detail:
            routing = f"{routing} ({n.routing_detail})"
        w(
            f"| {n.order} | `{n.name}` | {stage} | {mod} | {routing} "
            f"| {esc(purpose)} | {principles} |"
        )
    w("")

    # ---- stage map
    if stages:
        w("## Stages")
        w("")
        w(
            "The stage column groups nodes into the resume points the operator "
            "actually thinks in. These are the candidate values for the proposed "
            "`--from <stage>` flag."
        )
        w("")
        w("| Stage | Nodes | Artifacts it owns | What entering here means |")
        w("|-------|------:|-------------------|--------------------------|")
        for key, meta in stages.items():
            members = [
                n.name
                for n in nodes_sorted
                if node_overlay.get(n.name, {}).get("stage") == key
            ]
            w(
                f"| `{key}` | {len(members)} | {esc(meta.get('artifacts', ''))} "
                f"| {esc(meta.get('description', ''))} |"
            )
        w("")
        unstaged = [n.name for n in nodes_sorted if not node_overlay.get(n.name, {}).get("stage")]
        if unstaged:
            w("Nodes assigned to no stage: " + ", ".join(f"`{n}`" for n in unstaged))
            w("")

    # ---- edges
    w("## Execution order")
    w("")
    w("```")
    chain, seen, cur = [], set(), entry
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = edges.get(cur, "")
    w("\n".join(f"{i:>2}. {name}" for i, name in enumerate(chain, 1)))
    for source, router, mapping in conditionals:
        w("")
        head = f"    {source} ──({router})──"
        pad = " " * len(head)
        # A LangGraph branch label is usually the target's own name; printing
        # "finalize → finalize" is noise, so collapse the identity case.
        items = [
            target if label == target else f"{label} → {target}"
            for label, target in mapping.items()
        ]
        for i, item in enumerate(items):
            if len(items) == 1:
                elbow = "──▶ "
            elif i == 0:
                elbow = "┬─▶ "
            elif i == len(items) - 1:
                elbow = "└─▶ "
            else:
                elbow = "├─▶ "
            w((head if i == 0 else pad) + elbow + item)
    terminal = sorted(k for k, v in edges.items() if v == "END")
    if terminal:
        w("")
        w("    " + ", ".join(terminal) + " ──▶ END")
    w("```")
    w("")

    # ---- llm routing summary
    w("## LLM routing inventory")
    w("")
    w(
        "`src/llm_provider.py` tries the local Claude Code seat first and falls "
        "back to the metered API with a warning. Modules that construct "
        "`ChatAnthropic(...)` or `anthropic.Anthropic(...)` themselves bill the "
        "API unconditionally and cannot use the seat — the defect tracked in "
        "`context-v/issues/Route-Every-Claude-Call-Through-The-CLI-First-Provider.md`. "
        "Counts below are live."
    )
    w("")
    buckets: dict[str, list[Node]] = {}
    for n in nodes_sorted:
        buckets.setdefault(n.routing, []).append(n)
    w("| Routing | Nodes | Meaning |")
    w("|---------|-------|---------|")
    meanings = {
        "routed": "goes through `llm_provider` — can use the seat",
        "mixed": "routes in one place, builds a client in another",
        "bypasses": "builds an Anthropic client directly — always metered",
        "other provider": "no Anthropic client; calls Perplexity/Tavily/Firecrawl",
        "no model call": "no model or retrieval client in the node's own modules",
        "—": "no module resolved",
    }
    for key in ("routed", "mixed", "bypasses", "other provider", "no model call", "—"):
        group = buckets.get(key, [])
        if group:
            w(f"| **{key}** | {len(group)} | {meanings[key]} |")
    w("")

    bypassing, routing_files = repo_inventory()
    total_sites = sum(n for _, n, _ in bypassing)
    def _plural(n: int, word: str) -> str:
        return f"{n} {word}" if n == 1 else f"{n} {word}s"

    if bypassing:
        w(
            f"Across all of `src/`: **{_plural(len(bypassing), 'module')} / "
            f"{_plural(total_sites, 'call site')}** still construct a client directly; "
            f"**{_plural(len(routing_files), 'module')}** route through `llm_provider`."
        )
    else:
        w(
            f"Across all of `src/`: **nothing constructs a client directly**. "
            f"All {_plural(len(routing_files), 'module')} that call a model route "
            "through `llm_provider`."
        )
    w("")
    w("| Module | Sites | Constructs |")
    w("|--------|------:|------------|")
    for rel, count, detail in sorted(bypassing, key=lambda x: (-x[1], x[0])):
        w(f"| `{rel}` | {count} | {detail} |")
    w("")
    w("<details><summary>Modules already routing through <code>llm_provider</code></summary>")
    w("")
    for rel in routing_files:
        w(f"- `{rel}`")
    w("")
    w("</details>")
    w("")

    # ---- main flags
    w("## `python -m src.main` — the main entry point")
    w("")
    w("| Flag | Choices / default | Help |")
    w("|------|-------------------|------|")
    for a in parse_argparse(MAIN):
        names = ", ".join(f"`{x}`" for x in a["names"])
        bits = []
        if a["choices"]:
            bits.append("/".join(a["choices"]))
        if a["default"]:
            bits.append(f"default `{a['default']}`")
        if a["action"] == "store_true":
            bits.append("flag")
        w(f"| {names} | {esc(', '.join(bits)) or '—'} | {esc(a['help'])} |")
    w("")

    # ---- cli tools
    w("## Standalone CLI tools")
    w("")
    w(
        "Every executable under `cli/`, `cli/utils/`, and `src/cli/`. Purpose is "
        "each file's own docstring — a tool with a blank cell has no docstring, "
        "which is itself the finding."
    )
    w("")
    for directory in CLI_DIRS:
        if not directory.exists():
            continue
        rel = directory.relative_to(REPO)
        files = sorted(
            f
            for f in directory.iterdir()
            if f.is_file()
            and f.suffix in (".py", ".sh")
            and not f.name.startswith("__")
        )
        if not files:
            continue
        w(f"### `{rel}/`")
        w("")
        w("| Tool | Flags | Purpose |")
        w("|------|-------|---------|")
        for f in files:
            if f.suffix == ".sh":
                summary, flags = shell_summary(f), []
            else:
                summary, flags = docstring_summary(f), parse_argparse(f)
            flag_names = ", ".join(
                f"`{a['names'][0]}`" for a in flags if a["names"][0].startswith("-")
            )
            positional = ", ".join(
                f"`{a['names'][0]}`" for a in flags if not a["names"][0].startswith("-")
            )
            shown = " · ".join(x for x in (positional, flag_names) if x) or "—"
            w(f"| `{rel}/{f.name}` | {shown} | {esc(summary)} |")
        w("")

    # ---- console scripts
    w("### Installed console scripts")
    w("")
    w("From `pyproject.toml` `[project.scripts]`:")
    w("")
    pyproject = (REPO / "pyproject.toml").read_text()
    block = re.search(r"\[project\.scripts\](.*?)(\n\[|\Z)", pyproject, re.S)
    if block:
        for line in block.group(1).strip().splitlines():
            if "=" in line:
                name, target = line.split("=", 1)
                clean = target.strip().strip('"')
                w(f"- `{name.strip()}` → `{clean}`")
    w("")

    notes = overlay.get("notes", "")
    if notes:
        w("## Notes")
        w("")
        w(notes.strip())
        w("")

    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------------ main


def build() -> tuple[str, list[str]]:
    nodes, entry, edges, conditionals = parse_graph()
    for n in nodes:
        n.routing, n.routing_detail = scan_routing(n.module)

    overlay = yaml.safe_load(OVERLAY.read_text()) if OVERLAY.exists() else {}
    overlay = overlay or {}
    documented = set((overlay.get("nodes") or {}).keys())
    missing = sorted({n.name for n in nodes} - documented)
    stale = sorted(documented - {n.name for n in nodes})

    problems = []
    problems += [f"node in graph with no overlay entry: {n}" for n in missing]
    problems += [f"overlay entry for a node no longer in the graph: {n}" for n in stale]

    return render(nodes, entry, edges, conditionals, overlay), problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit 1 if the committed doc is out of date or the overlay has gaps.",
    )
    args = ap.parse_args()

    content, problems = build()

    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != content:
            problems.append(
                f"{OUTPUT.relative_to(REPO)} is out of date — "
                "run scripts/gen_pipeline_reference.py"
            )
        for p in problems:
            print(f"DRIFT: {p}", file=sys.stderr)
        return 1 if problems else 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content)
    print(f"wrote {OUTPUT.relative_to(REPO)} ({len(content.splitlines())} lines)")
    for p in problems:
        print(f"  ⚠️  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
