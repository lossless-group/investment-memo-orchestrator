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
    use_llm: bool = True,
    firm_name: Optional[str] = None,
    deal_config: Optional[dict] = None,
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

    # Step 0: Transcribe parked media, BEFORE the scan, so transcripts are
    # ordinary documents by the time the scanner walks the tree.
    #
    # Video was the one dataroom category always reported and never used —
    # "unsupported file type '.mp4'" — while being the largest thing in the repo.
    # The media itself lives in the gitignored _zip-originals/; only the
    # transcript is committed, and it reads like any other document. Idempotent:
    # an existing transcript is never regenerated, because it costs money and
    # does not change.
    try:
        from ...media_transcribe import transcribe_dataroom_media
        transcripts = transcribe_dataroom_media(Path(dataroom_path))
        fresh = [t for t in transcripts if t.ok and t.seconds]
        failed = [t for t in transcripts if not t.ok]
        if fresh:
            print(f"🎙️  Transcribed {len(fresh)} media file(s) parked in _zip-originals/")
            for t in fresh:
                print(f"      ✓ {t.source.name} ({len(t.text)} chars)")
        for t in failed:
            print(f"      ⚠️  {t.source.name}: {t.error}")
        if transcripts:
            print()
    except Exception as exc:  # noqa: BLE001 - never break a run over transcription
        print(f"   ⚠️  media transcription skipped: {exc}\n")

    # Step 1: Scan dataroom
    print("📁 Scanning dataroom...")
    inventory, skipped = scan_dataroom(dataroom_path, return_skipped=True)
    print(f"   Found {len(inventory)} documents")
    if skipped:
        print(f"   ⚠️  {len(skipped)} file(s) could not be read:")
        for entry in skipped:
            print(f"      - {entry['filename']}: {entry['reason']}")
    print()

    # Step 2: Classify documents
    #
    # The company and firm names are passed so they can be stripped before
    # pattern matching. Without this a company whose name contains a category
    # word poisons every filename in its own dataroom.
    print("🏷️  Classifying documents...")
    inventory = classify_documents(
        inventory,
        use_llm=use_llm,
        company_name=company_name,
        firm_name=firm_name,
        dataroom_root=dataroom_path,
    )
    classification_summary = get_classification_summary(inventory)
    print(f"   Classified {classification_summary['total']} documents")
    print(f"   High confidence: {classification_summary['by_confidence']['high']}")
    print(f"   Medium confidence: {classification_summary['by_confidence']['medium']}")
    print(f"   Low/Unknown: {classification_summary['by_confidence']['low']}\n")

    # Step 3: Run extractors on classified documents
    # The inventory is complete and expensive (a full classification pass). It
    # goes to disk before the extractors start, not after they finish.
    if output_dir is None:
        output_dir = _get_or_create_output_dir(company_name, firm=firm_name)
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "0-dataroom-inventory.json").write_text(
            json.dumps({"dataroom_path": dataroom_path, "documents": inventory},
                       indent=2, default=str), encoding="utf-8")
        print("   💾 wrote 0-dataroom-inventory.json")
    except Exception as exc:
        print(f"   ⚠️  could not checkpoint inventory: {exc}")

    extraction_results = _run_extractors(inventory, use_llm=use_llm,
                                         company_name=company_name,
                                         output_dir=output_dir)

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
        "legal_summary": extraction_results.get("legal_summary"),
        "unreadable_files": skipped,
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
            f"{len(skipped)} file(s) unreadable" if skipped else "all files readable",
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

    _earmark_anomalies(output_dir, company_name, extraction_results)
    _transcribe_time_series(output_dir, company_name, extraction_results, deal_config)

    save_dataroom_analysis_artifacts(output_dir, analysis, company_name, synthesis_results)

    print(f"\n{'='*60}")
    print(f"✓ Analysis complete in {duration:.1f}s")
    print(f"✓ Artifacts saved to: {output_dir}")
    print(f"{'='*60}\n")

    return analysis




def _transcribe_time_series(output_dir, company_name: str, extraction_results: dict,
                            deal_config: dict = None) -> None:
    """
    Write the company's stated series to ``<output_dir>/timeseries/``.

    Transcription, not analysis: numbers land on the grid exactly as documents
    state them, and anything without an evidenced period is dropped with the
    reason recorded rather than pinned to a guessed date. Roll-ups, fiscal cuts,
    and derived metrics belong to the data-analyst agent, which reads these files.

    Never raises — a dataroom with no dated numbers is the normal case for a
    pre-seed company, and it must not fail a run.
    """
    try:
        from ..timeseries.from_dataroom import transcribe_dataroom

        cfg = deal_config or {}
        summary, trace = transcribe_dataroom(
            company_name, output_dir, extraction_results,
            fiscal_year_start_month=cfg.get("fiscal_year_start_month"),
            incorporation_date=cfg.get("incorporation_date"),
        )
        files = summary.get("files") or []
        if files:
            print(f"   📉 transcribed {summary.get('observations')} observations to "
                  f"timeseries/ ({len(files)} files), origin "
                  f"{summary.get('origin')} via {summary.get('origin_basis')}")
        else:
            print(f"   📉 no dated series in this dataroom — {summary.get('note', 'nothing written')}")
        for line in trace[:8]:
            print(f"      · {line}")
        if len(trace) > 8:
            print(f"      · …and {len(trace) - 8} more")
    except Exception as exc:
        print(f"   ⚠️  time-series transcription skipped: {type(exc).__name__}: {exc}")


def _earmark_anomalies(output_dir, company_name: str, extraction_results: dict) -> None:
    """
    Park instinctive observations in anomalies.json — never in the memo.

    This is a pass over data the extractors already produced. It makes no model
    call and takes no second look at any document, because noticing is not the
    job: the file is a pressure valve so a real observation has somewhere to go
    that is not the deliverable. See
    ``context-v/reminders/Round-Closing-Timeline-Nuances.md`` §3.

    Deliberately narrow. Ordinary closing mechanics are not anomalies, absence
    of data is not an anomaly, and a claim in a deck is not data.
    """
    from ...agents import anomalies

    for doc in extraction_results.get("legal_docs", []) or []:
        source = doc.get("document_source", "")
        notes = " ".join(doc.get("extraction_notes", []) or [])

        # A signed instrument and an unsigned one are different facts about a
        # position. The filename claiming one and the text the other is the
        # rare case worth a second look.
        if "filename says executed but the text says unexecuted" in notes:
            anomalies.record(
                output_dir, company=company_name, agent="legal_extractor",
                source_path=source,
                observation="filename marks this instrument executed; the text's signature block is blank",
                evidence=(doc.get("evidence", {}) or {}).get("investment_amount", ""),
                why=("decides whether this is a closed subscription or an unsigned form, "
                     "which changes the cap table"),
                kind="document_contradicts_metadata",
            )

        # A financing document that yielded no text is not a document that says
        # nothing — it is one nobody has read.
        if doc.get("extraction_status") == "failed" or "no text extracted" in notes.lower():
            anomalies.record(
                output_dir, company=company_name, agent="legal_extractor",
                source_path=source,
                observation="financing document produced no extractable text",
                why="terms in an unread instrument cannot contradict the ones recorded here",
                kind="unreadable_source",
            )

    # Two documents disagreeing about the SAME instrument is a conflict. Two
    # instruments with different terms is structure, and is not recorded here.
    for conflict in (extraction_results.get("legal_summary", {}) or {}).get("conflicts", []) or []:
        claims = conflict.get("claims", []) or []
        investors = {(c.get("evidence") or "")[:0] or c.get("source") for c in claims}
        if len(claims) > 1 and len(investors) == 1:
            anomalies.record(
                output_dir, company=company_name, agent="legal_extractor",
                source_path=claims[0].get("source", ""),
                observation=f"same instrument, disagreeing {conflict.get('field')}: {conflict.get('values')}",
                evidence=(claims[0].get("evidence") or "")[:300],
                why="one of the two numbers is wrong, and the cap table depends on which",
                kind="conflicting_claims",
            )

def _run_extractors(inventory: list, use_llm: bool = True, company_name: str = None,
                    output_dir=None) -> dict:
    """
    Run specialized extractors on classified documents.

    Each extractor's result is written to ``output_dir`` the moment it finishes,
    before the next one starts. This phase runs for tens of minutes across eight
    extractors, and holding all of it in memory until a single save at the end
    meant a run killed partway through produced nothing at all — not slow to
    redo, unrecoverable. See
    ``context-v/reminders/Every-Step-Writes-Its-Output-To-File.md``.

    Args:
        inventory: List of classified DocumentInventoryItem dicts
        use_llm: Whether to use LLM for extraction
        company_name: Company name, for extractors that disambiguate parties
        output_dir: Where to write each result as it completes. Omitted only by
            callers that have nowhere to write, which should be none of them.

    Returns:
        Dict with extraction results by type
    """
    import json as _json
    from pathlib import Path as _Path

    def _checkpoint(name: str, value) -> None:
        """Write one extractor's result. Never raises — a save must not fail a run."""
        if output_dir is None or value in (None, [], {}):
            return
        try:
            d = _Path(output_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{name}.json").write_text(
                _json.dumps(value, indent=2, default=str), encoding="utf-8")
            print(f"   💾 wrote {name}.json")
        except Exception as exc:
            print(f"   ⚠️  could not checkpoint {name}: {type(exc).__name__}: {exc}")
    from .extractors import (
        extract_competitive_data,
        extract_cap_table_data,
        extract_financial_data,
        extract_traction_data,
        extract_team_data,
        extract_legal_data,
        reconcile_legal_docs,
        LEGAL_DOCUMENT_TYPES,
    )

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
            _checkpoint("1-competitive-analysis", results["competitive"])
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
            _checkpoint("2-cap-table", results["cap_table"])
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
            _checkpoint("3-financial-analysis", results["financials"])
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
            _checkpoint("4-traction-analysis", results["traction"])
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
            _checkpoint("5-team-analysis", results["team"])
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

    # Run legal extractor. This slot existed from the beginning and was never
    # filled; for a portfolio archive the executed paper IS the dataroom.
    legal_docs = [d for d in inventory if d["document_type"] in LEGAL_DOCUMENT_TYPES]
    if legal_docs:
        print(f"⚖️  Extracting deal terms from {len(legal_docs)} legal documents...")
        try:
            records = extract_legal_data(legal_docs, use_llm=use_llm, company_name=company_name)
            results["legal_docs"] = records
            _checkpoint("5b-legal-terms", records)
            results["legal_summary"] = reconcile_legal_docs(records)
            _checkpoint("5b-legal-summary", results["legal_summary"])

            summary = results["legal_summary"]
            terms = summary.get("terms", {})
            print(f"   ✓ {summary['executed']} executed / {summary['documents']} documents")
            if terms:
                rendered = ", ".join(
                    f"{k}={v:,.0f}" if isinstance(v, (int, float)) and v > 100 else f"{k}={v}"
                    for k, v in terms.items()
                )
                print(f"   ✓ Terms: {rendered}")
                results["notes"].append(f"Reconciled deal terms: {rendered}")
            for conflict in summary.get("conflicts", []):
                print(f"   ⚠️  Conflict on {conflict['field']}: {conflict['values']}")
                results["notes"].append(
                    f"Conflicting {conflict['field']} across documents: {conflict['values']}"
                )
        except Exception as e:
            results["notes"].append(f"Legal extraction error: {str(e)}")
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

    # _get_or_create_output_dir() makes its own directory, but a caller-supplied
    # output_dir has never been created here, so passing one always failed.
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

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

    # 5b. Save legal / deal-terms analysis
    if analysis.get("legal_docs"):
        legal_json_path = output_dir / "5b-legal-terms.json"
        with open(legal_json_path, "w") as f:
            json.dump(
                {
                    "documents": analysis["legal_docs"],
                    "reconciled": analysis.get("legal_summary"),
                },
                f, indent=2, ensure_ascii=False, default=str,
            )
        print(f"   📄 Saved: {legal_json_path.name}")

        legal_md_path = output_dir / "5b-legal-terms.md"
        with open(legal_md_path, "w") as f:
            f.write(format_legal_report(
                analysis["legal_docs"], analysis.get("legal_summary"), company_name
            ))
        print(f"   📄 Saved: {legal_md_path.name}")

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




# Artifacts that together mean a dataroom pass finished.
_DATAROOM_ARTIFACTS = ("0-dataroom-inventory.json", "state.json")


def _reusable_dataroom_analysis(output_dir, dataroom_path: str, fresh: bool = False):
    """
    A completed analysis of this same dataroom, from this run or a previous one.

    The dataroom pass is by far the most expensive step — on ProfileHealth it
    read 109 legal documents, one model call each — and it is also the most
    deterministic: the same documents produce the same inventory. Re-running it
    to write a new memo version is paying twice for one answer.

    Reuse only when the dataroom has not changed. The check is a scan, which
    costs nothing: same path, same document count, same total bytes. Anything
    else — a file added, removed, or edited — and the analysis is stale, so it
    reruns. ``--fresh`` always reruns.

    Returns the loaded analysis, or None.
    """
    if fresh:
        return None
    try:
        from pathlib import Path as _Path

        current = _Path(output_dir)
        candidates = [current]
        # Prior versions of the same deal: v0.0.1 while writing v0.0.2.
        if current.parent.exists():
            candidates += sorted(
                (d for d in current.parent.iterdir() if d.is_dir() and d != current),
                reverse=True,
            )

        scanned, _ = scan_dataroom(dataroom_path, return_skipped=True)
        now_count = len(scanned)
        now_bytes = sum(d.get("file_size_bytes") or 0 for d in scanned)

        for cand in candidates:
            if not all((cand / name).exists() for name in _DATAROOM_ARTIFACTS):
                continue
            inventory = json.loads((cand / "0-dataroom-inventory.json").read_text())
            # The end-of-run writer uses "inventory"; the mid-run checkpoint uses
            # "documents". Either is the same list.
            docs = inventory.get("inventory") or inventory.get("documents") or []
            # Stored absolute, compared against whatever the caller passed.
            if _Path(inventory.get("dataroom_path", "")).resolve() != _Path(dataroom_path).resolve():
                continue
            if len(docs) != now_count:
                print(f"   ↻ {cand.name} analysed {len(docs)} documents, "
                      f"the dataroom now holds {now_count} — re-analysing")
                continue
            was_bytes = sum(d.get("file_size_bytes") or 0 for d in docs)
            if was_bytes != now_bytes:
                print(f"   ↻ dataroom contents changed since {cand.name} — re-analysing")
                continue

            # The extraction lives in the prior run's state, not in the synthesis
            # report — the report summarises, `dataroom_analysis` is the thing
            # itself, with legal_docs, cap_table, financials, traction and team.
            prior = json.loads((cand / "state.json").read_text())
            analysis = prior.get("dataroom_analysis")
            if not isinstance(analysis, dict) or not analysis.get("document_count"):
                print(f"   ↻ {cand.name} has no usable dataroom_analysis — re-analysing")
                continue
            analysis.setdefault("inventory", docs)
            analysis["reused_from"] = str(cand)
            print(f"   ♻️  reusing the dataroom analysis from {cand.name} "
                  f"({now_count} documents, unchanged) — no re-extraction")
            return analysis
    except Exception as exc:
        print(f"   ⚠️  could not check for a reusable analysis: {type(exc).__name__}: {exc}")
    return None


def _load_deal_config(company_name: str, firm: Optional[str]) -> dict:
    """The deal's own JSON, or {} when there isn't one. Never raises."""
    try:
        from ...paths import resolve_deal_context

        ctx = resolve_deal_context(company_name, firm=firm)
        if ctx.deal_json_path and ctx.deal_json_path.exists():
            return json.loads(ctx.deal_json_path.read_text())
    except Exception as exc:
        print(f"   ⚠️  could not read deal config: {type(exc).__name__}: {exc}")
    return {}


def dataroom_agent(state) -> dict:
    """
    LangGraph-compatible wrapper for the dataroom analyzer.

    Runs as the first step in the memo generation pipeline.
    Skips gracefully if no dataroom_path is provided in state.

    Args:
        state: MemoState with optional dataroom_path

    Returns:
        Dict with dataroom_analysis and messages for state merge
    """
    dataroom_path = state.get("dataroom_path")

    if not dataroom_path:
        print("\n⏭️  No dataroom path provided, skipping dataroom analysis")
        return {
            "messages": ["Dataroom analysis skipped: no dataroom path provided"]
        }

    dataroom_dir = Path(dataroom_path)
    if not dataroom_dir.exists():
        print(f"\n⚠️  Dataroom path does not exist: {dataroom_path}")
        return {
            "messages": [f"Dataroom analysis skipped: path not found ({dataroom_path})"]
        }

    if not dataroom_dir.is_dir():
        print(f"\n⚠️  Dataroom path is not a directory: {dataroom_path}")
        return {
            "messages": [f"Dataroom analysis skipped: not a directory ({dataroom_path})"]
        }

    company_name = state["company_name"]
    firm = state.get("firm")

    # Use the output directory from state (created at workflow start)
    from ...utils import get_output_dir_from_state

    try:
        output_dir = get_output_dir_from_state(state)
    except FileNotFoundError:
        # Fallback: create directory if state didn't have one
        from ...versioning import VersionManager
        from ...artifacts import sanitize_filename, create_artifact_directory
        safe_name = sanitize_filename(company_name)
        if firm:
            vm = VersionManager(firm=firm)
        else:
            vm = VersionManager(output_dir=Path("output"))
        version = vm.get_next_version(safe_name)
        output_dir = create_artifact_directory(company_name, str(version), firm=firm)

    reused = _reusable_dataroom_analysis(output_dir, str(dataroom_dir),
                                         fresh=bool(state.get("fresh")))
    if reused is not None:
        # Transcription is free — no model calls, only reformatting numbers the
        # extraction already holds — so it runs on the reuse path too. Skipping
        # it here meant a reused analysis produced no timeseries/ at all.
        _transcribe_time_series(output_dir, company_name, reused,
                                _load_deal_config(company_name, firm))
        return {
            "dataroom_analysis": reused,
            "messages": [f"Dataroom analysis reused from {reused.get('reused_from')} "
                         f"({reused.get('document_count', '?')} documents, unchanged)"],
        }

    try:
        analysis = analyze_dataroom(
            dataroom_path=str(dataroom_dir),
            company_name=company_name,
            output_dir=output_dir,
            use_llm=True,
            # Both names are stripped from filenames before classification, so a
            # company or firm whose name contains a category word cannot poison
            # its own dataroom.
            firm_name=firm,
            # Carries incorporation_date and fiscal_year_start_month through to
            # the time-series transcriber. A charter date is the strongest origin
            # evidence there is, and it lives in the deal config rather than in
            # any document the extractors read.
            deal_config=_load_deal_config(company_name, firm),
        )

        doc_count = analysis.get("document_count", 0)
        duration = analysis.get("processing_duration_seconds", 0)
        data_gaps = analysis.get("data_gaps", [])
        conflicts = analysis.get("conflicts", [])

        summary_parts = [
            f"Dataroom analysis complete: {doc_count} documents in {duration:.1f}s"
        ]
        if data_gaps:
            summary_parts.append(f"Data gaps identified: {len(data_gaps)}")
        if conflicts:
            summary_parts.append(f"Data conflicts found: {len(conflicts)}")

        return {
            "dataroom_analysis": analysis,
            "messages": summary_parts
        }

    except Exception as e:
        print(f"\n❌ Dataroom analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "messages": [f"Dataroom analysis failed: {str(e)}"]
        }


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


def format_legal_report(
    legal_docs: list, legal_summary: dict, company_name: str
) -> str:
    """
    Render extracted deal terms as markdown.

    Organized so a reader can answer the two questions that matter first — what
    are the terms, and is the paper signed — before descending into per-document
    detail. Every figure is followed by the sentence it was read from, because a
    term sheet reconstructed from OCR is a claim until someone checks it.
    """
    def money(value):
        if value is None:
            return "—"
        if value >= 1_000_000:
            return f"${value / 1_000_000:,.2f}M"
        return f"${value:,.0f}"

    lines = [
        f"# Deal Terms — {company_name}",
        "",
        "Extracted from executed and unexecuted financing documents.",
        "",
    ]

    if legal_summary:
        terms = legal_summary.get("terms", {})
        lines += [
            "## Reconciled position",
            "",
            f"- **Documents analyzed:** {legal_summary.get('documents', 0)} "
            f"({legal_summary.get('executed', 0)} executed, "
            f"{legal_summary.get('unexecuted', 0)} unexecuted/form)",
        ]
        if legal_summary.get("instruments"):
            kinds = ", ".join(f"{k} ({v})" for k, v in legal_summary["instruments"].items())
            lines.append(f"- **Instruments:** {kinds}")
        for label, field in (
            ("Investment amount", "investment_amount"),
            ("Valuation cap", "valuation_cap"),
            ("Pre-money valuation", "pre_money_valuation"),
            ("Post-money valuation", "post_money_valuation"),
            ("Price per share", "share_price"),
        ):
            if field in terms:
                lines.append(f"- **{label}:** {money(terms[field])}")
        if "discount_rate" in terms:
            lines.append(f"- **Discount:** {terms['discount_rate']:g}%")
        if legal_summary.get("investors"):
            lines.append(f"- **Investors named:** {', '.join(legal_summary['investors'])}")
        lines.append("")

        if legal_summary.get("conflicts"):
            lines += ["### Conflicts", ""]
            for conflict in legal_summary["conflicts"]:
                lines.append(
                    f"- **{conflict['field']}** — documents disagree: "
                    f"{conflict['values']}. {conflict['resolution']}."
                )
                for claim in conflict["claims"]:
                    mark = "executed" if claim["executed"] else "unexecuted"
                    lines.append(f"    - {claim['value']} — {claim['source']} ({mark})")
            lines.append("")

    lines += ["## By document", ""]

    for record in legal_docs:
        mark = {True: "signed", False: "form/draft", None: "execution unclear"}[
            record.get("is_executed")
        ]
        lines += [
            f"### {record['document_source']}",
            "",
            f"*{record.get('document_type', 'unknown')} · {mark} · "
            f"extraction confidence {record.get('confidence', 0):.2f}*",
            "",
        ]

        rows = []
        for label, field, kind in (
            ("Security", "security_type", "text"),
            ("Effective date", "effective_date", "text"),
            ("Investment amount", "investment_amount", "money"),
            ("Valuation cap", "valuation_cap", "money"),
            ("Discount", "discount_rate", "pct"),
            ("Interest rate", "interest_rate", "pct"),
            ("Maturity", "maturity_date", "text"),
            ("Pre-money", "pre_money_valuation", "money"),
            ("Post-money", "post_money_valuation", "money"),
            ("Price per share", "share_price", "money"),
            ("Shares", "shares_purchased", "int"),
            ("Liquidation preference", "liquidation_preference", "text"),
            ("Anti-dilution", "anti_dilution", "text"),
            ("Board seats", "board_seats", "text"),
            ("Governing law", "governing_law", "text"),
        ):
            value = record.get(field)
            if value in (None, "", []):
                continue
            if kind == "money":
                shown = money(value)
            elif kind == "pct":
                shown = f"{value:g}%"
            elif kind == "int":
                shown = f"{value:,}"
            else:
                shown = str(value)
            rows.append((label, shown, record.get("evidence", {}).get(field, "")))

        if rows:
            lines += ["| Term | Value | Source text |", "|---|---|---|"]
            for label, shown, evidence in rows:
                quoted = evidence.replace("|", "\\|")[:180] if evidence else "—"
                lines.append(f"| {label} | {shown} | {quoted} |")
            lines.append("")

        for flag, label in (
            ("mfn_clause", "MFN"),
            ("pro_rata_rights", "Pro rata rights"),
            ("information_rights", "Information rights"),
            ("management_rights", "Management rights"),
        ):
            if record.get(flag):
                lines.append(f"- {label}: yes")
        if record.get("investors"):
            lines.append(f"- Investors: {', '.join(record['investors'])}")
        if record.get("counsel"):
            lines.append(f"- Counsel: {', '.join(record['counsel'])}")

        notes = record.get("extraction_notes", [])
        if notes:
            lines += ["", "**Extraction notes:**", ""]
            lines += [f"- {n}" for n in notes]
        lines.append("")

    return "\n".join(lines)
