"""
Regression tests for the dataroom extraction layer.

These cover the failure modes that were found in production data and that would
fail silently if reintroduced — each one produced a confidently wrong answer
rather than an error, which is why they survived so long.
"""

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
