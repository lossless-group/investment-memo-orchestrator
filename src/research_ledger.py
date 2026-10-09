"""
Deal-level search ledger: every web search an agent runs, recorded once.

Spec: context-v/specs/Reuse-and-Augment-Research-Across-Runs.md

`inputs/sources/` already gives fetched documents a durable, version-independent
home, so a second run never re-reads a page it has read. Searches had no such
memory: every run re-asked the same questions of Tavily and Perplexity. The
ledger is that memory. A search younger than its TTL is answered from the
ledger; anything else runs and is recorded.

The ledger lives at `inputs/research-ledger.json`, beside `Sources.md`, with a
human-readable `inputs/Research-Ledger.md` rendered from it.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

LEDGER_NAME = "research-ledger.json"
LEDGER_MD_NAME = "Research-Ledger.md"

# Queries about things that move week to week. Everything else (founders,
# technology, market structure, science) holds for months.
_VOLATILE = re.compile(
    r"\b(funding|fundrais\w*|raise[sd]?|round|series [a-k]|valuation|valued|ipo|"
    r"news|announce\w*|latest|recent|acquisition|acquired|earnings|quarter|q[1-4]|"
    r"20[2-3]\d)\b",
    re.IGNORECASE,
)
VOLATILE_TTL_DAYS = 7
STABLE_TTL_DAYS = 90

_LOCK = threading.Lock()


def normalize_query(query: str) -> str:
    """Case- and whitespace-insensitive form, so trivial rewordings still hit."""
    return re.sub(r"\s+", " ", (query or "").strip().lower())


def ttl_days_for(query: str) -> int:
    override = os.getenv("MEMOPOP_SEARCH_TTL_DAYS")
    if override and override.strip().isdigit():
        return int(override)
    return VOLATILE_TTL_DAYS if _VOLATILE.search(query or "") else STABLE_TTL_DAYS


def refresh_requested() -> bool:
    """`--refresh-searches` (or `--fresh`) sets this for the run."""
    return os.getenv("MEMOPOP_REFRESH_SEARCHES", "").strip() in ("1", "true", "yes")


def ledger_path_for_state(state: Dict[str, Any]) -> Optional[Path]:
    firm = state.get("firm")
    company = state.get("company_name")
    if not (firm and company):
        return None
    return Path("io") / firm / "deals" / company / "inputs" / LEDGER_NAME


class ResearchLedger:
    """Load, query and append the ledger. Writes are immediate, so a run that
    dies halfway still keeps every search it paid for."""

    def __init__(self, path: Optional[Path]):
        self.path = Path(path) if path else None
        self.entries: List[Dict[str, Any]] = []
        if self.path and self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text()).get("entries", [])
            except (OSError, ValueError):
                self.entries = []

    @staticmethod
    def key(agent: str, query: str) -> str:
        return f"{agent}::{normalize_query(query)}"

    def lookup(self, agent: str, query: str) -> Optional[Dict[str, Any]]:
        """The freshest entry for this query if it is still within its TTL."""
        if refresh_requested():
            return None
        key = self.key(agent, query)
        hits = [e for e in self.entries if e.get("key") == key]
        if not hits:
            return None
        latest = max(hits, key=lambda e: e.get("searched_at", ""))
        try:
            when = datetime.fromisoformat(latest["searched_at"])
        except (KeyError, ValueError):
            return None
        ttl = latest.get("ttl_days") or ttl_days_for(query)
        if datetime.now() - when > timedelta(days=ttl):
            return None
        return latest

    def record(self, agent: str, query: str, provider: str, results: List[Dict[str, Any]],
               *, run: str = "", section: str = "") -> Dict[str, Any]:
        entry = {
            "key": self.key(agent, query),
            "agent": agent,
            "query": query,
            "provider": provider,
            "section": section,
            "run": run,
            "searched_at": datetime.now().isoformat(timespec="seconds"),
            "ttl_days": ttl_days_for(query),
            "results": results,
        }
        self.entries.append(entry)
        self.save()
        return entry

    def save(self) -> None:
        if not self.path:
            return
        with _LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"entries": self.entries}, indent=2, ensure_ascii=False))
            (self.path.parent / LEDGER_MD_NAME).write_text(self.render_markdown())

    def render_markdown(self) -> str:
        lines = [
            "# Research Ledger",
            "",
            "Every web search run for this deal, newest first. Generated from "
            "`research-ledger.json`; do not edit by hand. A search younger than its "
            "TTL is answered from here instead of being run again.",
            "",
            "| Searched | Agent | Query | Provider | Results | TTL (days) | Run |",
            "| --- | --- | --- | --- | ---: | ---: | --- |",
        ]
        for e in sorted(self.entries, key=lambda e: e.get("searched_at", ""), reverse=True):
            query = (e.get("query") or "").replace("|", "\\|")[:120]
            lines.append(
                f"| {e.get('searched_at', '')[:16]} | {e.get('agent', '')} | {query} | "
                f"{e.get('provider', '')} | {len(e.get('results') or [])} | "
                f"{e.get('ttl_days', '')} | {e.get('run', '')} |"
            )
        return "\n".join(lines) + "\n"


def run_version_of(state: Dict[str, Any]) -> str:
    out = state.get("output_dir")
    return Path(out).name if out else ""


def cached_search(
    state: Dict[str, Any],
    agent: str,
    query: str,
    provider: str,
    search: Callable[[], List[Dict[str, Any]]],
    *,
    section: str = "",
    ledger: Optional[ResearchLedger] = None,
) -> List[Dict[str, Any]]:
    """
    Answer a search from the ledger when it is fresh, otherwise run and record it.

    `search` is a zero-argument callable so the caller keeps its own provider
    arguments. Failed searches (exceptions) are not recorded, so they are
    retried on the next run rather than remembered as empty.
    """
    ledger = ledger or ResearchLedger(ledger_path_for_state(state))
    hit = ledger.lookup(agent, query)
    if hit is not None:
        print(f"   📒 ledger: reusing {len(hit.get('results') or [])} result(s) from "
              f"{hit.get('searched_at', '')[:10]} — no search")
        return list(hit.get("results") or [])
    results = search() or []
    ledger.record(agent, query, provider, results, run=run_version_of(state), section=section)
    return results
