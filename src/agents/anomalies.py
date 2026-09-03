"""
anomalies.json — a place to put an instinctive observation, not a job to do.

Agents notice things: numbers that disagree, a claim that cannot be checked, a
document that contradicts its own filename. The instinct to report all of it is
strong and, in early-stage venture, wrong. Left unconstrained every agent writes
down every concern it can conjure, and the operator receives a memo about an
investment they have already made that reads like a doomscroll.

So this module is a pressure valve, and the rules around it matter more than the
file does. The full discipline is
``context-v/reminders/Round-Closing-Timeline-Nuances.md`` §3. In short:

* Writing here is **optional and incidental**. No agent's task is "find
  anomalies", and none should take an extra pass or an extra model call to
  populate it. Zero entries is a correct outcome.
* **Nothing here reaches the memo**, as a caveat, a footnote, or a
  considerations section. Assembly never reads this file.
* **Nothing here is raised in conversation.** The operator reads it when they
  want it.
* Ordinary closing mechanics are never anomalies — a wire before a signature is
  how closings work.
* Absence of data is not an anomaly. A dataroom without a cap table is a
  dataroom without a cap table.
* **Only note things in the data that is real.** Money spent, web traffic,
  signed contracts, billed subscription revenue, cap tables. An implausible TAM
  is not an anomaly; it is a deck.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Loose grouping labels, not a taxonomy to satisfy.
KINDS = (
    "conflicting_claims",            # two documents, same instrument, different numbers
    "identity_violation",            # a total that is not the sum of its parts
    "unit_or_convention",            # an 85% "Discount Rate" read as an 85% discount
    "document_contradicts_metadata",  # "Signed" in the name, blank signature block
    "unreadable_source",             # scanned where content would move a real number
)


def _slug(text: str) -> str:
    """
    A kebab-case subject slug, expected to be loose now and canonical later.

    Coin one from whatever you have. Nothing validates it at write time; a slug
    that turns out to be a synonym of an existing one is a reconciliation job
    later, not an error now.
    """
    s = re.sub(r"[^A-Za-z0-9]+", "-", (text or "unknown")).strip("-").lower()
    return re.sub(r"-{2,}", "-", s)[:80] or "unknown"


def record(
    output_dir: str | Path,
    *,
    company: str,
    agent: str,
    source_path: str,
    observation: str,
    why: str,
    evidence: str = "",
    kind: str = "",
    slug: Optional[str] = None,
) -> None:
    """
    Append one entry. Never raises — a failure here must not fail a run.

    Args:
        output_dir: The analysis run's output directory.
        company: Company token.
        agent: Which agent noticed it, e.g. ``legal_extractor``.
        source_path: Where the file lives, repo-relative. An entry whose document
            cannot be located is not actionable.
        observation: What was seen. One sentence, no remediation advice.
        why: What it would change. Hold this to "what decision or number does
            this affect?" — if the honest answer is "none", do not write it.
        evidence: A quotation, not a paraphrase. An entry a reader cannot check
            against the document is worse than no entry.
        kind: One of KINDS, loosely.
        slug: Subject slug; derived from company + source when omitted.
    """
    try:
        path = Path(output_dir) / "anomalies.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = {
                "company": company,
                "run_started": datetime.now().isoformat(timespec="seconds"),
                "entries": [],
            }

        payload["entries"].append({
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
            "slug": slug or _slug(f"{company}-{Path(source_path).stem}"),
            "agent": agent,
            "source_path": str(source_path),
            "observation": observation,
            "evidence": (evidence or "")[:400],
            "why": why,
            "kind": kind,
        })
        path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # Silence is deliberate. This file is a convenience; nothing downstream
        # depends on it, and an agent must never fail a run over a side note.
        pass


def read(output_dir: str | Path) -> List[Dict[str, Any]]:
    """Entries written this run. For a person, or for a later triage pass."""
    path = Path(output_dir) / "anomalies.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except Exception:
        return []
