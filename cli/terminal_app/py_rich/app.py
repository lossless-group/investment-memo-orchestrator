#!/usr/bin/env python3
"""
Interactive Terminal Application — Investment Memo Orchestrator.

A guided CLI that walks users through memo generation, export, and iteration
without requiring knowledge of individual commands, flags, or file paths.

Usage:
    python -m cli.terminal_app.py_rich.app
"""

import sys
import os
import json
import subprocess
import time
from pathlib import Path
from typing import Optional

# Project root: 3 levels up from py-rich/
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.rule import Rule
from rich import box

from cli.terminal_app.py_rich.discovery import discover_firms, discover_deals, get_latest_output_dir, load_state
from cli.terminal_app.py_rich.theme import APP_THEME, QUESTIONARY_STYLE, APP_VERSION, APP_NAME, ACCENT

console = Console(theme=APP_THEME)
q_style = Style(QUESTIONARY_STYLE)


# ── Banner ───────────────────────────────────────────────────────────

def show_banner():
    """Display the application banner."""
    console.print()
    console.print(Panel.fit(
        f"[bold white]{APP_NAME}[/]\n"
        f"[{ACCENT}]v{APP_VERSION}[/] · [dim]33 agents · Powered by Claude + Perplexity[/]",
        border_style=ACCENT,
        padding=(1, 3),
    ))
    console.print()


# ── Firm & Deal Selection ────────────────────────────────────────────

def select_firm() -> Optional[dict]:
    """Interactive firm selection."""
    firms = discover_firms()
    if not firms:
        console.print("[error]No firms found in io/ directory.[/]")
        console.print("[dim]Create a firm directory: io/{firm-name}/deals/[/]")
        return None

    choices = [
        questionary.Choice(
            title=f"{f['name'].replace('-', ' ').title()} ({f['deal_count']} deal{'s' if f['deal_count'] != 1 else ''})",
            value=f
        )
        for f in firms
    ]

    firm = questionary.select(
        "Select firm:",
        choices=choices,
        style=q_style,
    ).ask()

    return firm


def select_deal(firm: dict) -> Optional[dict]:
    """Interactive deal selection."""
    deals = discover_deals(firm["name"])
    if not deals:
        console.print(f"[error]No deals found for {firm['name']}.[/]")
        return None

    choices = []
    for d in deals:
        label = d["name"]
        details = []
        if d["latest_version"]:
            details.append(f"latest: {d['latest_version']}")
        if d["latest_date"]:
            details.append(d["latest_date"])
        details.append(d["stage"])
        if d["has_deck"]:
            details.append("deck ✓")
        if d["has_dataroom"]:
            details.append("dataroom ✓")

        choices.append(questionary.Choice(
            title=f"{label} ({' · '.join(details)})",
            value=d
        ))

    deal = questionary.select(
        "Select deal:",
        choices=choices,
        style=q_style,
    ).ask()

    return deal


def select_version(deal: dict) -> Optional[dict]:
    """Interactive version selection."""
    if not deal["versions"]:
        return None

    choices = []
    for v in reversed(deal["versions"]):  # newest first
        indicators = []
        if v["has_final_draft"]:
            indicators.append("draft ✓")
        if v["has_one_pager"]:
            indicators.append("one-pager ✓")
        indicator_str = f" [{', '.join(indicators)}]" if indicators else ""

        choices.append(questionary.Choice(
            title=f"{v['version']} ({v['date']}){indicator_str}",
            value=v
        ))

    version = questionary.select(
        "Select version:",
        choices=choices,
        style=q_style,
    ).ask()

    return version


# ── Main Menu ────────────────────────────────────────────────────────

def main_menu() -> Optional[str]:
    """Show the main action menu."""
    return questionary.select(
        "What would you like to do?",
        choices=[
            questionary.Choice("📝  Generate a new investment memo", value="generate"),
            questionary.Choice("📄  Generate a one-pager summary", value="one_pager"),
            questionary.Choice("📤  Export an existing memo (HTML / PDF / Word)", value="export"),
            questionary.Choice("🔧  Improve a specific section", value="improve"),
            questionary.Choice("🔄  Integrate content from versions", value="integrate"),
            questionary.Choice("📊  Run a specific agent", value="agent"),
            questionary.Choice("❌  Exit", value="exit"),
        ],
        style=q_style,
    ).ask()


# ── Generate Flow ────────────────────────────────────────────────────

def flow_generate():
    """Full memo generation flow."""
    firm = select_firm()
    if not firm:
        return

    deal = select_deal(firm)
    if not deal:
        return

    # Determine version strategy
    if deal["latest_version"]:
        strategy = questionary.select(
            f"{deal['name']} has existing output at {deal['latest_version']}. What would you like to do?",
            choices=[
                questionary.Choice(f"Generate fresh (clean slate)", value="fresh"),
                questionary.Choice(f"Resume from {deal['latest_version']}", value="resume"),
                questionary.Choice("Start at a specific version number", value="specific"),
            ],
            style=q_style,
        ).ask()
    else:
        strategy = "fresh"

    version_flag = ""
    fresh_flag = ""

    if strategy == "fresh":
        fresh_flag = "--fresh"
    elif strategy == "specific":
        version_str = questionary.text(
            "Enter version (e.g., v0.3.0):",
            style=q_style,
        ).ask()
        if version_str:
            version_flag = f"--version {version_str}"
            fresh_flag = "--fresh"
    # resume = no flags needed

    # Show confirmation
    config = deal.get("config", {})
    info_table = Table(box=box.ROUNDED, show_header=False, border_style=ACCENT, padding=(0, 1))
    info_table.add_column("Field", style="accent")
    info_table.add_column("Value")
    info_table.add_row("Company", deal["name"])
    info_table.add_row("Firm", firm["name"])
    info_table.add_row("Type", config.get("type", "direct").title() + " Investment")
    info_table.add_row("Mode", "Prospective" if config.get("mode") == "consider" else "Retrospective")
    info_table.add_row("Deck", "✓ Found" if deal["has_deck"] else "✗ Not found")
    info_table.add_row("Dataroom", "✓ Found" if deal["has_dataroom"] else "✗ Not found")
    if strategy == "fresh":
        info_table.add_row("Strategy", "Fresh start")

    console.print()
    console.print(info_table)
    console.print()

    if not questionary.confirm("Start generation?", default=True, style=q_style).ask():
        return

    # Run the pipeline
    cmd = f'source .venv/bin/activate && python -m src.main "{deal["name"]}" --firm {firm["name"]} {fresh_flag} {version_flag}'.strip()
    console.print()
    console.print(Rule(f"[accent]Running Pipeline[/]"))
    console.print(f"[dim]{cmd}[/]")
    console.print()

    os.system(cmd)

    console.print()
    console.print(Rule(f"[accent]Pipeline Complete[/]"))

    # Post-run options
    post_run_menu(firm, deal)


# ── Export Flow ──────────────────────────────────────────────────────

def flow_export():
    """Export an existing memo."""
    firm = select_firm()
    if not firm:
        return

    deal = select_deal(firm)
    if not deal:
        return

    if not deal["versions"]:
        console.print("[error]No versions found. Generate a memo first.[/]")
        return

    version = select_version(deal)
    if not version:
        return

    # Find the final draft
    output_dir = Path(version["path"])
    final_drafts = list(output_dir.glob("7-*.md")) or list(output_dir.glob("4-final-draft.md"))
    if not final_drafts:
        console.print("[error]No final draft found in this version.[/]")
        return

    final_draft = final_drafts[0]

    format_choice = questionary.select(
        "What would you like to export?",
        choices=[
            questionary.Choice("Full memo (HTML + PDF)", value="html_pdf"),
            questionary.Choice("One-pager summary", value="one_pager"),
            questionary.Choice("Word document (.docx)", value="docx"),
            questionary.Choice("All formats", value="all"),
        ],
        style=q_style,
    ).ask()

    mode = "light"
    if format_choice in ("html_pdf", "all"):
        mode = questionary.select(
            "Export mode:",
            choices=[
                questionary.Choice("Light mode", value="light"),
                questionary.Choice("Dark mode", value="dark"),
                questionary.Choice("Both", value="both"),
            ],
            style=q_style,
        ).ask()

    console.print()
    console.print(Rule(f"[accent]Exporting[/]"))

    if format_choice in ("html_pdf", "all"):
        modes = ["light", "dark"] if mode == "both" else [mode]
        for m in modes:
            cmd = f'source .venv/bin/activate && python -m cli.export_branded "{final_draft}" --brand {firm["name"]} --mode {m} --pdf'
            console.print(f"[dim]{cmd}[/]")
            os.system(cmd)

    if format_choice in ("docx", "all"):
        cmd = f'source .venv/bin/activate && python -m cli.md2docx "{final_draft}"'
        console.print(f"[dim]{cmd}[/]")
        os.system(cmd)

    if format_choice in ("one_pager", "all"):
        cmd = f'source .venv/bin/activate && python -m cli.generate_one_pager "{output_dir}" --firm {firm["name"]}'
        console.print(f"[dim]{cmd}[/]")
        os.system(cmd)

    console.print()
    console.print("[success]Export complete![/]")


# ── One-Pager Flow ───────────────────────────────────────────────────

def flow_one_pager():
    """Generate a one-pager from existing output."""
    firm = select_firm()
    if not firm:
        return

    deal = select_deal(firm)
    if not deal:
        return

    if not deal["versions"]:
        console.print("[error]No versions found. Generate a memo first.[/]")
        return

    version = select_version(deal)
    if not version:
        return

    mode = questionary.select(
        "Color mode:",
        choices=[
            questionary.Choice("Light mode", value="light"),
            questionary.Choice("Dark mode", value="dark"),
        ],
        style=q_style,
    ).ask()

    console.print()
    console.print(Rule(f"[accent]Generating One-Pager[/]"))

    cmd = f'source .venv/bin/activate && python -m cli.generate_one_pager "{version["path"]}" --firm {firm["name"]} --mode {mode}'
    console.print(f"[dim]{cmd}[/]")
    os.system(cmd)

    console.print()
    console.print("[success]One-pager generated![/]")


# ── Improve Section Flow ─────────────────────────────────────────────

def flow_improve():
    """Improve a specific section."""
    firm = select_firm()
    if not firm:
        return

    deal = select_deal(firm)
    if not deal:
        return

    if not deal["versions"]:
        console.print("[error]No versions found. Generate a memo first.[/]")
        return

    version = select_version(deal)
    if not version:
        return

    # List sections
    sections_dir = Path(version["path"]) / "2-sections"
    if not sections_dir.exists():
        console.print("[error]No sections found in this version.[/]")
        return

    section_files = sorted(sections_dir.glob("*.md"))
    choices = [
        questionary.Choice(
            title=f.stem.replace("-", " ").title(),
            value=f.stem
        )
        for f in section_files
    ]

    section = questionary.select(
        "Which section would you like to improve?",
        choices=choices,
        style=q_style,
    ).ask()

    if not section:
        return

    # Map section stem to display name for improve-section.py
    section_display = section.split("-", 1)[1].replace("-", " ").title() if "-" in section else section

    console.print()
    console.print(Rule(f"[accent]Improving Section: {section_display}[/]"))

    cmd = f'source .venv/bin/activate && python improve-section.py "{deal["name"]}" "{section_display}" --version {version["version"].replace("v", "")}'
    console.print(f"[dim]{cmd}[/]")
    os.system(cmd)

    console.print()
    console.print("[success]Section improved![/]")


# ── Run Specific Agent Flow ──────────────────────────────────────────

def flow_agent():
    """Run a specific agent on existing output."""
    firm = select_firm()
    if not firm:
        return

    deal = select_deal(firm)
    if not deal:
        return

    if not deal["versions"]:
        console.print("[error]No versions found. Generate a memo first.[/]")
        return

    version = select_version(deal)
    if not version:
        return

    agent = questionary.select(
        "Which agent would you like to run?",
        choices=[
            questionary.Separator("── Assembly & Export ──"),
            questionary.Choice("Assemble final draft (citations + TOC)", value="assemble"),
            questionary.Choice("Generate tables", value="tables"),
            questionary.Choice("Generate one-pager", value="one_pager"),
            questionary.Choice("Fix citation spacing", value="spacing"),
            questionary.Separator("── Export ──"),
            questionary.Choice("Export HTML + PDF (light)", value="export_light"),
            questionary.Choice("Export HTML + PDF (dark)", value="export_dark"),
            questionary.Choice("Export Word (.docx)", value="export_docx"),
        ],
        style=q_style,
    ).ask()

    if not agent:
        return

    output_dir = version["path"]
    console.print()
    console.print(Rule(f"[accent]Running Agent[/]"))

    cmd_map = {
        "assemble": f'python -m cli.assemble_draft "{output_dir}"',
        "tables": f'python -m cli.generate_tables "{output_dir}" --firm {firm["name"]}',
        "one_pager": f'python -m cli.generate_one_pager "{output_dir}" --firm {firm["name"]}',
        "spacing": f'python -c "from src.agents.citation_spacing import fix_citation_spacing; from pathlib import Path; p=Path(\'{output_dir}\'); [print(f.name) for f in sorted((p/\'2-sections\').glob(\'*.md\'))]"',
        "export_light": f'python -m cli.export_branded "{output_dir}/7-*.md" --brand {firm["name"]} --mode light --pdf',
        "export_dark": f'python -m cli.export_branded "{output_dir}/7-*.md" --brand {firm["name"]} --mode dark --pdf',
        "export_docx": f'python -m cli.md2docx "{output_dir}/7-*.md"',
    }

    cmd = f'source .venv/bin/activate && {cmd_map.get(agent, "echo unknown agent")}'
    console.print(f"[dim]{cmd}[/]")
    os.system(cmd)

    console.print()
    console.print("[success]Done![/]")


# ── Integrate Content Flow ───────────────────────────────────────────

def flow_integrate():
    """Integrate content from previous versions."""
    firm = select_firm()
    if not firm:
        return

    deal = select_deal(firm)
    if not deal:
        return

    action = questionary.select(
        "What would you like to integrate?",
        choices=[
            questionary.Choice("🔍  Review & curate sources", value="sources"),
            questionary.Choice("⚔️   Review competitive landscape", value="competitive"),
            questionary.Choice("📊  Review table proposals", value="tables"),
            questionary.Choice("👥  Investigate syndicate & investors", value="syndicate"),
            questionary.Separator("── Coming Soon ──"),
            questionary.Choice("📝  Select best sections across versions (planned)", value="sections"),
            questionary.Choice("✓   Review fact-check findings (planned)", value="fact_check"),
        ],
        style=q_style,
    ).ask()

    if action in ("sections", "fact_check"):
        console.print("[warning]This feature is not yet implemented.[/]")
        return

    if action == "sources":
        flow_integrate_sources(firm, deal)
    elif action == "competitive":
        flow_integrate_competitive(firm, deal)
    elif action == "tables":
        console.print("[warning]Table review flow coming soon.[/]")
    elif action == "syndicate":
        console.print("[warning]Syndicate investigation flow coming soon.[/]")


def flow_integrate_sources(firm: dict, deal: dict):
    """Walk through source catalog for curation."""
    if not deal["versions"]:
        console.print("[error]No versions to integrate from.[/]")
        return

    # Find latest version with source catalog
    latest = get_latest_output_dir(deal["path"])
    if not latest:
        console.print("[error]No output found.[/]")
        return

    catalog_dir = latest / "3-source-catalog"
    if not catalog_dir.exists():
        console.print("[error]No source catalog found. Run the pipeline first.[/]")
        return

    catalog_files = sorted(catalog_dir.glob("*-Complete-Source-List.md"))
    console.print(f"\n[accent]Found {len(catalog_files)} section source catalogs[/]")
    console.print(f"[dim]From: {latest.name}[/]\n")

    # For now, show what's available
    for f in catalog_files:
        section_name = f.stem.replace("-Complete-Source-List", "").replace("-", " ").title()
        line_count = len(f.read_text().splitlines())
        console.print(f"  📋 {section_name} ({line_count} lines)")

    console.print()
    console.print("[warning]Interactive source curation coming in next iteration.[/]")
    console.print(f"[dim]Source catalogs available at: {catalog_dir}[/]")


def flow_integrate_competitive(firm: dict, deal: dict):
    """Walk through competitive landscape for curation."""
    if not deal["versions"]:
        console.print("[error]No versions to integrate from.[/]")
        return

    # Collect competitors across all versions
    all_competitors = {}
    for v in deal["versions"]:
        eval_file = Path(v["path"]) / "1-competitive-evaluation.json"
        if eval_file.exists():
            try:
                data = json.loads(eval_file.read_text())
                for comp in data.get("evaluated_competitors", []):
                    name = comp.get("name", "Unknown")
                    if name not in all_competitors:
                        all_competitors[name] = {
                            **comp,
                            "first_seen": v["version"],
                            "seen_in": [v["version"]],
                        }
                    else:
                        all_competitors[name]["seen_in"].append(v["version"])
            except (json.JSONDecodeError, KeyError):
                pass

    if not all_competitors:
        console.print("[error]No competitive data found across versions.[/]")
        return

    console.print(f"\n[accent]Found {len(all_competitors)} unique competitors across {len(deal['versions'])} versions[/]\n")

    # Show summary table
    comp_table = Table(box=box.ROUNDED, border_style=ACCENT)
    comp_table.add_column("Competitor", style="bold")
    comp_table.add_column("AI Classification")
    comp_table.add_column("Versions Seen")
    comp_table.add_column("Key Differentiator", max_width=40)

    for name, comp in sorted(all_competitors.items()):
        comp_table.add_row(
            name,
            comp.get("classification", "?"),
            ", ".join(comp.get("seen_in", [])),
            (comp.get("key_differentiator", "") or "")[:40],
        )

    console.print(comp_table)
    console.print()
    console.print("[warning]Interactive competitive curation coming in next iteration.[/]")


# ── Post-Run Menu ────────────────────────────────────────────────────

def post_run_menu(firm: dict, deal: dict):
    """Show options after a pipeline run completes."""
    action = questionary.select(
        "What next?",
        choices=[
            questionary.Choice("📤  Export this memo (HTML/PDF/Word)", value="export"),
            questionary.Choice("📄  Generate one-pager", value="one_pager"),
            questionary.Choice("🔧  Improve a weak section", value="improve"),
            questionary.Choice("🏠  Return to main menu", value="menu"),
            questionary.Choice("❌  Exit", value="exit"),
        ],
        style=q_style,
    ).ask()

    if action == "export":
        flow_export()
    elif action == "one_pager":
        flow_one_pager()
    elif action == "improve":
        flow_improve()
    elif action == "exit":
        sys.exit(0)


# ── Main Loop ────────────────────────────────────────────────────────

def main():
    """Main application loop."""
    show_banner()

    # Check for API keys
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[warning]⚠ ANTHROPIC_API_KEY not set.[/]")
        console.print("[dim]Add it to .env or: export ANTHROPIC_API_KEY=sk-...[/]\n")

    while True:
        action = main_menu()

        if action == "exit" or action is None:
            console.print("\n[dim]Goodbye![/]\n")
            break
        elif action == "generate":
            flow_generate()
        elif action == "one_pager":
            flow_one_pager()
        elif action == "export":
            flow_export()
        elif action == "improve":
            flow_improve()
        elif action == "integrate":
            flow_integrate()
        elif action == "agent":
            flow_agent()

        console.print()


if __name__ == "__main__":
    main()
