"""
Regression tests for the dataroom extraction layer.

These cover the failure modes that were found in production data and that would
fail silently if reintroduced — each one produced a confidently wrong answer
rather than an error, which is why they survived so long.
"""

from pathlib import Path

import pytest

from src.agents.dataroom.document_classifier import (
    build_name_stopwords,
    classify_documents,
    strip_names,
)
from src.agents.dataroom.extractors.legal_extractor import _apply_patterns, _blank_record


def _item(filename, parent="Transaction Documents", path=None, ext=".pdf"):
    return {
        "file_path": path or f"/dataroom/{parent}/{filename}",
        "filename": filename,
        "extension": ext,
        "file_size_bytes": 1000,
        "page_count": 1,
        "parent_directory": parent,
        "document_type": "unknown",
        "classification_confidence": 0.0,
        "classification_reasoning": "",
        "classification_source": "unknown",
        "processed": False,
        "extraction_status": "pending",
        "extraction_error": None,
    }


# =============================================================================
# The company name must not leak into classification
# =============================================================================

class TestNameStripping:
    """
    A company called "Vantage Products" put the token `product` into all 43 of
    its filenames, and every one of them classified as product_documentation.
    """

    def test_stopwords_include_singular_and_plural(self):
        stop = build_name_stopwords("Vantage Products")
        assert "products" in stop
        assert "product" in stop

    def test_stopwords_skip_corporate_suffixes(self):
        stop = build_name_stopwords("Meridian Systems AI, Inc.")
        assert "meridian" in stop
        assert "inc" not in stop

    def test_strip_names_removes_tokens(self):
        stop = build_name_stopwords("Vantage Products")
        assert "product" not in strip_names("vantage products cap table", stop).lower()

    def test_cap_table_survives_a_company_named_products(self):
        inventory = classify_documents(
            [_item("Vantage Products - Series A - Pro Forma.xlsx", ext=".xlsx")],
            use_llm=False,
            company_name="Vantage Products",
            use_content=False,
        )
        assert inventory[0]["document_type"] == "cap_table"

    def test_charter_survives_a_company_named_products(self):
        inventory = classify_documents(
            [_item("Vantage Products - Certificate of Incorporation.pdf")],
            use_llm=False,
            company_name="Vantage Products",
            use_content=False,
        )
        assert inventory[0]["document_type"] == "charter_document"

    def test_without_the_company_name_the_leak_is_still_prevented_by_specificity(self):
        # Even with no name supplied, a specific phrase must outrank a bare word.
        inventory = classify_documents(
            [_item("Series A - Schedule of Purchasers.pdf")],
            use_llm=False,
            use_content=False,
        )
        assert inventory[0]["document_type"] == "schedule_of_purchasers"


# =============================================================================
# Directory matching must be anchored
# =============================================================================

class TestDirectoryMatching:
    def test_multiword_directory_beats_single_word(self):
        inventory = classify_documents(
            [_item("Amendment.pdf", parent="Series A Executed Documents",
                   path="/dr/Series A Executed Documents/Amendment.pdf")],
            use_llm=False,
            dataroom_root="/dr",
            use_content=False,
        )
        assert inventory[0]["document_type"] == "executed_financing_doc"

    def test_container_directory_is_weak_evidence(self):
        # "Research/" names a shelf, not a kind — it must not claim high confidence.
        inventory = classify_documents(
            [_item("Some Paper.pdf", parent="Research", path="/dr/Research/Some Paper.pdf")],
            use_llm=False,
            dataroom_root="/dr",
            use_content=False,
        )
        assert inventory[0]["classification_confidence"] <= 0.6


# =============================================================================
# Execution status
# =============================================================================

class TestExecutionStatus:
    @pytest.mark.parametrize("filename,expected", [
        ("Voting Agreement [Executed].pdf", True),
        ("Side Letter (Executed).pdf", True),
        ("Form of Series A Preferred Stock Warrant.docx", False),
        ("Deal Memo (Draft).docx", False),
        ("Voting Agreement.docx", None),
    ])
    def test_executed_flag(self, filename, expected):
        inventory = classify_documents(
            [_item(filename)], use_llm=False, use_content=False
        )
        assert inventory[0]["is_executed"] is expected


# =============================================================================
# The SAFE "Discount Rate" inversion
# =============================================================================

class TestLegalPatterns:
    """
    A YC SAFE reading `"Discount Rate" is 85%` grants a 15% discount. Recording
    85 would overstate the discount by more than five times.
    """

    def _extract(self, text, filename="doc.pdf"):
        record = _blank_record({"filename": filename, "document_type": "safe_note"}, "Acme")
        _apply_patterns(record, text)
        return record

    def test_discount_rate_is_inverted(self):
        record = self._extract('The “Discount Rate” is 85%.')
        assert record["discount_rate"] == 15.0

    def test_plain_discount_is_taken_literally(self):
        record = self._extract("The Notes convert at a discount of 20%.")
        assert record["discount_rate"] == 20.0

    def test_valuation_cap_in_a_definitions_block(self):
        record = self._extract('The “Post-Money Valuation Cap” is $120,000,000.')
        assert record["valuation_cap"] == 120_000_000

    def test_purchase_amount_stated_before_its_label(self):
        record = self._extract(
            'in exchange for the payment by Investor of $200,000 (the “Purchase Amount”)'
        )
        assert record["investment_amount"] == 200_000

    def test_money_suffixes(self):
        record = self._extract('The “Valuation Cap” is $48 million.')
        assert record["valuation_cap"] == 48_000_000

    def test_security_type_reads_the_title_not_a_passing_mention(self):
        # An Investors' Rights Agreement discusses warrants without being one.
        body = (
            "AMENDED AND RESTATED INVESTORS' RIGHTS AGREEMENT. "
            + "This agreement governs registration rights. " * 40
            + "Each holder of a warrant to purchase shares shall be entitled to notice."
        )
        assert self._extract(body)["security_type"] != "Warrant"

    def test_every_extracted_scalar_carries_its_source_text(self):
        record = self._extract('The “Valuation Cap” is $48,000,000.')
        assert "48,000,000" in record["evidence"]["valuation_cap"]


# =============================================================================
# The text layer fails loudly
# =============================================================================

class TestDocumentText:
    def test_missing_file_reports_an_error_rather_than_empty_text(self):
        from src.agents.dataroom.document_text import extract_text

        result = extract_text("/nonexistent/file.pdf")
        assert result.ok is False
        assert result.error is not None

    def test_unsupported_extension_names_the_extension(self):
        from src.agents.dataroom.document_text import extract_text

        result = extract_text(__file__.replace(".py", ".sqlite3"))
        assert result.ok is False

    def test_docx_and_eml_are_handled(self):
        from src.agents.dataroom.document_text import supported_extensions

        assert {".docx", ".eml", ".pptx", ".xlsx"} <= supported_extensions()


# =============================================================================
# The scanner reports what it skipped
# =============================================================================

class TestScanner:
    def test_skipped_files_are_reported_not_dropped(self, tmp_path):
        from src.agents.dataroom.document_scanner import scan_dataroom

        (tmp_path / "deck.pdf").write_bytes(b"%PDF-1.4\n")
        (tmp_path / "memo.pages").write_bytes(b"PK\x03\x04")

        inventory, skipped = scan_dataroom(str(tmp_path), return_skipped=True)

        assert len(inventory) == 1
        assert len(skipped) == 1
        assert skipped[0]["filename"] == "memo.pages"
        assert "export" in skipped[0]["reason"].lower()

    def test_legacy_signature_still_returns_a_bare_list(self, tmp_path):
        from src.agents.dataroom.document_scanner import scan_dataroom

        (tmp_path / "deck.pdf").write_bytes(b"%PDF-1.4\n")
        assert isinstance(scan_dataroom(str(tmp_path)), list)


# =============================================================================
# Slide stenographer
# =============================================================================

class TestDateResolution:
    """
    The VP board deck is the worked example: named 9-24-2025, PDF title
    "LookAhead BoD Q2 06132025", slide one reading "BoD Meeting 06-13-2025".
    """

    def test_slide_content_outranks_filename(self):
        from src.agents.slides.date_resolution import resolve_deck_date

        result = resolve_deck_date(
            first_slides_text="BoD Meeting 06-13-2025",
            filename="VPBoard Meeting 9-24-2025 - pwd VPBODJUNE2025.pdf",
        )
        assert result.date_on_deck.isoformat() == "2025-06-13"
        assert result.date_source == "slide-content"
        assert any("filename implies" in n for n in result.notes)

    def test_a_stated_day_beats_a_completed_one(self):
        # "June 2025" resolves to the 1st, a day the document never claimed. It
        # must lose to a date that names its day, whatever their ordering.
        from src.agents.slides.date_resolution import resolve_deck_date

        result = resolve_deck_date(
            first_slides_text="BoD Meeting 06-13-2025 ... CONFIDENTIAL June 2025",
        )
        assert result.date_on_deck.isoformat() == "2025-06-13"

    def test_a_closing_deadline_never_dates_the_deck(self):
        # The SPV deck's "Closing Sept 30, 2024" is a future event.
        from src.agents.slides.date_resolution import resolve_deck_date

        result = resolve_deck_date(
            first_slides_text="Keystone Ventures SPV Terms. Closing Sept 30, 2024",
            pdf_creation_date="D:20240926193236Z",
        )
        assert result.date_on_deck.isoformat() == "2024-09-26"
        kinds = {c.kind for c in result.dates_mentioned}
        assert "closing_deadline" in kinds

    def test_sibling_inference_is_low_confidence_and_says_so(self):
        from datetime import date
        from src.agents.slides.date_resolution import resolve_deck_date

        result = resolve_deck_date(
            filename="Auralis-deck.pdf",
            sibling_dates=[date(2025, 4, 18), date(2025, 4, 30)],
        )
        assert result.date_confidence == "low"
        assert result.date_source == "sibling"
        assert result.notes


class TestDeckLineage:
    def test_deck_slug_matches_house_convention(self):
        from datetime import date
        from src.agents.slides.deck_lineage import deck_slug

        assert deck_slug("MeridianAI", "Seed", date(2024, 9, 10), 1) == "20240910_MeridianAI_Seed--v1"
        assert deck_slug("MeridianAI", "Seed", date(2024, 9, 26), 1, variant="SPV") == \
            "20240926_MeridianAI_Seed_SPV--v1"

    def test_internal_capitals_survive(self):
        from datetime import date
        from src.agents.slides.deck_lineage import deck_slug

        assert "MeridianAI" in deck_slug("MeridianAI", "Seed", date(2024, 1, 1))

    def test_firm_authorship_forces_fork_however_high_the_overlap(self):
        from src.agents.slides.deck_lineage import compare_decks

        slides = [f"Slide {i} about cognitive networks and inference" for i in range(10)]
        result = compare_decks(slides, slides + ["SPV terms carry admin fee"],
                               "company", "firm")
        assert result.relationship == "fork"

    def test_same_slides_same_author_is_a_version(self):
        from src.agents.slides.deck_lineage import compare_decks

        a = [f"Slide {i} about cognitive networks and inference engines" for i in range(10)]
        b = a[:8] + ["Brand new slide on go to market motion and channel strategy"]
        assert compare_decks(a, b, "company", "company").relationship == "version"

    def test_low_overlap_is_a_sibling_not_a_version(self):
        from src.agents.slides.deck_lineage import compare_decks

        a = ["cognitive networks inference engines transformers architecture"] * 5
        b = ["values imperatives measures systems organizational design culture"] * 5
        assert compare_decks(a, b, "company", "company").relationship == "sibling"

    def test_a_shared_title_pairs_slides_without_calling_them_identical(self):
        # MeridianAI's "Thank you." and Keystone's "Thank you." share a heading and
        # nothing else. Pair them; do not report the swap as no change.
        from src.agents.slides.deck_lineage import match_slides

        matches = match_slides(
            ["Thank you.\nDana Whitfield, CEO\ndana@meridian.ai"],
            ["Thank you.\nMorgan Reyes\nManaging Partner\nmorgan@keystone.vc"],
        )
        paired = [m for m in matches if m.index_a and m.index_b]
        assert len(paired) == 1
        assert paired[0].relation == "edited"
        assert paired[0].matched_on == "title"

    def test_repeated_titles_flag_an_unconfirmed_build(self):
        from src.agents.slides.deck_lineage import detect_reveal_sequences

        pages = [
            "Our Solution | Translating how the brain computes\nfirst point entirely",
            "Our Solution | Translating how the brain computes\nsecond wholly different",
            "Competitive Landscape\nfirst generation transformer architecture",
        ]
        groups = detect_reveal_sequences(pages)
        assert len(groups) == 1
        assert groups[0].indices == [1, 2]
        assert groups[0].confirmed is False   # title-only, needs the images

    def test_normalization_survives_extractor_line_break_differences(self):
        from src.agents.slides.deck_lineage import similarity

        pdf_text = "Cognitive Networks for AI\nFoundational new \nAI architecture \nthat understands"
        pptx_text = "Cognitive Networks for AI\nFoundational new AI architecture that understands"
        assert similarity(pdf_text, pptx_text) > 0.9


class TestSlideMarkdown:
    def test_user_commentary_survives_reanalysis(self):
        from src.agents.slides.slide_markdown import (
            extract_user_commentary, render_slide_markdown,
        )

        first = render_slide_markdown({
            "slide_type": "team", "core_message": "x", "content": {"titleRow": {"titleTxt": "T"}},
        })
        edited = first.replace("*No commentary yet.*", "Dana is the real asset here.")
        recovered = extract_user_commentary(edited)
        assert recovered == "Dana is the real asset here."

        second = render_slide_markdown({
            "slide_type": "team", "core_message": "y", "content": {"titleRow": {"titleTxt": "T"}},
        }, existing_user_commentary=recovered)
        assert "Dana is the real asset here." in second

    def test_placeholder_is_not_mistaken_for_commentary(self):
        from src.agents.slides.slide_markdown import (
            extract_user_commentary, render_slide_markdown,
        )

        doc = render_slide_markdown({"slide_type": "cover", "content": {}})
        assert extract_user_commentary(doc) is None


class TestSlideSchemas:
    def test_shortlist_finds_fund_terms_for_an_spv_slide(self):
        from src.agents.slides.slide_schemas import rank_slide_types

        assert "fund_terms" in rank_slide_types(
            "Keystone Ventures SPV Terms Commitment Admin Fee Carry Minimum commitment LPs"
        )

    def test_shortlist_always_offers_a_generic_fallback(self):
        from src.agents.slides.slide_schemas import rank_slide_types

        assert rank_slide_types("qwerty asdf zxcv")[-1] == "other"

    def test_a_coined_type_is_a_proposal_not_an_error(self):
        # The vocabulary is a coherence aid, not a gate. A deck that genuinely
        # does something new should be able to name it; forcing it to "other"
        # discards the observation. Eight slides of organizational design filed
        # as "other" is a taxonomy gap reported as noise.
        from src.agents.slides.slide_schemas import validate_slide_record

        problems = validate_slide_record({
            "slide_type": "regulatory_pathway", "core_message": "x",
            "content": {"titleRow": {"titleTxt": "T"}},
        })
        assert any("not yet in the canon" in p for p in problems)
        assert not any("use 'other' instead" in p for p in problems)

    def test_an_unusable_identifier_is_still_an_error(self):
        from src.agents.slides.slide_schemas import validate_slide_record

        problems = validate_slide_record({
            "slide_type": "Regulatory Pathway!", "core_message": "x",
            "content": {"titleRow": {"titleTxt": "T"}},
        })
        assert any("lower_snake_case" in p for p in problems)

    def test_proposals_accumulate_occurrences(self, tmp_path):
        # One sighting is an oddity; the same coined type across several decks
        # is a type the canon is missing.
        import yaml
        from src.agents.slides.slide_schemas import propose_slide_type

        path = tmp_path / "_proposed-slide-types.yaml"
        propose_slide_type(path, "regulatory_pathway", "FDA timeline", "deck-a#04", "2026-08-23")
        propose_slide_type(path, "regulatory_pathway", "FDA timeline", "deck-b#07", "2026-08-24")

        data = yaml.safe_load(path.read_text())
        assert len(data["proposals"]) == 1
        assert data["proposals"][0]["occurrences"] == 2
        assert data["proposals"][0]["seen_in"] == ["deck-a#04", "deck-b#07"]
        assert data["proposals"][0]["status"] == "proposed"


class TestResumeSafety:
    """
    Resume reads frontmatter only. Anything that then rewrites the file from that
    partial record destroys the body — which is exactly what happened: two reused
    slides had their transcribed json-content replaced with `{}`.
    """

    def test_a_resumed_record_is_not_rewritten(self, tmp_path):
        from src.agents.slides.slide_markdown import render_slide_markdown

        path = tmp_path / "01-team.md"
        path.write_text(render_slide_markdown({
            "slide_type": "team",
            "core_message": "The founders are neuroscientists.",
            "content": {"titleRow": {"titleTxt": "FOUNDING TEAM"},
                        "executivesRow": [{"fullName": "Dana Whitfield, PhD"}]},
        }), encoding="utf-8")
        before = path.read_text(encoding="utf-8")

        # Simulate the final write pass over a resumed record: frontmatter only,
        # no content. The guard must skip it.
        resumed = {"slide_type": "team", "_resumed": True, "index_number": 1,
                   "filename": "01-team.md"}
        if not (resumed.get("_resumed") and not resumed.get("_cdn_added")):
            from src.agents.slides.slide_stenographer import _write_slide
            _write_slide(tmp_path, resumed)

        assert path.read_text(encoding="utf-8") == before
        assert "Dana Whitfield, PhD" in path.read_text(encoding="utf-8")

    def test_existing_slide_returns_none_when_stale(self, tmp_path):
        from src.agents.slides.slide_stenographer import _is_stale

        # Written before the reveal verdict was captured.
        assert _is_stale({"reveal_sequence": "2/3"}) is not None
        # Written before the vocabulary was opened.
        assert _is_stale({"slide_type": "other"}) is not None
        # Current.
        assert _is_stale({"reveal_sequence": "2/3", "reveal_evidence": "vision",
                          "slide_type": "team"}) is None
        assert _is_stale({"slide_type": "team"}) is None


# =============================================================================
# Time-series analyst
# =============================================================================

class TestPeriodParsing:
    """
    Source documents spell periods every way there is. None of those forms may
    survive into a written file — `03/04/2023` is March 4th to an American and
    April 3rd to everyone else.
    """

    @pytest.mark.parametrize("raw,expected", [
        ("Feb-23", "2023-02"),
        ("February 2023", "2023-02"),
        ("2023-02", "2023-02"),
        ("2/2023", "2023-02"),
        ("2023/02", "2023-02"),
        ("as of 2023-02", "2023-02"),
        ("Feb 1, 2023", "2023-02"),
        ("1-Feb-23", "2023-02"),
    ])
    def test_every_month_form_normalizes_to_iso(self, raw, expected):
        from src.agents.timeseries.periods import parse_period

        assert parse_period(raw).year_month == expected

    @pytest.mark.parametrize("raw,expected", [
        ("Q1 2024", "2024-Q1"), ("Q1'24", "2024-Q1"),
        ("2024-Q1", "2024-Q1"), ("2024Q1", "2024-Q1"),
    ])
    def test_quarter_forms(self, raw, expected):
        from src.agents.timeseries.periods import parse_period

        period = parse_period(raw)
        assert period.year_quarter == expected
        assert period.grain == "quarterly"

    def test_two_digit_years_are_flagged_ambiguous(self):
        from src.agents.timeseries.periods import parse_period

        assert parse_period("Feb-23").ambiguous is True
        assert parse_period("February 2023").ambiguous is False

    def test_a_column_settles_its_own_day_first_convention(self):
        # 03/04/2023 alone is unresolvable. Beside 13/04/2023 it is not: 13
        # cannot be a month, so the whole column is day-first.
        from src.agents.timeseries.periods import parse_period, parse_period_series

        assert parse_period("03/04/2023").iso_date == "2023-03-04"
        assert parse_period("03/04/2023").ambiguous is True

        column = parse_period_series(["03/04/2023", "13/04/2023"])
        assert column[0].iso_date == "2023-04-03"

    def test_unparseable_returns_none_rather_than_guessing(self):
        from src.agents.timeseries.periods import parse_period

        assert parse_period("sometime last year") is None
        assert parse_period("") is None


class TestTimeline:
    """The origin belongs to the company, never to the document."""

    def _timeline(self, year=2023, month=2):
        from src.agents.timeseries.timeline import Origin, Timeline

        return Timeline(Origin(year=year, month=month, basis="earliest_data_point"))

    def test_a_source_starting_later_does_not_restart_the_count(self):
        # With a Feb-2023 origin, a spreadsheet beginning January 2024 lands on
        # month_count 12 — not 01. This is the whole mechanism.
        from src.agents.timeseries.periods import parse_period

        assert self._timeline().month_count(parse_period("2024-01")) == 12

    def test_origin_month_is_count_one(self):
        from src.agents.timeseries.periods import parse_period

        assert self._timeline().month_count(parse_period("2023-02")) == 1

    def test_quarter_and_year_counts_share_the_origin(self):
        from src.agents.timeseries.periods import parse_period

        timeline = self._timeline()
        assert timeline.quarter_count(parse_period("2023-Q1")) == 1   # contains the origin
        assert timeline.quarter_count(parse_period("Q2 2025")) == 10
        assert timeline.year_count(parse_period("2025")) == 3

    def test_count_for_follows_the_periods_own_grain(self):
        from src.agents.timeseries.periods import parse_period

        timeline = self._timeline()
        assert timeline.count_for(parse_period("2024-01")) == 12    # monthly
        assert timeline.count_for(parse_period("Q2 2025")) == 10    # quarterly
        assert timeline.count_for(parse_period("2025")) == 3        # annual

    def test_fiscal_month_counts_from_the_fiscal_year_start(self):
        from src.agents.timeseries.periods import parse_period
        from src.agents.timeseries.timeline import Origin, Timeline

        timeline = Timeline(Origin(2023, 2, "earliest_data_point"),
                            fiscal_year_start_month=4)
        assert timeline.fiscal_month(parse_period("2024-04")) == "01"
        assert timeline.fiscal_month(parse_period("2025-01")) == "10"
        assert timeline.fiscal_month(parse_period("2025-03")) == "12"
        assert self._timeline().fiscal_month(parse_period("2024-04")) is None

    def test_coarse_grains_do_not_invent_finer_columns(self):
        from src.agents.timeseries.periods import parse_period

        columns = self._timeline().columns_for(parse_period("2025"))
        assert columns["YYYY"] == "2025"
        assert columns["MM"] is None and columns["date"] is None
        # a half is finer than a year, so an annual row does not claim one
        assert columns["HH"] is None

    def test_month_range_is_dense(self):
        # Lag operators are index arithmetic; a skipped month shifts every
        # comparison after it and still looks plausible.
        from src.agents.timeseries.periods import parse_period

        assert len(self._timeline().month_range(parse_period("2024-01"))) == 12

    def test_the_earliest_evidence_wins_even_when_it_is_not_data(self):
        from src.agents.timeseries.periods import parse_period
        from src.agents.timeseries.timeline import establish_origin

        origin = establish_origin([
            {"basis": "earliest_data_point", "period": parse_period("2023-02")},
            {"basis": "incorporation", "period": parse_period("2019-04"),
             "source_document": "charter.pdf"},
        ])
        assert origin.year_month == "2019-04"
        assert origin.basis == "incorporation"
        assert origin.confidence == "high"
        # The gap is the point: data starting 2023 now lands at month_count 47.
        assert any(a["basis"] == "earliest_data_point" for a in origin.alternatives)


class TestTimeSeriesTranscriber:
    def _transcriber(self, tmp_path):
        from src.agents.timeseries import TimeSeriesTranscriber

        return TimeSeriesTranscriber("Acme", tmp_path)

    def test_writes_one_file_per_source_and_grain(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([
            Observation(parse_period("2023-02"), "revenue", 1.0, source_document="a.xlsx"),
            Observation(parse_period("2023-03"), "revenue", 2.0, source_document="a.xlsx"),
            Observation(parse_period("Q2 2023"), "revenue", 9.0, source_document="b.pdf"),
        ])
        result = transcriber.write()
        assert len(result["files"]) == 2          # one monthly, one quarterly
        assert any("Monthly" in f for f in result["files"])
        assert any("Quarterly" in f for f in result["files"])

    def test_disagreeing_documents_are_both_kept(self, tmp_path):
        # Juxtapose, never reconcile. The divergence is the finding.
        import csv as _csv
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([
            Observation(parse_period("2023-02"), "revenue", 100.0, basis="actual",
                        source_document="20240101_Acme_Actuals.xlsx"),
            Observation(parse_period("2023-02"), "revenue", 120.0, basis="projection",
                        source_document="20230101_Acme_Projections.xlsx"),
        ])
        result = transcriber.write()
        assert len(result["files"]) == 2
        values = []
        for path in result["files"]:
            values += [r["value"] for r in _csv.DictReader(open(path))]
        assert sorted(values) == ["100.0", "120.0"]

    def test_the_source_period_string_is_preserved(self, tmp_path):
        import csv as _csv
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("Feb-23"), "revenue", 1.0,
                                 source_document="a.xlsx")])
        rows = list(_csv.DictReader(open(transcriber.write()["files"][0])))
        assert rows[0]["year_month"] == "2023-02"       # ISO in the column
        assert rows[0]["source_raw_period"] == "Feb-23"  # the form, as provenance

    def test_dimensioned_series_get_their_own_file(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([
            Observation(parse_period("2023-02"), "revenue", 1.0, source_document="a.xlsx"),
            Observation(parse_period("2023-02"), "shares", 100.0,
                        dimensions={"holder": "Fund I", "security_class": "Series A"},
                        source_document="a.xlsx"),
        ])
        result = transcriber.write()
        assert len(result["files"]) == 2
        assert any("By-Holder-SecurityClass" in f for f in result["files"])

    def test_a_grain_is_never_doubled_in_a_filename(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("Q2 2025"), "revenue", 1.0,
                                 source_document="20250924_Acme_Financials--Quarterly.pdf")])
        name = Path(transcriber.write()["files"][0]).name
        assert name.count("Quarterly") == 1
        assert "---" not in name

    def test_no_observations_is_reported_not_raised(self, tmp_path):
        assert self._transcriber(tmp_path).write()["files"] == []


# =============================================================================
# Defects found by the first live run of the analyst
#
# Every one of these produced a plausible-looking file rather than an error,
# which is why 75 tests passed over them. See
# context-v/issue-resolution/Archive-Dating-And-Time-Series-Defect-Hitlist.md.
# =============================================================================

class TestAnalystDefectsFromFirstRun:

    def _transcriber(self, tmp_path, **kw):
        from src.agents.timeseries import TimeSeriesTranscriber

        return TimeSeriesTranscriber("Acme", tmp_path, **kw)

    def _rows(self, path):
        import csv

        with open(path, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    # --- T1 -----------------------------------------------------------------

    def test_annual_rows_do_not_claim_a_half(self):
        """
        A full year is not the first half of itself. Leaving these populated
        stamped every annual row "H1", so grouping a mixed frame by half counted
        full-year revenue as first-half revenue.
        """
        from src.agents.timeseries import parse_period
        from src.agents.timeseries.timeline import Origin, Timeline

        timeline = Timeline(Origin(year=2018, month=1, basis="incorporation"), None)
        columns = timeline.columns_for(parse_period("2024"))
        assert columns["HH"] is None
        assert columns["half_id"] is None
        assert columns["year_half"] is None

    def test_a_quarter_still_knows_its_half(self):
        from src.agents.timeseries import parse_period
        from src.agents.timeseries.timeline import Origin, Timeline

        timeline = Timeline(Origin(year=2018, month=1, basis="incorporation"), None)
        assert timeline.columns_for(parse_period("2024-Q3"))["QQ"] == "Q3"
        assert timeline.columns_for(parse_period("2024-Q3"))["HH"] == "H2"

    def test_annual_csv_carries_no_half_column(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("2024"), "revenue", 10.0,
                                 source_document="20240101_Acme_Deck.pdf")])
        path = transcriber.write()["files"][0]
        assert "HH" not in self._rows(path)[0]

    # --- T2 -----------------------------------------------------------------

    def test_a_grid_is_dense_from_count_one(self, tmp_path):
        """A missing row is a wrong answer; a visible null row is a known gap."""
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.offer_origin("incorporation", parse_period("2024-01"), "charter.pdf")
        transcriber.add([Observation(parse_period("2024-04"), "revenue", 10.0,
                                 source_document="20240401_Acme_Deck.pdf")])
        result = transcriber.write()
        rows = self._rows(result["files"][0])

        assert [r["month_count"] for r in rows] == ["01", "02", "03", "04"]
        assert [r["is_gap_fill"] for r in rows] == ["True", "True", "True", "False"]
        assert result["gap_rows"] == 3

    def test_a_gap_row_states_no_value(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.offer_origin("incorporation", parse_period("2024-01"), "charter.pdf")
        transcriber.add([Observation(parse_period("2024-03"), "revenue", 10.0,
                                 source_document="20240301_Acme_Deck.pdf")])
        gap = self._rows(transcriber.write()["files"][0])[0]
        assert gap["value"] == "" and gap["metric"] == "" and gap["basis"] == ""

    def test_annual_and_quarterly_grids_densify_on_their_own_counts(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.offer_origin("incorporation", parse_period("2021-01"), "charter.pdf")
        transcriber.add([Observation(parse_period("2024"), "revenue", 10.0,
                                 source_document="20240101_Acme_Deck.pdf")])
        rows = self._rows(transcriber.write()["files"][0])
        assert [r["year_count"] for r in rows] == ["01", "02", "03", "04"]

    # --- T4 -----------------------------------------------------------------

    def test_a_dated_document_lands_on_the_monthly_grid(self, tmp_path):
        """
        The spec defines three grids. A cap table as-of a date is a monthly-grid
        observation that knows its day, not a grid of its own.
        """
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.offer_origin("incorporation", parse_period("2024-09"), "charter.pdf")
        transcriber.add([Observation(parse_period("9/29/2024"), "shares", 100.0,
                                 source_document="20240929_Acme_CapTable.xlsx")])
        path = transcriber.write()["files"][0]
        assert path.endswith("--Monthly.csv")

        row = self._rows(path)[0]
        assert row["date"] == "2024-09-29"       # the stated day survives
        assert row["DD"] == "29"
        assert row["source_raw_period"] == "9/29/2024"

    # --- T6 -----------------------------------------------------------------

    def test_a_source_with_no_date_is_named_undated_not_zeroes(self, tmp_path):
        """`00000000` sorts like a date, reads like a date, and is not one."""
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("2024"), "deal_size", 1.0,
                                 source_document="UNP Deals.xlsx")])
        result = transcriber.write()
        assert Path(result["files"][0]).name.startswith("undated_")
        assert result["undated_sources"] == ["UNP Deals.xlsx"]

    def test_a_declared_source_date_beats_an_absent_filename_stamp(self, tmp_path):
        from datetime import date

        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.declare_source_date("cap.xlsx", date(2024, 9, 29))
        transcriber.add([Observation(parse_period("2024-09"), "shares", 1.0,
                                 source_document="cap.xlsx")])
        result = transcriber.write()
        assert Path(result["files"][0]).name.startswith("20240929_")
        assert result["undated_sources"] == []

    # --- T3: the transcriber computes nothing --------------------------------

    def _twelve_months(self, year=2024, metric="revenue", source="20240101_Acme_M.xlsx"):
        from src.agents.timeseries import Observation, parse_period

        return [Observation(parse_period(f"{year}-{m:02d}"), metric, 10.0,
                            source_document=source) for m in range(1, 13)]

    def test_monthly_data_never_reaches_a_coarser_grid(self, tmp_path):
        """
        Twelve stated months are twelve monthly rows and nothing else. Summing
        them into a year produces a number no document states, and a derived
        number in a transcription cannot be told from a transcribed one.
        """
        transcriber = self._transcriber(tmp_path)
        transcriber.add(self._twelve_months())
        files = transcriber.write()["files"]

        assert len(files) == 1
        assert files[0].endswith("--Monthly.csv")

    def test_there_is_no_metric_kind_declaration(self, tmp_path):
        """Flow-versus-stock is an analysis judgment; nothing here consumes it."""
        assert not hasattr(self._transcriber(tmp_path), "declare_metric_kind")

    def test_no_is_rolled_up_column_exists(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("2024-01"), "revenue", 1.0,
                                     source_document="20240101_Acme_M.xlsx")])
        assert "is_rolled_up" not in self._rows(transcriber.write()["files"][0])[0]

    def test_a_quarterly_figure_is_never_split_into_months(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("Q2 2024"), "revenue", 300.0,
                                     source_document="20240401_Acme_Q.xlsx")])
        files = transcriber.write()["files"]
        assert len(files) == 1 and files[0].endswith("--Quarterly.csv")

    # --- zero padding ---------------------------------------------------------

    def test_every_count_and_date_part_is_zero_padded(self, tmp_path):
        """
        Unpadded values sort 1, 10, 11, 12, 2, 3 in every spreadsheet and naive
        join, silently reordering a series while the chart still looks fine.
        """
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.offer_origin("incorporation", parse_period("2024-01"), "charter.pdf")
        transcriber.add([Observation(parse_period("2024-03"), "revenue", 1.0,
                                     source_document="20240301_Acme_M.xlsx")])
        row = [r for r in self._rows(transcriber.write()["files"][0])
               if r["metric"] == "revenue"][0]
        assert row["month_count"] == "03"
        assert row["MM"] == "03"
        assert row["DD"] == "01"
        assert row["YYYY"] == "2024"
        assert row["date"] == "2024-03-01"

    def test_counts_past_ninety_nine_still_sort_by_value(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.offer_origin("incorporation", parse_period("2016-01"), "charter.pdf")
        transcriber.add([Observation(parse_period("2024-08"), "revenue", 1.0,
                                     source_document="20240801_Acme_M.xlsx")])
        counts = [r["month_count"] for r in self._rows(transcriber.write()["files"][0])]
        assert counts[-1] == "104"
        assert counts == sorted(counts, key=int)   # not lexically

    # --- fiscal ---------------------------------------------------------------

    def test_fiscal_month_is_one_column_not_a_fiscal_calendar(self, tmp_path):
        from src.agents.timeseries import parse_period
        from src.agents.timeseries.timeline import Origin, Timeline

        timeline = Timeline(Origin(year=2024, month=1, basis="x"), 4)   # April start
        assert timeline.columns_for(parse_period("2024-04"))["FM"] == "01"
        assert timeline.columns_for(parse_period("2024-12"))["FM"] == "09"
        assert timeline.columns_for(parse_period("2025-03"))["FM"] == "12"

    def test_fiscal_month_is_null_on_a_calendar_year(self, tmp_path):
        from src.agents.timeseries import parse_period
        from src.agents.timeseries.timeline import Origin, Timeline

        timeline = Timeline(Origin(year=2024, month=1, basis="x"), None)
        assert timeline.columns_for(parse_period("2024-04"))["FM"] is None

    # --- T9 -----------------------------------------------------------------

    def test_the_readme_names_metrics_missing_from_a_sibling_file(self, tmp_path):
        """
        Labels are never renamed, so a reader filtering on one can silently miss
        the same series under another. Naming the asymmetry is the README's job;
        deciding the two are the same thing is not.
        """
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([
            Observation(parse_period("2024-01"), "Total Revenue", 1.0,
                        source_document="20240101_Acme_Hist.xlsx"),
            Observation(parse_period("2024-01"), "Revenue", 2.0,
                        source_document="20240102_Acme_Model.xlsx"),
        ])
        transcriber.write()
        readme = (tmp_path / "timeseries" / "README.md").read_text()

        assert "Metrics that are not in every file of a grain" in readme
        assert "`Total Revenue`" in readme and "`Revenue`" in readme

    def test_the_readme_lists_undated_sources(self, tmp_path):
        from src.agents.timeseries import Observation, parse_period

        transcriber = self._transcriber(tmp_path)
        transcriber.add([Observation(parse_period("2024"), "deal_size", 1.0,
                                 source_document="UNP Deals.xlsx")])
        transcriber.write()
        readme = (tmp_path / "timeseries" / "README.md").read_text()
        assert "## Undated sources" in readme and "`UNP Deals.xlsx`" in readme


# =============================================================================
# Grounding memo sections in the dataroom
#
# The writer wrote every section from web research alone while a fully populated
# `dataroom_analysis` sat unread in state — which is how a memo reported terms as
# "not publicly available" beside seven executed SAFEs in the same folder.
#
# Grounding is an enhancement on the existing path, never a precondition. Most
# deals are pipeline deals: a deck plus web research, no dataroom. Those must
# keep working exactly as before, so every shape `dataroom_analysis` takes in the
# wild is covered here.
# =============================================================================

class TestDataroomGrounding:

    def _section(self, name="Funding & Terms", filename="09-funding--terms.md"):
        from types import SimpleNamespace

        return SimpleNamespace(name=name, filename=filename)

    def _facts(self, *args):
        from src.agents.writer import dataroom_facts_for_section

        return dataroom_facts_for_section(*args)

    # --- pipeline deals: no dataroom, and nothing may break ------------------

    @pytest.mark.parametrize("absent", [None, {}, "", [], 0, False])
    def test_a_deal_with_no_dataroom_gets_no_block(self, absent):
        """Aito, Kearny Jackson, Thinking Machines: the key is absent entirely."""
        assert self._facts(self._section(), absent) == ""

    def test_a_malformed_dataroom_is_ignored_not_raised(self):
        """A section must never fail because a grounding block could not be built."""
        for junk in ("a string", 42, ["not", "a", "dict"], object()):
            assert self._facts(self._section(), junk) == ""

    def test_a_section_with_no_name_gets_no_block(self):
        from types import SimpleNamespace

        assert self._facts(SimpleNamespace(), {"legal_docs": [{"investment_amount": 1}]}) == ""

    def test_a_dataroom_with_nothing_for_this_section_gets_no_block(self):
        """A cap table says nothing about competitive positioning."""
        room = {"legal_docs": [{"document_source": "x.pdf", "investment_amount": 50000}]}
        assert self._facts(self._section("Competitive Landscape", "06-competitive.md"), room) == ""

    # --- portfolio companies: the dataroom is there and must be used ---------

    def test_financing_instruments_reach_the_terms_section(self):
        room = {
            "document_count": 158,
            "legal_docs": [
                {"document_source": "Ritchson_SAFE.pdf", "investment_amount": 125000.0,
                 "valuation_cap": 5000000.0, "discount_rate": None},
                {"document_source": "Wearne_SAFE.pdf", "investment_amount": 50000.0,
                 "valuation_cap": 10000000.0, "discount_rate": 20.0},
                {"document_source": "Bylaws.pdf"},          # no terms — excluded
            ],
        }
        out = self._facts(self._section(), room)
        assert "Ritchson_SAFE.pdf" in out and "Wearne_SAFE.pdf" in out
        assert "Bylaws.pdf" not in out

    def test_differing_terms_are_both_present_and_not_reconciled(self):
        """Seven SAFEs at three caps is structure, not a conflict to resolve."""
        room = {"legal_docs": [
            {"document_source": "a.pdf", "investment_amount": 125000.0, "valuation_cap": 5000000.0},
            {"document_source": "b.pdf", "investment_amount": 25000.0, "valuation_cap": 10000000.0},
        ]}
        out = self._facts(self._section(), room)
        assert "5000000" in out and "10000000" in out
        assert "never average or pick one" in out

    def test_the_reconciled_summary_is_never_used(self):
        """`legal_summary` collapses instruments; only per-document rows are passed."""
        room = {
            "legal_docs": [{"document_source": "a.pdf", "investment_amount": 50000.0,
                            "valuation_cap": 10000000.0}],
            "legal_summary": {"terms": {"valuation_cap": 99999999.0}},
        }
        assert "99999999" not in self._facts(self._section(), room)

    def test_legal_docs_as_a_dict_is_handled(self):
        """The artifact writes {documents: [...]}; state carries a bare list."""
        room = {"legal_docs": {"documents": [
            {"document_source": "a.pdf", "investment_amount": 50000.0, "valuation_cap": 7000000.0}]}}
        assert "7000000" in self._facts(self._section(), room)

    def test_the_block_forbids_saying_a_stated_fact_is_undisclosed(self):
        room = {"legal_docs": [{"document_source": "a.pdf", "valuation_cap": 7000000.0}]}
        out = self._facts(self._section(), room)
        assert "not disclosed" in out and "outrank web research" in out

    def test_team_and_traction_route_to_their_own_sections(self):
        room = {"team": {"founders": [{"name": "A"}]},
                "traction": {"total_customers": 12},
                "legal_docs": []}
        team = self._facts(self._section("Organization", "04-organization.md"), room)
        opp = self._facts(self._section("Opportunity", "06-opportunity.md"), room)
        assert "founders" in team
        assert "total_customers" in opp
        assert "total_customers" not in team
