#!/usr/bin/env python3

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

from src.versioning import VersionManager
from src.artifacts import sanitize_filename
from src.state import MemoState
from src.agents.scorecard_agent import scorecard_agent


def load_state(artifact_dir: Path, console: Console) -> MemoState:
    state_file = artifact_dir / "state.json"
    if not state_file.exists():
        console.print(f"[red]Error: state.json not found in {artifact_dir}[/red]")
        sys.exit(1)
    with open(state_file) as f:
        state_data = json.load(f)
    console.print("[green]✓ Loaded state.json[/green]")
    return state_data  # already matches MemoState structure persisted by workflow


def resolve_artifact_dir(target: str, version: str | None, console: Console) -> Path:
    target_path = Path(target)
    if target_path.exists() and target_path.is_dir():
        return target_path

    safe_name = sanitize_filename(target)
    output_root = Path("output")

    if version:
        artifact_dir = output_root / f"{safe_name}-{version}"
    else:
        version_mgr = VersionManager(output_root)
        if safe_name not in version_mgr.versions_data:
            console.print(
                f"[red]Error: No versions found for '{target}' in output/versions.json[/red]"
            )
            sys.exit(1)
        latest_version = version_mgr.versions_data[safe_name]["latest_version"]
        artifact_dir = output_root / f"{safe_name}-{latest_version}"

    if not artifact_dir.exists():
        console.print(f"[red]Error: Artifact directory not found:[/red] {artifact_dir}")
        sys.exit(1)

    return artifact_dir


def main() -> None:
    console = Console()
    load_dotenv()

    parser = argparse.ArgumentParser(
        description=(
            "Generate an emerging manager scorecard for a fund memo using "
            "the Hypernova framework."
        )
    )
    parser.add_argument(
        "target",
        help=(
            "Company name (e.g., 'Avalanche') or path to artifact directory "
            "(e.g., output/Avalanche-v0.0.5)"
        ),
    )
    parser.add_argument(
        "--version",
        help="Specific version (e.g., 'v0.0.5') if target is a company name.",
    )

    args = parser.parse_args()

    artifact_dir = resolve_artifact_dir(args.target, args.version, console)

    console.print(
        Panel(
            f"[bold cyan]Generating Scorecard for: {args.target}[/bold cyan]\n"
            f"[dim]Artifact directory: {artifact_dir}[/dim]"
        )
    )

    state = load_state(artifact_dir, console)

    # Ensure required context exists
    if state.get("investment_type") != "fund":
        console.print("[yellow]Scorecard is designed for fund memos; skipping.[/yellow]")
        sys.exit(0)

    if state.get("outline_name") != "lpcommit-emerging-manager":
        console.print(
            "[yellow]Outline is not 'lpcommit-emerging-manager'; "
            "scorecard not generated.[/yellow]"
        )
        sys.exit(0)

    result = scorecard_agent(state)  # type: ignore[arg-type]

    messages = result.get("messages", [])
    for msg in messages:
        console.print(f"[green]{msg}[/green]")

    scorecard_path = result.get("scorecard_path")
    if scorecard_path:
        console.print(f"[bold]Scorecard file:[/bold] {scorecard_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
