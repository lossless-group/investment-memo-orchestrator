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

    # Step 4: Build initial analysis result
    inventory_summary = get_inventory_summary(inventory)

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

        # Synthesis (will be populated below)
        "key_facts": _extract_key_facts(extraction_results),
        "data_gaps": _identify_data_gaps(classification_summary),
        "conflicts": [],

        # Metadata
        "processing_duration_seconds": 0,  # Will update at end
        "extraction_notes": [
            f"Scanned {len(inventory)} documents",
            f"Classification sources: {classification_summary['by_source']}",
        ] + extraction_results.get("notes", []),
    }

    # Step 5: Run synthesis (Phase 3 - cross-reference, conflicts, gaps)
    from .synthesizer import synthesize_dataroom
    synthesis_results = synthesize_dataroom(analysis)

    # Update analysis with synthesis results
    analysis["conflicts"] = synthesis_results.get("conflicts", [])
    analysis["data_gaps"] = synthesis_results.get("gaps", [])
    analysis["key_facts"]["unified_metrics"] = synthesis_results.get("unified", {}).get("company_metrics", {})

    # Calculate final duration
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    analysis["processing_duration_seconds"] = duration

    # Step 6: Save artifacts
    if output_dir is None:
        output_dir = _get_or_create_output_dir(company_name)

    save_dataroom_analysis_artifacts(output_dir, analysis, company_name, synthesis_results)

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
    from .extractors import extract_competitive_data, extract_cap_table_data, extract_financial_data, extract_traction_data, extract_team_data

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

    # Run cap table extractor
    if "cap_table" in docs_by_type:
        cap_docs = docs_by_type["cap_table"]
        print(f"📊 Extracting cap table data from {len(cap_docs)} documents...")
        try:
            results["cap_table"] = extract_cap_table_data(cap_docs, use_llm=use_llm)
            if results["cap_table"]:
                shareholder_count = len(results["cap_table"].get("shareholders", []))
                results["notes"].append(f"Extracted {shareholder_count} shareholders from cap table")
                print(f"   ✓ Found {shareholder_count} shareholders")
            else:
                print(f"   ⚠️ No cap table data extracted")
        except Exception as e:
            results["notes"].append(f"Cap table extraction error: {str(e)}")
            print(f"   ✗ Error: {e}")

    # Run financial extractor (handles both financial_statements and financial_projections)
    financial_docs = []
    for doc_type in ["financial_statements", "financial_projections"]:
        if doc_type in docs_by_type:
            financial_docs.extend(docs_by_type[doc_type])

    if financial_docs:
        print(f"💰 Extracting financial data from {len(financial_docs)} documents...")
        try:
            results["financials"] = extract_financial_data(financial_docs, use_llm=use_llm)
            if results["financials"]:
                results["notes"].append(f"Extracted financial data from {len(financial_docs)} documents")
                # Summarize what was found
                fin = results["financials"]
                if fin.get("revenue"):
                    periods = len(fin["revenue"])
                    print(f"   ✓ Found revenue data for {periods} periods")
                if fin.get("projections"):
                    print(f"   ✓ Found financial projections")
                if fin.get("headcount"):
                    print(f"   ✓ Found headcount data")
            else:
                print(f"   ⚠️ No financial data extracted")
        except Exception as e:
            results["notes"].append(f"Financial extraction error: {str(e)}")
            print(f"   ✗ Error: {e}")

    # Run traction extractor (handles traction_metrics, customer_list, pipeline_metrics, pitch_deck)
    traction_docs = []
    for doc_type in ["traction_metrics", "customer_list", "pipeline_metrics", "pitch_deck"]:
        if doc_type in docs_by_type:
            traction_docs.extend(docs_by_type[doc_type])

    if traction_docs:
        print(f"📈 Extracting traction data from {len(traction_docs)} documents...")
        try:
            results["traction"] = extract_traction_data(traction_docs, use_llm=use_llm)
            if results["traction"]:
                notes_list = []
                if results["traction"].get("customer_count"):
                    notes_list.append(f"{results['traction']['customer_count']} customers")
                if results["traction"].get("arr"):
                    notes_list.append(f"${results['traction']['arr']:,.0f} ARR")
                if results["traction"].get("pipeline_value"):
                    notes_list.append(f"${results['traction']['pipeline_value']:,.0f} pipeline")

                if notes_list:
                    results["notes"].append(f"Extracted traction: {', '.join(notes_list)}")
                    print(f"   ✓ Found: {', '.join(notes_list)}")
                else:
                    print(f"   ✓ Found traction data")
            else:
                print(f"   ⚠️ No traction data extracted")
        except Exception as e:
            results["notes"].append(f"Traction extraction error: {str(e)}")
            print(f"   ✗ Error: {e}")

    # Run team extractor (handles team_bios and pitch_deck documents)
    team_docs = []
    for doc_type in ["team_bios", "pitch_deck"]:
        if doc_type in docs_by_type:
            team_docs.extend(docs_by_type[doc_type])

    if team_docs:
        print(f"👥 Extracting team data from {len(team_docs)} documents...")
        try:
            results["team"] = extract_team_data(team_docs, use_llm=use_llm)
            if results["team"]:
                founder_count = len(results["team"].get("founders", []))
                leadership_count = len(results["team"].get("leadership", []))
                headcount = results["team"].get("total_headcount")

                notes_list = []
                if founder_count:
                    notes_list.append(f"{founder_count} founders")
                if leadership_count:
                    notes_list.append(f"{leadership_count} leaders")
                if headcount:
                    notes_list.append(f"{headcount} total headcount")

                if notes_list:
                    results["notes"].append(f"Extracted team: {', '.join(notes_list)}")
                    print(f"   ✓ Found: {', '.join(notes_list)}")
                else:
                    print(f"   ✓ Found team data")
            else:
                print(f"   ⚠️ No team data extracted")
        except Exception as e:
            results["notes"].append(f"Team extraction error: {str(e)}")
            print(f"   ✗ Error: {e}")

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

    # Cap table facts
    cap_table = extraction_results.get("cap_table")
    if cap_table:
        shareholders = cap_table.get("shareholders", [])
        key_facts["cap_table"] = {
            "shareholder_count": len(shareholders),
            "total_shares": cap_table.get("total_shares_outstanding"),
            "option_pool_pct": cap_table.get("option_pool_percentage"),
        }
        # Extract founder ownership
        founder_ownership = sum(
            s.get("ownership_percentage", 0)
            for s in shareholders
            if s.get("investor_type") == "Founder"
        )
        if founder_ownership > 0:
            key_facts["cap_table"]["founder_ownership_pct"] = founder_ownership

    # Financial facts
    financials = extraction_results.get("financials")
    if financials:
        key_facts["financials"] = {}

        # Latest ARR
        arr = financials.get("arr")
        if arr:
            latest_period = max(arr.keys()) if arr else None
            if latest_period:
                key_facts["financials"]["latest_arr"] = arr[latest_period]
                key_facts["financials"]["latest_arr_period"] = latest_period

        # Burn rate and runway
        if financials.get("burn_rate"):
            key_facts["financials"]["monthly_burn"] = financials["burn_rate"]
        if financials.get("runway_months"):
            key_facts["financials"]["runway_months"] = financials["runway_months"]

        # Headcount
        headcount = financials.get("headcount")
        if headcount:
            latest_period = max(headcount.keys()) if headcount else None
            if latest_period:
                key_facts["financials"]["headcount"] = headcount[latest_period]

    # Traction facts
    traction = extraction_results.get("traction")
    if traction:
        key_facts["traction"] = {}

        if traction.get("customer_count"):
            key_facts["traction"]["customer_count"] = traction["customer_count"]
        if traction.get("arr"):
            key_facts["traction"]["arr"] = traction["arr"]
        if traction.get("mrr"):
            key_facts["traction"]["mrr"] = traction["mrr"]
        if traction.get("retention_rate"):
            key_facts["traction"]["retention_rate"] = traction["retention_rate"]
        if traction.get("nps_score"):
            key_facts["traction"]["nps_score"] = traction["nps_score"]
        if traction.get("pipeline_value"):
            key_facts["traction"]["pipeline_value"] = traction["pipeline_value"]
        if traction.get("win_rate"):
            key_facts["traction"]["win_rate"] = traction["win_rate"]

        # Clean empty traction dict
        if not key_facts["traction"]:
            del key_facts["traction"]

    # Team facts
    team = extraction_results.get("team")
    if team:
        key_facts["team"] = {}

        founders = team.get("founders", [])
        if founders:
            key_facts["team"]["founder_count"] = len(founders)
            key_facts["team"]["founder_names"] = [f.get("name") for f in founders if f.get("name")]

            # Extract notable backgrounds
            notable_companies = []
            for founder in founders:
                for company in founder.get("previous_companies", []):
                    if company and company not in notable_companies:
                        notable_companies.append(company)
            if notable_companies:
                key_facts["team"]["notable_prior_companies"] = notable_companies[:5]

        leadership = team.get("leadership", [])
        if leadership:
            key_facts["team"]["leadership_count"] = len(leadership)

        if team.get("total_headcount"):
            key_facts["team"]["total_headcount"] = team["total_headcount"]

        if team.get("advisors"):
            key_facts["team"]["advisor_count"] = len(team["advisors"])

        if team.get("board_members"):
            key_facts["team"]["board_size"] = len(team["board_members"])

        # Clean empty team dict
        if not key_facts["team"]:
            del key_facts["team"]

    return key_facts


def _get_or_create_output_dir(company_name: str, firm: str = None) -> Path:
    """Get or create output directory following project conventions.

    Args:
        company_name: Name of the company
        firm: Optional firm name for firm-scoped outputs

    Returns:
        Path to the output directory
    """
    from ...artifacts import sanitize_filename, create_artifact_directory
    from ...versioning import VersionManager
    from ...paths import resolve_deal_context

    safe_name = sanitize_filename(company_name)

    # Get version manager - firm-aware
    if firm:
        ctx = resolve_deal_context(company_name, firm=firm)
        version_mgr = VersionManager(ctx.outputs_dir.parent if ctx.outputs_dir else Path("output"), firm=firm)
        version = version_mgr.get_next_version(safe_name)
        output_dir = create_artifact_directory(company_name, str(version), firm=firm)
    else:
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
    company_name: str,
    synthesis_results: dict = None
) -> None:
    """
    Save dataroom analysis artifacts (JSON and markdown).

    Each extraction type gets its own numbered artifact files:
    - 0-dataroom-inventory.json/md - Document inventory and classification
    - 1-competitive-analysis.json/md - Competitive landscape data
    - 2-cap-table.json/md - Cap table and ownership
    - 3-financial-analysis.json/md - Financial projections
    - 4-traction-analysis.json/md - Traction metrics
    - 5-team-analysis.json/md - Team profiles
    - 6-synthesis-report.json/md - Cross-reference, conflicts, gaps

    Args:
        output_dir: Directory to save artifacts
        analysis: DataroomAnalysis result
        company_name: Company name for report header
        synthesis_results: Optional synthesis results from synthesize_dataroom()
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

    # 2. Save cap table analysis (if present)
    if analysis.get("cap_table"):
        cap_json_path = output_dir / "2-cap-table.json"
        with open(cap_json_path, "w") as f:
            json.dump(analysis["cap_table"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {cap_json_path.name}")

        cap_md_path = output_dir / "2-cap-table.md"
        cap_report = format_cap_table_report(analysis["cap_table"], company_name)
        with open(cap_md_path, "w") as f:
            f.write(cap_report)
        print(f"   📄 Saved: {cap_md_path.name}")

    # 3. Save financial analysis (if present)
    if analysis.get("financials"):
        fin_json_path = output_dir / "3-financial-analysis.json"
        with open(fin_json_path, "w") as f:
            json.dump(analysis["financials"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {fin_json_path.name}")

        fin_md_path = output_dir / "3-financial-analysis.md"
        fin_report = format_financial_report(analysis["financials"], company_name)
        with open(fin_md_path, "w") as f:
            f.write(fin_report)
        print(f"   📄 Saved: {fin_md_path.name}")

    # 4. Save traction analysis (if present)
    if analysis.get("traction"):
        traction_json_path = output_dir / "4-traction-analysis.json"
        with open(traction_json_path, "w") as f:
            json.dump(analysis["traction"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {traction_json_path.name}")

        traction_md_path = output_dir / "4-traction-analysis.md"
        traction_report = format_traction_report(analysis["traction"], company_name)
        with open(traction_md_path, "w") as f:
            f.write(traction_report)
        print(f"   📄 Saved: {traction_md_path.name}")

    # 5. Save team analysis (if present)
    if analysis.get("team"):
        team_json_path = output_dir / "5-team-analysis.json"
        with open(team_json_path, "w") as f:
            json.dump(analysis["team"], f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {team_json_path.name}")

        team_md_path = output_dir / "5-team-analysis.md"
        team_report = format_team_report(analysis["team"], company_name)
        with open(team_md_path, "w") as f:
            f.write(team_report)
        print(f"   📄 Saved: {team_md_path.name}")

    # 6. Save synthesis report (conflicts, gaps, cross-references)
    if synthesis_results:
        # Save JSON with structured synthesis data
        synthesis_json_path = output_dir / "6-synthesis-report.json"
        synthesis_json_data = {
            "conflicts": synthesis_results.get("conflicts", []),
            "gaps": synthesis_results.get("gaps", []),
            "unified_metrics": synthesis_results.get("unified", {}),
            "analysis_date": analysis["analysis_date"],
        }
        with open(synthesis_json_path, "w") as f:
            json.dump(synthesis_json_data, f, indent=2, ensure_ascii=False, default=str)
        print(f"   📄 Saved: {synthesis_json_path.name}")

        # Save markdown report
        synthesis_md_path = output_dir / "6-synthesis-report.md"
        with open(synthesis_md_path, "w") as f:
            f.write(synthesis_results.get("report", "# Synthesis Report\n\nNo synthesis data available."))
        print(f"   📄 Saved: {synthesis_md_path.name}")


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


def format_cap_table_report(cap_table_data: dict, company_name: str) -> str:
    """Format cap table as human-readable markdown report."""
    md = f"# Cap Table: {company_name}\n\n"

    if cap_table_data.get("as_of_date"):
        md += f"**As of**: {cap_table_data['as_of_date']}\n\n"

    md += "---\n\n"

    # Ownership Summary
    md += "## Ownership Summary\n\n"

    if cap_table_data.get("total_shares_outstanding"):
        md += f"**Total Shares Outstanding**: {cap_table_data['total_shares_outstanding']:,}\n\n"

    if cap_table_data.get("fully_diluted_shares"):
        md += f"**Fully Diluted Shares**: {cap_table_data['fully_diluted_shares']:,}\n\n"

    # Shareholders Table
    shareholders = cap_table_data.get("shareholders", [])
    if shareholders:
        md += "## Shareholders\n\n"
        md += "| Shareholder | Shares | Ownership % | Class | Type |\n"
        md += "|-------------|--------|-------------|-------|------|\n"

        for sh in shareholders:
            name = sh.get("name", "Unknown")
            shares = sh.get("shares", 0)
            pct = sh.get("ownership_percentage", 0)
            share_class = sh.get("share_class", "Common")
            inv_type = sh.get("investor_type", "Unknown")

            shares_str = f"{shares:,}" if shares else "-"
            pct_str = f"{pct:.1f}%" if pct else "-"

            md += f"| {name} | {shares_str} | {pct_str} | {share_class} | {inv_type} |\n"

        md += "\n"

        # Ownership by type summary
        md += "### Ownership by Type\n\n"
        by_type = {}
        for sh in shareholders:
            inv_type = sh.get("investor_type", "Other")
            by_type[inv_type] = by_type.get(inv_type, 0) + sh.get("ownership_percentage", 0)

        for inv_type, total_pct in sorted(by_type.items(), key=lambda x: -x[1]):
            md += f"- **{inv_type}**: {total_pct:.1f}%\n"
        md += "\n"

    # Option Pool
    if any(cap_table_data.get(k) for k in ["option_pool_size", "option_pool_percentage", "options_granted", "options_available"]):
        md += "## Option Pool\n\n"

        if cap_table_data.get("option_pool_size"):
            md += f"- **Total Pool**: {cap_table_data['option_pool_size']:,} shares\n"
        if cap_table_data.get("option_pool_percentage"):
            md += f"- **Pool Percentage**: {cap_table_data['option_pool_percentage']:.1f}%\n"
        if cap_table_data.get("options_granted"):
            md += f"- **Issued Options**: {cap_table_data['options_granted']:,}\n"
        if cap_table_data.get("options_available"):
            md += f"- **Available Options**: {cap_table_data['options_available']:,}\n"
        md += "\n"

    # SAFEs
    safes = cap_table_data.get("safes", [])
    if safes:
        md += "## SAFEs\n\n"
        md += "| Investor | Amount | Valuation Cap | Discount |\n"
        md += "|----------|--------|---------------|----------|\n"
        for safe in safes:
            name = safe.get("investor_name", "Unknown")
            amount = f"${safe.get('amount_invested', 0):,.0f}"
            cap = f"${safe.get('valuation_cap', 0):,.0f}" if safe.get("valuation_cap") else "-"
            discount = f"{safe.get('discount_rate', 0)}%" if safe.get("discount_rate") else "-"
            md += f"| {name} | {amount} | {cap} | {discount} |\n"
        md += "\n"

    # Convertible Notes
    notes = cap_table_data.get("convertible_notes", [])
    if notes:
        md += "## Convertible Notes\n\n"
        md += "| Investor | Principal | Interest Rate | Maturity |\n"
        md += "|----------|-----------|---------------|----------|\n"
        for note in notes:
            name = note.get("investor_name", "Unknown")
            principal = f"${note.get('principal_amount', 0):,.0f}"
            rate = f"{note.get('interest_rate', 0)}%"
            maturity = note.get("maturity_date", "-")
            md += f"| {name} | {principal} | {rate} | {maturity} |\n"
        md += "\n"

    # Extraction Notes
    notes = cap_table_data.get("extraction_notes", [])
    if notes:
        md += "## Notes\n\n"
        for note in notes:
            md += f"- {note}\n"
        md += "\n"

    return md


def format_financial_report(financial_data: dict, company_name: str) -> str:
    """Format financial data as human-readable markdown report."""
    md = f"# Financial Analysis: {company_name}\n\n"

    if financial_data.get("extraction_date"):
        md += f"**Extracted**: {financial_data['extraction_date']}\n\n"

    md += f"**Currency**: {financial_data.get('currency', 'USD')}\n\n"
    md += "---\n\n"

    # Key Metrics Summary
    md += "## Key Metrics\n\n"

    has_metrics = False

    if financial_data.get("burn_rate"):
        md += f"- **Monthly Burn Rate**: ${financial_data['burn_rate']:,.0f}\n"
        has_metrics = True
    if financial_data.get("runway_months"):
        md += f"- **Runway**: {financial_data['runway_months']:.0f} months\n"
        has_metrics = True
    if financial_data.get("cash"):
        md += f"- **Cash Position**: ${financial_data['cash']:,.0f}\n"
        has_metrics = True
    if financial_data.get("ltv_cac_ratio"):
        md += f"- **LTV/CAC Ratio**: {financial_data['ltv_cac_ratio']:.1f}x\n"
        has_metrics = True

    if not has_metrics:
        md += "*No key metrics extracted*\n"
    md += "\n"

    # Revenue / ARR
    def format_time_series(data: dict, label: str, is_currency: bool = True) -> str:
        if not data:
            return ""

        result = f"## {label}\n\n"
        result += "| Period | Value |\n"
        result += "|--------|-------|\n"

        for period in sorted(data.keys()):
            value = data[period]
            if is_currency:
                value_str = f"${value:,.0f}" if value else "-"
            else:
                value_str = f"{value:,.0f}" if value else "-"
            result += f"| {period} | {value_str} |\n"

        result += "\n"
        return result

    if financial_data.get("arr"):
        md += format_time_series(financial_data["arr"], "Annual Recurring Revenue (ARR)")

    if financial_data.get("revenue"):
        md += format_time_series(financial_data["revenue"], "Revenue")

    if financial_data.get("mrr"):
        md += format_time_series(financial_data["mrr"], "Monthly Recurring Revenue (MRR)")

    # Profitability
    if financial_data.get("gross_margin"):
        md += "## Gross Margin\n\n"
        md += "| Period | Margin % |\n"
        md += "|--------|----------|\n"
        for period in sorted(financial_data["gross_margin"].keys()):
            margin = financial_data["gross_margin"][period]
            md += f"| {period} | {margin:.1f}% |\n"
        md += "\n"

    if financial_data.get("ebitda"):
        md += format_time_series(financial_data["ebitda"], "EBITDA")

    if financial_data.get("net_income"):
        md += format_time_series(financial_data["net_income"], "Net Income")

    # Operating Expenses
    if financial_data.get("operating_expenses"):
        md += format_time_series(financial_data["operating_expenses"], "Operating Expenses")

    # Headcount
    if financial_data.get("headcount"):
        md += format_time_series(financial_data["headcount"], "Headcount", is_currency=False)

    if financial_data.get("headcount_by_department"):
        md += "### Headcount by Department\n\n"
        for dept, count in financial_data["headcount_by_department"].items():
            md += f"- **{dept.title()}**: {count}\n"
        md += "\n"

    # Projections
    projections = financial_data.get("projections")
    if projections:
        md += "## Projections\n\n"
        md += "*Financial model projections*\n\n"

        for metric, data in projections.items():
            if data:
                md += f"### Projected {metric.replace('_', ' ').title()}\n\n"
                md += "| Period | Value |\n"
                md += "|--------|-------|\n"
                for period in sorted(data.keys()):
                    value = data[period]
                    value_str = f"${value:,.0f}" if isinstance(value, (int, float)) else str(value)
                    md += f"| {period} | {value_str} |\n"
                md += "\n"

    # Extraction Notes
    notes = financial_data.get("extraction_notes", [])
    if notes:
        md += "## Extraction Notes\n\n"
        for note in notes:
            md += f"- {note}\n"
        md += "\n"

    return md


def format_traction_report(traction_data: dict, company_name: str) -> str:
    """Format traction data as human-readable markdown report."""
    md = f"# Traction Analysis: {company_name}\n\n"

    if traction_data.get("extraction_date"):
        md += f"**Extracted**: {traction_data['extraction_date']}\n\n"

    md += "---\n\n"

    # Key Metrics Summary
    md += "## Key Metrics\n\n"

    has_metrics = False

    if traction_data.get("customer_count"):
        md += f"- **Total Customers**: {traction_data['customer_count']:,}\n"
        has_metrics = True
    if traction_data.get("arr"):
        md += f"- **ARR**: ${traction_data['arr']:,.0f}\n"
        has_metrics = True
    if traction_data.get("mrr"):
        md += f"- **MRR**: ${traction_data['mrr']:,.0f}\n"
        has_metrics = True
    if traction_data.get("revenue_growth"):
        md += f"- **Revenue Growth**: {traction_data['revenue_growth']:.1f}%\n"
        has_metrics = True
    if traction_data.get("retention_rate"):
        md += f"- **Retention Rate**: {traction_data['retention_rate']:.1f}%\n"
        has_metrics = True
    if traction_data.get("churn_rate"):
        md += f"- **Churn Rate**: {traction_data['churn_rate']:.1f}%\n"
        has_metrics = True
    if traction_data.get("nps_score"):
        md += f"- **NPS Score**: {traction_data['nps_score']}\n"
        has_metrics = True

    if not has_metrics:
        md += "*No key metrics extracted*\n"
    md += "\n"

    # Customer Details
    customers = traction_data.get("customers", [])
    if customers:
        md += "## Customers\n\n"
        md += f"**{len(customers)} customers identified**\n\n"

        md += "| Customer | Type | Revenue | Status |\n"
        md += "|----------|------|---------|--------|\n"

        for cust in customers:
            name = cust.get("name", "Unknown")
            cust_type = cust.get("type", "-")
            revenue = cust.get("revenue")
            revenue_str = f"${revenue:,.0f}" if revenue else "-"
            status = cust.get("status", "-")

            md += f"| {name} | {cust_type} | {revenue_str} | {status} |\n"

        md += "\n"

        # Customer breakdown by type
        by_type = {}
        for cust in customers:
            cust_type = cust.get("type", "Other")
            by_type[cust_type] = by_type.get(cust_type, 0) + 1

        if len(by_type) > 1:
            md += "### Customer Breakdown\n\n"
            for cust_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
                pct = count / len(customers) * 100
                md += f"- **{cust_type}**: {count} ({pct:.0f}%)\n"
            md += "\n"

    # Pipeline
    if any(traction_data.get(k) for k in ["pipeline_value", "pipeline_deals", "win_rate", "avg_deal_size", "sales_cycle_days"]):
        md += "## Sales Pipeline\n\n"

        if traction_data.get("pipeline_value"):
            md += f"- **Pipeline Value**: ${traction_data['pipeline_value']:,.0f}\n"
        if traction_data.get("pipeline_deals"):
            md += f"- **Deals in Pipeline**: {traction_data['pipeline_deals']}\n"
        if traction_data.get("win_rate"):
            md += f"- **Win Rate**: {traction_data['win_rate']:.1f}%\n"
        if traction_data.get("avg_deal_size"):
            md += f"- **Average Deal Size**: ${traction_data['avg_deal_size']:,.0f}\n"
        if traction_data.get("sales_cycle_days"):
            md += f"- **Average Sales Cycle**: {traction_data['sales_cycle_days']} days\n"
        md += "\n"

    # Revenue by Segment
    revenue_by_segment = traction_data.get("revenue_by_segment")
    if revenue_by_segment:
        md += "## Revenue by Segment\n\n"
        md += "| Segment | Revenue |\n"
        md += "|---------|----------|\n"
        for segment, revenue in sorted(revenue_by_segment.items(), key=lambda x: -x[1]):
            md += f"| {segment} | ${revenue:,.0f} |\n"
        md += "\n"

    # Milestones
    milestones = traction_data.get("milestones", [])
    if milestones:
        md += "## Key Milestones\n\n"
        for milestone in milestones:
            date = milestone.get("date", "")
            description = milestone.get("description", "")
            date_str = f"**{date}**: " if date else "• "
            md += f"- {date_str}{description}\n"
        md += "\n"

    # Logos (key customer names)
    logos = traction_data.get("logos", [])
    if logos:
        md += "## Notable Customers\n\n"
        md += ", ".join(logos)
        md += "\n\n"

    # Extraction Notes
    notes = traction_data.get("extraction_notes", [])
    if notes:
        md += "## Extraction Notes\n\n"
        for note in notes:
            md += f"- {note}\n"
        md += "\n"

    return md


def format_team_report(team_data: dict, company_name: str) -> str:
    """Format team data as human-readable markdown report."""
    md = f"# Team Analysis: {company_name}\n\n"

    if team_data.get("document_source"):
        md += f"**Sources**: {team_data['document_source']}\n\n"

    md += "---\n\n"

    # Founders Section
    founders = team_data.get("founders", [])
    if founders:
        md += "## Founders\n\n"

        for founder in founders:
            name = founder.get("name", "Unknown")
            title = founder.get("title", "")

            md += f"### {name}"
            if title:
                md += f" - {title}"
            md += "\n\n"

            # LinkedIn
            if founder.get("linkedin_url"):
                md += f"**LinkedIn**: [{founder['linkedin_url']}]({founder['linkedin_url']})\n\n"

            # Background
            prev_companies = founder.get("previous_companies", [])
            prev_roles = founder.get("previous_roles", [])

            if prev_companies or prev_roles:
                md += "**Background:**\n"
                if prev_companies:
                    md += f"- Previous Companies: {', '.join(prev_companies)}\n"
                if prev_roles:
                    md += f"- Previous Roles: {', '.join(prev_roles)}\n"
                md += "\n"

            # Education
            education = founder.get("education", [])
            if education:
                md += "**Education:**\n"
                for edu in education:
                    md += f"- {edu}\n"
                md += "\n"

            # Achievements
            achievements = founder.get("notable_achievements", [])
            if achievements:
                md += "**Notable Achievements:**\n"
                for achievement in achievements:
                    md += f"- {achievement}\n"
                md += "\n"

            # Expertise
            expertise = founder.get("domain_expertise", [])
            if expertise:
                md += f"**Domain Expertise:** {', '.join(expertise)}\n\n"

            if founder.get("years_experience"):
                md += f"**Years of Experience:** {founder['years_experience']}\n\n"

            md += "---\n\n"

    # Leadership Section
    leadership = team_data.get("leadership", [])
    if leadership:
        md += "## Leadership Team\n\n"

        md += "| Name | Title | Background |\n"
        md += "|------|-------|------------|\n"

        for leader in leadership:
            name = leader.get("name", "Unknown")
            title = leader.get("title", "-")
            prev = leader.get("previous_companies", [])
            background = ", ".join(prev[:2]) if prev else "-"

            md += f"| {name} | {title} | {background} |\n"

        md += "\n"

        # Detailed leadership profiles if they have rich data
        for leader in leadership:
            if leader.get("previous_companies") or leader.get("education"):
                name = leader.get("name", "Unknown")
                title = leader.get("title", "")

                md += f"### {name}"
                if title:
                    md += f" - {title}"
                md += "\n\n"

                if leader.get("linkedin_url"):
                    md += f"**LinkedIn**: [{leader['linkedin_url']}]({leader['linkedin_url']})\n\n"

                prev_companies = leader.get("previous_companies", [])
                if prev_companies:
                    md += f"**Previous Companies:** {', '.join(prev_companies)}\n\n"

                education = leader.get("education", [])
                if education:
                    md += "**Education:**\n"
                    for edu in education:
                        md += f"- {edu}\n"
                    md += "\n"

    # Organization Overview
    if team_data.get("total_headcount") or team_data.get("headcount_by_department"):
        md += "## Organization\n\n"

        if team_data.get("total_headcount"):
            md += f"**Total Headcount:** {team_data['total_headcount']}\n\n"

        headcount_by_dept = team_data.get("headcount_by_department", {})
        if headcount_by_dept:
            md += "### Headcount by Department\n\n"
            md += "| Department | Count |\n"
            md += "|------------|-------|\n"
            # Filter out None values and sort by count descending
            valid_depts = [(k, v) for k, v in headcount_by_dept.items() if v is not None]
            for dept, count in sorted(valid_depts, key=lambda x: -x[1]):
                md += f"| {dept.title()} | {count} |\n"
            md += "\n"

    # Advisors
    advisors = team_data.get("advisors", [])
    if advisors:
        md += "## Advisors\n\n"
        for advisor in advisors:
            md += f"- {advisor}\n"
        md += "\n"

    # Board Members
    board = team_data.get("board_members", [])
    if board:
        md += "## Board of Directors\n\n"
        for member in board:
            md += f"- {member}\n"
        md += "\n"

    # Extraction Notes
    notes = team_data.get("extraction_notes", [])
    if notes:
        md += "## Extraction Notes\n\n"
        for note in notes:
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
