#!/usr/bin/env python3
"""Describe all portfolio companies listed in a fund's deck/state artifacts.

This CLI is intended for fund memos (especially in `lpcommit-emerging-manager`
mode). It:

- Locates a fund's artifact directory (output/<Company>-vX.Y.Z or explicit
  path)
- Loads `state.json` and `1-research.json`
- Uses Perplexity Sonar Pro to:
  - Enumerate every portfolio company it can identify from deck analysis /
    research
  - Generate a markdown subsection that *exhaustively* lists and briefly
    describes each company, with links where available
- Saves the result into `2-sections/04-portfolio-companies.md` in the
  artifact directory (does NOT overwrite 04-portfolio-construction.md)

Usage examples:

    # Use latest version for WatershedVC
    python cli/describe_all_listed_portfolio_companies.py "WatershedVC"

    # Use explicit artifact directory
    python cli/describe_all_listed_portfolio_companies.py \
        output/WatershedVC-v0.0.1

The generated section can then be manually referenced or incorporated into the
Portfolio Construction section.
"""

import os
import sys
import json
import argparse
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Ensure project root on path so src.* imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename
from src.versioning import VersionManager


def load_artifacts(artifact_dir: Path, console: Console) -> dict:
    """Load state and research artifacts for the fund.

    This is intentionally minimal: we only need state + research context.
    """
    artifacts: dict = {"state": None, "research": None}

    state_file = artifact_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            artifacts["state"] = json.load(f)
        console.print("[green]\u2713 Loaded state.json[/green]")
    else:
        console.print("[yellow]\u26a0 No state.json found[/yellow]")

    research_file = artifact_dir / "1-research.json"
    if research_file.exists():
        with open(research_file) as f:
            artifacts["research"] = json.load(f)
        console.print("[green]\u2713 Loaded 1-research.json[/green]")
    else:
        console.print("[yellow]\u26a0 No 1-research.json found[/yellow]")

    return artifacts


def describe_portfolio_companies_with_sonar_pro(
    artifacts: dict, artifact_dir: Path, console: Console
) -> str:
    """Call Sonar Pro to enumerate and describe all portfolio companies.

    The prompt explicitly asks for an exhaustive list based ONLY on internal
    materials (deck analysis in state.json and research JSON), with links.
    """
    from openai import OpenAI

    state = artifacts.get("state") or {}
    research = artifacts.get("research") or {}

    company_name = state.get("company_name", "Unknown Fund")
    investment_type = state.get("investment_type", "fund")
    memo_mode = state.get("memo_mode", "consider")

    deck_analysis = state.get("deck_analysis") or {}
    research_company = (research.get("company") if isinstance(research, dict) else {}) or {}

    # Build a compact context; we do not need the full huge JSONs
    context = {
        "state_company_fields": {
            k: state.get(k)
            for k in [
                "company_name",
                "company_description",
                "company_url",
                "company_stage",
            ]
            if k in state
        },
        "deck_analysis": {
            k: deck_analysis.get(k)
            for k in [
                "investment_themes",
                "traction_metrics",
                "portfolio_companies",
                "extraction_notes",
                "milestones",
            ]
            if k in deck_analysis
        },
        "research_company": research_company,
    }

    prompt = f"""You are helping write a fund LP commitment memo for {company_name}.

We have deck-derived analysis and research artifacts that may mention specific
portfolio companies (current and historical), but previous agents have
under-listed them.

Your task is to:

1. Carefully scan the structured context (deck_analysis, research company
   section, traction/milestones) for ANY mention of portfolio companies
   (past or present) associated with this fund.
2. Produce an EXHAUSTIVE list of all such companies you can identify from
   this context. If uncertain, err on the side of including plausible
   portfolio companies but DO NOT hallucinate names that do not appear at
   all in the context.
3. For each company you list, provide:
   - Company name
   - One-sentence description of what they do
   - Stage (if indicated or reasonably inferrable from context)
   - Thematic fit (e.g., healthcare, automotive, healthy living, etc.)
   - A markdown link to the most relevant URL if it appears in the context
     (company website, portfolio page, or credible external link). If no URL
     is present in the context, omit the link rather than guessing.

Output format:

- Return a markdown section starting with:

  "### Portfolio Companies"

- Then use a markdown bullet list, ONE bullet per company, in this pattern:

  - **Company Name** — short description. Stage: X. Theme: Y. [Website](https://...)

- If you truly cannot identify any specific portfolio company names from the
  context provided, output:

  "### Portfolio Companies\n\nNo specific portfolio companies were identifiable from the current deck and
  research context."

CONTEXT (deck + research, truncated for brevity but sufficient for you):
{json.dumps(context, indent=2)}

Now write ONLY the markdown section as specified above.
"""

    console.print(
        "[dim]Calling Perplexity Sonar Pro to enumerate and describe portfolio companies...[/dim]"
    )

    client = OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )

    response = client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": prompt}],
    )

    section_md = response.choices[0].message.content

    # Save to 2-sections as a dedicated file
    sections_dir = artifact_dir / "2-sections"
    sections_dir.mkdir(parents=True, exist_ok=True)
    target_file = sections_dir / "04-portfolio-companies.md"
    with open(target_file, "w") as f:
        f.write("# Portfolio Companies\n\n")
        f.write(section_md.strip() + "\n")

    console.print(
        f"[green]\u2713 Saved portfolio companies section to:[/green] {target_file}"
    )

    return section_md


def main() -> None:
    console = Console()
    load_dotenv()

    if not os.getenv("PERPLEXITY_API_KEY"):
        console.print("[bold red]Error:[/bold red] PERPLEXITY_API_KEY not set")
        console.print(
            "[yellow]describe_all_listed_portfolio_companies.py requires Perplexity Sonar Pro.[/yellow]"
        )
        console.print("[yellow]Set PERPLEXITY_API_KEY in your .env file.[/yellow]")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description=(
            "Enumerate and describe all portfolio companies mentioned in a fund's "
            "deck/state artifacts, saving a dedicated markdown section."
        )
    )
    parser.add_argument(
        "target",
        help=(
            "Company name (e.g., 'WatershedVC') or path to artifact directory "
            "(e.g., output/WatershedVC-v0.0.1)"
        ),
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.1') if target is a company name.",
    )

    args = parser.parse_args()

    target_path = Path(args.target)

    if target_path.exists() and target_path.is_dir():
        artifact_dir = target_path
    else:
        safe_name = sanitize_filename(args.target)
        output_root = Path("output")

        if args.version:
            artifact_dir = output_root / f"{safe_name}-{args.version}"
        else:
            version_mgr = VersionManager(output_root)
            if safe_name not in version_mgr.versions_data:
                console.print(
                    f"[red]Error: No versions found for '{args.target}' in output/versions.json[/red]"
                )
                sys.exit(1)
            latest_version = version_mgr.versions_data[safe_name]["latest_version"]
            artifact_dir = output_root / f"{safe_name}-{latest_version}"

    if not artifact_dir.exists():
        console.print(
            f"[red]Error: Artifact directory not found:[/red] {artifact_dir}"
        )
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]Describing Portfolio Companies for: {args.target}[/bold cyan]\n"
            f"[dim]Artifact directory: {artifact_dir}[/dim]"
        )
    )

    console.print("\n[bold]Loading artifacts...[/bold]")
    artifacts = load_artifacts(artifact_dir, console)

    console.print()
    section_md = describe_portfolio_companies_with_sonar_pro(
        artifacts, artifact_dir, console
    )

    console.print("\n" + "=" * 80)
    console.print(
        Panel("[bold green]Portfolio Companies Section Generated Successfully[/bold green]")
    )
    console.print("\n[bold]Preview (first 500 chars):[/bold]")
    console.print(section_md[:500] + "...\n")

    console.print("\n[bold cyan]Next steps:[/bold cyan]")
    console.print(
        f"1. Review: {artifact_dir}/2-sections/04-portfolio-companies.md and integrate into 04-portfolio-construction.md as needed."
    )
    console.print(
        "2. Re-export branded memo if you want the new section included in the final HTML/PDF."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
