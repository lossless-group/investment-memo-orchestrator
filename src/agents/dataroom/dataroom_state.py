"""
Dataroom State Schemas

TypedDict definitions for dataroom analysis data structures.
These are kept separate from main state.py to avoid conflicts
and will be integrated later.
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal


# =============================================================================
# Document Inventory
# =============================================================================

class DocumentInventoryItem(TypedDict):
    """Single document in dataroom inventory."""
    file_path: str
    filename: str
    extension: str
    file_size_bytes: int
    page_count: Optional[int]  # For PDFs
    parent_directory: str  # Parent folder name for classification hints

    # Classification
    document_type: str
    classification_confidence: float
    classification_reasoning: str
    classification_source: Literal["directory", "filename", "content", "unknown"]

    # Processing Status
    processed: bool
    extraction_status: Literal["pending", "success", "error", "skipped"]
    extraction_error: Optional[str]


# =============================================================================
# Financial Data
# =============================================================================

class FinancialData(TypedDict):
    """Structured financial extraction."""
    document_source: str
    extraction_date: str

    # Income Statement
    revenue: Optional[Dict[str, float]]  # {"2023": 1000000, "2024": 2000000}
    arr: Optional[Dict[str, float]]
    mrr: Optional[Dict[str, float]]
    gross_margin: Optional[Dict[str, float]]
    operating_expenses: Optional[Dict[str, float]]
    net_income: Optional[Dict[str, float]]
    ebitda: Optional[Dict[str, float]]

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
    projections: Optional[Dict[str, Dict[str, float]]]  # {"2025": {"revenue": X}}
    projection_assumptions: Optional[List[str]]

    # Headcount
    headcount: Optional[Dict[str, int]]  # {"2024": 29, "2025": 41}
    headcount_by_department: Optional[Dict[str, int]]

    # Metadata
    fiscal_year_end: Optional[str]
    currency: str
    extraction_notes: List[str]


# =============================================================================
# Cap Table Data
# =============================================================================

class ShareholderEntry(TypedDict):
    """Individual shareholder entry."""
    name: str
    shares: int
    ownership_percentage: float
    share_class: str  # "Common", "Series A", "Series B", etc.
    investor_type: str  # "Founder", "Employee", "VC", "Angel"


class SAFEEntry(TypedDict):
    """SAFE note entry."""
    investor_name: str
    amount_invested: float
    valuation_cap: Optional[float]
    discount_rate: Optional[float]
    conversion_trigger: str


class ConvertibleNoteEntry(TypedDict):
    """Convertible note entry."""
    investor_name: str
    principal_amount: float
    interest_rate: float
    maturity_date: Optional[str]
    valuation_cap: Optional[float]
    discount_rate: Optional[float]


class CapTableData(TypedDict):
    """Structured cap table extraction."""
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


# =============================================================================
# Competitive Analysis Data
# =============================================================================

class CompetitorEntry(TypedDict):
    """Individual competitor entry."""
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
    """Competitor pricing entry."""
    company: str
    pricing_model: str  # "Subscription", "Usage-based", "Per-seat", etc.
    price_range: Optional[str]
    free_tier: Optional[bool]
    enterprise_pricing: Optional[str]


class SWOTAnalysis(TypedDict):
    """SWOT analysis structure."""
    strengths: List[str]
    weaknesses: List[str]
    opportunities: List[str]
    threats: List[str]


class CompetitiveData(TypedDict):
    """Structured competitive analysis extraction."""
    document_source: str
    analysis_date: Optional[str]

    # Direct Competitors
    competitors: List[CompetitorEntry]

    # Market Positioning
    market_positioning: Optional[str]
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
    market_share_estimates: Optional[Dict[str, float]]
    market_share_source: Optional[str]

    # SWOT (if present)
    swot: Optional[SWOTAnalysis]

    # Competitive Dynamics
    barriers_to_entry: List[str]
    switching_costs: Optional[str]
    network_effects: Optional[str]

    # Sales Enablement (from battlecards)
    winning_angles: List[str]
    discovery_questions: List[str]

    extraction_notes: List[str]


# =============================================================================
# Team Data
# =============================================================================

class FounderProfile(TypedDict):
    """Founder profile entry."""
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


class TeamData(TypedDict):
    """Structured team extraction."""
    document_source: str

    # Founders
    founders: List[FounderProfile]

    # Leadership Team
    leadership: List[FounderProfile]  # Reuse same structure

    # Organizational
    total_headcount: Optional[int]
    headcount_by_department: Optional[Dict[str, int]]

    # Advisors & Board
    advisors: List[str]
    board_members: List[str]

    extraction_notes: List[str]


# =============================================================================
# Traction Data
# =============================================================================

class CustomerEntry(TypedDict):
    """Customer entry."""
    name: str
    contract_value: Optional[float]
    contract_type: str  # "Annual", "Multi-year", "Pilot"
    use_case: Optional[str]
    logo_permission: Optional[bool]


class PartnershipEntry(TypedDict):
    """Partnership entry."""
    partner_name: str
    partnership_type: str  # "Technology", "Channel", "Strategic"
    description: Optional[str]


class TractionData(TypedDict):
    """Structured traction extraction."""
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


# =============================================================================
# Legal Document Data
# =============================================================================

class LegalDocData(TypedDict):
    """Structured legal document extraction."""
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
    liquidation_preference: Optional[str]
    anti_dilution: Optional[str]
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


# =============================================================================
# Data Conflict Resolution
# =============================================================================

class DataConflict(TypedDict):
    """Conflict between data sources."""
    field: str
    sources: List[Dict[str, Any]]  # [{source: "file.pdf", value: X}, ...]
    recommended_value: Any
    resolution_reasoning: str


# =============================================================================
# Main Dataroom Analysis Output
# =============================================================================

class DataroomAnalysis(TypedDict):
    """Comprehensive dataroom analysis output."""
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
    competitive: Optional[CompetitiveData]
    pitch_deck: Optional[Dict[str, Any]]  # Reuse existing DeckAnalysisData

    # Synthesis
    key_facts: Dict[str, Any]  # Deduplicated facts across all docs
    data_gaps: List[str]  # Missing critical information
    conflicts: List[DataConflict]  # Conflicting info between docs

    # Metadata
    processing_duration_seconds: float
    extraction_notes: List[str]
