"""
Dataroom Synthesizer

Cross-references data across all extractors to:
1. Identify conflicts between data sources
2. Detect data gaps (missing critical information)
3. Build a unified view of the company
4. Generate confidence scores for key metrics
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from .dataroom_state import (
    DataroomAnalysis,
    DataConflict,
    FinancialData,
    CapTableData,
    TractionData,
    TeamData,
    CompetitiveData,
)


# =============================================================================
# Conflict Detection
# =============================================================================

def detect_conflicts(analysis: DataroomAnalysis) -> List[DataConflict]:
    """
    Detect conflicts between data extracted from different sources.

    Args:
        analysis: Complete dataroom analysis with all extracted data

    Returns:
        List of DataConflict entries describing inconsistencies
    """
    conflicts = []

    # 1. ARR conflicts between financial and traction data
    arr_conflicts = _check_arr_conflicts(analysis)
    conflicts.extend(arr_conflicts)

    # 2. Headcount conflicts between financial, team, and traction
    headcount_conflicts = _check_headcount_conflicts(analysis)
    conflicts.extend(headcount_conflicts)

    # 3. Customer count conflicts
    customer_conflicts = _check_customer_conflicts(analysis)
    conflicts.extend(customer_conflicts)

    # 4. Valuation/funding conflicts between cap table and other sources
    valuation_conflicts = _check_valuation_conflicts(analysis)
    conflicts.extend(valuation_conflicts)

    # 5. Founder/leadership count conflicts
    team_conflicts = _check_team_conflicts(analysis)
    conflicts.extend(team_conflicts)

    return conflicts


def _check_arr_conflicts(analysis: DataroomAnalysis) -> List[DataConflict]:
    """Check for ARR/revenue conflicts between financial and traction data."""
    conflicts = []

    financials = analysis.get("financials")
    traction = analysis.get("traction")

    if not financials or not traction:
        return conflicts

    # Get latest ARR from financial data
    financial_arr = None
    financial_arr_period = None
    if financials.get("arr"):
        arr_dict = financials["arr"]
        if arr_dict:
            # Find most recent period
            financial_arr_period = max(arr_dict.keys())
            financial_arr = arr_dict[financial_arr_period]

    # Get ARR from traction data
    traction_arr = traction.get("arr")

    if financial_arr and traction_arr:
        # Check if they differ by more than 10%
        diff_pct = abs(financial_arr - traction_arr) / max(financial_arr, traction_arr) * 100

        if diff_pct > 10:
            conflicts.append({
                "field": "ARR",
                "sources": [
                    {
                        "source": financials.get("document_source", "Financial Model"),
                        "value": financial_arr,
                        "context": f"Period: {financial_arr_period}"
                    },
                    {
                        "source": traction.get("document_source", "Pitch Deck"),
                        "value": traction_arr,
                        "context": f"As of: {traction.get('data_as_of', 'Unknown')}"
                    }
                ],
                "recommended_value": max(financial_arr, traction_arr),  # Assume higher is more recent
                "resolution_reasoning": f"ARR differs by {diff_pct:.1f}%. Recommending higher value as likely more recent. Verify with company which figure is current.",
                "severity": "high" if diff_pct > 25 else "medium",
            })

    return conflicts


def _check_headcount_conflicts(analysis: DataroomAnalysis) -> List[DataConflict]:
    """Check for headcount conflicts across data sources."""
    conflicts = []

    headcount_sources = []

    # From financial data
    financials = analysis.get("financials")
    if financials and financials.get("headcount"):
        headcount_dict = financials["headcount"]
        if headcount_dict:
            latest_period = max(headcount_dict.keys())
            headcount_sources.append({
                "source": financials.get("document_source", "Financial Model"),
                "value": headcount_dict[latest_period],
                "context": f"Period: {latest_period}"
            })

    # From team data
    team = analysis.get("team")
    if team and team.get("total_headcount"):
        headcount_sources.append({
            "source": team.get("document_source", "Team Document"),
            "value": team["total_headcount"],
            "context": "From team/org data"
        })

    # Check for conflicts if we have multiple sources
    if len(headcount_sources) >= 2:
        values = [s["value"] for s in headcount_sources]
        if max(values) - min(values) > 5:  # More than 5 person difference
            conflicts.append({
                "field": "Total Headcount",
                "sources": headcount_sources,
                "recommended_value": max(values),  # Assume higher is more current
                "resolution_reasoning": f"Headcount varies by {max(values) - min(values)} across sources. Verify current headcount with company.",
                "severity": "low",
            })

    return conflicts


def _check_customer_conflicts(analysis: DataroomAnalysis) -> List[DataConflict]:
    """Check for customer count conflicts."""
    conflicts = []

    traction = analysis.get("traction")
    competitive = analysis.get("competitive")

    if not traction:
        return conflicts

    customer_count = traction.get("total_customers")
    notable_customers = traction.get("notable_customers", [])

    if customer_count and notable_customers:
        # Check if notable customer count exceeds total
        if len(notable_customers) > customer_count:
            conflicts.append({
                "field": "Customer Count",
                "sources": [
                    {
                        "source": traction.get("document_source", "Traction Data"),
                        "value": customer_count,
                        "context": "Total customers reported"
                    },
                    {
                        "source": traction.get("document_source", "Traction Data"),
                        "value": len(notable_customers),
                        "context": "Named customers listed"
                    }
                ],
                "recommended_value": max(customer_count, len(notable_customers)),
                "resolution_reasoning": "More customers named than total reported. Using higher count.",
                "severity": "low",
            })

    return conflicts


def _check_valuation_conflicts(analysis: DataroomAnalysis) -> List[DataConflict]:
    """Check for valuation/funding conflicts."""
    conflicts = []

    cap_table = analysis.get("cap_table")

    if not cap_table:
        return conflicts

    # Check if total ownership percentages sum to ~100%
    shareholders = cap_table.get("shareholders", [])
    if shareholders:
        total_pct = sum(s.get("ownership_percentage", 0) for s in shareholders)

        if total_pct < 95 or total_pct > 105:
            conflicts.append({
                "field": "Ownership Percentages",
                "sources": [
                    {
                        "source": cap_table.get("document_source", "Cap Table"),
                        "value": total_pct,
                        "context": f"Sum of {len(shareholders)} shareholders"
                    }
                ],
                "recommended_value": 100.0,
                "resolution_reasoning": f"Ownership percentages sum to {total_pct:.1f}%, not 100%. Cap table may be incomplete or have rounding errors.",
                "severity": "medium" if abs(total_pct - 100) > 10 else "low",
            })

    return conflicts


def _check_team_conflicts(analysis: DataroomAnalysis) -> List[DataConflict]:
    """Check for team/leadership conflicts."""
    conflicts = []

    team = analysis.get("team")
    traction = analysis.get("traction")

    if not team:
        return conflicts

    founders = team.get("founders", [])
    leadership = team.get("leadership", [])

    # Check for duplicate names across founders and leadership
    founder_names = {f.get("name", "").lower() for f in founders if f.get("name")}
    leader_names = {l.get("name", "").lower() for l in leadership if l.get("name")}

    overlap = founder_names & leader_names
    if overlap:
        conflicts.append({
            "field": "Team Classification",
            "sources": [
                {
                    "source": team.get("document_source", "Team Document"),
                    "value": list(overlap),
                    "context": "Names appearing in both founders and leadership"
                }
            ],
            "recommended_value": "Keep in founders list only",
            "resolution_reasoning": f"Same person(s) listed as both founder and leadership: {', '.join(overlap)}. Should be classified as founder.",
            "severity": "low",
        })

    return conflicts


# =============================================================================
# Data Gap Identification
# =============================================================================

def identify_data_gaps(analysis: DataroomAnalysis) -> List[Dict[str, Any]]:
    """
    Identify missing critical information for investment analysis.

    Args:
        analysis: Complete dataroom analysis

    Returns:
        List of data gaps with severity and recommendations
    """
    gaps = []

    # Define critical data requirements for investment memos
    critical_requirements = [
        # Financial
        ("financials", "arr", "ARR/Revenue", "high", "Essential for valuation and growth analysis"),
        ("financials", "burn_rate", "Monthly Burn Rate", "high", "Critical for runway calculation"),
        ("financials", "runway_months", "Runway (months)", "high", "Key investment timing metric"),
        ("financials", "gross_margin", "Gross Margin", "medium", "Important for unit economics"),

        # Cap Table
        ("cap_table", "shareholders", "Cap Table / Ownership", "high", "Required for investment structure"),
        ("cap_table", "option_pool_percentage", "Option Pool Size", "medium", "Important for dilution analysis"),

        # Traction
        ("traction", "total_customers", "Customer Count", "high", "Essential traction metric"),
        ("traction", "retention_rate", "Customer Retention Rate", "medium", "Key for SaaS companies"),
        ("traction", "arr", "Current ARR", "high", "Primary revenue metric"),

        # Team
        ("team", "founders", "Founder Backgrounds", "high", "Critical for team assessment"),
        ("team", "total_headcount", "Team Size", "low", "Useful context"),

        # Competitive
        ("competitive", "competitors", "Competitive Landscape", "medium", "Important for market positioning"),
        ("competitive", "key_differentiators", "Key Differentiators", "medium", "Important for investment thesis"),
    ]

    for section, field, name, severity, reason in critical_requirements:
        section_data = analysis.get(section)

        is_missing = False
        if section_data is None:
            is_missing = True
        elif isinstance(section_data, dict):
            field_data = section_data.get(field)
            if field_data is None:
                is_missing = True
            elif isinstance(field_data, (list, dict)) and len(field_data) == 0:
                is_missing = True

        if is_missing:
            gaps.append({
                "field": name,
                "section": section,
                "severity": severity,
                "reason": reason,
                "recommendation": _get_gap_recommendation(section, field),
            })

    return gaps


def _get_gap_recommendation(section: str, field: str) -> str:
    """Get recommendation for filling a data gap."""
    recommendations = {
        ("financials", "arr"): "Request current P&L or financial model from company",
        ("financials", "burn_rate"): "Calculate from monthly operating expenses or request from company",
        ("financials", "runway_months"): "Calculate from cash position and burn rate",
        ("financials", "gross_margin"): "Request P&L breakdown or estimate from industry benchmarks",
        ("cap_table", "shareholders"): "Request current cap table from company",
        ("cap_table", "option_pool_percentage"): "Request cap table with option pool details",
        ("traction", "total_customers"): "Request customer list or count from company",
        ("traction", "retention_rate"): "Request cohort analysis or retention metrics",
        ("traction", "arr"): "Request current ARR figure or calculate from contracts",
        ("team", "founders"): "Request founder bios or LinkedIn profiles",
        ("team", "total_headcount"): "Request org chart or headcount breakdown",
        ("competitive", "competitors"): "Conduct independent market research",
        ("competitive", "key_differentiators"): "Review product docs or request positioning deck",
    }
    return recommendations.get((section, field), "Request additional documentation from company")


# =============================================================================
# Cross-Reference Engine
# =============================================================================

def cross_reference_data(analysis: DataroomAnalysis) -> Dict[str, Any]:
    """
    Build cross-referenced unified view of company data.

    Args:
        analysis: Complete dataroom analysis

    Returns:
        Dict with unified metrics and confidence scores
    """
    unified = {
        "company_metrics": {},
        "confidence_scores": {},
        "data_sources": {},
    }

    # Unify financial metrics
    financials = analysis.get("financials")
    traction = analysis.get("traction")

    # ARR - prefer financial model, fallback to traction
    arr_value, arr_confidence, arr_sources = _unify_metric(
        primary=(financials.get("arr") if financials else None, "Financial Model"),
        secondary=(traction.get("arr") if traction else None, "Pitch Deck"),
        metric_name="ARR"
    )
    if arr_value:
        unified["company_metrics"]["arr"] = arr_value
        unified["confidence_scores"]["arr"] = arr_confidence
        unified["data_sources"]["arr"] = arr_sources

    # Headcount - prefer team data, fallback to financial
    team = analysis.get("team")
    headcount_value, headcount_confidence, headcount_sources = _unify_metric(
        primary=(team.get("total_headcount") if team else None, "Team Document"),
        secondary=(_get_latest_headcount(financials) if financials else None, "Financial Model"),
        metric_name="Headcount"
    )
    if headcount_value:
        unified["company_metrics"]["headcount"] = headcount_value
        unified["confidence_scores"]["headcount"] = headcount_confidence
        unified["data_sources"]["headcount"] = headcount_sources

    # Customer count
    if traction and traction.get("total_customers"):
        unified["company_metrics"]["customer_count"] = traction["total_customers"]
        unified["confidence_scores"]["customer_count"] = "high"
        unified["data_sources"]["customer_count"] = [traction.get("document_source", "Traction Data")]

    # Founder ownership
    cap_table = analysis.get("cap_table")
    if cap_table:
        founder_ownership = _calculate_founder_ownership(cap_table)
        if founder_ownership:
            unified["company_metrics"]["founder_ownership_pct"] = founder_ownership
            unified["confidence_scores"]["founder_ownership_pct"] = "high"
            unified["data_sources"]["founder_ownership_pct"] = [cap_table.get("document_source", "Cap Table")]

    # Competitor count
    competitive = analysis.get("competitive")
    if competitive and competitive.get("competitors"):
        unified["company_metrics"]["competitor_count"] = len(competitive["competitors"])
        unified["confidence_scores"]["competitor_count"] = "medium"
        unified["data_sources"]["competitor_count"] = [competitive.get("document_source", "Battlecards")]

    return unified


def _unify_metric(
    primary: Tuple[Any, str],
    secondary: Tuple[Any, str],
    metric_name: str
) -> Tuple[Any, str, List[str]]:
    """
    Unify a metric from multiple sources.

    Returns:
        (value, confidence, sources)
    """
    primary_value, primary_source = primary
    secondary_value, secondary_source = secondary

    if primary_value is not None:
        # Handle dict values (time series)
        if isinstance(primary_value, dict) and primary_value:
            latest_key = max(primary_value.keys())
            return (primary_value[latest_key], "high", [primary_source])
        return (primary_value, "high", [primary_source])

    if secondary_value is not None:
        if isinstance(secondary_value, dict) and secondary_value:
            latest_key = max(secondary_value.keys())
            return (secondary_value[latest_key], "medium", [secondary_source])
        return (secondary_value, "medium", [secondary_source])

    return (None, "none", [])


def _get_latest_headcount(financials: Optional[FinancialData]) -> Optional[int]:
    """Get latest headcount from financial data."""
    if not financials or not financials.get("headcount"):
        return None

    headcount = financials["headcount"]
    if not headcount:
        return None

    latest_period = max(headcount.keys())
    return headcount[latest_period]


def _calculate_founder_ownership(cap_table: CapTableData) -> Optional[float]:
    """Calculate total founder ownership percentage."""
    shareholders = cap_table.get("shareholders", [])
    if not shareholders:
        return None

    founder_pct = sum(
        s.get("ownership_percentage", 0)
        for s in shareholders
        if s.get("investor_type", "").lower() == "founder"
    )

    return founder_pct if founder_pct > 0 else None


# =============================================================================
# Synthesis Report Generation
# =============================================================================

def generate_synthesis_report(
    analysis: DataroomAnalysis,
    conflicts: List[DataConflict],
    gaps: List[Dict[str, Any]],
    unified: Dict[str, Any]
) -> str:
    """
    Generate a markdown synthesis report.

    Args:
        analysis: Complete dataroom analysis
        conflicts: Detected conflicts
        gaps: Identified data gaps
        unified: Cross-referenced unified data

    Returns:
        Markdown report string
    """
    md = "# Dataroom Synthesis Report\n\n"
    md += f"**Generated**: {datetime.now().isoformat()}\n\n"
    md += "---\n\n"

    # Executive Summary
    md += "## Executive Summary\n\n"

    metrics = unified.get("company_metrics", {})
    if metrics:
        md += "### Key Metrics (Unified View)\n\n"
        md += "| Metric | Value | Confidence | Sources |\n"
        md += "|--------|-------|------------|----------|\n"

        confidence_scores = unified.get("confidence_scores", {})
        data_sources = unified.get("data_sources", {})

        for metric, value in metrics.items():
            conf = confidence_scores.get(metric, "unknown")
            conf_icon = "🟢" if conf == "high" else "🟡" if conf == "medium" else "🔴"
            sources = ", ".join(data_sources.get(metric, []))

            # Format value
            if isinstance(value, float):
                if value > 1000000:
                    value_str = f"${value/1000000:.1f}M"
                elif value > 1000:
                    value_str = f"${value/1000:.0f}K"
                elif value < 1:
                    value_str = f"{value*100:.1f}%"
                else:
                    value_str = f"{value:.1f}"
            else:
                value_str = str(value)

            metric_name = metric.replace("_", " ").title()
            md += f"| {metric_name} | {value_str} | {conf_icon} {conf} | {sources} |\n"

        md += "\n"

    # Data Quality Overview
    high_gaps = [g for g in gaps if g["severity"] == "high"]
    medium_gaps = [g for g in gaps if g["severity"] == "medium"]
    high_conflicts = [c for c in conflicts if c.get("severity") == "high"]

    md += "### Data Quality Summary\n\n"
    md += f"- **Critical Gaps**: {len(high_gaps)}\n"
    md += f"- **Medium Gaps**: {len(medium_gaps)}\n"
    md += f"- **High-Severity Conflicts**: {len(high_conflicts)}\n"
    md += f"- **Total Conflicts**: {len(conflicts)}\n\n"

    # Conflicts Section
    if conflicts:
        md += "## Data Conflicts\n\n"

        for i, conflict in enumerate(conflicts, 1):
            severity = conflict.get("severity", "unknown")
            severity_icon = "🔴" if severity == "high" else "🟡" if severity == "medium" else "🟢"

            md += f"### {i}. {conflict['field']} {severity_icon}\n\n"

            md += "**Sources:**\n"
            for source in conflict["sources"]:
                md += f"- **{source['source']}**: {source['value']}"
                if source.get("context"):
                    md += f" ({source['context']})"
                md += "\n"

            md += f"\n**Recommended Value**: {conflict['recommended_value']}\n\n"
            md += f"**Resolution**: {conflict['resolution_reasoning']}\n\n"
            md += "---\n\n"

    # Data Gaps Section
    if gaps:
        md += "## Data Gaps\n\n"

        # Group by severity
        for severity in ["high", "medium", "low"]:
            severity_gaps = [g for g in gaps if g["severity"] == severity]
            if severity_gaps:
                severity_icon = "🔴" if severity == "high" else "🟡" if severity == "medium" else "🟢"
                md += f"### {severity_icon} {severity.title()} Priority\n\n"

                md += "| Missing Data | Section | Reason | Recommendation |\n"
                md += "|--------------|---------|--------|----------------|\n"

                for gap in severity_gaps:
                    md += f"| {gap['field']} | {gap['section'].title()} | {gap['reason']} | {gap['recommendation']} |\n"

                md += "\n"

    # Cross-Reference Insights
    md += "## Cross-Reference Insights\n\n"

    # Financial vs Traction alignment
    financials = analysis.get("financials")
    traction = analysis.get("traction")

    if financials and traction:
        md += "### Financial & Traction Alignment\n\n"

        financial_arr = None
        if financials.get("arr"):
            arr_dict = financials["arr"]
            if arr_dict:
                financial_arr = arr_dict[max(arr_dict.keys())]

        traction_arr = traction.get("arr")

        if financial_arr and traction_arr:
            diff_pct = abs(financial_arr - traction_arr) / max(financial_arr, traction_arr) * 100
            if diff_pct < 5:
                md += "✅ ARR figures align across financial model and pitch deck\n\n"
            else:
                md += f"⚠️ ARR differs by {diff_pct:.1f}% between sources\n\n"

    # Team & Org alignment
    team = analysis.get("team")
    if team and financials:
        team_headcount = team.get("total_headcount")
        financial_headcount = _get_latest_headcount(financials)

        if team_headcount and financial_headcount:
            if abs(team_headcount - financial_headcount) <= 2:
                md += "✅ Headcount aligns between team data and financial model\n\n"
            else:
                md += f"⚠️ Headcount differs: Team says {team_headcount}, Financial says {financial_headcount}\n\n"

    # Cap table completeness
    cap_table = analysis.get("cap_table")
    if cap_table:
        shareholders = cap_table.get("shareholders", [])
        total_pct = sum(s.get("ownership_percentage", 0) for s in shareholders)

        if 98 <= total_pct <= 102:
            md += "✅ Cap table ownership sums to ~100%\n\n"
        else:
            md += f"⚠️ Cap table ownership sums to {total_pct:.1f}% (expected ~100%)\n\n"

    return md


# =============================================================================
# Main Synthesis Function
# =============================================================================

def synthesize_dataroom(analysis: DataroomAnalysis) -> Dict[str, Any]:
    """
    Main entry point for dataroom synthesis.

    Args:
        analysis: Complete dataroom analysis from analyzer

    Returns:
        Dict containing:
        - conflicts: List of detected conflicts
        - gaps: List of data gaps
        - unified: Cross-referenced unified data
        - report: Markdown synthesis report
    """
    print("\n🔄 Synthesizing dataroom data...")

    # Detect conflicts
    print("   Checking for data conflicts...")
    conflicts = detect_conflicts(analysis)
    print(f"   Found {len(conflicts)} conflicts")

    # Identify gaps
    print("   Identifying data gaps...")
    gaps = identify_data_gaps(analysis)
    high_gaps = len([g for g in gaps if g["severity"] == "high"])
    print(f"   Found {len(gaps)} gaps ({high_gaps} critical)")

    # Cross-reference data
    print("   Cross-referencing data sources...")
    unified = cross_reference_data(analysis)
    print(f"   Unified {len(unified.get('company_metrics', {}))} metrics")

    # Generate report
    print("   Generating synthesis report...")
    report = generate_synthesis_report(analysis, conflicts, gaps, unified)

    return {
        "conflicts": conflicts,
        "gaps": gaps,
        "unified": unified,
        "report": report,
    }
