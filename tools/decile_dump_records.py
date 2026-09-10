#!/usr/bin/env python3
"""
Dump Decile Hub's structured records to JSON for offline fund analysis.

The PDFs are the paper; this is the data. A financial package tells you the
Q1 2026 balance sheet; `capital_accounts` and `portfolio_company_investments`
let you compute one.

Handles the three pagination patterns the decile-hub-connector skill documents,
because assuming one shape silently truncates the others:

  A — offset, 0-indexed   `{data: [...], pagination: {total_pages, ...}}`
      directory, events, files, tasks, financial_reports
  B — offset, 1-indexed   `{<resource_key>: [...], page, per_page, total}`
      firm-admin / accounting: entities, capital_accounts, journal_entries
  C — keyset              `{data: [...], pagination: {next_page_token}}`
      portfolio companies and their investments/valuations

Writes one file per resource under <dest>/records/. Never prints the token.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from decile_bulk_fetch import api_get, credentials  # noqa: E402

# (path, pagination pattern, resource key for pattern B)
AS_OF = "2026-06-30"   # current-portfolio calc is available through this date

RESOURCES = [
    ("whoami", "single", None),
    ("organizations", "A", None),
    ("people", "A", None),
    ("events", "A", None),
    ("tasks", "A", None),
    ("files", "A", None),
    ("folders", "A", None),
    ("variables", "A", None),
    ("email_templates", "A", None),
    ("account_users", "A", None),
    ("financial_reports", "A", None),
    ("deal_memos", "A", None),
    ("pipelines", "A", None),
    ("newsletters", "A", None),
    ("entities", "B", "entities"),
    ("accounting_accounts", "B", "accounting_accounts"),
    ("activity_entries", "B", "activity_entries"),
    ("portfolio_companies", "C", None),
]

# Accounting lives UNDER an entity, not at the account root — a flat
# /api/v1/capital_accounts is a 404. Discover entities first, then walk each.
# (resource, pattern-B key)
ENTITY_SCOPED = [
    ("capital_accounts", "capital_accounts"),
    ("capital_account_calculations", "capital_account_calculations"),
    ("capital_calls", "capital_calls"),
    ("journal_entries", "journal_entries"),
    ("bank_transactions", "bank_transactions"),
    ("schedule_of_investments", "schedule_of_investments"),
    ("fees", "fees"),
    ("commitments", "commitments"),
]


def fetch_all(base: str, token: str, path: str, pattern: str, key: Optional[str]) -> List[dict]:
    rows: List[dict] = []
    if pattern == "single":
        return [api_get(base, token, path)]

    if pattern == "A":
        page = 0
        while True:
            payload = api_get(base, token, path, {"page": page})
            batch = payload.get("data", [])
            rows.extend(batch)
            pg = payload.get("pagination", {})
            if not batch or page >= pg.get("total_pages", 1) - 1:
                return rows
            page += 1

    if pattern == "B":
        page = 1
        while True:
            payload = api_get(base, token, path, {"page": page, "per_page": 100})
            batch = payload.get(key or path, [])
            rows.extend(batch)
            if len(rows) >= payload.get("total", 0) or not batch:
                return rows
            page += 1

    token_ = None
    while True:  # C
        payload = api_get(base, token, path, {"per_page": 100, "page_token": token_})
        batch = payload.get("data", [])
        rows.extend(batch)
        token_ = payload.get("pagination", {}).get("next_page_token")
        if not token_ or not batch:
            return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="io/humain/fund")
    args = ap.parse_args()

    token, base = credentials()
    out = Path(args.dest) / "records"
    out.mkdir(parents=True, exist_ok=True)

    portfolio_ids: List[int] = []
    for path, pattern, key in RESOURCES:
        try:
            rows = fetch_all(base, token, path, pattern, key)
        except urllib.error.HTTPError as exc:
            print(f"  ✗ {path}: HTTP {exc.code}")
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {path}: {type(exc).__name__}")
            continue
        (out / f"{path}.json").write_text(json.dumps(rows, indent=2))
        print(f"  ✓ {path}: {len(rows)} record(s)")
        if path == "portfolio_companies":
            portfolio_ids = [r["id"] for r in rows if r.get("id")]

    # Entity-scoped accounting: capital accounts, calls, ledger, commitments.
    entities_file = out / "entities.json"
    if entities_file.exists():
        import json as _json
        for ent in _json.loads(entities_file.read_text()):
            eid, ename = ent.get("id"), ent.get("name", "?")
            if not eid:
                continue
            for resource, key in ENTITY_SCOPED:
                try:
                    if resource == "schedule_of_investments":
                        payload = api_get(base, token, f"entities/{eid}/{resource}",
                                          {"as_of_date": AS_OF, "page": 1, "per_page": 100})
                        rows = payload.get(key, payload.get("data", []))
                    else:
                        rows = fetch_all(base, token, f"entities/{eid}/{resource}", "B", key)
                except urllib.error.HTTPError as exc:
                    if exc.code != 404:
                        print(f"  ✗ entities/{eid}/{resource}: HTTP {exc.code}")
                    continue
                except Exception:  # noqa: BLE001
                    continue
                if rows:
                    (out / f"entity_{eid}_{resource}.json").write_text(_json.dumps(rows, indent=2))
                    print(f"  ✓ entity {eid} ({ename[:28]}) {resource}: {len(rows)}")

    # Per-company detail: the tranche-level rows fund analysis actually needs.
    for pid in portfolio_ids:
        for sub in ("investments", "valuations"):
            try:
                payload = api_get(base, token, f"portfolio_companies/{pid}/{sub}",
                                  {"per_page": 100, "as_of_date": "2026-06-30"})
                rows = payload.get("data", [])
            except Exception:  # noqa: BLE001
                continue
            (out / f"portfolio_company_{pid}_{sub}.json").write_text(json.dumps(rows, indent=2))
            print(f"  ✓ portfolio_companies/{pid}/{sub}: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
