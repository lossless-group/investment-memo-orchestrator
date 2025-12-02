#!/usr/bin/env python3
"""Refocus or repair a specific memo section when web research is thin or noisy.

This CLI is especially useful for `mode: "justify"` memos where the investment
has ALREADY been made and we need to craft a clear LP-facing narrative based
primarily on:

- The deck
- Existing memo sections
- Internal research artifacts

Web research is treated as OPTIONAL signal only. If it is sparse or
conflicting (e.g., multiple entities named "Watershed"), the model should:

1. Emit a short, easy-to-spot line near the top of the section, e.g.:

   "Web research returned limited fund-specific information; falling back to
   narrative based on internal materials."

2. Then produce the best possible justification / narrative based on
   INTERNAL context, without meta text about being unable to complete the task.

Usage examples:

    # Firm-scoped (recommended):
    python cli/refocus_section.py --firm hypernova --deal WatershedVC "Recommendation"
    python cli/refocus_section.py --firm hypernova --deal WatershedVC "Risks & Mitigations" --version v0.0.1

    # Legacy:
    python cli/refocus_section.py "WatershedVC" "Recommendation"
    python cli/refocus_section.py output/WatershedVC-v0.0.1 "Risks & Mitigations"

The interface and artifact handling intentionally mirror cli/improve_section.py
so it fits naturally into the existing workflow.
"""

import os
import sys
import json
import argparse
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Ensure project root is on sys.path so `src.*` imports work when running from cli/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.artifacts import sanitize_filename, save_section_artifact
from src.versioning import VersionManager
from src.paths import resolve_deal_context, get_latest_output_dir_for_deal, DealContext


# Reuse / extend the same section mapping as improve_section.py
SECTION_MAP = {
    "Executive Summary": (1, "01-executive-summary.md"),
    "Business Overview": (2, "02-business-overview.md"),
    "Market Context": (3, "03-market-context.md"),
    "Team": (4, "04-team.md"),
    "Technology & Product": (5, "05-technology--product.md"),
    "Traction & Milestones": (6, "06-traction--milestones.md"),
    "Funding & Terms": (7, "07-funding--terms.md"),
    "Risks & Mitigations": (8, "08-risks--mitigations.md"),
    "Investment Thesis": (9, "09-investment-thesis.md"),
    "Recommendation": (10, "10-recommendation.md"),
    # Fund template sections
    "GP Background & Track Record": (2, "02-gp-background--track-record.md"),
    "Fund Strategy & Thesis": (3, "03-fund-strategy--thesis.md"),
    "Portfolio Construction": (4, "04-portfolio-construction.md"),
    "Value Add & Differentiation": (5, "05-value-add--differentiation.md"),
    "Track Record Analysis": (6, "06-track-record-analysis.md"),
    "Fee Structure & Economics": (7, "07-fee-structure--economics.md"),
    "LP Base & References": (8, "08-lp-base--references.md"),
}


def load_artifacts(artifact_dir: Path) -> dict:
    """Load existing artifacts from a memo output directory.

    This mirrors cli/improve_section.py but is kept local so the CLI is
    self-contained.
    """
    console = Console()

    artifacts = {
        "state": None,
        "research": None,
        "sections": {},
        "validation": None,
    }

    state_file = artifact_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            artifacts["state"] = json.load(f)
        console.print("[green] Loaded state.json[/green]")
    else:
        console.print("[yellow] No state.json found[/yellow]")

    research_file = artifact_dir / "1-research.json"
    if research_file.exists():
        with open(research_file) as f:
            artifacts["research"] = json.load(f)
        console.print("[green] Loaded research data[/green]")
    else:
        console.print("[yellow] No research data found[/yellow]")

    sections_dir = artifact_dir / "2-sections"
    if sections_dir.exists():
        for section_file in sections_dir.glob("*.md"):
            with open(section_file) as f:
                artifacts["sections"][section_file.name] = f.read()
        console.print(
            f"[green] Loaded {len(artifacts['sections'])} existing sections[/green]"
        )
    else:
        console.print("[yellow] No sections directory found[/yellow]")

    validation_file = artifact_dir / "3-validation.json"
    if validation_file.exists():
        with open(validation_file) as f:
            artifacts["validation"] = json.load(f)
        console.print("[green] Loaded validation data[/green]")

    return artifacts


def refocus_section_with_sonar_pro(
    section_name: str,
    artifacts: dict,
    artifact_dir: Path,
    console: Console,
) -> str:
    """Refocus a section, prioritizing internal context over web research.

    This uses Perplexity Sonar Pro under the hood (same as improve_section),
    but with a different prompt contract:

    - Lock the entity identity using state.json (company_name, type, mode).
    - For mode="justify", treat deck + existing sections as primary truth.
    - Web research is optional; if it is thin or conflicting, include ONE
      short fallback line, then produce the best internal narrative.
    - Never output meta text like "I cannot complete this task" or long
      explanations about search limitations inside the section body.
    """
    from openai import OpenAI

    if section_name not in SECTION_MAP:
        console.print(f"[red]Error: Unknown section '{section_name}'[/red]")
        console.print("[yellow]Available sections:[/yellow]")
        for name in sorted(SECTION_MAP.keys()):
            console.print(f"  - {name}")
        sys.exit(1)

    section_num, section_file = SECTION_MAP[section_name]

    existing_content = artifacts["sections"].get(section_file, "")
    is_new = not existing_content or existing_content.strip() == ""

    action = "Creating" if is_new else "Refocusing"
    console.print(f"\n[bold cyan]{action} section:[/bold cyan] {section_name}")

    state = artifacts.get("state", {}) or {}
    company_name = state.get("company_name", "Unknown Company")
    investment_type = state.get("investment_type", "direct")
    memo_mode = state.get("memo_mode", "consider")
    research_data = artifacts.get("research", {}) or {}

    # Optionally load additional numeric constraints from data/<company>.json
    fund_size = None
    amount_committed = None
    try:
        data_file = Path("data") / f"{company_name}.json"
        if data_file.exists():
            with open(data_file, "r") as f:
                company_data = json.load(f)
            fund_size = company_data.get("fund_size")
            amount_committed = company_data.get("amount_committed")
    except Exception:
        # Never fail if the data file is missing or malformed; just skip constraints.
        fund_size = None
        amount_committed = None

    # Load template & style guide to keep tone consistent
    if investment_type == "fund":
        template_file = Path("templates/memo-template-fund.md")
    else:
        template_file = Path("templates/memo-template-direct.md")

    template_content = ""
    if template_file.exists():
        with open(template_file) as f:
            template_content = f.read()

    style_guide = ""
    style_guide_file = Path("templates/style-guide.md")
    if style_guide_file.exists():
        with open(style_guide_file) as f:
            style_guide = f.read()

    # Build context from other sections (trimmed for prompt size)
    other_sections_context = ""
    if artifacts["sections"]:
        other_sections_context = "\n\n## OTHER SECTIONS (for context):\n\n"
        for filename, content in sorted(artifacts["sections"].items()):
            if filename != section_file:
                other_sections_context += (
                    f"### {filename}\n{content[:500]}...\n\n"
                )

    # In justify mode we want a very explicit contract
    justify_note = (
        "In JUSTIFY mode, the investment is already made. Focus on explaining "
        "why the decision is reasonable for LPs, not on re-deciding whether to "
        "invest. If external web research is thin, noisy, or conflicts across "
        "entities with the same name, you MUST still produce the best possible "
        "section using ONLY internal materials (deck, internal research, other "
        "sections). In that case, include ONE short line near the top: \n\n"
        "  \"Web research returned limited fund-specific information; falling "
        "back to narrative based on internal materials.\"\n\n"
        "After that line, DO NOT discuss web research limitations again. Do not "
        "output meta-text like 'I cannot complete this task' or long "
        "explanations about search results."
    )

    if is_new:
        task_description = (
            f"Create a coherent '{section_name}' section that is fully "
            f"consistent with the existing memo and deck."
        )
    else:
        task_description = (
            f"Refocus and repair the existing '{section_name}' section. "
            f"Remove any meta-commentary about being unable to complete the "
            f"task or about confusing search results. Strengthen the narrative "
            f"using the deck and other memo sections, and keep only content "
            f"that helps justify our position to LPs.\n\n"
            f"EXISTING SECTION CONTENT (to be improved or partially reused):\n"
            f"{existing_content}\n\n"
        )

    memo_mode_label = (
        f"{memo_mode.upper()} (retrospective justification)"
        if memo_mode == "justify"
        else f"{memo_mode.upper()} (prospective analysis)"
    )

    numerical_constraints = []
    if fund_size:
        numerical_constraints.append(f"- Fund size: ${fund_size:,.0f}")
    if amount_committed:
        numerical_constraints.append(
            f"- Our commitment (amount_committed from data JSON): ${amount_committed:,.0f}"
        )
    numerical_constraints_text = (
        "\n".join(numerical_constraints) if numerical_constraints else "(none provided)"
    )

    prompt = f"""You are refocusing the '{section_name}' section for an
investment memo about {company_name}.

INVESTMENT TYPE: {investment_type.upper()}
MEMO MODE: {memo_mode_label}

TEMPLATE GUIDANCE (for structure and tone):
{template_content}

STYLE GUIDE (for voice and formatting):
{style_guide}

STATE (from state.json):
{json.dumps(state, indent=2)}

INTERNAL RESEARCH DATA (1-research.json):
{json.dumps(research_data, indent=2)}

{other_sections_context}

TASK:
{task_description}

SPECIAL RULES FOR JUSTIFY MODE:
{justify_note if memo_mode == 'justify' else 'In non-justify modes you may use web research more heavily, but still avoid meta-text about being unable to complete the task.'}

NUMERICAL CONSTRAINTS (if available):
{numerical_constraints_text}

REQUIREMENTS:
- Produce a polished section body only (no top-level markdown header like '# Recommendation').
- Ensure the section is self-consistent with the rest of the memo.
- Prefer deck + internal sections over external web snippets.
- If you include the fallback line about limited web research, do it ONCE near the top.
- Do NOT include generic meta commentary about search limitations.
- Match the tone and depth of high-quality VC LP memos.

REFocused SECTION CONTENT:
"""

    console.print(
        "[dim]Calling Perplexity Sonar Pro to refocus section with internal-first logic...[/dim]"
    )

    perplexity_client = OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai",
        default_headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )

    response = perplexity_client.chat.completions.create(
        model="sonar-pro",
        messages=[{"role": "user", "content": prompt}],
    )

    new_content = response.choices[0].message.content

    # Save updated section using the same artifact helper
    save_section_artifact(artifact_dir, section_num, section_name, new_content)
    console.print(
        f"[green] Saved refocused section to:[/green] {artifact_dir}/2-sections/{section_file}"
    )

    return new_content


def reassemble_final_draft(artifact_dir: Path, console: Console) -> Path:
    """Reassemble 4-final-draft.md from all section files.

    Copied from improve_section.py so refocus can be run independently.
    """
    console.print("\n[bold]Reassembling final draft...[/bold]")

    content = ""

    header_file = artifact_dir / "header.md"
    if header_file.exists():
        with open(header_file) as f:
            content = f.read() + "\n"
        console.print("[dim]   Included header.md (company trademark)[/dim]")

    sections_dir = artifact_dir / "2-sections"
    section_files = sorted(sections_dir.glob("*.md"))
    console.print(f"[dim]   Loading {len(section_files)} sections...[/dim]")

    for section_file in section_files:
        with open(section_file) as f:
            content += f.read() + "\n\n"

    final_draft = artifact_dir / "4-final-draft.md"
    with open(final_draft, "w") as f:
        f.write(content.strip())

    console.print(f"[green] Final draft reassembled:[/green] {final_draft}")
    return final_draft


def main() -> None:
    console = Console()
    load_dotenv()

    if not os.getenv("PERPLEXITY_API_KEY"):
        console.print("[bold red]Error:[/bold red] PERPLEXITY_API_KEY not set")
        console.print(
            "[yellow]refocus_section.py requires Perplexity Sonar Pro for analysis.[/yellow]"
        )
        console.print("[yellow]Set PERPLEXITY_API_KEY in your .env file.[/yellow]")
        sys.exit(1)

    parser = argparse.ArgumentParser(
        description=(
            "Refocus or repair a specific memo section, prioritizing deck + "
            "internal analysis over noisy web research (especially for JUSTIFY mode)."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help=(
            "Company name (e.g., 'WatershedVC') or path to an artifact directory "
            "(e.g., output/WatershedVC-v0.0.1). Optional if --firm and --deal are provided."
        ),
    )
    parser.add_argument(
        "section",
        help="Section name (e.g., 'Recommendation', 'Risks & Mitigations')",
    )
    parser.add_argument(
        "--firm",
        help="Firm name for firm-scoped IO (e.g., 'hypernova'). Uses io/{firm}/deals/{deal}/"
    )
    parser.add_argument(
        "--deal",
        help="Deal name when using --firm. Required if --firm is provided."
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.1') if target is a company name.",
    )

    args = parser.parse_args()

    # Check for MEMO_DEFAULT_FIRM environment variable if --firm not provided
    if not args.firm:
        args.firm = os.environ.get("MEMO_DEFAULT_FIRM")
        if args.firm:
            console.print(f"[dim]Using MEMO_DEFAULT_FIRM: {args.firm}[/dim]")

    # Validate arguments
    if args.firm and not args.deal:
        console.print("[red]Error: --deal is required when --firm is provided[/red]")
        sys.exit(1)

    if not args.firm and not args.target:
        console.print("[red]Error: Either provide a target (company name or path) or use --firm and --deal[/red]")
        sys.exit(1)

    # Determine artifact directory
    artifact_dir = None
    deal_name = args.deal or args.target

    if args.firm:
        # Firm-scoped path resolution
        ctx = resolve_deal_context(deal_name, firm=args.firm)

        if not ctx.outputs_dir or not ctx.outputs_dir.exists():
            console.print(f"[red]Error: Outputs directory not found for {args.firm}/{deal_name}[/red]")
            console.print(f"[dim]Expected: {ctx.outputs_dir}[/dim]")
            sys.exit(1)

        if args.version:
            artifact_dir = ctx.get_version_output_dir(args.version)
        else:
            try:
                artifact_dir = get_latest_output_dir_for_deal(ctx)
            except FileNotFoundError as e:
                console.print(f"[red]Error: {e}[/red]")
                sys.exit(1)

    elif args.target:
        target_path = Path(args.target)

        if target_path.exists() and target_path.is_dir():
            artifact_dir = target_path
        else:
            # Try firm-scoped auto-detection first
            ctx = resolve_deal_context(args.target)

            if not ctx.is_legacy and ctx.outputs_dir and ctx.outputs_dir.exists():
                # Found in io/{firm}/deals/{deal}/
                console.print(f"[dim]Auto-detected firm: {ctx.firm}[/dim]")
                if args.version:
                    artifact_dir = ctx.get_version_output_dir(args.version)
                else:
                    try:
                        artifact_dir = get_latest_output_dir_for_deal(ctx)
                    except FileNotFoundError:
                        console.print(f"[red]Error: No output versions found for {args.target}[/red]")
                        sys.exit(1)
            else:
                # Fall back to legacy output/ structure
                safe_name = sanitize_filename(args.target)
                output_root = Path("output")

                if args.version:
                    artifact_dir = output_root / f"{safe_name}-{args.version}"
                else:
                    version_mgr = VersionManager(output_root)
                    if safe_name not in version_mgr.versions_data:
                        console.print(f"[red]Error: No versions found for '{args.target}'[/red]")
                        console.print(f"[dim]Checked: io/ (auto-detect) and output/versions.json[/dim]")
                        sys.exit(1)
                    latest_version = version_mgr.versions_data[safe_name]["latest_version"]
                    artifact_dir = output_root / f"{safe_name}-{latest_version}"

    if not artifact_dir or not artifact_dir.exists():
        console.print(
            f"[red]Error: Artifact directory not found:[/red] {artifact_dir}"
        )
        sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]Refocusing Section: {args.section}[/bold cyan]\n"
            f"[dim]Artifact directory: {artifact_dir}[/dim]"
        )
    )

    console.print("\n[bold]Loading existing artifacts...[/bold]")
    artifacts = load_artifacts(artifact_dir)

    console.print()
    new_content = refocus_section_with_sonar_pro(
        args.section,
        artifacts,
        artifact_dir,
        console,
    )

    final_draft = reassemble_final_draft(artifact_dir, console)

    console.print("\n" + "=" * 80)
    console.print(Panel("[bold green]Section Refocused Successfully[/bold green]"))
    console.print("\n[bold]Preview (first 500 chars):[/bold]")
    console.print(new_content[:500] + "...\n")

    console.print("\n[bold cyan]Next steps:[/bold cyan]")
    console.print(f"1. Review the refocused section in: {artifact_dir}/2-sections/")
    console.print(f"2. View complete memo: {final_draft}")
    console.print(
        "3. Export to HTML: python cli/export_branded.py "
        f"{final_draft} --brand hypernova --mode dark"
    )
    if args.firm:
        console.print(
            f"4. Refocus another section: python cli/refocus_section.py "
            f"--firm {args.firm} --deal {deal_name} \"<section name>\""
        )
    else:
        console.print(
            "4. Refocus another section: python cli/refocus_section.py "
            f"\"{deal_name}\" \"<section name>\""
        )


if __name__ == "__main__":  # pragma: no cover
    main()
