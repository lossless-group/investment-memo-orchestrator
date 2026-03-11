"""
Diagram Generator Agent - Creates visual diagrams from memo data.

Phase 1 (MVP): TAM/SAM/SOM concentric circle diagrams using matplotlib.
Future phases will add Mermaid-based structured diagrams (competitive landscapes,
timelines, funding waterfalls, etc.).

Runs after table generation, before visualization enrichment.
Outputs SVG (primary) + PNG (fallback) to output/{Company}-v0.0.x/diagrams/.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..state import MemoState
from ..utils import get_output_dir_from_state


# ---------------------------------------------------------------------------
# Market data extraction
# ---------------------------------------------------------------------------


def _parse_dollar_value(text: str) -> Optional[float]:
    """
    Parse a dollar string like '$50B', '$12.5 billion', '$800M' into a float (in dollars).

    Returns None if parsing fails.
    """
    if not text or not isinstance(text, str):
        return None

    text = text.strip().replace(",", "")

    # Match patterns like $50B, $12.5M, $800K, $1.2T
    match = re.search(r"\$?([\d.]+)\s*(T|B|billion|M|million|K|thousand)?", text, re.IGNORECASE)
    if not match:
        return None

    value = float(match.group(1))
    suffix = (match.group(2) or "").lower()

    multipliers = {
        "t": 1e12, "trillion": 1e12,
        "b": 1e9, "billion": 1e9,
        "m": 1e6, "million": 1e6,
        "k": 1e3, "thousand": 1e3,
    }

    return value * multipliers.get(suffix, 1.0)


def _format_dollar_label(value: float) -> str:
    """Format a dollar value into a compact label like '$50B' or '$800M'."""
    if value >= 1e12:
        return f"${value / 1e12:.1f}T".replace(".0T", "T")
    if value >= 1e9:
        return f"${value / 1e9:.1f}B".replace(".0B", "B")
    if value >= 1e6:
        return f"${value / 1e6:.0f}M"
    if value >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:.0f}"


def extract_market_sizing_data(state: MemoState) -> Dict[str, Any]:
    """
    Extract TAM/SAM/SOM values from deck analysis and research data.

    Returns dict with keys 'tam', 'sam', 'som' (float values in dollars),
    plus optional 'tam_growth', 'sam_growth', 'som_growth' (strings).
    """
    result = {}

    # Try deck analysis first (most structured source)
    deck = state.get("deck_analysis")
    if deck and isinstance(deck, dict):
        market_size = deck.get("market_size", {})
        if isinstance(market_size, dict):
            for key in ("tam", "sam", "som"):
                raw = market_size.get(key) or market_size.get(key.upper())
                if raw and str(raw).lower() not in ("not mentioned", "n/a", "none", ""):
                    parsed = _parse_dollar_value(str(raw))
                    if parsed:
                        result[key] = parsed

            # Check for growth rates
            for key in ("tam_growth", "sam_growth", "som_growth", "cagr"):
                raw = market_size.get(key)
                if raw and str(raw).lower() not in ("not mentioned", "n/a", "none", ""):
                    result[key] = str(raw)

    # Supplement from research data
    research = state.get("research")
    if research and isinstance(research, dict):
        market_data = research.get("market", {})
        if isinstance(market_data, dict):
            for key in ("tam", "sam", "som"):
                if key not in result:
                    raw = market_data.get(key) or market_data.get(key.upper())
                    if raw:
                        parsed = _parse_dollar_value(str(raw))
                        if parsed:
                            result[key] = parsed

    return result


# ---------------------------------------------------------------------------
# TAM/SAM/SOM concentric circle renderer (matplotlib)
# ---------------------------------------------------------------------------


def render_tam_sam_som(
    tam: float,
    sam: float,
    som: float,
    output_path: Path,
    growth_rates: Optional[Dict[str, str]] = None,
    company_name: str = "",
) -> Tuple[Path, Path]:
    """
    Render a TAM/SAM/SOM bubble diagram using matplotlib.

    Three adjacent circles sized proportionally to market values, arranged
    left-to-right (TAM largest, SOM smallest). Each bubble has a callout
    line connecting to a label block on the right with the acronym, dollar
    value, full name, and optional growth rate.

    Args:
        tam: Total Addressable Market value in dollars
        sam: Serviceable Addressable Market value in dollars
        som: Serviceable Obtainable Market value in dollars
        output_path: Directory to save SVG and PNG files
        growth_rates: Optional dict with 'tam_growth', 'sam_growth', 'som_growth'
        company_name: Company name for title

    Returns:
        Tuple of (svg_path, png_path)
    """
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt
    import math

    fig, ax = plt.subplots(1, 1, figsize=(12, 6))

    # Color palette — professional blues, darkest for TAM, lightest for SOM
    palette = [
        {"key": "tam", "fill": "#1a365d", "label_color": "#1a365d",
         "name": "Total Addressable Market", "value": tam},
        {"key": "sam", "fill": "#2b6cb0", "label_color": "#2b6cb0",
         "name": "Serviceable Addressable Market", "value": sam},
        {"key": "som", "fill": "#4299e1", "label_color": "#4299e1",
         "name": "Serviceable Obtainable Market", "value": som},
    ]
    growth = growth_rates or {}

    # --- Compute radii (area-proportional) ---
    max_radius = 2.2
    for item in palette:
        item["radius"] = max_radius * math.sqrt(item["value"] / tam) if tam > 0 else max_radius * 0.3
    # Ensure minimum visible size for smallest bubble
    for item in palette:
        item["radius"] = max(item["radius"], 0.35)

    # --- Position bubbles horizontally, bottoms aligned ---
    # Arrange left-to-right: TAM, SAM, SOM with small gaps between
    gap = 0.4
    cx = 0.0
    for item in palette:
        r = item["radius"]
        item["cx"] = cx + r
        item["cy"] = r  # bottom-aligned: center at y=radius
        cx += 2 * r + gap

    total_width = cx - gap
    # Center the group horizontally
    x_offset = -total_width / 2
    for item in palette:
        item["cx"] += x_offset

    # --- Draw bubbles ---
    for item in palette:
        circle = plt.Circle(
            (item["cx"], item["cy"]), item["radius"],
            color=item["fill"], alpha=0.9, zorder=2,
        )
        ax.add_patch(circle)

    # --- Callout labels on the right side ---
    # All labels are stacked vertically on the right, connected to their
    # bubble by a thin leader line (elbow style).
    label_x = max(item["cx"] + item["radius"] for item in palette) + 1.8
    label_spacing = 1.4

    # Stack labels top-to-bottom: TAM, SAM, SOM
    label_top = palette[0]["cy"] + palette[0]["radius"] + 0.2
    for i, item in enumerate(palette):
        label_y = label_top - (i * label_spacing)

        # Leader line: from bubble edge to label
        # Horizontal line from bubble rightmost point to a common x, then up/down to label
        bubble_edge_x = item["cx"] + item["radius"]
        elbow_x = label_x - 1.0  # vertical segment x

        # Draw leader: bubble edge -> elbow -> label
        ax.plot(
            [bubble_edge_x, elbow_x, elbow_x, label_x - 0.6],
            [item["cy"], item["cy"], label_y, label_y],
            color=item["fill"], linewidth=1.5, solid_capstyle="round", zorder=1,
        )
        # Small dot at the bubble connection point
        ax.plot(bubble_edge_x, item["cy"], "o",
                color=item["fill"], markersize=4, zorder=3)

        # Color swatch
        swatch_size = 0.25
        ax.add_patch(plt.Rectangle(
            (label_x - 0.5, label_y - swatch_size / 2),
            swatch_size, swatch_size,
            color=item["fill"], zorder=3,
        ))

        # Label text: acronym + dollar value on first line, full name below
        acronym = item["key"].upper()
        dollar = _format_dollar_label(item["value"])
        growth_key = f"{item['key']}_growth"
        growth_str = growth.get(growth_key, growth.get("cagr", "")) if i == 0 else growth.get(growth_key, "")

        primary = f"{acronym}  {dollar}"
        if growth_str:
            primary += f"  ({growth_str})"

        ax.text(label_x, label_y + 0.15, primary,
                ha="left", va="center", fontsize=12, fontweight="bold",
                color=item["label_color"], zorder=5)
        ax.text(label_x, label_y - 0.2, item["name"],
                ha="left", va="center", fontsize=9,
                color="#718096", zorder=5)

    # --- Title ---
    title = "Market Sizing"
    if company_name:
        title = f"{company_name} — Market Sizing"
    ax.set_title(title, fontsize=16, fontweight="bold", pad=16, color="#1a202c")

    # --- Styling ---
    # Compute bounds
    all_left = min(item["cx"] - item["radius"] for item in palette)
    all_bottom = 0
    all_top = max(item["cy"] + item["radius"] for item in palette)

    ax.set_xlim(all_left - 0.8, label_x + 4.5)
    ax.set_ylim(all_bottom - 0.8, all_top + 1.0)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")

    # Save both formats
    output_path.mkdir(parents=True, exist_ok=True)
    svg_path = output_path / "03-tam-sam-som.svg"
    png_path = output_path / "03-tam-sam-som.png"

    fig.savefig(str(svg_path), format="svg", bbox_inches="tight", dpi=150,
                facecolor="white", edgecolor="none")
    fig.savefig(str(png_path), format="png", bbox_inches="tight", dpi=200,
                facecolor="white", edgecolor="none")

    plt.close(fig)

    return svg_path, png_path


# ---------------------------------------------------------------------------
# Section insertion — embed diagram reference into markdown
# ---------------------------------------------------------------------------


def insert_diagram_reference(
    section_path: Path,
    diagram_filename: str,
    alt_text: str = "TAM/SAM/SOM Market Sizing",
) -> bool:
    """
    Insert an image reference into a section file.

    Inserts after the first paragraph (after the section header and opening text)
    to avoid disrupting the narrative flow.

    Returns True if inserted, False if already present.
    """
    content = section_path.read_text()

    # Check if diagram is already referenced
    if diagram_filename in content:
        return False

    image_md = f"\n![{alt_text}](diagrams/{diagram_filename})\n"

    # Find insertion point: after the first paragraph break following a header
    lines = content.split("\n")
    insert_idx = None

    found_header = False
    found_content = False
    for i, line in enumerate(lines):
        if line.startswith("#"):
            found_header = True
            continue
        if found_header and line.strip():
            found_content = True
            continue
        if found_content and not line.strip():
            # First blank line after header+content — insert after this paragraph
            insert_idx = i + 1
            break

    if insert_idx is None:
        # Fallback: append before the last non-empty line
        insert_idx = len(lines)

    lines.insert(insert_idx, image_md)
    section_path.write_text("\n".join(lines))
    return True


# ---------------------------------------------------------------------------
# Target section finder
# ---------------------------------------------------------------------------


def find_market_section(sections_dir: Path) -> Optional[Path]:
    """Find the market context section file."""
    for f in sorted(sections_dir.glob("*.md")):
        stem = f.stem.lower()
        if "market" in stem:
            return f
    return None


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def diagram_generator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Diagram Generator Agent (Phase 1: TAM/SAM/SOM).

    Scans state data for market sizing information and generates a concentric
    circle diagram if TAM/SAM/SOM values are available. Saves SVG + PNG to
    the diagrams/ directory and inserts an image reference into the Market
    Context section.

    Args:
        state: Current memo state with deck_analysis, research, etc.

    Returns:
        State update with diagrams_generated info and messages.
    """
    company_name = state["company_name"]

    # --- Resolve output directory ---
    try:
        output_dir = get_output_dir_from_state(state)
        sections_dir = output_dir / "2-sections"
    except FileNotFoundError:
        print("⊘ Diagram generator skipped — no output directory found")
        return {"messages": ["Diagram generator skipped — no output directory"]}

    if not sections_dir.exists():
        print("⊘ Diagram generator skipped — no sections directory")
        return {"messages": ["Diagram generator skipped — no sections directory"]}

    print(f"\n📐 Generating diagrams for {company_name}...")

    diagrams_dir = output_dir / "diagrams"
    generated_diagrams: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Phase 1: TAM/SAM/SOM concentric circle diagram
    # ------------------------------------------------------------------

    market_data = extract_market_sizing_data(state)

    tam = market_data.get("tam")
    sam = market_data.get("sam")
    som = market_data.get("som")

    if tam and sam and som:
        print(f"  Found market sizing: TAM={_format_dollar_label(tam)}, "
              f"SAM={_format_dollar_label(sam)}, SOM={_format_dollar_label(som)}")

        try:
            growth_rates = {
                k: v for k, v in market_data.items()
                if k.endswith("_growth") or k == "cagr"
            }

            svg_path, png_path = render_tam_sam_som(
                tam=tam,
                sam=sam,
                som=som,
                output_path=diagrams_dir,
                growth_rates=growth_rates if growth_rates else None,
                company_name=company_name,
            )

            print(f"  ✓ TAM/SAM/SOM diagram saved: {svg_path.name}, {png_path.name}")

            # Insert reference into market section
            market_section = find_market_section(sections_dir)
            if market_section:
                inserted = insert_diagram_reference(
                    market_section,
                    "03-tam-sam-som.svg",
                    alt_text=f"{company_name} TAM/SAM/SOM Market Sizing",
                )
                if inserted:
                    print(f"  ✓ Image reference inserted into {market_section.name}")
                else:
                    print(f"  ⊘ Diagram already referenced in {market_section.name}")
            else:
                print("  ⊘ No market section found for diagram insertion")

            diagram_info = {
                "id": "tam-sam-som",
                "type": "concentric_circles",
                "renderer": "matplotlib",
                "section": market_section.name if market_section else None,
                "svg_path": f"diagrams/{svg_path.name}",
                "png_path": f"diagrams/{png_path.name}",
                "data": {
                    "tam": tam,
                    "sam": sam,
                    "som": som,
                    **growth_rates,
                },
            }
            generated_diagrams.append(diagram_info)

        except ImportError:
            print("  ⚠️  matplotlib not installed — skipping diagram generation")
            print("     Install with: uv pip install matplotlib")
            return {"messages": ["Diagram generator skipped — matplotlib not installed"]}
        except Exception as e:
            print(f"  ⚠️  Diagram generation failed: {e}")
            return {"messages": [f"Diagram generator error: {e}"]}
    else:
        missing = []
        if not tam:
            missing.append("TAM")
        if not sam:
            missing.append("SAM")
        if not som:
            missing.append("SOM")
        print(f"  ⊘ Insufficient market data (missing: {', '.join(missing)})")

    # ------------------------------------------------------------------
    # Save manifest
    # ------------------------------------------------------------------

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "company": company_name,
        "diagrams": generated_diagrams,
        "summary": {
            "total_diagrams": len(generated_diagrams),
            "renderers_used": list(set(d["renderer"] for d in generated_diagrams)),
        },
    }

    if generated_diagrams:
        diagrams_dir.mkdir(parents=True, exist_ok=True)
        (diagrams_dir / "diagram-manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False)
        )

    total = len(generated_diagrams)
    if total > 0:
        print(f"\n✓ Diagram generation complete: {total} diagram(s) created")
        print(f"  Artifacts saved to {diagrams_dir}/")
    else:
        print("\n⊘ No diagrams generated (insufficient data)")

    return {
        "diagrams_generated": manifest,
        "messages": [
            f"Diagram generation: {total} diagram(s) saved to diagrams/"
        ],
    }
