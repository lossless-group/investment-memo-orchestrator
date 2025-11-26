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
    use_llm: bool = False
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

    # Step 3: Build analysis result
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

        # Extracted Data (populated by extractors in Phase 2)
        "financials": None,
        "cap_table": None,
        "legal_docs": [],
        "team": None,
        "traction": None,
        "competitive": None,
        "pitch_deck": None,

        # Synthesis (populated in Phase 3)
        "key_facts": {},
        "data_gaps": _identify_data_gaps(classification_summary),
        "conflicts": [],

        # Metadata
        "processing_duration_seconds": duration,
        "extraction_notes": [
            f"Scanned {len(inventory)} documents",
            f"Classification sources: {classification_summary['by_source']}",
        ],
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

    Args:
        output_dir: Directory to save artifacts
        analysis: DataroomAnalysis result
        company_name: Company name for report header
    """
    # Save structured JSON
    json_path = output_dir / "0-dataroom-analysis.json"
    with open(json_path, "w") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False, default=str)

    print(f"   📄 Saved: {json_path.name}")

    # Save human-readable markdown
    md_path = output_dir / "0-dataroom-analysis.md"
    report = format_dataroom_analysis_report(analysis, company_name)
    with open(md_path, "w") as f:
        f.write(report)

    print(f"   📄 Saved: {md_path.name}")


def format_dataroom_analysis_report(analysis: DataroomAnalysis, company_name: str) -> str:
    """Format dataroom analysis as human-readable markdown report."""
    md = f"# Dataroom Analysis: {company_name}\n\n"
    md += f"**Generated**: {analysis['analysis_date']}\n\n"
    md += f"**Source**: `{analysis['dataroom_path']}`\n\n"
    md += f"**Processing Time**: {analysis['processing_duration_seconds']:.1f}s\n\n"
    md += "---\n\n"

    # Document Inventory Summary
    md += "## Document Inventory\n\n"
    md += f"**Total Documents**: {analysis['document_count']}\n\n"

    md += "### By Type\n\n"
    md += "| Document Type | Count |\n"
    md += "|--------------|-------|\n"
    for doc_type, count in sorted(analysis['documents_by_type'].items()):
        md += f"| {doc_type.replace('_', ' ').title()} | {count} |\n"
    md += "\n"

    # Document List
    md += "### Document Details\n\n"

    # Group by type
    docs_by_type = {}
    for doc in analysis['inventory']:
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
    if analysis.get('data_gaps'):
        md += "## Data Gaps\n\n"
        md += "The following document types are missing or not detected:\n\n"
        for gap in analysis['data_gaps']:
            md += f"- ⚠️ {gap}\n"
        md += "\n"

    # Extraction Notes
    if analysis.get('extraction_notes'):
        md += "## Processing Notes\n\n"
        for note in analysis['extraction_notes']:
            md += f"- {note}\n"
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
