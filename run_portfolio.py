"""Dataroom bundle across a firm's portfolio, one company at a time.

Usage:
    python run_portfolio.py <firm> [--firm-name "Display Name"] [--companies "A" "B" ...]

Each company is a folder under io/<firm>/portfolio/. With no --companies, every
folder there is run except those starting with "_" or ".".

Analysis lands in `_analysis/<Company>/`; the transcriber's grid is moved to
`_source-transcriptions/<Company>/` afterwards, because a transcription is not
an analysis and the two directories mean different things.
"""
import argparse, shutil, sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.agents.dataroom import analyze_dataroom

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("firm", help="firm slug under io/, e.g. my-fund")
parser.add_argument("--firm-name", help="firm display name passed to the analyzer")
parser.add_argument("--companies", nargs="+", help="portfolio folder names; default is all")
args = parser.parse_args()

PORTFOLIO = Path("io") / args.firm / "portfolio"
COMPANIES = args.companies or sorted(
    p.name for p in PORTFOLIO.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
)

for name in COMPANIES:
    room = PORTFOLIO / name
    if not room.is_dir():
        print(f"\n### {name}: no such directory — skipped"); continue

    slug = name.replace(" ", "-")
    out = PORTFOLIO / "_analysis" / slug
    print(f"\n{'#'*70}\n### {name}  ({len(list(room.rglob('*')))} entries)\n{'#'*70}", flush=True)
    try:
        result = analyze_dataroom(
            dataroom_path=str(room), company_name=slug, output_dir=out,
            use_llm=True, firm_name=args.firm_name,
            deal_config={},          # portfolio companies carry no deal JSON
        )
        got = {k: bool(result.get(k)) for k in ("financials", "cap_table", "traction", "team", "competitive")}
        print(f"    extracted: {got} | legal_docs={len(result.get('legal_docs') or [])}", flush=True)

        # A transcription is not an analysis.
        ts = out / "timeseries"
        if ts.exists():
            dest = PORTFOLIO / "_source-transcriptions" / slug
            dest.mkdir(parents=True, exist_ok=True)
            if (dest / "timeseries").exists():
                shutil.rmtree(dest / "timeseries")
            shutil.move(str(ts), str(dest / "timeseries"))
            tl = out / "timeline.yaml"
            if tl.exists():
                shutil.move(str(tl), str(dest / "timeline.yaml"))
            n = len(list((dest / "timeseries").glob("*.csv")))
            print(f"    📉 {n} series file(s) -> _source-transcriptions/{slug}/", flush=True)
        else:
            print("    📉 no dated series", flush=True)
    except Exception:
        print(f"    ✗ FAILED\n{traceback.format_exc()}", flush=True)

print("\nAll done.")
