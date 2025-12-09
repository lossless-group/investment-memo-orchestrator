---
title: Deck Analyzer Agent
lede: A specialized agent for extracting structured data and visual screenshots from pitch decks (PDF and PowerPoint) to bootstrap investment memo generation.
date_authored_initial_draft: 2025-12-09
date_authored_current_draft: 2025-12-09
date_authored_final_draft:
date_first_published:
date_last_updated: 2025-12-09
at_semantic_version: 0.1.0
status: Implemented
augmented_with: Claude Code (Opus 4.5)
category: Agent Documentation
tags: [Deck-Analysis, PDF-Processing, Vision-API, Screenshot-Extraction, Investment-Analysis]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A pitch deck being analyzed by AI, with extracted data points (team, traction, market size) flowing into structured JSON, and key visual slides being captured as screenshots.
date_created: 2025-12-09
date_modified: 2025-12-09
---

# Deck Analyzer Agent

**File**: `src/agents/deck_analyst.py`
**Status**: Implemented
**Last Updated**: 2025-12-09

---

## Overview

The Deck Analyzer Agent is the **first agent** in the investment memo generation pipeline. It processes pitch decks (PDF or PowerPoint) to extract structured company information and create initial section drafts that subsequent agents build upon.

### Key Capabilities

1. **Multi-Format Support**: Processes both PDF (`.pdf`) and PowerPoint (`.pptx`, `.ppt`) decks
2. **Dual Processing Modes**: Text-based extraction for readable PDFs, vision-based for image PDFs
3. **Structured Data Extraction**: Extracts company info into typed schemas (team, traction, market, etc.)
4. **Initial Section Drafts**: Creates draft content for downstream writer agent
5. **Visual Screenshot Extraction**: Identifies and captures key visual pages (NEW - 2025-12-09)

---

## Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DECK ANALYST AGENT                            │
│                       (deck_analyst.py)                              │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Format Detection & Text Extraction                          │
│                                                                      │
│  PDF Deck                          PowerPoint Deck                   │
│  ├─ pypdf text extraction          ├─ python-pptx extraction        │
│  ├─ Check char count               ├─ Slide text + tables           │
│  └─ If < 1000 chars → Vision mode  └─ Notes extraction              │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 2: Content Analysis (Text or Vision)                           │
│                                                                      │
│  Text Mode                          Vision Mode (Image PDFs)         │
│  ├─ Send full text to Claude        ├─ Render pages as JPEG         │
│  └─ Extract JSON schema             ├─ Process in batches of 5      │
│                                     ├─ Send to Claude Vision API    │
│                                     └─ Merge batch results          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 3: Initial Section Draft Generation                            │
│                                                                      │
│  For each extracted field with substantial data:                     │
│  ├─ deck-problem.md      (problem_statement)                        │
│  ├─ deck-solution.md     (solution_description)                     │
│  ├─ deck-product.md      (product_description)                      │
│  ├─ deck-business-model.md (business_model)                         │
│  ├─ deck-market.md       (market_size: TAM/SAM/SOM)                 │
│  ├─ deck-competitive.md  (competitive_landscape)                    │
│  ├─ deck-traction.md     (traction_metrics, milestones)             │
│  ├─ deck-team.md         (team_members)                             │
│  ├─ deck-funding.md      (funding_ask, use_of_funds)                │
│  └─ deck-gtm.md          (go_to_market)                             │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 4: Artifact Saving                                             │
│                                                                      │
│  output/{Company}-v0.0.x/                                           │
│  ├─ 0-deck-analysis.json      Structured extraction data            │
│  ├─ 0-deck-analysis.md        Human-readable summary                │
│  └─ 0-deck-sections/          Initial section drafts                │
│      ├─ deck-problem.md                                             │
│      ├─ deck-solution.md                                            │
│      └─ ...                                                         │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 5: Visual Screenshot Extraction (PDF only)                     │
│                                                                      │
│  ├─ Send low-res thumbnails to Claude Vision                        │
│  ├─ Identify pages with visual value (not text-only slides)         │
│  ├─ Categorize: team, product, traction, market, etc.               │
│  ├─ Render selected pages at 150 DPI as PNG                         │
│  └─ Save to deck-screenshots/ directory                             │
│                                                                      │
│  output/{Company}-v0.0.x/                                           │
│  └─ deck-screenshots/                                               │
│      ├─ page-03-team.png                                            │
│      ├─ page-07-traction.png                                        │
│      └─ page-12-product.png                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Extraction Schema

The agent extracts data into the following JSON schema:

```json
{
  "company_name": "Company Name",
  "tagline": "One-line description",
  "problem_statement": "The problem being solved",
  "solution_description": "How the company solves it",
  "product_description": "What the product does",
  "business_model": "How the company makes money",
  "market_size": {
    "TAM": "Total Addressable Market",
    "SAM": "Serviceable Addressable Market",
    "SOM": "Serviceable Obtainable Market"
  },
  "traction_metrics": [
    {"metric": "ARR", "value": "$2M"},
    {"metric": "MoM Growth", "value": "15%"}
  ],
  "team_members": [
    {
      "name": "Jane Doe",
      "role": "CEO & Co-founder",
      "background": "Previously VP Engineering at BigCo"
    }
  ],
  "funding_ask": "$5M Series A",
  "use_of_funds": ["Product development", "Sales team expansion"],
  "competitive_landscape": "Main competitors are X, Y, Z...",
  "go_to_market": "Enterprise sales motion targeting...",
  "milestones": ["Launched v2.0", "Reached 100 customers"],
  "extraction_notes": ["Team backgrounds not fully disclosed"],
  "deck_page_count": 22,
  "screenshots": [
    {
      "path": "deck-screenshots/page-03-team.png",
      "filename": "page-03-team.png",
      "page_number": 3,
      "category": "team",
      "description": "Founding team photos with backgrounds",
      "width": 1275,
      "height": 1650
    }
  ]
}
```

---

## Screenshot Extraction Feature

### Purpose

Pitch decks contain valuable visual content that enhances investment memos:
- Team photos build credibility
- Traction charts show growth trajectory
- Product screenshots demonstrate the solution
- Market diagrams illustrate opportunity size

The screenshot extraction feature automatically identifies and captures these visuals.

### How It Works

#### 1. Visual Page Identification

After text extraction, Claude's vision API analyzes page thumbnails to identify visual content:

```python
def identify_visual_pages(pdf_path, deck_analysis, client):
    """Use Claude to identify pages with visual value."""

    # Render all pages at low resolution (0.3x scale)
    # Send to Claude Vision API
    # Return list of page selections with categories
```

Categories recognized:
- `team` - Team photos, org charts, founder headshots
- `product` - Product screenshots, UI mockups, demo screens
- `traction` - Growth charts, metrics graphs, revenue/user charts
- `market` - Market size charts, TAM/SAM/SOM diagrams
- `competitive` - Competitive landscape diagrams, positioning matrices
- `architecture` - Technical architecture diagrams, system diagrams
- `timeline` - Roadmap visuals, milestone timelines

#### 2. High-Quality Rendering

Selected pages are rendered using one of two backends:

**pdf2image (preferred)** - Uses Poppler for high-quality rendering
```python
from pdf2image import convert_from_path

images = convert_from_path(
    pdf_path,
    dpi=150,  # Resolution
    first_page=page_num,
    last_page=page_num,
    fmt="png"
)
```

**PyMuPDF (fallback)** - Built-in, no external dependencies
```python
import fitz

page = doc[page_num]
scale = 150 / 72.0  # 150 DPI
mat = fitz.Matrix(scale, scale)
pix = page.get_pixmap(matrix=mat)
```

#### 3. Artifact Storage

Screenshots are saved with semantic filenames:
```
deck-screenshots/
├── page-03-team.png
├── page-07-traction.png
├── page-12-product.png
└── page-15-market.png
```

### Configuration Options

```python
# In extract_deck_screenshots()
extract_deck_screenshots(
    pdf_path,
    output_dir,
    page_selections,
    use_pdf2image=True,    # Use Poppler if available
    dpi=150,               # Resolution (72-300)
    quality=85             # JPEG quality (unused for PNG)
)
```

### Dependencies

**Python packages**:
```toml
# pyproject.toml
dependencies = [
    "PyMuPDF>=1.24.0",     # Always available fallback
    "pdf2image>=1.17.0",   # Higher quality (optional)
]
```

**System dependencies** (for pdf2image):
```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt install poppler-utils
```

---

## Text vs Vision Mode

### When Text Mode is Used

Text extraction is attempted first for all PDF decks:

```python
deck_content = extract_text_from_pdf(deck_path)

# If sufficient text extracted (> 1000 chars), use text mode
if len(deck_content.strip()) >= 1000:
    # Text-based analysis
```

**Advantages**:
- Faster processing
- Lower API costs
- More accurate for text-heavy decks

### When Vision Mode is Used

Vision mode activates automatically when text extraction yields minimal content:

```python
if len(deck_content.strip()) < 1000:
    # Image-based PDF detected
    return analyze_pdf_with_vision(deck_path, state)
```

**Vision mode process**:
1. Render each page as JPEG (0.5x scale for API payload)
2. Process in batches of 5 pages (API limits)
3. Send to Claude Vision API with extraction prompt
4. Merge results from all batches

**Advantages**:
- Works with image-based PDFs (design-heavy decks)
- Extracts from charts and diagrams
- Handles scanned documents

---

## Integration with Pipeline

### Entry Point

The deck analyst is typically the **first agent** in the workflow:

```python
# In workflow.py
workflow.set_entry_point("deck_analyst")
workflow.add_edge("deck_analyst", "research")
```

### State Updates

The agent returns:

```python
return {
    "deck_analysis": deck_analysis,      # Extracted data
    "draft_sections": section_drafts,    # Initial section content
    "messages": ["Deck analysis complete..."]
}
```

### Downstream Usage

**Research Agent**: Uses deck analysis to target gaps
```python
# Focus research on areas not covered by deck
gaps = identify_gaps_from_deck(state["deck_analysis"])
```

**Writer Agent**: Incorporates deck drafts
```python
# Load deck section drafts as source material
deck_sections = load_deck_sections(output_dir / "0-deck-sections")
```

---

## Artifact Output

### Directory Structure

```
output/{Company}-v0.0.x/
├── 0-deck-analysis.json       # Structured extraction
├── 0-deck-analysis.md         # Human-readable summary
├── 0-deck-sections/           # Initial section drafts
│   ├── deck-problem.md
│   ├── deck-solution.md
│   ├── deck-product.md
│   ├── deck-business-model.md
│   ├── deck-market.md
│   ├── deck-competitive.md
│   ├── deck-traction.md
│   ├── deck-team.md
│   ├── deck-funding.md
│   └── deck-gtm.md
└── deck-screenshots/          # Visual page captures
    ├── page-03-team.png
    ├── page-07-traction.png
    └── page-12-product.png
```

### Human-Readable Summary

The `0-deck-analysis.md` includes:

```markdown
# Deck Analysis Summary

**Generated**: 2025-12-09 14:30:00
**Company**: Acme Corp
**Pages**: 22

---

## Key Information Extracted

### Business
- **Tagline**: AI-powered widgets for enterprise
- **Problem**: Manual widget management is slow
- **Solution**: Automated widget orchestration
- **Business Model**: SaaS subscription

### Market
{TAM/SAM/SOM data}

### Traction
{Metrics data}

### Team
{Team member data}

### Funding
- **Ask**: $5M Series A
- **Use of Funds**: ["Product", "Sales"]

## Extracted Screenshots

**Total**: 4 visual pages captured

### Team
- **Page 3**: Founding team photos with backgrounds
  - File: `deck-screenshots/page-03-team.png`
  - Dimensions: 1275x1650px

### Traction
- **Page 7**: MRR growth chart showing 3x YoY growth
  - File: `deck-screenshots/page-07-traction.png`
  - Dimensions: 1275x1650px

## Extraction Notes
- Team backgrounds not fully disclosed in deck
- Historical financials not included
```

---

## Error Handling

### Missing Deck

```python
if not deck_path or not Path(deck_path).exists():
    return {
        "deck_analysis": None,
        "messages": ["No deck available, skipping deck analysis"]
    }
```

### Unsupported Format

```python
if deck_suffix not in [".pdf", ".pptx", ".ppt"]:
    return {
        "deck_analysis": None,
        "messages": [f"Deck format {deck_suffix} not supported"]
    }
```

### Vision Mode Failures

Vision mode processes in batches with error isolation:

```python
try:
    response = client.messages.create(...)
except Exception as e:
    print(f"ERROR: Batch {batch_num} failed: {e}")
    continue  # Continue with next batch
```

### Screenshot Extraction Failures

Screenshot extraction is wrapped in try/except to not block the pipeline:

```python
try:
    page_selections = identify_visual_pages(...)
    deck_screenshots = extract_deck_screenshots(...)
except Exception as e:
    print(f"Screenshot extraction failed: {e}")
    # Continue without screenshots
```

---

## Performance Characteristics

### Processing Time

| Deck Type | Pages | Mode | Estimated Time |
|-----------|-------|------|----------------|
| Text PDF | 20 | Text | 15-30 seconds |
| Image PDF | 20 | Vision | 60-90 seconds |
| PowerPoint | 20 | Text | 15-30 seconds |
| + Screenshots | 5 selected | - | +10-15 seconds |

### API Costs

- **Text mode**: ~$0.10-0.30 per deck (single Claude call)
- **Vision mode**: ~$0.50-1.50 per deck (multiple vision calls)
- **Screenshot identification**: ~$0.10-0.20 (low-res thumbnails)

### File Sizes

- Screenshots at 150 DPI: ~200-500KB per page (PNG)
- Typical deck: 3-6 screenshots = 1-3MB total

---

## Related Documentation

- [Dataroom-Analyzer-Agent.md](./Dataroom-Analyzer-Agent.md) - Parent system for dataroom processing
- [Multi-Agent-Orchestration-for-Investment-Memo-Generation.md](./Multi-Agent-Orchestration-for-Investment-Memo-Generation.md) - Full pipeline architecture
- [Improving-Memo-Output.md](./Improving-Memo-Output.md) - Section improvement tools

---

## Changelog

### 2025-12-09: Screenshot Extraction
- Added `identify_visual_pages()` function for LLM-guided page selection
- Added `extract_deck_screenshots()` function for high-quality PNG rendering
- Integrated screenshot extraction into both text and vision processing paths
- Screenshots saved to `deck-screenshots/` directory
- Screenshot metadata included in `deck_analysis["screenshots"]`
- Added `pdf2image` dependency for higher quality rendering
- Updated artifact summary to include screenshot listing

### Previous
- Initial implementation with text and vision modes
- PowerPoint support added
- Section draft generation implemented
