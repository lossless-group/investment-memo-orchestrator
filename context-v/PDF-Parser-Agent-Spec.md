---
date_created: 2026-1-27
date_modified: 2026-1-27
publish: true
title: "PDF Parser Agent Specification"
slug: pdf-parser-agent-spec
at_semantic_version: 0.0.1.0
authors:
  - Michael Staton
augmented_with: "Claude Code on Opus 4.5"
site_uuid: a346a222-5313-b53f-7e4e-3196ca31d371
lede: "A small specification for an agent and script to parse PDFs and convert them to markdown with properly formatted citations."
---
# PDF Parser Agent Specification

## Overview

The `pdf_parser` agent extracts content from market research PDFs and converts them to well-structured markdown with properly formatted citations. This enables both users and downstream agents to leverage high-quality research sources for investment memo generation.

## Purpose

Market research reports (from firms like McKinsey, CB Insights, PitchBook, Gartner, etc.) contain valuable data, analysis, and citations that are difficult to work with in PDF format. This agent:

- **Converts content to markdown**: Preserves document structure (headings, lists, tables)
- **Extracts and reformats citations**: Converts footnotes, endnotes, and reference sections to our standard format
- **Creates agent-consumable output**: Structured JSON alongside human-readable markdown
- **Enables source attribution**: Parsed citations can be used by citation enrichment agents

---

## Available PDF Libraries

This project already includes PDF parsing libraries. **Use these, do not add new dependencies.**

### Primary: PyMuPDF (fitz)
```python
import fitz  # PyMuPDF>=1.24.0
```
- Fast text extraction with position data
- Handles both text-based and image-based PDFs
- Extracts document structure (headings, paragraphs)
- Can identify footnotes and endnotes by position
- Already used in `deck_analyst.py`

### Secondary: pypdf
```python
from pypdf import PdfReader  # Already imported in deck_analyst.py
```
- Simpler API for basic text extraction
- Good for quick text-only extraction
- Less structural information than PyMuPDF

### Image rendering: pdf2image (optional)
```python
from pdf2image import convert_from_path  # Requires Poppler
```
- For image-based PDFs requiring OCR
- High-quality page rendering
- Already configured with fallback handling

---

## Citation Format Standards

### Our Standard Format (Obsidian-style)

**Inline references:**
```markdown
The market is expected to reach $50B by 2030[^1], [^2].
```

**Citation block (at end of document, sometimes at end of page, sometimes both):**
```markdown
[^1]: 2024, Mar 15. [Global Nuclear Energy Market Report](https://example.com/report). Published: 2024-03-15 | Updated: N/A

[^2]: 2023, Nov 08. [McKinsey Energy Outlook](https://mckinsey.com/energy). Published: 2023-11-08 | Updated: 2024-01-20
```

### Common Input Formats to Parse

The agent must handle these citation styles commonly found in research PDFs, including be able to parse all content in the citation definition in the reference section, footnotes or endnotes:

#### 1. Numeric Footnotes
```
The market grew 15%¹ with major players including Company A² and Company B³.
---
¹ Gartner Market Analysis, 2024
² Company A Annual Report, 2023
³ CB Insights, "Competitor Landscape", November 2023
⁴ 2023, Nov. "An article title", The Atlantic. https://theatlantic.com/example-article-title
```

#### 2. Superscript References
```
Global TAM reached $23B (Smith et al., 2024)¹ representing a 12% CAGR²
```

#### 3. Bracketed References
```
Recent studies [1, 2, 3] indicate growth acceleration. The sector [4] shows promise.
```

#### 4. Endnotes/References Section
```
REFERENCES
1. Smith, J. (2024). Market Analysis Report. Gartner. https://gartner.com/report
2. CB Insights. (2023, November). Industry Report. Retrieved from https://cbinsights.com
3. McKinsey & Company. Global Outlook 2024.
```

#### 5. Bibliography Style
```
Bibliography

Gartner, Inc. (2024). Nuclear Energy Market Analysis. Available at: https://...
McKinsey & Company. (2023). Energy Transition Report. McKinsey Global Institute.
PitchBook Data, Inc. (2024). Q1 VC Funding Report.
```

---

## Output Structure

### Directory Layout

```
output/{Company}-v0.0.x/
├── 0-parsed-pdfs/                    # NEW - Parsed PDF artifacts
│   ├── parsed-pdfs-manifest.json     # Index of all parsed PDFs
│   ├── {pdf-name}/
│   │   ├── content.md                # Full markdown content
│   │   ├── content.json              # Structured JSON representation
│   │   ├── citations.json            # Extracted citations only
│   │   ├── sections/                 # Individual sections (optional)
│   │   │   ├── 01-executive-summary.md
│   │   │   └── ...
│   │   └── metadata.json             # PDF metadata and parsing stats
│   └── {another-pdf-name}/
│       └── ...
├── 0-deck-analysis.json + .md
├── 1-research/
└── ...
```

### `parsed-pdfs-manifest.json` Schema

```json
{
  "generated_at": "2024-01-15T10:30:00Z",
  "pdfs": [
    {
      "id": "mckinsey-nuclear-outlook-2024",
      "original_filename": "McKinsey Nuclear Energy Outlook 2024.pdf",
      "source_path": "data/research/McKinsey Nuclear Energy Outlook 2024.pdf",
      "output_dir": "0-parsed-pdfs/mckinsey-nuclear-outlook-2024/",
      "page_count": 48,
      "word_count": 15420,
      "citations_extracted": 67,
      "sections_identified": 8,
      "parsing_method": "text_extraction",  // or "vision_ocr"
      "confidence": 0.95
    }
  ],
  "summary": {
    "total_pdfs": 2,
    "total_citations": 134,
    "total_pages": 96,
    "parsing_methods": {
      "text_extraction": 1,
      "vision_ocr": 1
    }
  }
}
```

### `citations.json` Schema

```json
{
  "pdf_source": "McKinsey Nuclear Energy Outlook 2024.pdf",
  "extraction_date": "2024-01-15",
  "citation_format_detected": "endnotes",
  "citations": [
    {
      "original_ref": "1",
      "original_text": "IEA World Energy Outlook 2023, International Energy Agency, November 2023",
      "parsed": {
        "title": "IEA World Energy Outlook 2023",
        "author": "International Energy Agency",
        "date": "2023-11-01",
        "url": null,
        "type": "report"
      },
      "our_format": "[^1]: 2023, Nov 01. [IEA World Energy Outlook 2023](). Published: 2023-11-01 | Updated: N/A",
      "page_references": [4, 7, 12, 15],
      "confidence": 0.9
    },
    {
      "original_ref": "2",
      "original_text": "Nuclear Energy Market Size, Grand View Research, https://grandviewresearch.com/...",
      "parsed": {
        "title": "Nuclear Energy Market Size",
        "author": "Grand View Research",
        "date": null,
        "url": "https://grandviewresearch.com/...",
        "type": "market_research"
      },
      "our_format": "[^2]: N/A. [Nuclear Energy Market Size](https://grandviewresearch.com/...). Published: N/A | Updated: N/A",
      "page_references": [8],
      "confidence": 0.85
    }
  ],
  "unmatched_references": [
    {
      "text": "³ Internal company estimates",
      "reason": "No external source - internal data"
    }
  ]
}
```

### `metadata.json` Schema

```json
{
  "original_filename": "McKinsey Nuclear Energy Outlook 2024.pdf",
  "file_hash": "sha256:abc123...",
  "file_size_bytes": 2456789,
  "page_count": 48,
  "pdf_metadata": {
    "title": "Nuclear Energy: The Path to 2050",
    "author": "McKinsey & Company",
    "created": "2024-01-10T08:30:00Z",
    "modified": "2024-01-12T14:22:00Z",
    "producer": "Adobe InDesign"
  },
  "parsing_stats": {
    "method": "text_extraction",
    "text_extracted_chars": 125000,
    "images_detected": 24,
    "tables_detected": 8,
    "footnotes_detected": 45,
    "endnotes_detected": 22,
    "processing_time_seconds": 12.5
  },
  "structure_analysis": {
    "sections": [
      {"title": "Executive Summary", "start_page": 3, "end_page": 5},
      {"title": "Market Overview", "start_page": 6, "end_page": 12},
      {"title": "Competitive Landscape", "start_page": 13, "end_page": 20}
    ],
    "has_toc": true,
    "toc_page": 2,
    "references_section": {"start_page": 45, "end_page": 48}
  }
}
```

---

## Agent Architecture

### Function Signature

```python
def pdf_parser_agent(state: MemoState) -> dict:
    """
    Parses market research PDFs into markdown with extracted citations.

    Reads PDFs from paths specified in state or company data file.
    Outputs structured content to 0-parsed-pdfs/ directory.

    Args:
        state: Current memo state with pdf_paths or research_pdfs field

    Returns:
        Updated state with parsed_pdfs data
    """
```

### State Schema Addition

Add to `src/state.py`:

```python
class ParsedPDFData(TypedDict, total=False):
    """Data from a parsed research PDF."""
    pdf_id: str                      # Slugified identifier
    original_filename: str            # Original file name
    output_dir: str                   # Path to parsed output
    page_count: int
    word_count: int
    sections: List[Dict[str, Any]]    # Identified sections
    citations: List[Dict[str, Any]]   # Extracted citations in our format
    tables: List[Dict[str, Any]]      # Extracted tables
    key_findings: List[str]           # LLM-extracted key insights
    parsing_confidence: float         # 0.0-1.0

class MemoState(TypedDict):
    # ... existing fields ...
    research_pdf_paths: Optional[List[str]]  # Input PDF paths
    parsed_pdfs: Optional[List[ParsedPDFData]]  # Parsed PDF data
```

### Processing Pipeline

```
1. INPUT VALIDATION
   └── Check for PDF paths in state.research_pdf_paths or data/{company}.json
   └── Validate files exist and are readable
   └── Check file sizes (warn if >50MB)

2. PDF ANALYSIS (per file)
   ├── Extract PDF metadata (title, author, dates)
   ├── Detect PDF type (text-based vs image-based)
   ├── Identify document structure (TOC, sections, references)
   └── Choose extraction method

3. TEXT EXTRACTION
   ├── Text-based PDFs: PyMuPDF text extraction with layout preservation
   └── Image-based PDFs: Convert to images → Claude Vision API

4. STRUCTURE PARSING
   ├── Identify headings (by font size, bold, position)
   ├── Detect lists and bullet points
   ├── Extract tables (as markdown tables)
   └── Preserve paragraph boundaries

5. CITATION EXTRACTION
   ├── Identify citation format (footnotes, endnotes, bibliography)
   ├── Extract inline references (superscripts, brackets)
   ├── Parse reference section
   ├── Match inline refs to full citations
   └── Convert to our standard format

6. MARKDOWN GENERATION
   ├── Convert structure to markdown
   ├── Replace inline citations with [^n] format
   ├── Append citation block at end
   └── Preserve tables and lists

7. LLM ENHANCEMENT (optional)
   ├── Extract key findings/insights
   ├── Summarize each section
   └── Identify data points for tables

8. ARTIFACT SAVING
   ├── Save content.md (full markdown)
   ├── Save content.json (structured)
   ├── Save citations.json (citations only)
   ├── Save metadata.json
   └── Update manifest.json
```

---

## Citation Extraction Strategies

### Strategy 1: Position-Based Detection (PyMuPDF)

```python
def extract_footnotes_by_position(page) -> List[Dict]:
    """
    Detect footnotes by analyzing text position on page.
    Footnotes typically appear:
    - At bottom of page (y > 85% of page height)
    - With smaller font size
    - Starting with superscript number
    """
    blocks = page.get_text("dict")["blocks"]
    footnotes = []

    page_height = page.rect.height
    footnote_zone_start = page_height * 0.85

    for block in blocks:
        if block.get("type") == 0:  # Text block
            bbox = block.get("bbox", [0, 0, 0, 0])
            y_pos = bbox[1]

            if y_pos > footnote_zone_start:
                text = extract_text_from_block(block)
                if re.match(r'^\d+[\.\s]', text):
                    footnotes.append({
                        "ref": re.match(r'^(\d+)', text).group(1),
                        "text": text,
                        "page": page.number + 1
                    })

    return footnotes
```

### Strategy 2: Reference Section Detection

```python
def find_references_section(doc) -> Tuple[int, int]:
    """
    Find the references/bibliography section by looking for:
    - Headings containing "References", "Bibliography", "Notes", "Sources"
    - Sections at end of document with numbered/bulleted citations
    """
    keywords = ["references", "bibliography", "endnotes", "notes", "sources", "works cited"]

    for page_num in range(len(doc) - 1, max(0, len(doc) - 10), -1):
        page = doc[page_num]
        text = page.get_text().lower()

        for keyword in keywords:
            if keyword in text:
                # Verify it's a heading (check font size, position)
                if is_section_heading(page, keyword):
                    return (page_num, len(doc) - 1)

    return (None, None)
```

### Strategy 3: Regex Pattern Matching

```python
CITATION_PATTERNS = {
    # Superscript style: text¹ or text[1]
    "superscript": r'(\d+)\s*[\.\)]\s*(.+?)(?=\n\d+[\.\)]|\Z)',

    # Author-date: (Smith, 2024) or (Smith et al., 2024)
    "author_date": r'\(([A-Z][a-z]+(?:\s+et\s+al\.)?),?\s*(\d{4})\)',

    # Bracketed: [1], [2], [3, 4, 5]
    "bracketed": r'\[(\d+(?:,\s*\d+)*)\]',

    # URL with title: Title. https://...
    "url_citation": r'([^.]+)\.\s*(https?://[^\s]+)',

    # Date with title: November 2023, "Title"
    "dated": r'(\w+\s+\d{4}),?\s*["\']([^"\']+)["\']',
}
```

### Strategy 4: LLM-Assisted Extraction

For complex or ambiguous citation formats, use Claude to parse:

```python
def llm_parse_citation(raw_text: str) -> Dict:
    """Use Claude to parse ambiguous citation formats."""

    prompt = f"""Parse this citation into structured components:

Citation text: {raw_text}

Extract and return JSON with:
{{
  "title": "...",
  "author": "...",
  "date": "YYYY-MM-DD or null",
  "url": "... or null",
  "publication": "...",
  "type": "report|article|book|website|other"
}}

If a field cannot be determined, use null.
Return ONLY valid JSON."""

    response = llm.invoke(prompt)
    return json.loads(response.content)
```

---

## Markdown Conversion Rules

### Heading Detection

| PDF Characteristic | Markdown Level |
|-------------------|----------------|
| Font size > 18pt, bold | `#` (H1) |
| Font size 14-18pt, bold | `##` (H2) |
| Font size 12-14pt, bold | `###` (H3) |
| Bold, same line as text | `**bold text**` inline |

### List Detection

```python
def detect_list_items(text: str) -> List[str]:
    """Detect bullet points and numbered lists."""
    patterns = [
        r'^[\•\-\*\○\●]\s+',     # Bullet characters
        r'^\d+[\.\)]\s+',        # Numbered: 1. or 1)
        r'^[a-z][\.\)]\s+',      # Lettered: a. or a)
        r'^[ivxIVX]+[\.\)]\s+',  # Roman numerals
    ]
    # ...
```

### Table Preservation

Tables detected via PyMuPDF are converted to GitHub-flavored markdown:

```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
```

---

## Pipeline Position

```
PDF_PARSER (new) ──┐
                   │
deck_analyst ──────┼──→ writer → enrichment agents → citation_enrichment
                   │
research_enhanced ─┘
```

**Runs**: At the start of the pipeline, before or parallel to `deck_analyst`

**Consumes**:
- `state.research_pdf_paths`: List of PDF file paths
- `data/{company}.json` → `research_pdfs` field

**Produces**:
- `0-parsed-pdfs/` directory with all parsed content
- `state.parsed_pdfs`: List of `ParsedPDFData` objects
- Citations available for `citation_enrichment` agent

---

## Company Data File Integration

Add support in `data/{Company}.json`:

```json
{
  "type": "direct",
  "mode": "justify",
  "description": "...",
  "deck": "data/Company-deck.pdf",
  "research_pdfs": [
    "data/research/McKinsey-Nuclear-Outlook-2024.pdf",
    "data/research/CB-Insights-Cleantech-Q4-2023.pdf",
    "data/research/Gartner-Energy-Tech-Landscape.pdf"
  ],
  "research_pdf_config": {
    "extract_tables": true,
    "extract_key_findings": true,
    "max_pages_per_pdf": 100,
    "citation_priority": "endnotes"
  }
}
```

---

## Error Handling

### PDF Type Detection Fallback

```python
def extract_with_fallback(pdf_path: str) -> str:
    """Try text extraction, fall back to vision if minimal text."""

    # First attempt: Direct text extraction
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()

    # Check if sufficient text extracted
    if len(text.strip()) < 1000:  # Likely image-based PDF
        print("Minimal text extracted, using Claude Vision...")
        return extract_with_vision(pdf_path)

    return text
```

### Citation Confidence Scoring

```python
def score_citation_confidence(parsed: Dict) -> float:
    """Score how confident we are in citation parsing."""
    score = 1.0

    if not parsed.get("title"):
        score -= 0.3
    if not parsed.get("date"):
        score -= 0.2
    if not parsed.get("url"):
        score -= 0.1
    if parsed.get("type") == "other":
        score -= 0.1

    return max(0.0, score)
```

---

## Usage Examples

### Basic Usage

```bash
# Specify PDFs in company data file
python -m src.main "Aalo Atomics"
# → Reads data/Aalo-Atomics.json → research_pdfs field
# → Parses all listed PDFs before research phase

# Or pass directly via state (for scripts)
python scripts/parse-pdf.py "data/research/McKinsey-Report.pdf"
```

### Standalone PDF Parsing Script

```bash
# Parse a single PDF
python parse-pdf.py data/research/McKinsey-Nuclear-2024.pdf

# Parse multiple PDFs
python parse-pdf.py data/research/*.pdf --output output/parsed-research/

# Parse with specific options
python parse-pdf.py report.pdf --extract-tables --extract-findings
```

### Integration with Memo Generation

Once parsed, the research content is available to downstream agents:

```python
# In research_enhanced.py
def research_enhanced_agent(state: MemoState) -> dict:
    # Check for pre-parsed PDF research
    if state.get("parsed_pdfs"):
        for pdf_data in state["parsed_pdfs"]:
            # Use extracted citations as authoritative sources
            for citation in pdf_data.get("citations", []):
                if citation["confidence"] > 0.8:
                    add_to_research_sources(citation)

            # Use key findings for context
            for finding in pdf_data.get("key_findings", []):
                add_to_research_context(finding)
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Text extraction accuracy | >95% for text-based PDFs |
| Citation extraction rate | >90% of citations captured |
| Citation format conversion | >85% successfully converted to our format |
| Structure preservation | >90% headings/sections correctly identified |
| Processing speed | <30 seconds for 50-page PDF |

---

## Implementation Checklist

- [ ] Create `src/agents/pdf_parser.py` following agent pattern
- [ ] Add `ParsedPDFData` to `src/state.py`
- [ ] Add `research_pdf_paths` and `parsed_pdfs` to `MemoState`
- [ ] Implement text extraction with PyMuPDF
- [ ] Implement vision fallback for image PDFs
- [ ] Implement citation detection (footnotes, endnotes, bibliography)
- [ ] Implement citation format conversion
- [ ] Implement markdown generation with structure preservation
- [ ] Add artifact saving functions to `src/artifacts.py`
- [ ] Create standalone `parse-pdf.py` script
- [ ] Add to workflow graph in `src/workflow.py`
- [ ] Update company data file schema documentation
- [ ] Add tests for citation parsing patterns

---

## Related Documentation

- `context-v/Citation-Reminders.md` - Citation spacing and formatting standards
- `context-v/Table-Generator-Agent-Spec.md` - Similar agent spec pattern
- `context-v/Deck-Analyzer-Agent.md` - Existing PDF handling in deck_analyst
- `src/agents/deck_analyst.py` - Reference implementation for PDF processing
- `src/agents/citation_enrichment.py` - How citations are used downstream
