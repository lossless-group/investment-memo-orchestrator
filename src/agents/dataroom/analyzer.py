"""
Dataroom Analyzer Orchestrator

Main entry point for analyzing investment datarooms.
Scans, classifies, and outputs structured analysis to artifacts.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from .document_scanner import scan_dataroom, get_inventory_summary
from .document_classifier import classify_documents, get_classification_summary
from .dataroom_state import DataroomAnalysis, DocumentInventoryItem


def analyze_dataroom(
    dataroom_path: str,
    company_name: Optional[str] = None,
    output_dir: Optional[Path] = None,
    use_llm: bool = True
) -> DataroomAnalysis:
    """
    Analyze a dataroom and output structured artifacts.

    Args:
        dataroom_path: Path to the dataroom directory
        company_name: Optional company name (derived from path if not provided)
        output_dir: Optional output directory (uses standard output/ pattern if not provided)
        use_llm: Whether to use LLM for uncertain classifications

    Returns:
        DataroomAnalysis with complete analysis results
    """
    start_time = datetime.now()
    dataroom = Path(dataroom_path)

    # Derive company name from dataroom folder if not provided
    if not company_name:
        company_name = dataroom.name.replace(" Dataroom", "").replace("-", " ").strip()

    print(f"\n{'='*60}")
    print(f"DATAROOM ANALYZER")
    print(f"{'='*60}")
    print(f"Company: {company_name}")
    print(f"Path: {dataroom_path}")
    print(f"{'='*60}\n")

    # Step 1: Scan dataroom
    print("📁 Scanning dataroom...")
    inventory = scan_dataroom(dataroom_path)
    print(f"   Found {len(inventory)} documents\n")

    # Step 2: Classify documents
    print("🏷️  Classifying documents...")
    inventory = classify_documents(inventory, use_llm=use_llm)
    classification_summary = get_classification_summary(inventory)
    print(f"   Classified {classification_summary['total']} documents")
    print(f"   High confidence: {classification_summary['by_confidence']['high']}")
    print(f"   Medium confidence: {classification_summary['by_confidence']['medium']}")
    print(f"   Low/Unknown: {classification_summary['by_confidence']['low']}\n")

    # Step 3: Run extractors on classified documents
    extraction_results = _run_extractors(inventory, use_llm=use_llm)

    # Step 4: Build analysis result
    inventory_summary = get_inventory_summary(inventory)
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    analysis: DataroomAnalysis = {
        "dataroom_path": str(dataroom_path),
        "analysis_date": datetime.now().isoformat(),

        # Inventory
        "document_count": len(inventory),
        "documents_by_type": classification_summary["by_type"],
        "inventory": inventory,

        # Extracted Data
        "financials": extraction_results.get("financials"),
        "cap_table": extraction_results.get("cap_table"),
        "legal_docs": extraction_results.get("legal_docs", []),
        "team": extraction_results.get("team"),
        "traction": extraction_results.get("traction"),
        "competitive": extraction_results.get("competitive"),
        "pitch_deck": extraction_results.get("pitch_deck"),

        # Synthesis (populated in Phase 3)
        "key_facts": _extract_key_facts(extraction_results),
        "data_gaps": _identify_data_gaps(classification_summary),
        "conflicts": [],

        # Metadata
        "processing_duration_seconds": duration,
        "extraction_notes": [
            f"Scanned {len(inventory)} documents",
            f"Classification sources: {classification_summary['by_source']}",
        ] + extraction_results.get("notes", []),
    }

    # Step 4: Save artifacts
    if output_dir is None:
        output_dir = _get_or_create_output_dir(company_name)

    save_dataroom_analysis_artifacts(output_dir, analysis, company_name)

    print(f"\n{'='*60}")
    print(f"✓ Analysis complete in {duration:.1f}s")
    print(f"✓ Artifacts saved to: {output_dir}")
    print(f"{'='*60}\n")

    return analysis


def _run_extractors(inventory: list, use_llm: bool = True) -> dict:
    """
    Run specialized extractors on classified documents.

    Args:
        inventory: List of classified DocumentInventoryItem dicts
        use_llm: Whether to use LLM for extraction

    Returns:
        Dict with extraction results by type
    """
    from .extractors import extract_competitive_data

    results = {
        "financials": None,
        "cap_table": None,
        "legal_docs": [],
        "team": None,
        "traction": None,
        "competitive": None,
        "pitch_deck": None,
        "notes": []
    }

    # Group documents by type
    docs_by_type = {}
    for doc in inventory:
        doc_type = doc["document_type"]
        if doc_type not in docs_by_type:
            docs_by_type[doc_type] = []
        docs_by_type[doc_type].append(doc)

    # Run competitive extractor
    if "competitive_analysis" in docs_by_type:
        comp_docs = docs_by_type["competitive_analysis"]
        print(f"🔍 Extracting competitive data from {len(comp_docs)} documents...")
        try:
            results["competitive"] = extract_competitive_data(comp_docs, use_llm=use_llm)
            competitor_count = len(results["competitive"].get("competitors", []))
            results["notes"].append(f"Extracted {competitor_count} competitors from competitive analysis")
            print(f"   ✓ Found {competitor_count} competitors")
        except Exception as e:
            results["notes"].append(f"Competitive extraction error: {str(e)}")
            print(f"   ✗ Error: {e}")

    # Placeholder for other extractors (Phase 2 continued)
    # TODO: Add financial_extractor
    # TODO: Add cap_table_extractor
    # TODO: Add team_extractor
    # TODO: Add traction_extractor

    return results


def _extract_key_facts(extraction_results: dict) -> dict:
    """
    Extract key facts from extraction results for quick reference.

    Args:
        extraction_results: Results from _run_extractors

    Returns:
        Dict of key facts organized by category
    """
    key_facts = {}

    # Competitive facts
    competitive = extraction_results.get("competitive")
    if competitive:
        competitors = competitive.get("competitors", [])
        if competitors:
            key_facts["competitive"] = {
                "competitor_count": len(competitors),
                "competitors": [c.get("name") for c in competitors],
                "high_threat": [c.get("name") for c in competitors if c.get("threat_level") == "High"],
                "key_differentiators_count": len(competitive.get("key_differentiators", [])),
            }

    # Financial facts (placeholder for Phase 2)
    # TODO: Extract key financial metrics

    # Team facts (placeholder for Phase 2)
    # TODO: Extract team highlights

    return key_facts


def _get_or_create_output_dir(company_name: str) -> Path:
    """Get or create output directory following project conventions."""
    from ...artifacts import sanitize_filename
    from ...versioning import VersionManager

    safe_name = sanitize_filename(company_name)
    version_mgr = VersionManager(Path("output"))
    version = version_mgr.get_next_version(safe_name)

    output_dir = Path("output") / f"{safe_name}-{version}"
    output_dir.mkdir(parents=True, exist_ok=True)

    return output_dir


def _identify_data_gaps(classification_summary: dict) -> list:
    """Identify missing document types that would strengthen analysis."""
    gaps = []

    expected_types = {
        "pitch_deck": "Pitch deck for company overview",
        "financial_statements": "Historical financials",
        "financial_projections": "Financial model/projections",
        "cap_table": "Cap table for ownership structure",
        "competitive_analysis": "Competitive landscape analysis",
        "team_bios": "Team backgrounds and bios",
    }

    by_type = classification_summary.get("by_type", {})

    for doc_type, description in expected_types.items():
        if doc_type not in by_type or by_type[doc_type] == 0:
            gaps.append(f"Missing: {description} ({doc_type})")

    return gaps


def save_dataroom_analysis_artifacts(
    output_dir: Path,
    analysis: DataroomAnalysis,
    company_name: str
) -> None:
    """
    Save dataroom analysis artifacts (JSON and markdown).

    Each extraction type gets its own numbered artifact files:
    - 0-dataroom-inventory.json/md - Document inventory and classification
    - 1-competitive-analysis.json/md - Competitive landscape data
    - (future) 2-financial-analysis.json/md
    - (future) 3-team-analysis.json/md
    - etc.

    Args:
        output_dir: Directory to save artifacts
        analysis: DataroomAnalysis result
        company_name: Company name for report header
    """
    # 0. Save document inventory (lightweight, no extracted data)
    inventory_data = {
        "dataroom_path": analysis["dataroom_path"],
        "analysis_date": analysis["analysis_date"],
        "document_count": analysis["document_count"],
        "documents_by_type": analysis["documents_by_type"],
        "inventory": analysis["inventory"],
        "data_gaps": analysis["data_gaps"],
        "processing_duration_seconds": analysis["processing_duration_seconds"],
    }

    json_path = output_dir / "0-dataroom-inventory.json"
    with open(json_path, "w") as f:
        json.dump(inventory_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"   📄 Saved: {json_path.name}")

    md_path = output_dir / "0-dataroom-inventory.md"
    report = format_inventory_report(inventory_data, company_name)
    with open(md_path, "w") as f:
        f.write(report)
    print(f"   📄 Saved: {md_path.name}")

    # 1. Save competitive analysis (if present)
    if analysis.get("competitive"):
        comp_json_path = output_dir / "1-competitive-analysis.json"
        with open(comp_json_path, "w") as f:
            json.dump(analysis["competitive"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {comp_json_path.name}")

        comp_md_path = output_dir / "1-competitive-analysis.md"
        comp_report = format_competitive_report(analysis["competitive"], company_name)
        with open(comp_md_path, "w") as f:
            f.write(comp_report)
        print(f"   📄 Saved: {comp_md_path.name}")

    # 2. Save financial analysis (if present) - placeholder for Phase 2
    if analysis.get("financials"):
        fin_json_path = output_dir / "2-financial-analysis.json"
        with open(fin_json_path, "w") as f:
            json.dump(analysis["financials"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {fin_json_path.name}")

    # 3. Save team analysis (if present) - placeholder for Phase 2
    if analysis.get("team"):
        team_json_path = output_dir / "3-team-analysis.json"
        with open(team_json_path, "w") as f:
            json.dump(analysis["team"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {team_json_path.name}")


def format_inventory_report(inventory_data: dict, company_name: str) -> str:
    """Format document inventory as human-readable markdown report."""
    md = f"# Dataroom Inventory: {company_name}\n\n"
    md += f"**Generated**: {inventory_data['analysis_date']}\n\n"
    md += f"**Source**: `{inventory_data['dataroom_path']}`\n\n"
    md += f"**Processing Time**: {inventory_data['processing_duration_seconds']:.1f}s\n\n"
    md += "---\n\n"

    # Document Inventory Summary
    md += "## Document Summary\n\n"
    md += f"**Total Documents**: {inventory_data['document_count']}\n\n"

    md += "### By Type\n\n"
    md += "| Document Type | Count |\n"
    md += "|--------------|-------|\n"
    for doc_type, count in sorted(inventory_data['documents_by_type'].items()):
        md += f"| {doc_type.replace('_', ' ').title()} | {count} |\n"
    md += "\n"

    # Document List
    md += "### Document Details\n\n"

    # Group by type
    docs_by_type = {}
    for doc in inventory_data['inventory']:
        dtype = doc['document_type']
        if dtype not in docs_by_type:
            docs_by_type[dtype] = []
        docs_by_type[dtype].append(doc)

    for dtype in sorted(docs_by_type.keys()):
        docs = docs_by_type[dtype]
        md += f"#### {dtype.replace('_', ' ').title()} ({len(docs)})\n\n"

        for doc in docs:
            confidence = doc['classification_confidence']
            conf_indicator = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.5 else "🔴"
            size_kb = doc['file_size_bytes'] / 1024

            md += f"- {conf_indicator} **{doc['filename']}**\n"
            md += f"  - Size: {size_kb:.1f} KB"
            if doc.get('page_count'):
                md += f" | Pages: {doc['page_count']}"
            md += f"\n"
            md += f"  - Confidence: {confidence:.0%} ({doc['classification_source']})\n"
            if doc.get('classification_reasoning'):
                md += f"  - Reasoning: {doc['classification_reasoning']}\n"
            md += "\n"

    # Data Gaps
    if inventory_data.get('data_gaps'):
        md += "## Data Gaps\n\n"
        md += "The following document types are missing or not detected:\n\n"
        for gap in inventory_data['data_gaps']:
            md += f"- {gap}\n"
        md += "\n"

    return md


def format_competitive_report(competitive_data: dict, company_name: str) -> str:
    """Format competitive analysis as human-readable markdown report."""
    md = f"# Competitive Analysis: {company_name}\n\n"
    md += "---\n\n"

    # Competitor Overview Table
    competitors = competitive_data.get('competitors', [])
    if competitors:
        md += "## Competitor Overview\n\n"
        md += f"**Competitors Identified**: {len(competitors)}\n\n"

        md += "| Competitor | Threat Level | Strengths | Weaknesses |\n"
        md += "|------------|--------------|-----------|------------|\n"
        for c in competitors:
            threat = c.get('threat_level', 'N/A')
            threat_icon = "🔴" if threat == "High" else "🟡" if threat == "Medium" else "🟢"
            strengths_count = len(c.get('strengths', []))
            weaknesses_count = len(c.get('weaknesses', []))
            md += f"| {c.get('name', 'Unknown')} | {threat_icon} {threat} | {strengths_count} | {weaknesses_count} |\n"
        md += "\n"

    # Detailed Competitor Profiles
    if competitors:
        md += "## Detailed Competitor Profiles\n\n"
        for c in competitors:
            name = c.get('name', 'Unknown')
            threat = c.get('threat_level', 'N/A')
            threat_icon = "🔴" if threat == "High" else "🟡" if threat == "Medium" else "🟢"

            md += f"### {name} {threat_icon}\n\n"

            if c.get('description'):
                md += f"{c['description']}\n\n"

            if c.get('website'):
                md += f"**Website**: [{c['website']}]({c['website']})\n\n"

            # Strengths
            strengths = c.get('strengths', [])
            if strengths:
                md += "**Strengths:**\n"
                for s in strengths:
                    md += f"- {s}\n"
                md += "\n"

            # Weaknesses
            weaknesses = c.get('weaknesses', [])
            if weaknesses:
                md += "**Weaknesses:**\n"
                for w in weaknesses:
                    md += f"- {w}\n"
                md += "\n"

            # Feature comparison if available
            features = c.get('feature_comparison', {})
            if features:
                md += "**Feature Comparison:**\n"
                for feature, has_it in features.items():
                    icon = "✅" if has_it else "❌"
                    md += f"- {icon} {feature}\n"
                md += "\n"

            md += "---\n\n"

    # Key Differentiators
    differentiators = competitive_data.get('key_differentiators', [])
    if differentiators:
        md += "## Key Differentiators\n\n"
        md += f"*{len(differentiators)} differentiators identified*\n\n"
        for d in differentiators:
            md += f"- {d}\n"
        md += "\n"

    # Winning Angles
    winning_angles = competitive_data.get('winning_angles', [])
    if winning_angles:
        md += "## Winning Angles (Sales Talking Points)\n\n"
        md += f"*{len(winning_angles)} talking points identified*\n\n"
        for w in winning_angles:
            md += f"- {w}\n"
        md += "\n"

    # Discovery Questions
    discovery_questions = competitive_data.get('discovery_questions', [])
    if discovery_questions:
        md += "## Discovery Questions\n\n"
        md += f"*{len(discovery_questions)} discovery questions*\n\n"
        for q in discovery_questions:
            md += f"- {q}\n"
        md += "\n"

    # Market Positioning
    positioning = competitive_data.get('market_positioning')
    if positioning:
        md += "## Market Positioning\n\n"
        md += f"{positioning}\n\n"

    # SWOT Analysis
    swot = competitive_data.get('swot')
    if swot:
        md += "## SWOT Analysis\n\n"

        if swot.get('strengths'):
            md += "### Strengths\n"
            for s in swot['strengths']:
                md += f"- {s}\n"
            md += "\n"

        if swot.get('weaknesses'):
            md += "### Weaknesses\n"
            for w in swot['weaknesses']:
                md += f"- {w}\n"
            md += "\n"

        if swot.get('opportunities'):
            md += "### Opportunities\n"
            for o in swot['opportunities']:
                md += f"- {o}\n"
            md += "\n"

        if swot.get('threats'):
            md += "### Threats\n"
            for t in swot['threats']:
                md += f"- {t}\n"
            md += "\n"

    # Source Documents
    source_docs = competitive_data.get('source_documents', [])
    if source_docs:
        md += "## Source Documents\n\n"
        for doc in source_docs:
            md += f"- {doc}\n"
        md += "\n"

    return md


# CLI entry point for standalone use
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.agents.dataroom.analyzer <dataroom_path> [company_name]")
        print("\nExample:")
        print("  python -m src.agents.dataroom.analyzer data/Secure-Inputs/Hydden\\ Dataroom")
        print("  python -m src.agents.dataroom.analyzer data/Secure-Inputs/Hydden\\ Dataroom \"Hydden\"")
        sys.exit(1)

    dataroom_path = sys.argv[1]
    company_name = sys.argv[2] if len(sys.argv) > 2 else None

    analyze_dataroom(dataroom_path, company_name)
