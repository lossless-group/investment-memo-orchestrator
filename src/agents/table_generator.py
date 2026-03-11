"""
Table Generator Agent - Identifies tabular data opportunities and generates markdown tables.

Scans written memo sections and structured data from upstream agents to find content
that would be more effectively communicated in tabular format. Generates markdown tables,
inserts them into relevant sections, and handles overflow data through anchor links.

Runs after link enrichment, before visualization enrichment and TOC generation.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..state import MemoState
from ..utils import get_output_dir_from_state


# ---------------------------------------------------------------------------
# Table schema defaults (used when no outline or custom schema is configured)
# ---------------------------------------------------------------------------

DEFAULT_TABLE_SCHEMAS = {
    "funding_history": {
        "target_sections": ["funding", "terms"],
        "placement": "after_prose",
        "min_rows": 2,
        "columns": [
            {"name": "Round", "source_field": "round", "align": "left"},
            {"name": "Date", "source_field": "date", "align": "center"},
            {"name": "Amount", "source_field": "amount", "align": "right"},
            {"name": "Pre-Money", "source_field": "pre_money", "align": "right"},
            {"name": "Lead Investor", "source_field": "lead", "align": "left"},
            {
                "name": "Participants",
                "source_field": "participants",
                "align": "left",
                "overflow": {"max_inline": 3, "anchor_pattern": "{round}-participants"},
            },
        ],
    },
    "team_credentials": {
        "target_sections": ["team", "organization"],
        "placement": "after_prose",
        "min_rows": 2,
        "columns": [
            {"name": "Role", "source_field": "role", "align": "left"},
            {"name": "Name", "source_field": "name", "align": "left"},
            {"name": "Prior Experience", "source_field": "experience", "align": "left"},
            {"name": "Notable Achievement", "source_field": "achievement", "align": "left"},
        ],
    },
    "market_sizing": {
        "target_sections": ["market", "opening", "opportunity"],
        "placement": "after_prose",
        "min_rows": 2,
        "columns": [
            {"name": "Market Segment", "source_field": "segment", "align": "left"},
            {"name": "Size", "source_field": "size", "align": "right"},
            {"name": "Growth", "source_field": "growth", "align": "right"},
            {"name": "Source", "source_field": "source", "align": "left"},
        ],
    },
    "traction_metrics": {
        "target_sections": ["traction", "milestones", "offering"],
        "placement": "after_prose",
        "min_rows": 3,
        "columns": [
            {"name": "Metric", "source_field": "metric", "align": "left"},
            {"name": "Value", "source_field": "value", "align": "right"},
            {"name": "Period", "source_field": "period", "align": "center"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Structured data extractors — pull table rows from state
# ---------------------------------------------------------------------------


def extract_funding_history(state: MemoState) -> List[Dict[str, str]]:
    """Extract funding round data from deck analysis and research."""
    rows = []

    deck = state.get("deck_analysis")
    if deck:
        funding_ask = deck.get("funding_ask", "")
        if funding_ask:
            # Parse the funding ask into a row
            rows.append({
                "round": _guess_round_from_text(funding_ask),
                "date": "Current",
                "amount": _extract_dollar_amount(funding_ask),
                "pre_money": "—",
                "lead": "—",
                "participants": "",
            })

    # Try to extract from research data
    research = state.get("research")
    if research and isinstance(research, dict):
        funding_data = research.get("funding", {})
        if isinstance(funding_data, dict):
            rounds = funding_data.get("rounds", [])
            if isinstance(rounds, list):
                for r in rounds:
                    if isinstance(r, dict):
                        rows.append({
                            "round": r.get("round", "—"),
                            "date": r.get("date", "—"),
                            "amount": r.get("amount", "—"),
                            "pre_money": r.get("pre_money", r.get("valuation", "—")),
                            "lead": r.get("lead", r.get("lead_investor", "—")),
                            "participants": r.get("participants", ""),
                        })

    return rows


def extract_team_credentials(state: MemoState) -> List[Dict[str, str]]:
    """Extract team member data from deck analysis."""
    rows = []

    deck = state.get("deck_analysis")
    if deck:
        members = deck.get("team_members", [])
        if isinstance(members, list):
            for m in members:
                if isinstance(m, dict):
                    background = m.get("background", "")
                    # Split background into experience and achievement
                    experience, achievement = _split_background(background)
                    rows.append({
                        "role": m.get("role", "—"),
                        "name": m.get("name", "—"),
                        "experience": experience,
                        "achievement": achievement,
                    })

    return rows


def extract_market_sizing(state: MemoState) -> List[Dict[str, str]]:
    """Extract TAM/SAM/SOM data from deck analysis and research."""
    rows = []

    deck = state.get("deck_analysis")
    if deck:
        market_size = deck.get("market_size", {})
        if isinstance(market_size, dict):
            for segment, value in market_size.items():
                if value and str(value).lower() not in ("not mentioned", "n/a", "none", ""):
                    rows.append({
                        "segment": segment.upper() if segment.lower() in ("tam", "sam", "som") else segment,
                        "size": str(value),
                        "growth": "—",
                        "source": "Pitch Deck",
                    })

    return rows


def extract_traction_metrics(state: MemoState) -> List[Dict[str, str]]:
    """Extract traction metrics from deck analysis."""
    rows = []

    deck = state.get("deck_analysis")
    if deck:
        metrics = deck.get("traction_metrics", [])
        if isinstance(metrics, list):
            for m in metrics:
                if isinstance(m, dict):
                    rows.append({
                        "metric": m.get("metric", "—"),
                        "value": m.get("value", "—"),
                        "period": m.get("period", m.get("date", "—")),
                    })

    return rows


# ---------------------------------------------------------------------------
# Table formatting helpers
# ---------------------------------------------------------------------------


def format_overflow_cell(
    items: list,
    max_inline: int,
    anchor_id: str,
    anchor_label: str = "Full list",
) -> str:
    """Format a cell with overflow items linked to an anchor."""
    if not items:
        return "—"
    if isinstance(items, str):
        items = [i.strip() for i in items.split(",") if i.strip()]
    if len(items) <= max_inline:
        return ", ".join(items)
    inline = ", ".join(items[:max_inline])
    return f"{inline}, [{anchor_label}](#{anchor_id})"


def generate_overflow_details(
    overflow_data: Dict[str, List[str]],
    detail_header: str,
) -> str:
    """Generate the detail section for overflow data below the table."""
    if not overflow_data:
        return ""
    lines = [f"\n#### {detail_header}\n"]
    for anchor_id, items in overflow_data.items():
        display_name = anchor_id.replace("-", " ").title()
        lines.append(f"##### {display_name} {{#{anchor_id}}}")
        lines.append(", ".join(items))
        lines.append("")
    return "\n".join(lines)


def build_markdown_table(
    columns: List[Dict[str, Any]],
    rows: List[Dict[str, str]],
    subject_company: Optional[str] = None,
) -> Tuple[str, Dict[str, List[str]]]:
    """
    Build a markdown table string from column definitions and row data.

    Returns:
        Tuple of (table_markdown, overflow_data) where overflow_data maps
        anchor IDs to lists of items that overflowed.
    """
    if not rows:
        return "", {}

    overflow_data: Dict[str, List[str]] = {}

    # Header row
    headers = [c["name"] for c in columns]
    header_line = "| " + " | ".join(headers) + " |"

    # Alignment row
    align_parts = []
    for c in columns:
        a = c.get("align", "left")
        if a == "right":
            align_parts.append("---:")
        elif a == "center":
            align_parts.append(":---:")
        else:
            align_parts.append(":---")
    align_line = "| " + " | ".join(align_parts) + " |"

    # Data rows
    data_lines = []
    for row in rows:
        cells = []
        for c in columns:
            field = c.get("source_field", "")
            raw_value = row.get(field, "—")

            # Handle overflow columns
            overflow_cfg = c.get("overflow")
            if overflow_cfg and raw_value and raw_value != "—":
                items = raw_value if isinstance(raw_value, list) else [
                    i.strip() for i in str(raw_value).split(",") if i.strip()
                ]
                max_inline = overflow_cfg.get("max_inline", 3)
                pattern = overflow_cfg.get("anchor_pattern", "{name}-details")
                # Build anchor ID from row data
                anchor_base = row.get(columns[0]["source_field"], "item")
                anchor_id = _make_anchor_id(pattern, row, anchor_base)

                if len(items) > max_inline:
                    overflow_data[anchor_id] = items

                raw_value = format_overflow_cell(items, max_inline, anchor_id)

            cell_text = str(raw_value) if raw_value else "—"

            # Bold the subject company row
            if subject_company and c == columns[0]:
                name_lower = cell_text.lower().strip("*[]() ")
                if subject_company.lower() in name_lower or name_lower in subject_company.lower():
                    cell_text = f"**{cell_text}**"

            cells.append(cell_text)

        data_lines.append("| " + " | ".join(cells) + " |")

    table = "\n".join([header_line, align_line] + data_lines)
    return table, overflow_data


def _make_anchor_id(pattern: str, row: Dict[str, str], fallback: str) -> str:
    """Generate an anchor ID from a pattern and row data."""
    anchor_id = pattern
    for key, val in row.items():
        anchor_id = anchor_id.replace(f"{{{key}}}", str(val))
    # Clean up any remaining placeholders
    anchor_id = re.sub(r"\{[^}]+\}", fallback, anchor_id)
    # Slugify
    anchor_id = re.sub(r"[^a-z0-9-]", "-", anchor_id.lower())
    anchor_id = re.sub(r"-+", "-", anchor_id).strip("-")
    return anchor_id


# ---------------------------------------------------------------------------
# Section matching — find which section file a table should be inserted into
# ---------------------------------------------------------------------------


def find_target_section(
    section_files: List[Path],
    target_keywords: List[str],
) -> Optional[Path]:
    """Find the section file that best matches the target keywords."""
    for section_file in section_files:
        stem = section_file.stem.lower().replace("-", " ").replace("_", " ")
        for keyword in target_keywords:
            if keyword.lower() in stem:
                return section_file
    return None


def section_has_table(content: str) -> bool:
    """Check if a section already contains a markdown table."""
    # A markdown table has at least a header row and separator row
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if re.match(r"^\|.*\|$", line.strip()) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r"^\|[\s:|-]+\|$", next_line):
                return True
    return False


def find_insertion_point(content: str) -> int:
    """
    Find the optimal insertion point for a table in section content.

    Strategy: insert before the last paragraph break before a ### header,
    or at the end of the section if no subsection headers.
    """
    lines = content.split("\n")

    # Find subsection headers (###)
    subsection_indices = [
        i for i, line in enumerate(lines) if re.match(r"^###\s+", line)
    ]

    if subsection_indices:
        # Insert before the last subsection that isn't the first line
        for idx in reversed(subsection_indices):
            if idx > 2:
                # Walk back to find a blank line
                insert_at = idx
                while insert_at > 0 and lines[insert_at - 1].strip() == "":
                    insert_at -= 1
                return insert_at

    # No good subsection boundary — append at end
    return len(lines)


# ---------------------------------------------------------------------------
# Prose pattern detection — find tabular data embedded in prose
# ---------------------------------------------------------------------------

PROSE_DETECTION_PROMPT = """You are analyzing a memo section to identify data that could be presented as a markdown table.

Look for these patterns:
1. **Temporal series**: Numbers associated with time periods showing progression (e.g., "revenue grew from $1M in 2022 to $3M in 2023")
2. **Entity comparisons**: Multiple entities with the same attributes (e.g., "Competitor A raised $X, Competitor B raised $Y")
3. **Structured lists**: Bullet lists where each item has consistent data fields
4. **Funding rounds**: Investment rounds with dates and amounts
5. **Team credentials**: Multiple team members with roles and backgrounds listed inline

IMPORTANT:
- Only identify data that has 3+ comparable data points (2 is not enough for a table)
- Do NOT identify data that is already in a table
- Do NOT identify data that is too qualitative/narrative for tabulation
- If no tabular data is found, return an empty array

Return JSON:
{
    "tables": [
        {
            "table_type": "temporal_series|entity_comparison|funding_rounds|team_list|other",
            "description": "Brief description of what this table would show",
            "columns": ["Column1", "Column2", ...],
            "rows": [
                {"Column1": "value", "Column2": "value"},
                ...
            ],
            "insert_after_text": "First 10 words of the paragraph this table should follow..."
        }
    ]
}

SECTION CONTENT:
---
{content}
---"""


def detect_prose_tables(
    content: str,
    model: ChatAnthropic,
    section_name: str,
) -> List[Dict[str, Any]]:
    """Use LLM to detect tabular data patterns in prose content."""
    if len(content) < 200:
        return []

    # Skip if section already has tables
    if section_has_table(content):
        return []

    try:
        response = model.invoke([
            SystemMessage(content="You are a data analyst. Return ONLY valid JSON, no markdown fences."),
            HumanMessage(content=PROSE_DETECTION_PROMPT.format(content=content)),
        ])

        result = _parse_json_response(response.content)
        if result and isinstance(result.get("tables"), list):
            return result["tables"]
    except Exception as e:
        print(f"    Warning: Prose detection failed for {section_name}: {e}")

    return []


def _parse_json_response(content: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown code blocks."""
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", content)
    cleaned = re.sub(r"```\s*$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try finding JSON object
    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _guess_round_from_text(text: str) -> str:
    """Guess funding round name from text."""
    text_lower = text.lower()
    for round_name in ["series d", "series c", "series b", "series a", "pre-seed", "pre seed", "seed"]:
        if round_name in text_lower:
            return round_name.replace("pre seed", "Pre-Seed").title()
    return "Current Round"


def _extract_dollar_amount(text: str) -> str:
    """Extract dollar amount from text."""
    match = re.search(r"\$[\d,.]+[KMBkmb]?", text)
    return match.group(0) if match else "—"


def _split_background(background: str) -> Tuple[str, str]:
    """Split a background string into experience and notable achievement."""
    if not background:
        return "—", "—"

    sentences = re.split(r"(?<=[.!])\s+", background)
    if len(sentences) <= 1:
        return background[:120], "—"

    # Build experience from first N sentences until we have enough context
    experience = sentences[0]
    idx = 1
    while len(experience) < 50 and idx < len(sentences) - 1:
        experience = f"{experience} {sentences[idx]}"
        idx += 1
    if len(experience) > 120:
        experience = experience[:117] + "..."

    # Find the most "notable" sentence (contains superlatives, numbers, awards)
    notable_patterns = re.compile(r"(patent|acquired|founded|raised|\$|award|publish|Nature|first)", re.I)
    achievement = "—"
    for s in sentences[1:]:
        if notable_patterns.search(s):
            achievement = s.strip()
            if len(achievement) > 80:
                achievement = achievement[:77] + "..."
            break

    return experience, achievement


# ---------------------------------------------------------------------------
# Main agent function
# ---------------------------------------------------------------------------


def table_generator_agent(state: MemoState) -> Dict[str, Any]:
    """
    Table Generator Agent.

    Scans sections and structured state data for tabular data opportunities.
    Generates markdown tables and inserts them into relevant sections.
    Saves table artifacts to 2-tables/ directory.

    Args:
        state: Current memo state with deck_analysis, research, etc.

    Returns:
        State update with tables_generated info and messages.
    """
    company_name = state["company_name"]

    # --- Resolve output directory ---
    try:
        output_dir = get_output_dir_from_state(state)
        sections_dir = output_dir / "2-sections"
    except FileNotFoundError:
        print("⊘ Table generator skipped — no output directory found")
        return {"messages": ["Table generator skipped — no output directory"]}

    if not sections_dir.exists():
        print("⊘ Table generator skipped — no sections directory")
        return {"messages": ["Table generator skipped — no sections directory"]}

    # --- Initialize LLM for prose detection ---
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")

    model = ChatAnthropic(
        model=os.getenv("DEFAULT_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        temperature=0,
        max_tokens=4000,
    )

    print(f"\n📊 Generating tables for {company_name}...")

    section_files = sorted(sections_dir.glob("*.md"))
    tables_dir = output_dir / "2-tables"
    tables_dir.mkdir(exist_ok=True)

    generated_tables: List[Dict[str, Any]] = []
    sections_updated: List[str] = []

    # ------------------------------------------------------------------
    # Phase 1: Generate tables from structured state data
    # ------------------------------------------------------------------

    structured_extractors = [
        ("funding_history", extract_funding_history),
        ("team_credentials", extract_team_credentials),
        ("market_sizing", extract_market_sizing),
        ("traction_metrics", extract_traction_metrics),
    ]

    for table_type, extractor in structured_extractors:
        schema = DEFAULT_TABLE_SCHEMAS.get(table_type)
        if not schema:
            continue

        rows = extractor(state)
        min_rows = schema.get("min_rows", 3)

        if len(rows) < min_rows:
            print(f"  ⊘ {table_type}: only {len(rows)} rows (need {min_rows}), skipping")
            continue

        # Find the target section
        target = find_target_section(section_files, schema["target_sections"])
        if not target:
            print(f"  ⊘ {table_type}: no matching section found")
            continue

        # Check if section already has a table
        section_content = target.read_text()
        if section_has_table(section_content):
            print(f"  ⊘ {table_type}: section {target.name} already has a table, skipping")
            continue

        # Build the table
        table_md, overflow = build_markdown_table(
            schema["columns"],
            rows,
            subject_company=company_name,
        )

        if not table_md:
            continue

        # Generate overflow details if any
        overflow_md = ""
        if overflow:
            detail_header = "Details"
            for col in schema["columns"]:
                if col.get("overflow"):
                    detail_header = col.get("overflow", {}).get("detail_header", "Details")
                    break
            overflow_md = generate_overflow_details(overflow, detail_header)

        # Insert table into section
        full_table_block = f"\n{table_md}\n{overflow_md}" if overflow_md else f"\n{table_md}\n"
        insertion_idx = find_insertion_point(section_content)
        lines = section_content.split("\n")
        lines.insert(insertion_idx, full_table_block)
        updated_content = "\n".join(lines)

        # Save updated section
        target.write_text(updated_content)

        # Save table artifact
        artifact_name = table_type.replace("_", "-")
        (tables_dir / f"{artifact_name}.md").write_text(table_md)

        table_info = {
            "id": artifact_name,
            "type": table_type,
            "data_source": "structured_state",
            "inserted_in": target.name,
            "rows": len(rows),
            "columns": [c["name"] for c in schema["columns"]],
            "overflow_anchors": list(overflow.keys()),
        }
        generated_tables.append(table_info)
        sections_updated.append(target.name)

        print(f"  ✓ {table_type}: {len(rows)} rows → {target.name}")

    # ------------------------------------------------------------------
    # Phase 2: Detect tabular data in prose via LLM
    # ------------------------------------------------------------------

    for section_file in section_files:
        section_name = section_file.stem
        content = section_file.read_text()

        if len(content) < 200:
            continue

        # Skip sections we already inserted a table into
        if section_file.name in sections_updated:
            continue

        # Skip if section already has a table
        if section_has_table(content):
            continue

        detected = detect_prose_tables(content, model, section_name)
        if not detected:
            continue

        for i, table_data in enumerate(detected):
            cols = table_data.get("columns", [])
            rows = table_data.get("rows", [])

            if len(rows) < 3 or len(cols) < 2:
                continue

            # Build simple column definitions from detected columns
            col_defs = [
                {"name": c, "source_field": c, "align": "left"}
                for c in cols
            ]

            table_md, overflow = build_markdown_table(col_defs, rows, subject_company=company_name)
            if not table_md:
                continue

            # Insert into section
            content = section_file.read_text()  # Re-read in case we modified it
            insertion_idx = find_insertion_point(content)
            lines = content.split("\n")
            lines.insert(insertion_idx, f"\n{table_md}\n")
            section_file.write_text("\n".join(lines))

            # Save artifact
            table_type_name = table_data.get("table_type", "prose-detected")
            artifact_name = f"{section_name}-{table_type_name}-{i}"
            (tables_dir / f"{artifact_name}.md").write_text(table_md)

            table_info = {
                "id": artifact_name,
                "type": table_type_name,
                "data_source": "prose_detection",
                "inserted_in": section_file.name,
                "rows": len(rows),
                "columns": cols,
                "overflow_anchors": [],
            }
            generated_tables.append(table_info)
            sections_updated.append(section_file.name)

            print(f"  ✓ prose-detected ({table_type_name}): {len(rows)} rows → {section_file.name}")

    # ------------------------------------------------------------------
    # Save manifest
    # ------------------------------------------------------------------

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "company": company_name,
        "schema_source": "default",
        "tables": generated_tables,
        "summary": {
            "total_tables": len(generated_tables),
            "sections_updated": list(set(sections_updated)),
            "sources": {
                "structured_state": sum(1 for t in generated_tables if t["data_source"] == "structured_state"),
                "prose_detection": sum(1 for t in generated_tables if t["data_source"] == "prose_detection"),
            },
        },
    }

    (tables_dir / "tables-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )

    total = len(generated_tables)
    updated = len(set(sections_updated))

    if total > 0:
        print(f"\n✓ Table generation complete: {total} tables inserted into {updated} sections")
        print(f"  Artifacts saved to {tables_dir}/")
    else:
        print("\n⊘ No tables generated (insufficient structured data or prose patterns)")

    return {
        "tables_generated": manifest,
        "messages": [
            f"Table generation: {total} tables saved to 2-tables/, inserted into {updated} sections"
        ],
    }
