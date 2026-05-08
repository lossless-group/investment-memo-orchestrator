#!/usr/bin/env python3
"""Extract a structured TeamRoster from any organization URL.

Implements [[Team-and-People-Metadata-Ingestion]] phase 2 (discovery + extraction).

USAGE: Always run with venv Python:
    .venv/bin/python cli/extract_team_roster.py --url https://example.com

Or activate venv first:
    source .venv/bin/activate && python cli/extract_team_roster.py --url ...

Discovery is link-graph-driven via Firecrawl:
    1. firecrawl.map(root, search="team")
    2. firecrawl.scrape(root, formats=["links"]) — read nav/footer
    3. Probe canonical paths (/team, /about, ...) — last resort

Phase 3 will populate Photo.is_externally_stable.
Phase 4 will fill social/photo gaps via fallback agents.

Requirements:
    - FIRECRAWL_API_KEY in .env
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from firecrawl import Firecrawl

from src.agents.team_roster_enrichment import enrich_roster_socials
from src.schemas.team_roster import TeamRoster, TeamRosterExtraction
from src.scrapers.team_roster_scraper import FirecrawlScraper


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract structured team roster (names, titles, photos, socials) "
        "from any organization URL.",
    )
    parser.add_argument(
        "--url",
        required=False,
        help="Root URL of the organization (e.g., https://example.com). "
        "Required unless --from-memo is used.",
    )
    parser.add_argument(
        "--name",
        help="Organization name (for disambiguation when search is needed).",
    )
    parser.add_argument(
        "--description",
        help="One-line organization description (for disambiguation).",
    )
    parser.add_argument(
        "--from-memo",
        metavar="COMPANY",
        help="Read url/name/description from data/{COMPANY}.json instead of flags.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory. Defaults to output/{slug}-roster/.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached roster and re-crawl.",
    )
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="Skip the photo + social fallback enrichment pass (Phase 4).",
    )
    parser.add_argument(
        "--allow-linkedin-photo",
        action="store_true",
        help="Permit public LinkedIn photos as a fallback source. Off by default.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery only; print candidate URLs without calling extract.",
    )
    return parser.parse_args(argv)


def _slug(value: str) -> str:
    """Filesystem-safe slug. If `value` is a URL, derive from netloc minus
    leading `www.` and trailing TLD; otherwise sanitize the raw string.
    """
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        host = parsed.netloc.removeprefix("www.")
        # Drop trailing TLD: "lossless.group" -> "lossless"; "co.example.com" -> "co.example"
        host = host.rsplit(".", 1)[0] if "." in host else host
        value = host
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "org"


def _load_from_memo(company: str, console: Console) -> dict:
    data_path = Path("data") / f"{company}.json"
    if not data_path.exists():
        console.print(f"[red]Error:[/red] {data_path} not found")
        sys.exit(2)
    return json.loads(data_path.read_text())


def main() -> int:
    load_dotenv()
    console = Console()
    args = parse_args()

    # Resolve url / name / description from --from-memo if present.
    if args.from_memo:
        memo_data = _load_from_memo(args.from_memo, console)
        url = args.url or memo_data.get("url")
        name = args.name or args.from_memo
        description = args.description or memo_data.get("description")
    else:
        url = args.url
        name = args.name
        description = args.description

    if not url:
        console.print("[red]Error:[/red] one of --url or --from-memo is required.")
        return 2

    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] FIRECRAWL_API_KEY not set in .env")
        return 2

    organization = name or url
    output_dir = args.output_dir or (Path("output") / f"{_slug(organization)}-roster")
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "team-roster.json"

    if cache_path.exists() and not args.refresh:
        console.print(
            f"[yellow]![/yellow] Cached roster exists at {cache_path}. "
            "Pass --refresh to re-crawl."
        )
        return 0

    console.print(
        Panel(
            f"[bold cyan]extract_team_roster[/bold cyan]\n"
            f"[dim]url:[/dim] {url}\n"
            f"[dim]organization:[/dim] {organization}\n"
            f"[dim]output:[/dim] {output_dir}",
        )
    )

    scraper = FirecrawlScraper(api_key=api_key)

    # --- Discovery ---
    console.print("\n[bold]Discovering team page(s)...[/bold]")
    candidates = scraper.discover_team_pages(url)
    if not candidates:
        console.print("[red]No candidate team pages found.[/red]")
        return 1
    console.print(f"[green]✓[/green] {len(candidates)} candidate URL(s):")
    for c in candidates:
        console.print(f"   • {c}")

    if args.dry_run:
        console.print("\n[yellow]--dry-run set; skipping extract.[/yellow]")
        return 0

    # --- Extraction ---
    console.print("\n[bold]Extracting roster via Firecrawl extract...[/bold]")
    raw = scraper.extract_roster(candidates)

    # Save raw for debugging regardless of validation outcome.
    raw_path = output_dir / "team-roster.raw.json"
    raw_path.write_text(json.dumps(raw, indent=2, default=str))

    try:
        extracted = TeamRosterExtraction.model_validate(raw)
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]Validation failed:[/red] {e}")
        console.print(f"[dim]Raw payload saved to {raw_path}[/dim]")
        return 1

    roster = TeamRoster(
        organization=organization,
        organization_url=url,
        team_page_url=extracted.team_page_url or (candidates[0] if candidates else None),
        members=extracted.members,
        crawled_at=datetime.now(timezone.utc),
        crawler="firecrawl",
        notes=description,
    )

    # --- Socials enrichment (Phase 2 acceptance criterion) ---
    if not args.no_enrich and roster.members:
        console.print(
            f"\n[bold]Enriching socials via Firecrawl search "
            f"({len(roster.members)} members × 1 search each)...[/bold]"
        )
        fc = Firecrawl(api_key=api_key)
        roster = enrich_roster_socials(roster, fc)

    cache_path.write_text(roster.model_dump_json(indent=2))
    _write_markdown_preview(roster, output_dir / "team-roster.md")

    console.print(f"\n[green]✓ Wrote[/green] {cache_path}")
    console.print(f"[green]✓ Wrote[/green] {output_dir / 'team-roster.md'}")
    console.print(f"\n[bold]Members extracted:[/bold] {len(roster.members)}")
    for m in roster.members:
        photo = "📷" if m.photo else "  "
        socials = sum(1 for v in m.socials.model_dump().values() if v)
        console.print(f"  {photo} {m.name} — {m.title}  ({socials} socials)")

    if any(m.photo for m in roster.members):
        console.print(
            "\n[dim]Note: photo.is_externally_stable is False until Phase 3 probes them.[/dim]"
        )
    return 0


def _write_markdown_preview(roster: TeamRoster, path: Path) -> None:
    lines: list[str] = [
        f"# Team — {roster.organization}",
        "",
        f"_Crawled {roster.crawled_at.isoformat()} via {roster.crawler}_",
        "",
        f"- Organization URL: <{roster.organization_url}>",
        f"- Team page URL: {f'<{roster.team_page_url}>' if roster.team_page_url else '(none)'}",
        f"- Members: {len(roster.members)}",
        "",
    ]
    for m in roster.members:
        lines.append(f"## {m.name}")
        lines.append(f"_{m.title}_")
        lines.append("")
        if m.bio_short:
            lines.append(m.bio_short)
            lines.append("")
        elif m.bio_long:
            lines.append(m.bio_long)
            lines.append("")
        if m.photo:
            lines.append(
                f"- Photo: <{m.photo.url}> "
                f"(source: {m.photo.source}, stable: {m.photo.is_externally_stable})"
            )
        socials = m.socials.model_dump()
        for k, v in socials.items():
            if v:
                lines.append(f"- {k}: <{v}>")
        if m.confidence:
            lines.append(f"- confidence: {m.confidence:.2f}")
        lines.append("")
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
