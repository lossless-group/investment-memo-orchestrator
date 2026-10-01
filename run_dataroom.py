"""Dataroom bundle for one deal: scan → classify → extract → transcribe.

Usage:
    python run_dataroom.py <firm> <deal> [--firm-name "Display Name"] [--no-llm]

Reads io/<firm>/deals/<deal>/<deal>.json, whose "dataroom" key points at the
dataroom folder relative to the deal directory. Writes to
io/<firm>/deals/<deal>/outputs/<deal>-dataroom-<YYYY-MM-DD>/.
"""
import argparse, json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from src.agents.dataroom import analyze_dataroom

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("firm", help="firm slug under io/, e.g. my-fund")
parser.add_argument("deal", help="deal folder name under io/<firm>/deals/")
parser.add_argument("--firm-name", help="firm display name passed to the analyzer")
parser.add_argument("--no-llm", action="store_true", help="skip LLM extraction")
args = parser.parse_args()

DEAL = Path("io") / args.firm / "deals" / args.deal
OUT  = DEAL / f"outputs/{args.deal}-dataroom-{date.today().isoformat()}"
cfg  = json.loads((DEAL / f"{args.deal}.json").read_text())

result = analyze_dataroom(
    dataroom_path=str(DEAL / cfg["dataroom"]),
    company_name=args.deal,
    output_dir=OUT,
    use_llm=not args.no_llm,
    firm_name=args.firm_name,
    deal_config=cfg,
)
print("\n=== what landed ===")
for k in ("financials", "cap_table", "traction", "team", "competitive"):
    v = result.get(k)
    print(f"  {k:12} {'yes' if v else 'no'}")
print(f"  legal_docs   {len(result.get('legal_docs') or [])}")
