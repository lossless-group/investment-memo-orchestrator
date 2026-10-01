"""Dataroom analysis with the inner workings exposed, for troubleshooting.

Usage:
    python run_dataroom_verbose.py <firm> <company> [--firm-name "Display Name"]

Reads the dataroom at io/<firm>/portfolio/<company>/ and writes to
io/<firm>/portfolio/_analysis/<company>/, printing each stage (scan, classify,
legal-document routing, extraction, terms log) as it goes.
"""
import argparse, json, sys, time
from pathlib import Path

O = Path(__file__).resolve().parent
sys.path.insert(0, str(O))

from src.agents.dataroom import scan_dataroom, classify_documents
from src.agents.dataroom.dataroom_analyzer import analyze_dataroom

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("firm", help="firm slug under io/, e.g. my-fund")
parser.add_argument("company", help="portfolio folder name under io/<firm>/portfolio/")
parser.add_argument("--firm-name", help="firm display name passed to the analyzer")
args = parser.parse_args()

DATAROOM = O / "io" / args.firm / "portfolio" / args.company
OUT = O / "io" / args.firm / "portfolio" / "_analysis" / args.company
COMPANY = args.company

def hr(t): print(f"\n{'='*78}\n{t}\n{'='*78}", flush=True)

hr("STEP 1 — SCAN (what the scanner can and cannot read)")
inventory, skipped = scan_dataroom(str(DATAROOM), return_skipped=True)
print(f"readable: {len(inventory)}   skipped: {len(skipped)}", flush=True)
for s in skipped:
    print(f"   SKIP  {s['filename'][:62]:62}  {s['reason']}", flush=True)

hr("STEP 2 — CLASSIFY (type, confidence, and why)")
t0 = time.time()
inventory = classify_documents(
    inventory, use_llm=True, company_name=COMPANY,
    firm_name=args.firm_name, dataroom_root=str(DATAROOM),
)
print(f"classified {len(inventory)} in {time.time()-t0:.0f}s\n", flush=True)

by_type = {}
for d in inventory:
    by_type.setdefault(d["document_type"], []).append(d)
for t, docs in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
    print(f"\n--- {t}  ({len(docs)}) ---", flush=True)
    for d in docs[:6]:
        print(f"   {d['classification_confidence']:.2f} [{d['classification_source']:>8}] "
              f"{d['filename'][:56]}", flush=True)
        if d.get("classification_reasoning"):
            print(f"          why: {d['classification_reasoning'][:110]}", flush=True)
    if len(docs) > 6:
        print(f"   … and {len(docs)-6} more", flush=True)

# The whole point of this run: what lands in the terms log.
hr("STEP 3 — LEGAL DOCUMENTS THE EXTRACTOR WILL SEE")
from src.agents.dataroom.extractors.legal_extractor import LEGAL_DOCUMENT_TYPES
legal = [d for d in inventory if d["document_type"] in LEGAL_DOCUMENT_TYPES]
print(f"{len(legal)} of {len(inventory)} documents classified legal:", flush=True)
for d in legal:
    print(f"   {d['document_type']:<22} {d['filename'][:60]}", flush=True)

safes = [d for d in inventory if "/SAFEs/" in d["file_path"]]
missed = [d for d in safes if d["document_type"] not in LEGAL_DOCUMENT_TYPES]
print(f"\nfiles under Corporate Docs/SAFEs/: {len(safes)}   NOT classified legal: {len(missed)}", flush=True)
for d in missed:
    print(f"   MISSED  {d['document_type']:<22} {d['filename'][:56]}", flush=True)

hr("STEP 4 — FULL EXTRACTION")
result = analyze_dataroom(
    dataroom_path=str(DATAROOM), company_name=COMPANY,
    output_dir=OUT, use_llm=True, firm_name=args.firm_name,
)

hr("STEP 5 — WHAT THE TERMS LOG WOULD SAY")
for doc in result.get("legal_docs") or []:
    print(f"\n### {doc['document_source'][:70]}", flush=True)
    for k in ("document_type", "security_type", "is_executed", "document_date",
              "effective_date", "investment_amount", "valuation_cap",
              "discount_rate", "investors", "confidence"):
        print(f"    {k:20} {doc.get(k)}", flush=True)

print("\n--- legal_summary.terms (the D8 collapse) ---", flush=True)
print(json.dumps((result.get("legal_summary") or {}).get("terms"), indent=1), flush=True)
print("--- conflicts reported ---", flush=True)
for c in ((result.get("legal_summary") or {}).get("conflicts") or []):
    print(f"    {c.get('field')}: {c.get('values')}", flush=True)

from src.agents import anomalies
ents = anomalies.read(OUT)
print(f"\n--- anomalies.json: {len(ents)} entries ---", flush=True)
for e in ents:
    print(f"    [{e['kind']}] {e['observation'][:80]}", flush=True)
