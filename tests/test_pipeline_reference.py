"""
Guards on docs/PIPELINE-REFERENCE.md and the inventory it is built from.

Two jobs.

First, keep the reference honest. Four hand-maintained references drifted from
this graph — the README's agent table documented 27 of 35 nodes and omitted
`aggregate_sources`, the curation halt codified mode depends on. The doc is now
generated, and these tests fail when it stops matching the code, so the drift is
a red suite rather than a quietly wrong table.

Second, ratchet the CLI-first-provider refactor. `src/llm_provider.py` tries the
Claude Code seat before the metered API; modules that construct an Anthropic
client themselves cannot use the seat and die outright on a zero credit balance.
Nineteen still do. `test_no_new_modules_bypass_llm_provider` fails when a
twentieth appears, and `test_bypass_allowlist_has_no_stale_entries` fails when a
listed module is fixed but not struck from the list — so the number only moves
down.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
GENERATOR = REPO / "scripts" / "gen_pipeline_reference.py"
OVERLAY = REPO / "docs" / "pipeline-reference.overlay.yaml"
DOC = REPO / "docs" / "PIPELINE-REFERENCE.md"

REGENERATE = ".venv/bin/python scripts/gen_pipeline_reference.py"


def _load_generator():
    """scripts/ is not a package, so the generator is loaded by path.

    It must be registered in sys.modules *before* exec_module: @dataclass
    resolves annotations through sys.modules[cls.__module__], which is None for
    a module that was created but never registered.
    """
    spec = importlib.util.spec_from_file_location("gen_pipeline_reference", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


# Modules that still build an Anthropic client directly, with their call-site
# count.
#
# Two steps of the refactor are done and gone from this list. deck_analyst.py
# was first — four sites, the only image path, and the one that actually failed
# a run. Then the single-call agents: validator, scorecard_evaluator,
# table_generator, link_enrichment, visualization_enrichment.
#
# Then the writer and the three researchers, which needed complete_with_retry
# and the system-prompt fold.
#
# Remaining: the correctors, the standalone agents, and brand_fetch.py last —
# it runs in the FastAPI sidecar, so the CLI has to be shown reachable from
# there before it moves.
#
# When you route one of these through llm_provider, delete its line. Do not add
# lines — a new entry means a new agent was written against the metered API.
KNOWN_BYPASSING = {
    "src/agents/one_pager_generator.py": 2,
    "src/agents/portfolio_listing_agent.py": 1,
    "src/agents/key_info_rewrite.py": 1,
    "src/agents/revise_summary_sections.py": 1,
    "src/agents/scorecard_agent.py": 1,
    "src/server/brand_fetch.py": 1,
}


@pytest.fixture(scope="module")
def graph():
    nodes, entry, edges, conditionals = gen.parse_graph()
    return {"nodes": nodes, "entry": entry, "edges": edges, "conditionals": conditionals}


@pytest.fixture(scope="module")
def overlay():
    return yaml.safe_load(OVERLAY.read_text())


# ------------------------------------------------------------------ the doc


def test_generated_doc_is_current():
    content, _ = gen.build()
    assert DOC.exists(), f"{DOC.name} is missing — run {REGENERATE}"
    assert DOC.read_text() == content, (
        f"{DOC.name} no longer matches the code it is generated from. "
        f"Run {REGENERATE} and commit the result."
    )


def test_doc_is_marked_generated():
    assert DOC.read_text().startswith("<!-- GENERATED FILE"), (
        "the doc must announce itself as generated, or someone will hand-edit it "
        "and lose the edit on the next regeneration"
    )


# ---------------------------------------------------------------- the overlay


def test_every_node_is_documented(graph, overlay):
    in_graph = {n.name for n in graph["nodes"]}
    documented = set(overlay["nodes"])
    undocumented = sorted(in_graph - documented)
    assert not undocumented, (
        f"nodes in src/workflow.py with no entry in {OVERLAY.name}: {undocumented}. "
        "A node without a purpose, a stage, and its AGENTS.md principles is a node "
        "no operator can reason about."
    )


def test_overlay_has_no_orphans(graph, overlay):
    in_graph = {n.name for n in graph["nodes"]}
    orphans = sorted(set(overlay["nodes"]) - in_graph)
    assert not orphans, f"{OVERLAY.name} documents nodes no longer in the graph: {orphans}"


def test_every_node_has_a_valid_stage(graph, overlay):
    stages = set(overlay["stages"])
    for name in sorted(n.name for n in graph["nodes"]):
        entry = overlay["nodes"][name]
        stage = entry.get("stage")
        assert stage, f"`{name}` has no stage — it cannot be reached by `--from`"
        assert stage in stages, f"`{name}` names stage `{stage}`, which is not declared"


def test_every_node_has_a_purpose(graph, overlay):
    missing = sorted(
        n.name for n in graph["nodes"] if not overlay["nodes"][n.name].get("purpose", "").strip()
    )
    assert not missing, f"nodes with no purpose in {OVERLAY.name}: {missing}"


def test_every_stage_has_at_least_one_node(overlay):
    used = {entry.get("stage") for entry in overlay["nodes"].values()}
    empty = sorted(set(overlay["stages"]) - used)
    assert not empty, f"stages declared but assigned to no node: {empty}"


# ------------------------------------------------------------------ the graph


def test_entry_point_is_a_real_node(graph):
    assert graph["entry"] in {n.name for n in graph["nodes"]}


def test_every_node_is_reachable_from_the_entry_point(graph):
    """A node with order 0 was appended by the fallback, not reached by a walk."""
    unreached = sorted(n.name for n in graph["nodes"] if n.order == 0)
    assert not unreached, f"nodes unreachable from `{graph['entry']}`: {unreached}"


def test_every_edge_target_exists(graph):
    names = {n.name for n in graph["nodes"]} | {"END"}
    for source, target in graph["edges"].items():
        assert target in names, f"edge {source} → {target} points at nothing"
    for source, _router, mapping in graph["conditionals"]:
        for label, target in mapping.items():
            assert target in names, f"conditional {source} [{label}] → {target} points at nothing"


# ------------------------------------------------- llm_provider routing ratchet


@pytest.fixture(scope="module")
def bypassing():
    modules, _routing = gen.repo_inventory()
    return {rel: count for rel, count, _detail in modules}


def test_no_new_modules_bypass_llm_provider(bypassing):
    new = sorted(set(bypassing) - set(KNOWN_BYPASSING))
    assert not new, (
        f"new modules constructing an Anthropic client directly: {new}. "
        "Route them through src/llm_provider.call() so they can use the Claude "
        "Code seat and degrade with a warning instead of a 400."
    )


def test_bypass_call_site_counts_do_not_grow(bypassing):
    grown = {
        rel: (KNOWN_BYPASSING[rel], count)
        for rel, count in bypassing.items()
        if rel in KNOWN_BYPASSING and count > KNOWN_BYPASSING[rel]
    }
    assert not grown, f"new direct-client call sites in known modules (was, now): {grown}"


def test_bypass_allowlist_has_no_stale_entries(bypassing):
    """Fixing a module without striking it from the list lets the count drift back up."""
    fixed = sorted(set(KNOWN_BYPASSING) - set(bypassing))
    assert not fixed, (
        f"these modules no longer construct a client and should be removed from "
        f"KNOWN_BYPASSING: {fixed}"
    )
    shrunk = {
        rel: (KNOWN_BYPASSING[rel], count)
        for rel, count in bypassing.items()
        if rel in KNOWN_BYPASSING and count < KNOWN_BYPASSING[rel]
    }
    assert not shrunk, f"call-site counts dropped; update KNOWN_BYPASSING (was, now): {shrunk}"


def test_llm_provider_itself_is_not_counted(bypassing):
    assert "src/llm_provider.py" not in bypassing, (
        "the provider layer is supposed to construct clients; exempting it is the "
        "whole point of the scan"
    )
