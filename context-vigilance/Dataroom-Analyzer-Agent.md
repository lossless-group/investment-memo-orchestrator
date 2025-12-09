---
title: Dataroom Analyzer Agent System Plan
lede: A comprehensive plan for implementing a multi-agent dataroom analysis system that intelligently recognizes, categorizes, and extracts information from diverse document types in investment datarooms.
date_authored_initial_draft: 2025-11-26
date_authored_current_draft: 2025-11-26
date_authored_final_draft:
date_first_published:
date_last_updated: 2025-11-26
at_semantic_version: 0.0.1
status: Planning
augmented_with: Claude Code (Opus 4.5)
category: Architecture
tags: [Dataroom, Document-Analysis, Multi-Agent, PDF, OCR, Investment-Analysis]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A sophisticated document processing pipeline showing diverse document types (financials, legal contracts, pitch decks, cap tables) flowing through AI analysis nodes, with document classification icons and data extraction visualizations.
date_created: 2025-11-26
date_modified: 2025-11-26
---

# Dataroom Analyzer Agent System Plan

**Status**: Planning
**Date**: 2025-11-26
**Author**: AI Labs Team
**Related**: Multi-Agent-Orchestration-for-Investment-Memo-Generation.md, deck_analyst.py

---

## Executive Summary

This document outlines a comprehensive plan for implementing a `dataroom_analyzer.py` agent system that can intelligently process, recognize, and extract information from the diverse document types found in investment datarooms. Unlike the existing `deck_analyst.py` which processes a single pitch deck, the dataroom analyzer must:

1. **Discover and inventory** all documents in a dataroom directory
2. **Classify** each document by type (financials, legal, cap table, team bios, etc.)
3. **Route** documents to specialized extraction agents based on classification
4. **Synthesize** extracted data into structured output for downstream agents
5. **Handle** various file formats (PDF, Excel, Word, images, etc.)

The system will use a **document classification layer** followed by **specialized extraction agents**, coordinated by a **dataroom orchestrator** that integrates with the existing memo generation pipeline.

---

## Problem Statement

### Current Limitations

**Issue #1: Single Document Input**
- The existing `deck_analyst.py` only handles pitch decks
- No capability to process multiple documents simultaneously
- Cannot handle the variety of document types in a typical dataroom

**Issue #2: No Document Classification**
- System assumes document type is known upfront (pitch deck)
- No intelligence to recognize what type of document it's looking at
- Cannot adapt extraction strategy based on document content

**Issue #3: Limited Format Support**
- Current system primarily handles PDF text and images
- No native Excel/CSV parsing (critical for financials, cap tables)
- No Word document extraction (common for legal docs)
- No structured data extraction from tables

**Issue #4: No Multi-Document Synthesis**
- Cannot cross-reference information across documents
- No deduplication of facts found in multiple sources
- Cannot resolve conflicts between document versions

### Dataroom Reality

A typical investment dataroom contains:

| Document Category | Common Formats | Examples |
|------------------|----------------|----------|
| **Pitch Materials** | PDF, PPTX | Pitch deck, executive summary, one-pager |
| **Financials** | XLSX, PDF, CSV | P&L, balance sheet, projections, cap table |
| **Legal** | PDF, DOCX | Articles of incorporation, term sheets, SAFEs |
| **Team** | PDF, DOCX | Founder bios, org chart, LinkedIn exports |
| **Product** | PDF, images | Product specs, screenshots, architecture diagrams |
| **Marketing** | PDF | Product sheets, integration guides, collateral |
| **Competitive** | PDF | Battlecards, competitive matrices, positioning docs |
| **Market** | PDF, XLSX | Market research, TAM analysis |
| **Traction** | XLSX, PDF | Customer list, metrics dashboard, pipeline |
| **Governance** | PDF, DOCX | Board minutes, investor updates, policies |

### Real-World Example: Hydden Dataroom

Analysis of the Hydden identity security company dataroom reveals common patterns:

**Directory Structure Pattern**: `N N_0 Category Name/` (numbered categories)
```
1 1_0 Executive Summary/     → pitch_deck
2 2_0 Product Overview/      → product_documentation
3 3_0 Marketing Materials/   → marketing_collateral
4 4_0 GTM_Competitive/       → competitive_analysis (8 battlecards!)
5 5_0 Financial Overview/    → financial_statements + cap_table
```

**Key Observations**:
1. **Numbered directories** provide strong classification signals
2. **Multiple battlecards** (one per competitor) - need synthesis across docs
3. **CSV financial models** with monthly projections through 5 years
4. **Cap tables in PDF** (not always Excel) - need PDF table extraction
5. **Marketing collateral** is a distinct category worth capturing

---

## Solution Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      DATAROOM ORCHESTRATOR                       │
│                   (dataroom_orchestrator.py)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
┌───────────────────┐ ┌───────────────┐ ┌───────────────────────┐
│  Document Scanner │ │  Classifier   │ │  Synthesis Engine     │
│  (discover files) │ │  (categorize) │ │  (merge & dedupe)     │
└─────────┬─────────┘ └───────┬───────┘ └───────────┬───────────┘
          │                   │                     │
          ▼                   ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SPECIALIZED EXTRACTORS                        │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Financial    │  │ Legal Doc    │  │ Pitch Deck Analyzer  │  │
│  │ Extractor    │  │ Extractor    │  │ (existing deck_      │  │
│  │              │  │              │  │  analyst.py)         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Team Bio     │  │ Cap Table    │  │ Traction/Metrics     │  │
│  │ Extractor    │  │ Extractor    │  │ Extractor            │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Product Doc  │  │ Market       │  │ Generic Document     │  │
│  │ Extractor    │  │ Research     │  │ Extractor (fallback) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ARTIFACT OUTPUT                               │
│                                                                  │
│  output/{Company}-v0.0.x/                                       │
│  ├── 0-dataroom-inventory.json    # All discovered files        │
│  ├── 0-dataroom-inventory.md      # Human-readable inventory    │
│  ├── 0-dataroom-analysis.json     # Structured extraction       │
│  ├── 0-dataroom-analysis.md       # Synthesized summary         │
│  └── 0-dataroom-documents/        # Processed document copies   │
│      ├── financials/                                            │
│      ├── legal/                                                 │
│      ├── team/                                                  │
│      └── ...                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Integration with Existing Pipeline

The dataroom analyzer integrates at the **start** of the existing workflow, replacing/augmenting the deck analyst:

```
┌──────────────────┐
│  Dataroom        │ ← NEW: Processes entire dataroom
│  Orchestrator    │   Returns comprehensive DataroomAnalysis
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Deck Analyst    │ ← UPDATED: Skips if dataroom processed deck
│  (if standalone  │   OR receives deck from dataroom
│   deck provided) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Research Agent  │ ← ENHANCED: Uses dataroom data to
│  (enhanced)      │   target research gaps
└────────┬─────────┘
         │
         ▼
    [Rest of pipeline unchanged]
```

---

## Document Classification System

### Classification Approach

The classifier uses a **three-stage approach**:

**Stage 1: Directory-Based Pre-Classification** (NEW - from Hydden analysis)
- Parse parent directory name for category hints
- Common patterns: `N N_0 Category Name/`, `Category/`, `N. Category/`
- Map directory names to document types with high confidence (0.85+)

```python
DIRECTORY_CATEGORY_MAP = {
    "executive summary": "pitch_deck",
    "pitch": "pitch_deck",
    "deck": "pitch_deck",
    "product overview": "product_documentation",
    "product": "product_documentation",
    "marketing materials": "marketing_collateral",
    "marketing": "marketing_collateral",
    "collateral": "marketing_collateral",
    "gtm": "competitive_analysis",
    "competitive": "competitive_analysis",
    "compete": "competitive_analysis",
    "battlecard": "competitive_analysis",
    "financial": "financial_statements",
    "financials": "financial_statements",
    "legal": "term_sheet",  # or articles, need filename check
    "team": "team_bios",
    "traction": "traction_metrics",
    "customers": "customer_list",
}
```

**Stage 2: Heuristic Pre-Classification**
- Filename patterns (e.g., "Cap Table", "P&L", "Term Sheet", "BattleCard")
- File extension (XLSX → likely financials, CSV → financial model)
- File size and page count

**Stage 3: LLM-Based Content Classification**
- Sample first 2-3 pages of content
- Use Claude to classify based on content patterns
- Confidence scoring for each classification
- Only invoked if Stage 1+2 confidence < 0.8

### Document Type Taxonomy

```yaml
document_types:
  pitch_deck:
    description: "Investor presentation with company overview"
    indicators:
      - filename_patterns: ["pitch", "deck", "investor", "presentation"]
      - content_signals: ["TAM", "SAM", "SOM", "investment", "ask", "use of funds"]
    extractor: "pitch_deck_extractor"
    priority: 1  # Process first

  competitive_analysis:
    description: "Competitive landscape analysis with market positioning"
    indicators:
      - filename_patterns: ["competitive", "competitor", "landscape", "battlecard", "comparison", "vs", "versus"]
      - content_signals: ["competitors", "market share", "differentiation", "positioning", "strengths", "weaknesses", "SWOT", "feature comparison", "pricing comparison", "competitive advantage"]
    extractor: "competitive_extractor"
    priority: 1  # Critical for investment thesis

  financial_statements:
    description: "P&L, balance sheet, cash flow statements"
    indicators:
      - filename_patterns: ["p&l", "income", "balance", "financials", "statements"]
      - extensions: [".xlsx", ".xls", ".csv"]
      - content_signals: ["revenue", "COGS", "gross margin", "EBITDA", "assets", "liabilities"]
    extractor: "financial_extractor"
    priority: 2

  financial_projections:
    description: "Forward-looking financial models"
    indicators:
      - filename_patterns: ["model", "projections", "forecast", "plan"]
      - content_signals: ["FY2024", "FY2025", "projected", "assumptions"]
    extractor: "financial_extractor"
    priority: 2

  cap_table:
    description: "Capitalization table showing ownership"
    indicators:
      - filename_patterns: ["cap table", "captable", "ownership", "equity"]
      - content_signals: ["shares", "ownership %", "dilution", "options pool", "SAFE"]
    extractor: "cap_table_extractor"
    priority: 3

  term_sheet:
    description: "Investment terms and conditions"
    indicators:
      - filename_patterns: ["term sheet", "termsheet", "terms"]
      - content_signals: ["valuation", "pre-money", "post-money", "liquidation preference"]
    extractor: "legal_extractor"
    priority: 3

  safe_note:
    description: "Simple Agreement for Future Equity"
    indicators:
      - filename_patterns: ["SAFE", "safe", "note"]
      - content_signals: ["valuation cap", "discount rate", "conversion"]
    extractor: "legal_extractor"
    priority: 3

  articles_of_incorporation:
    description: "Corporate formation documents"
    indicators:
      - filename_patterns: ["articles", "incorporation", "certificate", "formation"]
      - content_signals: ["incorporated", "authorized shares", "registered agent"]
    extractor: "legal_extractor"
    priority: 4

  team_bios:
    description: "Founder and team background information"
    indicators:
      - filename_patterns: ["team", "bios", "founders", "leadership"]
      - content_signals: ["CEO", "CTO", "experience", "previously at", "founded"]
    extractor: "team_extractor"
    priority: 2

  org_chart:
    description: "Organizational structure visualization"
    indicators:
      - filename_patterns: ["org chart", "organization", "structure"]
      - content_signals: ["reports to", "department", "hierarchy"]
    extractor: "team_extractor"
    priority: 4

  customer_list:
    description: "Customer or client information"
    indicators:
      - filename_patterns: ["customers", "clients", "accounts"]
      - content_signals: ["customer name", "ACV", "contract value", "renewal"]
    extractor: "traction_extractor"
    priority: 3

  pipeline_metrics:
    description: "Sales pipeline or funnel data"
    indicators:
      - filename_patterns: ["pipeline", "funnel", "deals"]
      - content_signals: ["stage", "probability", "close date", "opportunity"]
    extractor: "traction_extractor"
    priority: 3

  product_documentation:
    description: "Product specs, architecture, roadmap"
    indicators:
      - filename_patterns: ["product", "spec", "architecture", "roadmap"]
      - content_signals: ["features", "requirements", "API", "integration"]
    extractor: "product_extractor"
    priority: 4

  marketing_collateral:
    description: "Product marketing materials, integration guides, sales collateral"
    indicators:
      - filename_patterns: ["marketing", "collateral", "datasheet", "brochure", "one-pager", "integration"]
      - directory_patterns: ["marketing materials", "collateral", "sales"]
      - content_signals: ["solution overview", "key benefits", "use cases", "integration", "partner"]
    extractor: "marketing_extractor"
    priority: 4

  market_research:
    description: "Market analysis and competitive landscape"
    indicators:
      - filename_patterns: ["market", "research", "competitive", "analysis"]
      - content_signals: ["market size", "competitors", "trends", "growth rate"]
    extractor: "market_extractor"
    priority: 3

  investor_update:
    description: "Periodic updates to existing investors"
    indicators:
      - filename_patterns: ["update", "monthly", "quarterly", "board"]
      - content_signals: ["highlights", "metrics", "runway", "next steps"]
    extractor: "generic_extractor"
    priority: 4

  unknown:
    description: "Unclassified document"
    extractor: "generic_extractor"
    priority: 5
```

### Classification Prompt

```python
CLASSIFICATION_PROMPT = """You are a document classifier for investment datarooms.

Analyze the following document sample and classify it into ONE of these categories:
{category_list}

DOCUMENT FILENAME: {filename}
FILE EXTENSION: {extension}
DOCUMENT CONTENT SAMPLE:
---
{content_sample}
---

Respond with a JSON object:
{{
  "document_type": "<category_name>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>",
  "key_signals": ["<signal1>", "<signal2>", ...]
}}

If confidence is below 0.6, classify as "unknown".
"""
```

---

## Specialized Extractors

### 1. Financial Extractor (`financial_extractor.py`)

**Purpose**: Extract structured financial data from Excel files and financial PDFs.

**Key Libraries**:
- `openpyxl` - Excel file parsing
- `pandas` - Data manipulation
- `tabula-py` - Table extraction from PDFs

**Extraction Schema**:

```python
class FinancialData(TypedDict):
    """Structured financial extraction"""
    document_source: str
    extraction_date: str

    # Income Statement
    revenue: Optional[Dict[str, float]]  # {"2023": 1000000, "2024": 2000000}
    arr: Optional[Dict[str, float]]
    mrr: Optional[Dict[str, float]]
    gross_margin: Optional[Dict[str, float]]
    operating_expenses: Optional[Dict[str, float]]
    net_income: Optional[Dict[str, float]]

    # Balance Sheet
    cash: Optional[float]
    total_assets: Optional[float]
    total_liabilities: Optional[float]

    # Key Metrics
    burn_rate: Optional[float]
    runway_months: Optional[float]
    ltv: Optional[float]
    cac: Optional[float]
    ltv_cac_ratio: Optional[float]

    # Projections (if available)
    projections: Optional[Dict[str, Dict[str, float]]]  # {"2025": {"revenue": X, "arr": Y}}
    projection_assumptions: Optional[List[str]]

    # Metadata
    fiscal_year_end: Optional[str]
    currency: str
    extraction_notes: List[str]
```

**Extraction Strategy**:

```python
def extract_financials(file_path: Path, file_type: str) -> FinancialData:
    """Extract financial data from various formats."""

    if file_type in [".xlsx", ".xls"]:
        return extract_from_excel(file_path)
    elif file_type == ".csv":
        return extract_from_csv(file_path)
    elif file_type == ".pdf":
        return extract_from_financial_pdf(file_path)
    else:
        raise UnsupportedFormatError(f"Cannot extract financials from {file_type}")


def extract_from_excel(file_path: Path) -> FinancialData:
    """Parse Excel financial statements."""

    wb = openpyxl.load_workbook(file_path, data_only=True)

    # Strategy: Look for common sheet names
    sheet_priorities = {
        "P&L": ["p&l", "income", "profit", "loss"],
        "Balance": ["balance", "sheet", "bs"],
        "Summary": ["summary", "overview", "dashboard"],
        "Model": ["model", "projections", "forecast"]
    }

    financial_data = FinancialData(
        document_source=str(file_path),
        extraction_date=datetime.now().isoformat(),
        currency="USD",
        extraction_notes=[]
    )

    for sheet_name in wb.sheetnames:
        sheet_lower = sheet_name.lower()

        # Detect sheet type and extract accordingly
        if any(kw in sheet_lower for kw in sheet_priorities["P&L"]):
            extract_income_statement(wb[sheet_name], financial_data)
        elif any(kw in sheet_lower for kw in sheet_priorities["Balance"]):
            extract_balance_sheet(wb[sheet_name], financial_data)
        # ... etc

    return financial_data


def extract_income_statement(sheet, data: FinancialData):
    """Extract P&L data from Excel sheet using LLM assistance."""

    # Step 1: Convert sheet to markdown table format
    table_md = sheet_to_markdown(sheet, max_rows=100, max_cols=20)

    # Step 2: Use Claude to identify and extract values
    prompt = f"""Extract revenue, costs, and margins from this financial statement.

TABLE:
{table_md}

Return a JSON object with:
{{
  "revenue": {{"year": value, ...}},
  "gross_margin_pct": {{"year": value, ...}},
  "operating_expenses": {{"year": value, ...}},
  "net_income": {{"year": value, ...}},
  "notes": ["any important observations"]
}}

Convert all values to numbers (remove $, commas). Use null for missing values.
"""

    response = claude_client.invoke(prompt)
    extracted = json.loads(response.content)

    # Merge into data structure
    data.revenue = extracted.get("revenue")
    data.gross_margin = extracted.get("gross_margin_pct")
    # ... etc
```

### 2. Cap Table Extractor (`cap_table_extractor.py`)

**Purpose**: Extract ownership structure, investor details, and dilution scenarios.

**Extraction Schema**:

```python
class CapTableData(TypedDict):
    """Structured cap table extraction"""
    document_source: str
    as_of_date: Optional[str]

    # Ownership Summary
    total_shares_outstanding: Optional[int]
    fully_diluted_shares: Optional[int]

    # Shareholders
    shareholders: List[ShareholderEntry]

    # Options Pool
    option_pool_size: Optional[int]
    option_pool_percentage: Optional[float]
    options_granted: Optional[int]
    options_available: Optional[int]

    # SAFEs and Convertibles
    safes: List[SAFEEntry]
    convertible_notes: List[ConvertibleNoteEntry]

    # Valuation Context
    last_priced_round_valuation: Optional[float]
    last_priced_round_date: Optional[str]

    extraction_notes: List[str]


class ShareholderEntry(TypedDict):
    name: str
    shares: int
    ownership_percentage: float
    share_class: str  # "Common", "Series A", "Series B", etc.
    investor_type: str  # "Founder", "Employee", "VC", "Angel"


class SAFEEntry(TypedDict):
    investor_name: str
    amount_invested: float
    valuation_cap: Optional[float]
    discount_rate: Optional[float]
    conversion_trigger: str
```

### 3. Legal Document Extractor (`legal_extractor.py`)

**Purpose**: Extract key terms from legal documents (term sheets, SAFEs, incorporation docs).

**Extraction Schema**:

```python
class LegalDocData(TypedDict):
    """Structured legal document extraction"""
    document_source: str
    document_type: str  # "term_sheet", "safe", "articles", etc.
    document_date: Optional[str]

    # Term Sheet / Investment Terms
    investment_amount: Optional[float]
    pre_money_valuation: Optional[float]
    post_money_valuation: Optional[float]
    share_price: Optional[float]
    shares_purchased: Optional[int]

    # Investor Rights
    liquidation_preference: Optional[str]  # "1x non-participating"
    anti_dilution: Optional[str]  # "Broad-based weighted average"
    board_seats: Optional[int]
    pro_rata_rights: Optional[bool]
    information_rights: Optional[bool]

    # Conditions
    closing_conditions: List[str]
    key_covenants: List[str]

    # Parties
    investors: List[str]
    company_name: str

    extraction_notes: List[str]
```

### 4. Team Extractor (`team_extractor.py`)

**Purpose**: Extract founder and team information, backgrounds, and organizational structure.

**Extraction Schema**:

```python
class TeamData(TypedDict):
    """Structured team extraction"""
    document_source: str

    # Founders
    founders: List[FounderProfile]

    # Leadership Team
    leadership: List[ExecutiveProfile]

    # Organizational
    total_headcount: Optional[int]
    headcount_by_department: Optional[Dict[str, int]]

    # Advisors & Board
    advisors: List[AdvisorProfile]
    board_members: List[BoardMemberProfile]

    extraction_notes: List[str]


class FounderProfile(TypedDict):
    name: str
    title: str
    linkedin_url: Optional[str]
    email: Optional[str]

    # Background
    previous_companies: List[str]
    previous_roles: List[str]
    education: List[str]
    notable_achievements: List[str]

    # Expertise
    domain_expertise: List[str]
    years_experience: Optional[int]
```

### 5. Traction/Metrics Extractor (`traction_extractor.py`)

**Purpose**: Extract customer lists, pipeline data, and key metrics.

**Extraction Schema**:

```python
class TractionData(TypedDict):
    """Structured traction extraction"""
    document_source: str
    data_as_of: Optional[str]

    # Customer Metrics
    total_customers: Optional[int]
    customers_by_segment: Optional[Dict[str, int]]
    notable_customers: List[CustomerEntry]

    # Revenue Metrics
    arr: Optional[float]
    mrr: Optional[float]
    revenue_growth_rate: Optional[float]  # YoY or MoM

    # Engagement Metrics
    dau: Optional[int]
    mau: Optional[int]
    retention_rate: Optional[float]
    churn_rate: Optional[float]
    nps_score: Optional[float]

    # Sales Pipeline
    pipeline_value: Optional[float]
    pipeline_stages: Optional[Dict[str, float]]
    average_deal_size: Optional[float]
    sales_cycle_days: Optional[int]

    # Partnerships
    partnerships: List[PartnershipEntry]

    extraction_notes: List[str]


class CustomerEntry(TypedDict):
    name: str
    contract_value: Optional[float]
    contract_type: str  # "Annual", "Multi-year", "Pilot"
    use_case: Optional[str]
    logo_permission: Optional[bool]
```

### 6. Competitive Analysis Extractor (`competitive_extractor.py`)

**Purpose**: Extract competitive landscape data, market positioning, and differentiation analysis. This is a **priority 1** extractor because understanding the competitive dynamics is critical for evaluating investment thesis viability.

**Key Libraries**:
- `pypdf` - PDF text extraction
- `openpyxl` - Excel comparison matrices
- `langchain_anthropic` - LLM-based analysis

**Extraction Schema**:

```python
class CompetitiveData(TypedDict):
    """Structured competitive analysis extraction"""
    document_source: str
    analysis_date: Optional[str]

    # Direct Competitors
    competitors: List[CompetitorEntry]

    # Market Positioning
    market_positioning: Optional[str]  # Company's stated position
    target_segments: List[str]
    geographic_focus: List[str]

    # Differentiation
    key_differentiators: List[str]
    unique_value_proposition: Optional[str]
    competitive_advantages: List[str]
    competitive_disadvantages: List[str]

    # Feature Comparison
    feature_matrix: Optional[Dict[str, Dict[str, Any]]]  # {feature: {company: value}}

    # Pricing Analysis
    pricing_comparison: Optional[Dict[str, PricingEntry]]
    pricing_strategy: Optional[str]  # "Premium", "Value", "Freemium", etc.

    # Market Share
    market_share_estimates: Optional[Dict[str, float]]  # {company: percentage}
    market_share_source: Optional[str]

    # SWOT (if present)
    swot: Optional[SWOTAnalysis]

    # Competitive Dynamics
    barriers_to_entry: List[str]
    switching_costs: Optional[str]
    network_effects: Optional[str]

    extraction_notes: List[str]


class CompetitorEntry(TypedDict):
    name: str
    description: Optional[str]
    website: Optional[str]
    funding_raised: Optional[float]
    estimated_revenue: Optional[float]
    employee_count: Optional[int]
    founded_year: Optional[int]
    headquarters: Optional[str]
    key_customers: List[str]
    strengths: List[str]
    weaknesses: List[str]
    threat_level: Optional[str]  # "High", "Medium", "Low"


class PricingEntry(TypedDict):
    company: str
    pricing_model: str  # "Subscription", "Usage-based", "Per-seat", etc.
    price_range: Optional[str]
    free_tier: Optional[bool]
    enterprise_pricing: Optional[str]


class SWOTAnalysis(TypedDict):
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]
```

**Extraction Strategy**:

```python
def extract_competitive(file_path: Path, file_type: str) -> CompetitiveData:
    """Extract competitive analysis data from various formats."""

    if file_type == ".pdf":
        return extract_competitive_from_pdf(file_path)
    elif file_type in [".xlsx", ".xls"]:
        return extract_competitive_from_excel(file_path)
    elif file_type in [".docx", ".doc"]:
        return extract_competitive_from_docx(file_path)
    else:
        return extract_competitive_generic(file_path)


def extract_competitive_from_pdf(file_path: Path) -> CompetitiveData:
    """Extract competitive data from PDF (battlecards, analysis docs)."""

    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    full_text = "\n".join(page.extract_text() for page in reader.pages)

    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    prompt = f"""Analyze this competitive analysis document and extract structured data.

DOCUMENT CONTENT:
{full_text[:15000]}  # Limit for context window

Extract the following as JSON:
{{
    "competitors": [
        {{
            "name": "...",
            "description": "...",
            "strengths": ["..."],
            "weaknesses": ["..."],
            "threat_level": "High/Medium/Low"
        }}
    ],
    "key_differentiators": ["..."],
    "competitive_advantages": ["..."],
    "competitive_disadvantages": ["..."],
    "market_positioning": "...",
    "feature_matrix": {{"feature_name": {{"company1": "value", "company2": "value"}}}},
    "pricing_comparison": {{"company": {{"pricing_model": "...", "price_range": "..."}}}},
    "swot": {{"strengths": [], "weaknesses": [], "opportunities": [], "threats": []}},
    "barriers_to_entry": ["..."],
    "extraction_notes": ["any important observations about data quality or gaps"]
}}

Be thorough but only include information explicitly stated in the document.
Use null for missing values, not guesses.
"""

    response = llm.invoke(prompt)
    extracted = json.loads(response.content)

    return CompetitiveData(
        document_source=str(file_path),
        analysis_date=None,  # Try to extract from document
        **extracted
    )


def extract_competitive_from_excel(file_path: Path) -> CompetitiveData:
    """Extract competitive data from Excel (feature matrices, comparisons)."""

    import openpyxl

    wb = openpyxl.load_workbook(str(file_path), data_only=True)

    # Look for comparison/matrix sheets
    comparison_keywords = ["comparison", "matrix", "competitive", "feature", "vs"]

    all_tables = []
    for sheet_name in wb.sheetnames:
        if any(kw in sheet_name.lower() for kw in comparison_keywords):
            sheet = wb[sheet_name]
            table_md = sheet_to_markdown(sheet, max_rows=50, max_cols=15)
            all_tables.append(f"## Sheet: {sheet_name}\n{table_md}")

    if not all_tables:
        # Fall back to first sheet
        sheet = wb.active
        all_tables.append(sheet_to_markdown(sheet, max_rows=50, max_cols=15))

    # Use LLM to interpret tables
    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    prompt = f"""Analyze these competitive comparison tables and extract structured data.

TABLES:
{chr(10).join(all_tables)}

Extract as JSON with competitors, feature_matrix, pricing_comparison, etc.
Focus on identifying:
1. Which companies are being compared
2. Feature/capability differences
3. Pricing differences
4. Strengths and weaknesses of each

Return structured CompetitiveData JSON.
"""

    response = llm.invoke(prompt)
    return json.loads(response.content)
```

**Why Priority 1?**

Competitive analysis documents are processed with the highest priority because:

1. **Investment Thesis Foundation**: Understanding competitive dynamics is essential for evaluating whether a company can win in its market
2. **Due Diligence Critical Path**: Investors need to understand competitive positioning before deeper analysis
3. **Cross-Document Enhancement**: Competitor names and market context extracted here enriches analysis of other documents (financials, traction, etc.)
4. **Risk Assessment**: Competitive threats are a primary source of investment risk

**Multi-Battlecard Synthesis Pattern** (from Hydden dataroom analysis)

Real datarooms often contain **multiple battlecards** (one per competitor). The Hydden dataroom has 8:
- SphereBattleCard.pdf
- SilverfortBattleCard.pdf
- AxoniusBattlecard.pdf
- Authomize BattleCard.pdf
- OrchidSecurityBattleCard.pdf
- OleriaBattleCard.pdf
- VezaBattlecard.pdf
- OktaBattleCard.pdf

Each battlecard contains:
- Feature comparison matrix (checkmarks/X's/Partial)
- "Deep dive" capability comparison table
- "Our winning angle" sales talking points
- Discovery questions to expose competitor weaknesses

**Synthesis Strategy**:
```python
def synthesize_battlecards(battlecard_extractions: List[CompetitorEntry]) -> CompetitiveData:
    """
    Combine multiple per-competitor battlecards into unified competitive landscape.

    1. Deduplicate features across all battlecards
    2. Build unified feature matrix with all competitors as columns
    3. Aggregate strengths/weaknesses by competitor
    4. Identify common themes in "winning angles"
    5. Compile discovery questions by category
    """

    # Extract unique features from all battlecards
    all_features = set()
    for extraction in battlecard_extractions:
        all_features.update(extraction.get("feature_matrix", {}).keys())

    # Build unified matrix
    unified_matrix = {}
    for feature in all_features:
        unified_matrix[feature] = {}
        for extraction in battlecard_extractions:
            competitor = extraction["name"]
            unified_matrix[feature][competitor] = extraction.get("feature_matrix", {}).get(feature)

    return CompetitiveData(
        competitors=[e for e in battlecard_extractions],
        feature_matrix=unified_matrix,
        key_differentiators=extract_common_differentiators(battlecard_extractions),
        # ... etc
    )
```

---

## Implementation Plan

### Phase 1: Foundation

**Goal**: Basic document discovery, classification, and file handling infrastructure.

#### Step 1.1: Create State Schema Extensions

**File**: `src/state.py` (additions)

```python
class DocumentInventoryItem(TypedDict):
    """Single document in dataroom inventory"""
    file_path: str
    filename: str
    extension: str
    file_size_bytes: int
    page_count: Optional[int]  # For PDFs

    # Classification
    document_type: str
    classification_confidence: float
    classification_reasoning: str

    # Processing Status
    processed: bool
    extraction_status: str  # "pending", "success", "error", "skipped"
    extraction_error: Optional[str]


class DataroomAnalysis(TypedDict):
    """Comprehensive dataroom analysis output"""
    dataroom_path: str
    analysis_date: str

    # Inventory
    document_count: int
    documents_by_type: Dict[str, int]
    inventory: List[DocumentInventoryItem]

    # Extracted Data
    financials: Optional[FinancialData]
    cap_table: Optional[CapTableData]
    legal_docs: List[LegalDocData]
    team: Optional[TeamData]
    traction: Optional[TractionData]
    pitch_deck: Optional[DeckAnalysisData]  # Reuse existing

    # Synthesis
    key_facts: Dict[str, Any]  # Deduplicated facts across all docs
    data_gaps: List[str]  # Missing critical information
    conflicts: List[DataConflict]  # Conflicting info between docs

    # Metadata
    processing_duration_seconds: float
    extraction_notes: List[str]


class DataConflict(TypedDict):
    """Conflict between data sources"""
    field: str
    sources: List[Dict[str, Any]]  # [{source: "file.pdf", value: X}, ...]
    recommended_value: Any
    resolution_reasoning: str


# Update MemoState to include dataroom
class MemoState(TypedDict):
    # ... existing fields ...

    # NEW: Dataroom fields
    dataroom_path: Optional[str]
    dataroom_analysis: Optional[DataroomAnalysis]
```

#### Step 1.2: Create Document Scanner

**File**: `src/agents/dataroom/document_scanner.py`

```python
"""Document scanner for dataroom inventory."""

from pathlib import Path
from typing import List, Dict
import os
import mimetypes
from pypdf import PdfReader
from datetime import datetime


# Supported file extensions
SUPPORTED_EXTENSIONS = {
    ".pdf": "document",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".csv": "data",
    ".docx": "document",
    ".doc": "document",
    ".pptx": "presentation",
    ".ppt": "presentation",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".md": "text",
    ".txt": "text",
}

# Files to ignore
IGNORE_PATTERNS = [
    ".DS_Store",
    "Thumbs.db",
    "__MACOSX",
    ".git",
    "~$",  # Office temp files
]


def scan_dataroom(dataroom_path: str) -> List[DocumentInventoryItem]:
    """
    Scan dataroom directory and create inventory of all documents.

    Args:
        dataroom_path: Path to dataroom directory

    Returns:
        List of DocumentInventoryItem objects
    """
    dataroom = Path(dataroom_path)

    if not dataroom.exists():
        raise FileNotFoundError(f"Dataroom path does not exist: {dataroom_path}")

    if not dataroom.is_dir():
        raise ValueError(f"Dataroom path is not a directory: {dataroom_path}")

    inventory = []

    # Walk directory tree
    for file_path in dataroom.rglob("*"):
        # Skip directories
        if file_path.is_dir():
            continue

        # Skip ignored files
        if should_ignore(file_path):
            continue

        # Get file info
        extension = file_path.suffix.lower()

        # Skip unsupported formats
        if extension not in SUPPORTED_EXTENSIONS:
            continue

        # Create inventory item
        item = DocumentInventoryItem(
            file_path=str(file_path),
            filename=file_path.name,
            extension=extension,
            file_size_bytes=file_path.stat().st_size,
            page_count=get_page_count(file_path) if extension == ".pdf" else None,
            document_type="unknown",  # Will be classified later
            classification_confidence=0.0,
            classification_reasoning="",
            processed=False,
            extraction_status="pending",
            extraction_error=None
        )

        inventory.append(item)

    # Sort by filename for consistent ordering
    inventory.sort(key=lambda x: x["filename"].lower())

    return inventory


def should_ignore(file_path: Path) -> bool:
    """Check if file should be ignored."""
    name = file_path.name

    for pattern in IGNORE_PATTERNS:
        if pattern in name or name.startswith(pattern):
            return True

    return False


def get_page_count(pdf_path: Path) -> int:
    """Get page count from PDF."""
    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        return 0


def get_directory_structure(dataroom_path: str) -> Dict[str, List[str]]:
    """Get directory structure hints for classification."""
    dataroom = Path(dataroom_path)
    structure = {}

    for dir_path in dataroom.rglob("*"):
        if dir_path.is_dir():
            rel_path = str(dir_path.relative_to(dataroom))
            files = [f.name for f in dir_path.iterdir() if f.is_file()]
            structure[rel_path] = files

    return structure
```

#### Step 1.3: Create Document Classifier

**File**: `src/agents/dataroom/document_classifier.py`

```python
"""Document classifier using heuristics and LLM."""

from pathlib import Path
from typing import Tuple, List
import re
from langchain_anthropic import ChatAnthropic
import json

from .document_scanner import DocumentInventoryItem
from .document_types import DOCUMENT_TYPE_TAXONOMY


def classify_documents(
    inventory: List[DocumentInventoryItem],
    use_llm: bool = True
) -> List[DocumentInventoryItem]:
    """
    Classify all documents in inventory.

    Uses two-stage approach:
    1. Heuristic classification based on filename/extension
    2. LLM classification for uncertain cases
    """
    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929") if use_llm else None

    for item in inventory:
        # Stage 1: Heuristic classification
        doc_type, confidence = heuristic_classify(item)

        # Stage 2: LLM classification if confidence low
        if confidence < 0.8 and use_llm:
            doc_type, confidence, reasoning = llm_classify(llm, item)
            item["classification_reasoning"] = reasoning
        else:
            item["classification_reasoning"] = "Heuristic match on filename/extension"

        item["document_type"] = doc_type
        item["classification_confidence"] = confidence

    return inventory


def heuristic_classify(item: DocumentInventoryItem) -> Tuple[str, float]:
    """Classify document using filename patterns and extension."""

    filename_lower = item["filename"].lower()
    extension = item["extension"]

    # Check each document type
    for doc_type, config in DOCUMENT_TYPE_TAXONOMY.items():
        # Check filename patterns
        if "filename_patterns" in config.get("indicators", {}):
            for pattern in config["indicators"]["filename_patterns"]:
                if pattern.lower() in filename_lower:
                    return doc_type, 0.85

        # Check extension matches
        if "extensions" in config.get("indicators", {}):
            if extension in config["indicators"]["extensions"]:
                # Extension match is weaker evidence
                return doc_type, 0.6

    return "unknown", 0.0


def llm_classify(
    llm: ChatAnthropic,
    item: DocumentInventoryItem
) -> Tuple[str, float, str]:
    """Classify document using LLM based on content sample."""

    # Get content sample
    content_sample = extract_content_sample(item["file_path"])

    if not content_sample:
        return "unknown", 0.3, "Could not extract content for classification"

    # Build category list
    category_descriptions = "\n".join([
        f"- {name}: {config['description']}"
        for name, config in DOCUMENT_TYPE_TAXONOMY.items()
        if name != "unknown"
    ])

    prompt = f"""You are a document classifier for investment datarooms.

Analyze the following document and classify it into ONE of these categories:
{category_descriptions}

DOCUMENT FILENAME: {item["filename"]}
FILE EXTENSION: {item["extension"]}

DOCUMENT CONTENT SAMPLE (first ~2000 chars):
---
{content_sample[:2000]}
---

Respond with a JSON object:
{{
  "document_type": "<category_name>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>",
  "key_signals": ["<signal1>", "<signal2>", ...]
}}

If confidence is below 0.6, classify as "unknown".
"""

    response = llm.invoke(prompt)

    try:
        result = json.loads(response.content)
        return (
            result["document_type"],
            result["confidence"],
            result["reasoning"]
        )
    except json.JSONDecodeError:
        return "unknown", 0.3, "LLM response parsing failed"


def extract_content_sample(file_path: str) -> str:
    """Extract text sample from document for classification."""

    path = Path(file_path)
    extension = path.suffix.lower()

    try:
        if extension == ".pdf":
            return extract_pdf_sample(path)
        elif extension in [".xlsx", ".xls"]:
            return extract_excel_sample(path)
        elif extension in [".docx"]:
            return extract_docx_sample(path)
        elif extension in [".txt", ".md", ".csv"]:
            return extract_text_sample(path)
        else:
            return ""
    except Exception as e:
        return f"[Extraction error: {str(e)}]"


def extract_pdf_sample(path: Path) -> str:
    """Extract text from first 3 pages of PDF."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text_parts = []

    for i, page in enumerate(reader.pages[:3]):
        text = page.extract_text()
        if text:
            text_parts.append(f"--- PAGE {i+1} ---\n{text}")

    return "\n".join(text_parts)


def extract_excel_sample(path: Path) -> str:
    """Extract data from first sheet of Excel file."""
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    sheet = wb.active

    # Get first 20 rows as table
    rows = []
    for row in sheet.iter_rows(max_row=20, values_only=True):
        row_str = " | ".join(str(cell) if cell else "" for cell in row)
        rows.append(row_str)

    return f"Sheet: {sheet.title}\n" + "\n".join(rows)


def extract_docx_sample(path: Path) -> str:
    """Extract text from Word document."""
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs[:30] if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text_sample(path: Path) -> str:
    """Extract from plain text file."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read(5000)
```

### Phase 2: Extractors

**Goal**: Implement specialized extractors for each document type.

#### Step 2.1: Financial Extractor

**File**: `src/agents/dataroom/extractors/financial_extractor.py`

(Implementation as detailed in Specialized Extractors section above)

#### Step 2.2: Cap Table Extractor

**File**: `src/agents/dataroom/extractors/cap_table_extractor.py`

#### Step 2.3: Legal Extractor

**File**: `src/agents/dataroom/extractors/legal_extractor.py`

#### Step 2.4: Team Extractor

**File**: `src/agents/dataroom/extractors/team_extractor.py`

#### Step 2.5: Traction Extractor

**File**: `src/agents/dataroom/extractors/traction_extractor.py`

### Phase 3: Orchestration

**Goal**: Build the dataroom orchestrator and synthesis engine.

#### Step 3.1: Dataroom Orchestrator Agent

**File**: `src/agents/dataroom_orchestrator.py`

```python
"""
Dataroom Orchestrator Agent

Coordinates the analysis of an entire dataroom:
1. Scans for all documents
2. Classifies each document
3. Routes to specialized extractors
4. Synthesizes results
5. Saves artifacts
"""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import json

from src.state import MemoState, DataroomAnalysis
from src.artifacts import save_dataroom_artifacts
from .dataroom.document_scanner import scan_dataroom, get_directory_structure
from .dataroom.document_classifier import classify_documents
from .dataroom.synthesis_engine import synthesize_extractions, identify_data_gaps


def dataroom_orchestrator_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main dataroom analysis agent.

    Processes entire dataroom directory and extracts structured data.
    """
    dataroom_path = state.get("dataroom_path")
    company_name = state["company_name"]

    # Skip if no dataroom provided
    if not dataroom_path:
        return {
            "dataroom_analysis": None,
            "messages": ["No dataroom path provided, skipping dataroom analysis"]
        }

    # Validate path
    if not Path(dataroom_path).exists():
        return {
            "dataroom_analysis": None,
            "messages": [f"Dataroom path does not exist: {dataroom_path}"]
        }

    start_time = datetime.now()

    # Step 1: Scan directory
    print(f"Scanning dataroom: {dataroom_path}")
    inventory = scan_dataroom(dataroom_path)
    print(f"  Found {len(inventory)} documents")

    # Step 2: Classify documents
    print("Classifying documents...")
    inventory = classify_documents(inventory, use_llm=True)

    # Log classification results
    type_counts = {}
    for item in inventory:
        doc_type = item["document_type"]
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
    print(f"  Classification: {type_counts}")

    # Step 3: Route to extractors by priority
    extractions = {}

    # Group by document type
    docs_by_type = {}
    for item in inventory:
        doc_type = item["document_type"]
        if doc_type not in docs_by_type:
            docs_by_type[doc_type] = []
        docs_by_type[doc_type].append(item)

    # Process each type with appropriate extractor
    extractor_map = {
        "pitch_deck": extract_pitch_deck,
        "competitive_analysis": extract_competitive,
        "financial_statements": extract_financials,
        "financial_projections": extract_financials,
        "cap_table": extract_cap_table,
        "term_sheet": extract_legal,
        "safe_note": extract_legal,
        "articles_of_incorporation": extract_legal,
        "team_bios": extract_team,
        "org_chart": extract_team,
        "customer_list": extract_traction,
        "pipeline_metrics": extract_traction,
        "product_documentation": extract_generic,
        "market_research": extract_generic,
        "investor_update": extract_generic,
        "unknown": extract_generic,
    }

    for doc_type, documents in docs_by_type.items():
        print(f"  Processing {len(documents)} {doc_type} documents...")

        extractor = extractor_map.get(doc_type, extract_generic)

        for doc in documents:
            try:
                result = extractor(doc)
                doc["extraction_status"] = "success"

                # Store extraction result
                if doc_type not in extractions:
                    extractions[doc_type] = []
                extractions[doc_type].append(result)

            except Exception as e:
                doc["extraction_status"] = "error"
                doc["extraction_error"] = str(e)
                print(f"    Error extracting {doc['filename']}: {e}")

            doc["processed"] = True

    # Step 4: Synthesize extractions
    print("Synthesizing extractions...")
    synthesis = synthesize_extractions(extractions, inventory)

    # Step 5: Identify data gaps
    data_gaps = identify_data_gaps(synthesis, state["investment_type"])

    # Build final analysis
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    dataroom_analysis = DataroomAnalysis(
        dataroom_path=dataroom_path,
        analysis_date=start_time.isoformat(),
        document_count=len(inventory),
        documents_by_type=type_counts,
        inventory=inventory,
        financials=synthesis.get("financials"),
        cap_table=synthesis.get("cap_table"),
        legal_docs=synthesis.get("legal_docs", []),
        team=synthesis.get("team"),
        traction=synthesis.get("traction"),
        pitch_deck=synthesis.get("pitch_deck"),
        key_facts=synthesis.get("key_facts", {}),
        data_gaps=data_gaps,
        conflicts=synthesis.get("conflicts", []),
        processing_duration_seconds=duration,
        extraction_notes=synthesis.get("notes", [])
    )

    # Step 6: Save artifacts
    save_dataroom_artifacts(company_name, dataroom_analysis)

    return {
        "dataroom_analysis": dataroom_analysis,
        "messages": [
            f"Dataroom analysis complete: {len(inventory)} documents processed in {duration:.1f}s",
            f"  Types: {type_counts}",
            f"  Data gaps identified: {len(data_gaps)}"
        ]
    }
```

#### Step 3.2: Synthesis Engine

**File**: `src/agents/dataroom/synthesis_engine.py`

```python
"""
Synthesis Engine

Merges extractions from multiple documents:
- Deduplicates facts
- Resolves conflicts
- Identifies gaps
- Creates unified data structure
"""

from typing import Dict, List, Any, Optional
from langchain_anthropic import ChatAnthropic
import json

from src.state import (
    DataroomAnalysis,
    FinancialData,
    CapTableData,
    TeamData,
    TractionData,
    DataConflict
)


def synthesize_extractions(
    extractions: Dict[str, List[Any]],
    inventory: List[Dict]
) -> Dict[str, Any]:
    """
    Synthesize all extractions into unified data structure.
    """
    synthesis = {
        "financials": None,
        "cap_table": None,
        "legal_docs": [],
        "team": None,
        "traction": None,
        "pitch_deck": None,
        "key_facts": {},
        "conflicts": [],
        "notes": []
    }

    # Merge financial data
    if "financial_statements" in extractions or "financial_projections" in extractions:
        all_financials = (
            extractions.get("financial_statements", []) +
            extractions.get("financial_projections", [])
        )
        synthesis["financials"], fin_conflicts = merge_financials(all_financials)
        synthesis["conflicts"].extend(fin_conflicts)

    # Use most recent cap table
    if "cap_table" in extractions:
        synthesis["cap_table"] = select_most_recent(extractions["cap_table"])

    # Collect all legal documents
    legal_types = ["term_sheet", "safe_note", "articles_of_incorporation"]
    for legal_type in legal_types:
        if legal_type in extractions:
            synthesis["legal_docs"].extend(extractions[legal_type])

    # Merge team information
    if "team_bios" in extractions or "org_chart" in extractions:
        all_team = (
            extractions.get("team_bios", []) +
            extractions.get("org_chart", [])
        )
        synthesis["team"] = merge_team_data(all_team)

    # Merge traction data
    if "customer_list" in extractions or "pipeline_metrics" in extractions:
        all_traction = (
            extractions.get("customer_list", []) +
            extractions.get("pipeline_metrics", [])
        )
        synthesis["traction"] = merge_traction_data(all_traction)

    # Use pitch deck if found
    if "pitch_deck" in extractions:
        synthesis["pitch_deck"] = extractions["pitch_deck"][0]  # Usually only one

    # Extract key facts across all documents
    synthesis["key_facts"] = extract_key_facts(synthesis)

    return synthesis


def merge_financials(financials: List[FinancialData]) -> Tuple[FinancialData, List[DataConflict]]:
    """Merge multiple financial extractions, resolving conflicts."""

    if not financials:
        return None, []

    if len(financials) == 1:
        return financials[0], []

    # Use LLM to intelligently merge
    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")

    prompt = f"""Merge these financial data extractions from multiple documents.

EXTRACTIONS:
{json.dumps(financials, indent=2, default=str)}

Rules:
1. Use the most recent data when dates differ
2. Flag conflicts where numbers significantly differ
3. Prefer actuals over projections
4. Note the source of each data point

Return a JSON object:
{{
  "merged_financials": {{...}},
  "conflicts": [
    {{"field": "...", "values": [...], "resolution": "..."}}
  ],
  "notes": ["..."]
}}
"""

    response = llm.invoke(prompt)
    result = json.loads(response.content)

    conflicts = [
        DataConflict(
            field=c["field"],
            sources=[{"value": v} for v in c["values"]],
            recommended_value=result["merged_financials"].get(c["field"]),
            resolution_reasoning=c["resolution"]
        )
        for c in result.get("conflicts", [])
    ]

    return result["merged_financials"], conflicts


def identify_data_gaps(
    synthesis: Dict[str, Any],
    investment_type: str
) -> List[str]:
    """Identify missing critical information based on investment type."""

    gaps = []

    # Critical fields by investment type
    if investment_type == "direct":
        critical_fields = {
            "financials.arr": "Annual Recurring Revenue (ARR)",
            "financials.burn_rate": "Monthly burn rate",
            "financials.runway_months": "Cash runway",
            "cap_table.total_shares_outstanding": "Cap table / ownership",
            "team.founders": "Founder backgrounds",
            "traction.total_customers": "Customer count / traction",
        }
    else:  # fund
        critical_fields = {
            "team.founders": "GP backgrounds and track record",
            "financials.projections": "Fund economics / projections",
            "legal_docs": "Fund terms / LPA highlights",
        }

    # Check each critical field
    for field_path, description in critical_fields.items():
        value = get_nested_value(synthesis, field_path)
        if value is None or value == [] or value == {}:
            gaps.append(f"Missing: {description}")

    return gaps


def get_nested_value(obj: Dict, path: str) -> Any:
    """Get value from nested dict using dot notation."""
    keys = path.split(".")
    value = obj

    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None

    return value
```

### Phase 4: Integration

**Goal**: Integrate dataroom analyzer into main workflow.

#### Step 4.1: Update Workflow

**File**: `src/workflow.py` (modifications)

```python
from src.agents.dataroom_orchestrator import dataroom_orchestrator_agent

def build_workflow() -> StateGraph:
    workflow = StateGraph(MemoState)

    # Add dataroom orchestrator as first node
    workflow.add_node("dataroom_analysis", dataroom_orchestrator_agent)

    # Existing nodes
    workflow.add_node("deck_analyst", deck_analyst_agent)
    workflow.add_node("research", research_agent_enhanced)
    # ... rest of nodes ...

    # Set entry point to dataroom analysis
    workflow.set_entry_point("dataroom_analysis")

    # Conditional routing after dataroom analysis
    def route_after_dataroom(state: MemoState) -> str:
        """Route based on dataroom results."""
        dataroom = state.get("dataroom_analysis")

        if dataroom and dataroom.get("pitch_deck"):
            # Dataroom had a pitch deck, skip standalone deck analyst
            return "research"
        else:
            # No dataroom or no deck found, try standalone deck
            return "deck_analyst"

    workflow.add_conditional_edges(
        "dataroom_analysis",
        route_after_dataroom,
        {
            "research": "research",
            "deck_analyst": "deck_analyst"
        }
    )

    workflow.add_edge("deck_analyst", "research")
    # ... rest of edges ...

    return workflow.compile()
```

#### Step 4.2: Update Main Entry Point

**File**: `src/main.py` (modifications)

```python
def main():
    parser = argparse.ArgumentParser(...)

    # Add dataroom argument
    parser.add_argument(
        '--dataroom',
        type=str,
        help='Path to dataroom directory'
    )

    args = parser.parse_args()

    # Load from company data JSON if exists
    dataroom_path = args.dataroom
    data_file = Path(f"data/{args.company_name}.json")

    if data_file.exists():
        with open(data_file) as f:
            company_data = json.load(f)
            # Dataroom path can come from JSON or CLI
            dataroom_path = dataroom_path or company_data.get("dataroom")

    # Initialize state
    initial_state = create_initial_state(
        company_name=args.company_name,
        investment_type=args.type,
        memo_mode=args.mode,
        dataroom_path=dataroom_path,  # NEW
        deck_path=deck_path,
        # ... rest of fields ...
    )
```

#### Step 4.3: Update Artifacts Module

**File**: `src/artifacts.py` (additions)

```python
def save_dataroom_artifacts(
    company_name: str,
    dataroom_analysis: DataroomAnalysis
) -> None:
    """Save dataroom analysis artifacts."""

    output_dir = get_or_create_output_dir(company_name)

    # Save inventory
    with open(output_dir / "0-dataroom-inventory.json", "w") as f:
        json.dump(dataroom_analysis["inventory"], f, indent=2)

    # Save human-readable inventory
    inventory_md = format_inventory_markdown(dataroom_analysis["inventory"])
    with open(output_dir / "0-dataroom-inventory.md", "w") as f:
        f.write(inventory_md)

    # Save full analysis
    with open(output_dir / "0-dataroom-analysis.json", "w") as f:
        json.dump(dataroom_analysis, f, indent=2, default=str)

    # Save human-readable analysis summary
    analysis_md = format_analysis_markdown(dataroom_analysis)
    with open(output_dir / "0-dataroom-analysis.md", "w") as f:
        f.write(analysis_md)

    print(f"Dataroom artifacts saved to {output_dir}")


def format_inventory_markdown(inventory: List[DocumentInventoryItem]) -> str:
    """Format inventory as markdown."""

    lines = [
        "# Dataroom Document Inventory",
        "",
        f"**Total Documents**: {len(inventory)}",
        "",
        "## Documents by Type",
        ""
    ]

    # Group by type
    by_type = {}
    for item in inventory:
        doc_type = item["document_type"]
        if doc_type not in by_type:
            by_type[doc_type] = []
        by_type[doc_type].append(item)

    for doc_type, items in sorted(by_type.items()):
        lines.append(f"### {doc_type.replace('_', ' ').title()} ({len(items)})")
        lines.append("")
        for item in items:
            status = "✓" if item["extraction_status"] == "success" else "✗"
            conf = f"{item['classification_confidence']:.0%}"
            lines.append(f"- {status} `{item['filename']}` (confidence: {conf})")
        lines.append("")

    return "\n".join(lines)


def format_analysis_markdown(analysis: DataroomAnalysis) -> str:
    """Format analysis as markdown summary."""

    lines = [
        "# Dataroom Analysis Summary",
        "",
        f"**Analysis Date**: {analysis['analysis_date']}",
        f"**Documents Processed**: {analysis['document_count']}",
        f"**Processing Time**: {analysis['processing_duration_seconds']:.1f} seconds",
        "",
        "## Key Facts Extracted",
        ""
    ]

    # Add key facts
    for category, facts in analysis.get("key_facts", {}).items():
        lines.append(f"### {category.title()}")
        if isinstance(facts, dict):
            for k, v in facts.items():
                lines.append(f"- **{k}**: {v}")
        else:
            lines.append(f"- {facts}")
        lines.append("")

    # Add data gaps
    if analysis.get("data_gaps"):
        lines.append("## Data Gaps Identified")
        lines.append("")
        for gap in analysis["data_gaps"]:
            lines.append(f"- {gap}")
        lines.append("")

    # Add conflicts
    if analysis.get("conflicts"):
        lines.append("## Data Conflicts")
        lines.append("")
        for conflict in analysis["conflicts"]:
            lines.append(f"- **{conflict['field']}**: {conflict['resolution_reasoning']}")
        lines.append("")

    return "\n".join(lines)
```

---

## Company Data File Updates

Update the company data JSON schema to support dataroom:

**File**: `data/{CompanyName}.json`

```json
{
  "type": "direct",
  "mode": "justify",
  "description": "Brief company description",
  "url": "https://company.com",
  "stage": "Series A",

  "dataroom": "data/datarooms/CompanyName/",
  "deck": "data/CompanyName-deck.pdf",

  "trademark_light": "https://company.com/logo-light.svg",
  "trademark_dark": "https://company.com/logo-dark.svg",

  "notes": "Focus on team backgrounds and financial metrics"
}
```

**Note**: If both `dataroom` and `deck` are provided, the dataroom takes precedence and will find/process the deck within the dataroom.

---

## Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    # ... existing ...

    # Dataroom analysis
    "openpyxl>=3.1.2",       # Excel file parsing
    "python-docx>=1.1.0",    # Word document parsing
    "tabula-py>=2.9.0",      # PDF table extraction (requires Java)
    "pandas>=2.0.0",         # Data manipulation
    "xlrd>=2.0.1",           # Legacy Excel support (.xls)
]
```

**System Dependencies**:
```bash
# For tabula-py (PDF table extraction)
brew install openjdk  # macOS
# or: apt install default-jdk  # Ubuntu/Debian
```

---

## Testing Strategy

### Test Fixtures

Create test dataroom at `tests/fixtures/dataroom/`:

```
tests/fixtures/dataroom/
├── pitch/
│   └── company-pitch-deck.pdf
├── financials/
│   ├── 2024-P&L.xlsx
│   └── 3-year-model.xlsx
├── legal/
│   ├── term-sheet-series-a.pdf
│   └── safe-notes.pdf
├── team/
│   └── founder-bios.pdf
└── traction/
    └── customer-metrics.xlsx
```

### Unit Tests

```python
# tests/test_dataroom_scanner.py
def test_scan_finds_all_documents():
    inventory = scan_dataroom("tests/fixtures/dataroom/")
    assert len(inventory) >= 7

def test_scan_ignores_system_files():
    # Add .DS_Store to fixture
    inventory = scan_dataroom("tests/fixtures/dataroom/")
    assert not any(".DS_Store" in i["filename"] for i in inventory)


# tests/test_document_classifier.py
def test_classifies_pitch_deck():
    item = DocumentInventoryItem(
        filename="company-pitch-deck.pdf",
        extension=".pdf",
        ...
    )
    doc_type, confidence = heuristic_classify(item)
    assert doc_type == "pitch_deck"
    assert confidence >= 0.8

def test_classifies_excel_financials():
    item = DocumentInventoryItem(
        filename="2024-P&L.xlsx",
        extension=".xlsx",
        ...
    )
    doc_type, confidence = heuristic_classify(item)
    assert doc_type == "financial_statements"


# tests/test_financial_extractor.py
def test_extracts_revenue_from_excel():
    result = extract_financials(
        Path("tests/fixtures/dataroom/financials/2024-P&L.xlsx"),
        ".xlsx"
    )
    assert result["revenue"] is not None
    assert "2024" in result["revenue"]
```

### Integration Tests

```python
# tests/test_dataroom_integration.py
def test_full_dataroom_analysis():
    """Test end-to-end dataroom processing."""
    state = {
        "company_name": "TestCo",
        "investment_type": "direct",
        "memo_mode": "consider",
        "dataroom_path": "tests/fixtures/dataroom/"
    }

    result = dataroom_orchestrator_agent(state)

    assert result["dataroom_analysis"] is not None
    assert result["dataroom_analysis"]["document_count"] >= 7
    assert result["dataroom_analysis"]["financials"] is not None
```

---

## Success Criteria

### Phase 1 Complete When:
- [ ] Document scanner discovers all files in test dataroom
- [ ] Classifier correctly identifies document types with >80% accuracy
- [ ] Artifacts saved: inventory.json, inventory.md

### Phase 2 Complete When:
- [ ] Financial extractor parses Excel P&L and projections
- [ ] Cap table extractor parses ownership structure
- [ ] Legal extractor identifies key terms
- [ ] Team extractor finds founder information
- [ ] Each extractor has unit tests passing

### Phase 3 Complete When:
- [ ] Orchestrator processes full dataroom end-to-end
- [ ] Synthesis engine merges data from multiple sources
- [ ] Data gaps correctly identified
- [ ] Conflicts detected and logged

### Phase 4 Complete When:
- [ ] Integrated into main memo generation workflow
- [ ] Works alongside existing deck analyst
- [ ] Research agent enhanced with dataroom findings
- [ ] CLI supports `--dataroom` argument
- [ ] Company JSON supports `dataroom` field

### Overall Success:
- [ ] Processing 10-document dataroom in <2 minutes
- [ ] >80% accuracy on document classification
- [ ] Extracted data correctly populates memo sections
- [ ] Reduced manual data entry by research agent

---

## Future Enhancements

### Near-term (v0.1.x)
- [ ] OCR support for scanned documents
- [ ] Image-based deck/document extraction (Claude Vision)
- [ ] Parallel document processing
- [ ] Progress streaming to terminal

### Medium-term (v0.2.x)
- [ ] Dataroom version tracking (detect updated documents)
- [ ] Incremental processing (only new/changed files)
- [ ] Cloud storage support (Box, Dropbox, Google Drive)
- [ ] Encrypted dataroom handling

### Long-term (v0.3.x)
- [ ] Real-time dataroom monitoring
- [ ] Automated document request generation
- [ ] Integration with VDR platforms (Intralinks, Merrill)
- [ ] Multi-dataroom comparison

---

## Appendix: Document Type Detection Patterns

### Filename Pattern Library

```python
FILENAME_PATTERNS = {
    "pitch_deck": [
        r"pitch.*deck", r"investor.*deck", r"presentation",
        r"one.*pager", r"teaser", r"executive.*summary"
    ],
    "competitive_analysis": [
        r"competitive", r"competitor", r"landscape", r"battlecard",
        r"comparison", r"vs", r"versus", r"market.*map", r"swot"
    ],
    "financial_statements": [
        r"p&l", r"p\s*&\s*l", r"profit.*loss", r"income.*statement",
        r"balance.*sheet", r"cash.*flow", r"financials?$"
    ],
    "financial_projections": [
        r"model", r"projection", r"forecast", r"plan",
        r"\d{4}.*model", r"financial.*model"
    ],
    "cap_table": [
        r"cap.*table", r"captable", r"ownership", r"equity",
        r"shareholding", r"stock.*ledger"
    ],
    "term_sheet": [
        r"term.*sheet", r"termsheet", r"terms",
        r"series.*[a-z].*terms"
    ],
    "safe_note": [
        r"safe", r"simple.*agreement", r"convertible",
        r"note.*purchase"
    ],
    "team_bios": [
        r"team", r"bio", r"founder", r"leadership",
        r"management", r"executive"
    ],
    "customer_list": [
        r"customer", r"client", r"account", r"logo"
    ],
}
```

### Content Signal Library

```python
CONTENT_SIGNALS = {
    "pitch_deck": [
        "investment opportunity", "use of funds", "ask",
        "tam", "sam", "som", "market size",
        "traction", "milestones", "roadmap"
    ],
    "competitive_analysis": [
        "competitors", "competitive landscape", "market share",
        "differentiation", "positioning", "strengths", "weaknesses",
        "swot", "feature comparison", "pricing comparison",
        "competitive advantage", "barriers to entry", "threat"
    ],
    "financial_statements": [
        "revenue", "cogs", "gross margin", "gross profit",
        "operating expenses", "ebitda", "net income",
        "assets", "liabilities", "equity"
    ],
    "cap_table": [
        "shares outstanding", "fully diluted", "ownership %",
        "option pool", "preferred stock", "common stock",
        "vesting", "strike price"
    ],
    "term_sheet": [
        "pre-money valuation", "post-money", "price per share",
        "liquidation preference", "anti-dilution",
        "board composition", "protective provisions"
    ],
    "legal": [
        "whereas", "hereby", "notwithstanding",
        "representation", "warranty", "indemnification"
    ],
}
```

---

---

## Known Issues & Troubleshooting

### Issue #1: Large Dataroom Performance - PDF Page Count Extraction (2025-11-30)

**Status**: Open - Needs Fix
**Severity**: High
**Discovered**: 2025-11-30 during Star-Catcher dataroom analysis

#### Problem Description

When processing large datarooms (100+ files, especially with many PDFs), the analyzer becomes extremely slow during the initial **scan phase**. The root cause is that `_get_page_count()` is called synchronously for every PDF file during inventory building.

**Observed behavior with Star-Catcher dataroom:**
- 218 total files (152 PDFs, 10 Excel files)
- Scanner opens every PDF with `pypdf.PdfReader` just to count pages
- Malformed PDFs trigger hundreds of `"Ignoring wrong pointing object"` warnings
- Each PDF open/parse adds latency
- Total scan time: Several minutes for just the inventory phase

#### Root Cause Analysis

**File**: `src/agents/dataroom/document_scanner.py:105`

```python
# Line 105 - PROBLEMATIC CODE
item: DocumentInventoryItem = {
    # ...
    "page_count": _get_page_count(file_path) if extension == ".pdf" else None,
    # ...
}
```

**File**: `src/agents/dataroom/document_scanner.py:213-220`

```python
def _get_page_count(pdf_path: Path) -> Optional[int]:
    """Get page count from PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))  # Opens and parses entire PDF
        return len(reader.pages)
    except Exception:
        return None
```

For each of the 152 PDFs:
1. `PdfReader` is instantiated (parses PDF structure)
2. Malformed object references trigger warnings (not silenced)
3. Page count is extracted
4. This happens synchronously, blocking the main thread

#### Impact

- Dataroom analysis becomes impractical for large datarooms (100+ files)
- Users see walls of `"Ignoring wrong pointing object"` warnings
- No progress indication during slow scan phase
- May timeout before reaching classification/extraction phases

#### Proposed Solutions

**Option 1: Lazy Page Counting (Recommended)**
Defer page count to extraction phase when the PDF is actually needed:

```python
# In scan_dataroom():
item: DocumentInventoryItem = {
    # ...
    "page_count": None,  # Defer to extraction phase
    # ...
}

# In extractor (when PDF is actually processed):
if item["page_count"] is None and item["extension"] == ".pdf":
    item["page_count"] = _get_page_count(item["file_path"])
```

**Option 2: Add `--fast` / `--skip-page-count` Flag**
Allow users to skip page counting for quick inventory:

```python
def scan_dataroom(dataroom_path: str, skip_page_count: bool = False) -> List[DocumentInventoryItem]:
    # ...
    "page_count": None if skip_page_count else _get_page_count(file_path),
```

**Option 3: Suppress pypdf Warnings**
At minimum, suppress the noisy warnings:

```python
import warnings
import logging

# Suppress pypdf warnings during scan
logging.getLogger("pypdf").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Ignoring wrong pointing object")
```

**Option 4: Parallel PDF Processing**
Use `concurrent.futures` to parallelize page counting:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def scan_dataroom_parallel(dataroom_path: str) -> List[DocumentInventoryItem]:
    # First pass: create inventory without page counts
    inventory = [create_item_no_pagecount(f) for f in files]

    # Second pass: parallel page count for PDFs
    pdf_items = [i for i in inventory if i["extension"] == ".pdf"]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_get_page_count, i["file_path"]): i
            for i in pdf_items
        }
        for future in as_completed(futures):
            item = futures[future]
            item["page_count"] = future.result()

    return inventory
```

**Option 5: Category-Based Analysis**
Add ability to analyze specific subfolders:

```bash
python -m src.agents.dataroom.analyzer "dataroom/Financials" "Company" --category financials
```

#### Recommended Implementation Priority

1. **Immediate**: Add warning suppression (Option 3) - minimal effort, reduces noise
2. **Short-term**: Implement lazy page counting (Option 1) - eliminates root cause
3. **Medium-term**: Add `--fast` flag (Option 2) - user control
4. **Future**: Parallel processing (Option 4) - optimization for very large datarooms

#### Workaround Until Fixed

For large datarooms, users should point directly to the pitch deck instead:

```json
// data/Company.json
{
  "deck": "data/Secure-Inputs/Dataroom/Star Catcher Deck vF 2024.pdf"
}
```

Then run standard memo generation without the dataroom:

```bash
python -m src.main "Star-Catcher"
```

This bypasses the dataroom analyzer entirely and uses the existing `deck_analyst.py` for the single pitch deck.

#### Test Case

```bash
# This command triggered the issue:
source .venv/bin/activate && python -m src.agents.dataroom.analyzer \
    "data/Secure-Inputs/2024_Star-Catcher-Dataroom" \
    "Star-Catcher"

# Expected: Quick scan with progress, then classification
# Actual: Minutes of "Ignoring wrong pointing object" warnings before any progress
```

#### Related Files

- `src/agents/dataroom/document_scanner.py` - Contains `_get_page_count()` function
- `src/agents/dataroom/analyzer.py` - Main entry point, calls `scan_dataroom()`

---

---

## Deck Screenshot Extraction Feature (2025-12-09)

### Overview

The Pitch Deck Analyzer (part of the dataroom system) now includes automatic screenshot extraction capability. This feature uses LLM-guided visual page identification to extract high-quality PNG screenshots of key deck pages for embedding in investment memos.

### How It Works

1. **Visual Page Identification**: After extracting text and data from the deck, Claude's vision API analyzes all pages to identify those with significant visual content (not just text/bullet slides)

2. **Category-Based Selection**: Pages are categorized by content type:
   - `team` - Team photos, org charts, founder headshots
   - `product` - Product screenshots, UI mockups, demo screens
   - `traction` - Growth charts, metrics graphs, revenue/user charts
   - `market` - Market size charts, TAM/SAM/SOM diagrams
   - `competitive` - Competitive landscape diagrams, positioning matrices
   - `architecture` - Technical architecture diagrams, system diagrams
   - `timeline` - Roadmap visuals, milestone timelines

3. **High-Quality Rendering**: Selected pages are rendered at 150 DPI using either:
   - `pdf2image` (Poppler backend) - Higher quality, requires system dependency
   - `PyMuPDF` (fallback) - Built-in, no additional dependencies

4. **Artifact Storage**: Screenshots saved to `output/{Company}-v0.0.x/deck-screenshots/`

### Output Structure

```
output/{Company}-v0.0.x/
├── deck-screenshots/
│   ├── page-03-team.png
│   ├── page-07-traction.png
│   ├── page-12-product.png
│   └── page-15-market.png
├── 0-deck-analysis.json    # Now includes "screenshots" array
├── 0-deck-analysis.md      # Now includes screenshot listing
└── ...
```

### Screenshot Metadata

Each screenshot includes metadata:
```json
{
  "path": "deck-screenshots/page-07-traction.png",
  "filename": "page-07-traction.png",
  "page_number": 7,
  "category": "traction",
  "description": "MRR growth chart showing 3x YoY growth",
  "width": 1275,
  "height": 1650
}
```

### Dependencies

**Python packages** (in pyproject.toml):
- `PyMuPDF>=1.24.0` - PDF rendering (always available)
- `pdf2image>=1.17.0` - Higher quality rendering (optional)

**System dependencies** (for pdf2image):
```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt install poppler-utils
```

### Integration with Dataroom Analyzer

When processing a dataroom that contains pitch decks, the screenshot extraction runs automatically:

1. Dataroom scanner identifies pitch deck(s)
2. Each deck is processed by the Pitch Deck Analyzer
3. Screenshot extraction runs as part of deck analysis
4. Screenshots are saved to the appropriate artifact directory
5. Screenshot metadata included in `DataroomAnalysis.pitch_deck.screenshots`

### Use Cases for Extracted Screenshots

1. **Memo Embedding**: Reference screenshots in investment memo sections
   ```markdown
   See team slide: ![Team](deck-screenshots/page-03-team.png)
   ```

2. **HTML/PDF Exports**: Include visual evidence in exported memos

3. **Quick Reference**: Review key visuals without opening full deck

4. **Archival**: Preserve visual state of deck at analysis time

### Configuration

Screenshot extraction runs by default for all PDF decks. To customize:

```python
# In deck_analyst.py - adjust DPI for quality/size tradeoff
deck_screenshots = extract_deck_screenshots(
    deck_path,
    output_dir,
    page_selections,
    use_pdf2image=PDF2IMAGE_AVAILABLE,
    dpi=150  # Default: 150 (good balance). Range: 72-300
)
```

### Related Documentation

- See [Deck-Analyzer-Agent.md](./Deck-Analyzer-Agent.md) for detailed deck analyst documentation
- See [Multi-Agent-Orchestration-for-Investment-Memo-Generation.md](./Multi-Agent-Orchestration-for-Investment-Memo-Generation.md) for pipeline overview

---

## References

- Existing `deck_analyst.py` implementation
- LangGraph state management patterns
- Multi-agent orchestration architecture doc
- YAML outline system design
