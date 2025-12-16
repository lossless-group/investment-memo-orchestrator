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

## Screenshot Placement in Final Memo (ANALYSIS)

**Status**: Gap identified 2025-12-15 - Screenshots extracted but NOT embedded in final draft

### The Problem

Screenshots are successfully extracted to `deck-screenshots/` with category metadata (team, traction, product, etc.), but they never appear in the final memo. The expected output:

```markdown
## 4. Team

![Team Slide from Deck](/absolute/path/to/deck-screenshots/page-03-team.png)

The founding team brings deep domain expertise...
```

**Current behavior**: No image embeds appear in `2-sections/` or the final draft (`6-{Deal}-{Version}.md`).

### Analysis: Where Should Placement Happen?

#### Option A: Embed in `0-deck-sections/` (During Deck Analysis) ✅ RECOMMENDED

**When**: During `deck_analyst_agent()`, after screenshots are extracted

**How**: When creating `0-deck-sections/deck-team.md`, `deck-traction.md`, etc., embed the corresponding screenshot at the top of each file.

**Pros**:
- **Earliest possible point** - images become part of source material from the start
- **Natural mapping** - screenshot categories (team, traction, product) already match section files
- **Downstream preservation** - writer agent sees images and preserves/relocates them
- **Single responsibility** - deck analyst already has all needed context (screenshot paths + categories)
- **No new agent needed** - extends existing functionality

**Cons**:
- Writer agent prompt must explicitly preserve image embeds
- Deck analyst scope increases slightly

**Implementation**:
```python
# In deck_analyst.py, when creating section drafts:
def create_section_draft(field_name, content, screenshots, output_dir):
    # Find matching screenshot by category
    matching_screenshots = [s for s in screenshots if s["category"] == field_to_category(field_name)]

    draft = ""
    for screenshot in matching_screenshots:
        abs_path = output_dir / screenshot["path"]
        draft += f"![{screenshot['description']}]({abs_path})\n\n"

    draft += content
    return draft
```

#### Option B: Separate `deck_screenshot_placement` Agent

**When**: After deck analysis, before research

**Pros**:
- Single responsibility principle
- Can be more sophisticated about placement decisions

**Cons**:
- Another agent to maintain
- Duplicates logic that deck analyst already has (category→section mapping)
- Adds pipeline complexity

**Verdict**: Overkill for this use case.

#### Option C: Place in `2-sections/` (After Writer)

**When**: After writer creates sections, before citation enrichment

**Pros**:
- Writer has already structured sections with proper headers
- Easy to find "## 4. Team" header and insert after it

**Cons**:
- Late in pipeline - if writer doesn't know about images, it can't reference them
- Feels like retrofitting rather than natural flow
- Screenshot context is lost by this point (deck analyst memory gone)

**Verdict**: Possible fallback, but not ideal.

#### Option D: Place in `1-research/`

**Cons**:
- Research files are about EXTERNAL sources, not deck content
- Conceptually wrong location

**Verdict**: Not appropriate.

### Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  DECK ANALYST (deck_analyst.py)                                      │
│                                                                      │
│  1. Extract text/vision content                                      │
│  2. Generate structured JSON (DeckAnalysisData)                      │
│  3. Extract screenshots with categories                              │
│  4. Create 0-deck-sections/ WITH EMBEDDED IMAGES  ◄── NEW           │
│     ├─ deck-team.md                                                  │
│     │   ![Team photo](/path/to/page-03-team.png)                    │
│     │   Content about team...                                        │
│     └─ deck-traction.md                                              │
│         ![Growth chart](/path/to/page-07-traction.png)              │
│         Content about traction...                                    │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  RESEARCH + WRITER                                                   │
│                                                                      │
│  - Research agent adds external sources (no images to add)           │
│  - Writer agent reads 0-deck-sections/ as source material            │
│  - Writer PRESERVES image embeds, placing them appropriately         │
│  - Writer prompt: "Preserve any ![image](path) embeds from source"  │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2-SECTIONS/ (Output)                                                │
│                                                                      │
│  04-team.md                                                          │
│  ## 4. Team                                                          │
│                                                                      │
│  ![Founding team with backgrounds](/path/to/page-03-team.png)       │
│                                                                      │
│  The ProfileHealth team combines deep healthcare expertise...        │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Insight: Early Embedding + Downstream Preservation

The principle is: **embed at the earliest point where context exists, then preserve downstream**.

The deck analyst has:
- Screenshot paths
- Screenshot categories (team, traction, product, market, etc.)
- Section draft content
- The mapping between categories and section files

No other agent has this complete context. By embedding images in `0-deck-sections/`, we ensure:

1. **Images are part of the source material** - not an afterthought
2. **Writer sees images and can decide optimal placement** - maybe move from top to inline
3. **Natural flow** - no special "image placement" logic needed later
4. **Single source of truth** - deck analyst owns both extraction AND initial placement

### Implementation Checklist

- [x] Update `deck_analyst.py` to embed screenshots when creating `0-deck-sections/` drafts
  - Added `embed_screenshots_in_section_files()` function
  - Called after screenshot extraction in both text and vision paths
- [x] Map screenshot categories to section fields:
  - `team` → `deck-team.md`
  - `traction` → `deck-traction.md`
  - `product` → `deck-product.md`
  - `market` → `deck-market.md`
  - `competitive` → `deck-competitive.md`
  - `architecture` → `deck-product.md` (merge with product)
  - `timeline` → `deck-traction.md` (merge with traction)
  - Added `SCREENSHOT_CATEGORY_TO_SECTION` constant
- [x] Use ABSOLUTE paths in image embeds (required for final export)
- [x] Save `section_to_deck_topics` and `section_to_screenshots` mappings to `0-deck-analysis.json`
  - Added `SECTION_TO_DECK_TOPICS` constant
  - Added `build_section_to_screenshots()` function
  - JSON re-saved after screenshots extracted
- [x] Create `inject_deck_images` agent (`src/agents/inject_deck_images.py`)
  - Reads mapping from `0-deck-analysis.json`
  - Injects screenshots into `2-sections/` files after writer
  - Added to workflow between `draft` and `enrich_trademark`
- [ ] Test that images flow through to `6-{Deal}-{Version}.md` (final draft)
- [ ] Verify HTML export renders images correctly

### Revised Architecture (2025-12-15)

The original plan to have images flow through Perplexity doesn't work because Perplexity
can't preserve `![image](path)` markdown. The revised architecture:

```
deck_analyst:
  1. Extract screenshots → deck-screenshots/
  2. Embed in 0-deck-sections/ (for reference)
  3. Save mapping to 0-deck-analysis.json:
     - section_to_deck_topics: {"organization": ["team"], ...}
     - section_to_screenshots: {"organization": ["/path/to/team.png"], ...}

section_researcher:
  - Reads 0-deck-sections/ content (text only)
  - Sends to Perplexity as context
  - Perplexity writes 1-research/ (images lost - expected)

writer:
  - Polishes 1-research/ → 2-sections/
  - Content from deck is integrated (via Perplexity)
  - Images NOT present yet

inject_deck_images: ← NEW AGENT
  - Reads section_to_screenshots from 0-deck-analysis.json
  - Matches section names to screenshots via keyword matching
  - Injects images into 2-sections/ files
  - Images now in final output
```

### Image Embed Format

Use absolute paths for cross-directory compatibility:

```markdown
![Team Slide from Deck](/Users/mpstaton/code/.../deck-screenshots/page-03-team.png)
```

**Why absolute paths?**
- `2-sections/` is a different directory than `deck-screenshots/`
- Relative paths would break: `../deck-screenshots/` might not resolve correctly during export
- Absolute paths work consistently in markdown preview, HTML export, and PDF generation

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
