---
title: Model Scorecard Agent and Template System
lede: Add proprietary investment scoring frameworks to memo generation, enabling VC firms to systematically evaluate and communicate their differentiated investment thesis.
date_authored_initial_draft: 2025-11-27
date_authored_current_draft: 2025-11-27
date_authored_final_draft:
date_first_published:
date_last_updated: 2025-11-27
at_semantic_version: 0.1.0
status: Planning
augmented_with: Claude Code (Opus 4.5)
category: Architecture
tags: [Agents, Scorecards, Proprietary-Insights, Templates, LP-Commitments]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A VC investment scorecard with multiple dimensions being evaluated by AI agents, showing radar charts, scoring rubrics, and contextual explanations flowing into a professional investment memo.
date_created: 2025-11-27
date_modified: 2025-11-27
---

# Model Scorecard Agent and Template System

**Status**: Planning
**Date**: 2025-11-27
**Author**: AI Labs Team
**Related**: Format-Memo-According-to-Template-Input.md, Multi-Agent-Orchestration-for-Investment-Memo-Generation.md

---

## Executive Summary

This document specifies the addition of a **Model Scorecard Agent** and supporting **Scorecard Template System** to the Investment Memo Orchestrator. This feature enables VC firms to:

1. **Define proprietary scoring frameworks** as structured YAML templates
2. **Systematically evaluate investments** against firm-specific criteria
3. **Generate scorecard visualizations** embedded in memos
4. **Provide contextual rationale** for each score dimension
5. **Differentiate memo output** from generic AI-generated analysis

The goal is to integrate the firm's "proprietary insights and thinking" into the automated memo generation process, preventing output from becoming too generic to provide real value.

---

## Problem Statement

### Current Limitations

**Issue #1: Generic Output Risk**
- AI-generated memos risk being too generic
- Without firm-specific frameworks, analysis lacks differentiation
- Memos may not reflect the firm's actual investment thesis
- Value to the firm diminishes when output looks like any other AI content

**Issue #2: No Structured Scoring Framework**
- Current system lacks mechanism for systematic evaluation
- Investment decisions are implicitly embedded in prompts
- No way to codify and reuse a firm's evaluation methodology
- Difficult to compare investments against consistent criteria

**Issue #3: Manual Scorecard Creation**
- The Class 5 Global memo shows a 12-dimension scorecard manually added
- These scorecards take significant time to create thoughtfully
- No AI assistance for scoring rationale generation
- Scorecards disconnected from the research/writing pipeline

**Issue #4: Missing Contextual Guidance for Agents**
- Research and writer agents lack awareness of what the firm values
- No mechanism to tell agents "we care about X dimension"
- Agents can't prioritize research around scoring criteria
- Results in memos that don't address firm-specific concerns

### The Class 5 Global Example

The existing LP commitment memo demonstrates a sophisticated 12-dimension scorecard:

| Dimension | Score | Percentile | Description |
|-----------|-------|------------|-------------|
| Empathy | 4/5 | Top 25% | Insight-driven empathy with founders |
| Theory of Market | 4/5 | Top 5% | Well-sharpened theory on market evolution |
| Ecosystem Imprint | 5/5 | Top 5% | Memorable to founders and brokers |
| Hustle | 5/5 | Top 2% | Super-human omnipresence |
| Pull Force | 5/5 | Top 5% | Become the "go-to" investor |
| Pounce | 4/5 | Top 10% | Move quickly with prepared diligence |
| Integrity | 4/5 | Top 20% | Waver-less integrity in drama |
| Grip | 4/5 | Top 10% | Deep trust enables continued access |
| Judgement | 5/5 | Top 5% | Codified systems for deal selection |
| Discipline | 3/5 | Top 20% | Purposeful with limited focus |
| Positioning | 5/5 | Top 10% | Differentiated, unique market position |
| Prudence | 4/5 | Top 10% | Exercise outstanding prudence |

**Key Observations**:
- Each dimension has a **score**, **percentile rank**, and **descriptive rationale**
- Scorecards are split across sections represented as either table columns or table rows. 
- Placement is strategic (after Executive Summary, within Strategy, within Track Record)
- Descriptions are substantial (30-60 words each explaining what the dimension means)

---

## Solution: Model Scorecard System

### Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    MODEL SCORECARD SYSTEM                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. SCORECARD TEMPLATES (YAML, Markdown)                        │
│     └─ Define dimensions, scoring rubrics, placement rules      │
│     └─ Create example or model scorecard, with authentic use    │
│                                                                 │
│  2. SCORECARD AGENT (New)                                       │
│     └─ Score investment against template dimensions             │
│     └─ Generate rationale for each score                        │
│     └─ Determine percentile rankings                            │
│                                                                 │
│  3. SCORECARD ENRICHMENT AGENT (New)                            │
│     └─ Insert formatted scorecard tables into memo sections     │
│     └─ Place tables according to template rules                 │
│                                                                 │
│  4. AGENT CONTEXT INJECTION                                     │
│     └─ Provide scoring dimensions to research agent             │
│     └─ Guide writer agent on firm priorities                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Architecture Overview

```
templates/
├── outlines/
│   ├── direct-investment.yaml
│   ├── fund-commitment.yaml
│   └── custom/
│       └── lpcommit-emerging-manager.yaml  # Uses scorecard
│
├── scorecards/                              # NEW
│   ├── README.md
│   ├── scorecard-schema.json
│   │
│   ├── hypernova-emerging-manager.yaml     # 12-dimension GP scorecard
│   ├── hypernova-direct-investment.yaml    # Startup scoring framework
│   │
│   └── examples/
│       └── class5-global-scored.yaml       # Example completed scorecard
```

---

## Scorecard Template Schema

### Template Definition

**File**: `templates/scorecards/hypernova-emerging-manager.yaml`

```yaml
# Hypernova Capital - Emerging Manager Scorecard
# Framework for evaluating LP commitments to emerging VC managers

metadata:
  scorecard_id: "hypernova-emerging-manager-v1"
  name: "Emerging Manager Evaluation Framework"
  description: "12-dimension framework for evaluating GP/emerging manager fund commitments"
  version: "1.0.0"
  applicable_types: ["fund"]  # Only for LP commitments
  applicable_modes: ["consider", "justify"]
  created_by: "Hypernova Capital"
  date_created: "2025-11-27"

# Scoring configuration
scoring:
  scale:
    min: 1
    max: 5
    labels:
      1: "Bottom quartile"
      2: "Below average"
      3: "Average"
      4: "Above average"
      5: "Exceptional"

  percentile_mapping:
    # Maps score to approximate percentile description
    5: "Top 5%"
    4: "Top 10-25%"
    3: "Top 50%"
    2: "Bottom 50%"
    1: "Bottom 25%"

# Dimension groups (for visual organization)
dimension_groups:
  - group_id: "founder_dynamics"
    name: "Founder & Deal Dynamics"
    description: "Dimensions evaluating GP's relationship with founders and deal access"
    placement:
      section: "executive_summary"
      position: "after"  # Insert after section content
    dimensions:
      - empathy
      - theory_of_market
      - ecosystem_imprint
      - hustle

  - group_id: "execution_style"
    name: "Execution & Investment Style"
    description: "Dimensions evaluating how GP executes on opportunities"
    placement:
      section: "fund_strategy_thesis"
      position: "within"  # Insert within section (after paragraph 2)
      after_paragraph: 1
    dimensions:
      - pull_force
      - pounce
      - integrity
      - grip

  - group_id: "portfolio_management"
    name: "Portfolio Management & Discipline"
    description: "Dimensions evaluating GP's portfolio construction and management"
    placement:
      section: "track_record_analysis"
      position: "within"
      after_paragraph: 1
    dimensions:
      - judgement
      - discipline
      - positioning
      - prudence

# Dimension definitions
dimensions:
  empathy:
    name: "Empathy"
    short_description: "Insight-driven empathy with founders, management, and operators"
    full_description: |
      The ongoing privilege to invest in competitive early-stage deals rests on deep,
      insight-driven empathy with founders, management, and operators. Reputational
      feedback loops are tight and have outsized effects.
    evaluation_guidance:
      questions:
        - "How well does the GP understand founder psychology and motivations?"
        - "What evidence exists of deep relationships with portfolio founders?"
        - "Do founders seek this GP's advice beyond investment matters?"
        - "What is the GP's reputation among founders they didn't invest in?"
      evidence_sources:
        - "Founder references"
        - "Portfolio company testimonials"
        - "GP's founder-facing content and communications"
      red_flags:
        - "Transactional relationships with founders"
        - "Limited follow-on from existing portfolio founders"
        - "Negative feedback from founders on deal that didn't close"
    scoring_rubric:
      5: "Exceptional founder relationships; founders actively seek GP's involvement; strong reputation even among non-portfolio founders"
      4: "Strong founder empathy; good references; founders recommend GP to others"
      3: "Adequate relationships; standard investor-founder dynamics"
      2: "Surface-level relationships; limited founder advocacy"
      1: "Transactional approach; poor founder feedback"

  theory_of_market:
    name: "Theory of Market"
    short_description: "Well-sharpened theory on market evolution and company building"
    full_description: |
      The ability to anticipate the performance horizon of companies at the earliest
      stages looks like intuition and luck, but it's forged from creating a well-sharpened,
      experience and information rich theory on market evolution and company building.
    evaluation_guidance:
      questions:
        - "Can the GP articulate a clear, differentiated market thesis?"
        - "How has their thesis evolved with market changes?"
        - "What evidence supports their market predictions?"
        - "Do they have unique information advantages in their focus areas?"
      evidence_sources:
        - "Written thesis documents"
        - "Public talks and podcasts"
        - "Portfolio company selection patterns"
        - "Timing of investments relative to market trends"
      red_flags:
        - "Vague or generic thesis (e.g., 'AI is big')"
        - "Thesis that doesn't explain portfolio construction"
        - "No evidence of thesis refinement over time"
    scoring_rubric:
      5: "Highly differentiated, proven thesis with clear track record of prescient investments"
      4: "Clear thesis with supporting evidence; some proven predictions"
      3: "Articulate thesis but limited differentiation or track record"
      2: "Generic thesis; hard to distinguish from market consensus"
      1: "No clear thesis; reactive rather than anticipatory investing"

  ecosystem_imprint:
    name: "Ecosystem Imprint"
    short_description: "Memorable presence among founders, brokers, and syndicate investors"
    full_description: |
      The first few investment rounds of any company are put together through deeply
      formed interpersonal relationships and off-the-cuff recommendations. Even good
      investors can be quickly forgotten and be left out. Outstanding investors are
      uniquely memorable to a large group of busy, high-velocity founders, relationship
      brokers, and syndicate investors.
    evaluation_guidance:
      questions:
        - "How well-known is this GP in their target ecosystem?"
        - "Do other investors proactively share deals with this GP?"
        - "Is the GP a 'must-have' on cap tables in their space?"
        - "What is their visibility at key industry events?"
      evidence_sources:
        - "Co-investor references"
        - "Deal flow sources and quality"
        - "Social media/content presence"
        - "Speaking engagements and industry recognition"
      red_flags:
        - "Unknown to other investors in their stated focus"
        - "Relies primarily on inbound cold outreach"
        - "No proactive deal sharing from ecosystem"
    scoring_rubric:
      5: "Category-defining presence; automatically included in best deals; 'must-have' investor"
      4: "Well-known in ecosystem; regularly receives proactive deal flow"
      3: "Recognized but not top-of-mind; adequate deal access"
      2: "Limited ecosystem presence; struggles for deal access"
      1: "Unknown in target ecosystem; relies on cold outreach"

  hustle:
    name: "Hustle"
    short_description: "Super-human level of omnipresence and energy"
    full_description: |
      Rising above the world of existing early-stage venture firms requires
      sweat-inducing levels of energy. The methods are myriad, but the result
      is a super-human level of omnipresence. GPs are somehow at the right events,
      have met with the right founders, are in the right deals, all before lesser
      investors even get a strategy together.
    evaluation_guidance:
      questions:
        - "What is the GP's meeting cadence and founder outreach volume?"
        - "How quickly do they respond to opportunities?"
        - "Are they consistently present at key ecosystem events?"
        - "Do they create their own deal flow through proactive outreach?"
      evidence_sources:
        - "Meeting and outreach metrics"
        - "Event attendance and hosting"
        - "Response time to opportunities"
        - "Content production and thought leadership"
      red_flags:
        - "Passive investment approach"
        - "Slow response to opportunities"
        - "Limited proactive founder engagement"
    scoring_rubric:
      5: "Exceptional energy; omnipresent in ecosystem; creates own luck through relentless activity"
      4: "High energy; proactive approach; consistently present"
      3: "Adequate activity level; standard VC engagement"
      2: "Below average activity; reactive approach"
      1: "Passive; minimal proactive engagement"

  pull_force:
    name: "Pull Force"
    short_description: "Become the 'go-to' investor for their market thesis"
    full_description: |
      As a company becomes a clear breakout opportunity, many founders short-cut
      running an investment process with the wider venture market. They figure out
      who the "go-to" investors are, and the rounds are done quickly. Great investors
      become a "go-to" for their market thesis and investment strategy.
    evaluation_guidance:
      questions:
        - "Do founders specifically seek out this GP?"
        - "Is the GP's name synonymous with a particular space?"
        - "How often do they win competitive deals?"
        - "Are they getting allocation in oversubscribed rounds?"
      evidence_sources:
        - "Win rate in competitive deals"
        - "Allocation in hot rounds"
        - "Brand recognition in focus area"
        - "Inbound deal flow quality"
      red_flags:
        - "Rarely wins competitive situations"
        - "Not associated with any particular space"
        - "Struggles to get allocation"
    scoring_rubric:
      5: "Category leader; founders specifically seek them out; wins most competitive deals"
      4: "Strong pull; recognized expert in space; good win rate"
      3: "Adequate brand; sometimes wins competitive deals"
      2: "Limited brand recognition; rarely wins competitive"
      1: "No pull; unknown or avoided by quality founders"

  pounce:
    name: "Pounce"
    short_description: "Move quickly with prepared, built-in due diligence"
    full_description: |
      Momentum rounds are circulated and closed in such short-order, the only way
      to participate is to move quickly, seemingly shortcutting professional process.
      The due diligence is there, but it's prepared and built into the DNA of the firm.
    evaluation_guidance:
      questions:
        - "How quickly can the GP make investment decisions?"
        - "Do they have pre-built conviction in their focus areas?"
        - "Is their diligence process efficient without being shallow?"
        - "Have they lost deals due to slow process?"
      evidence_sources:
        - "Time from first meeting to term sheet"
        - "Deal velocity metrics"
        - "Pre-existing research in focus areas"
        - "References on decision-making speed"
      red_flags:
        - "Multi-month decision processes"
        - "Lost deals due to slow diligence"
        - "No pre-built conviction or research"
    scoring_rubric:
      5: "Lightning fast; pre-built conviction enables rapid decisions; wins on speed"
      4: "Quick mover; efficient diligence; rarely loses to timing"
      3: "Standard pace; sometimes misses time-sensitive deals"
      2: "Slow process; frequently loses to faster investors"
      1: "Glacial; process prevents competitive participation"

  integrity:
    name: "Integrity"
    short_description: "Waver-less integrity in difficult moments"
    full_description: |
      At least 40% of partner time deals in drama of some kind. And most report
      that eventually 60% of all their investments will underperform. Being a
      shareholder across this recurring drama requires waver-less integrity in
      moments that may otherwise bring out the worst in lesser stakeholders.
    evaluation_guidance:
      questions:
        - "How does the GP behave when companies struggle?"
        - "Do they maintain supportive relationships through difficulties?"
        - "What is their reputation for fair dealing?"
        - "How do they handle conflicts of interest?"
      evidence_sources:
        - "Founder references on difficult situations"
        - "Co-investor references"
        - "Handling of failed investments"
        - "Reputation in legal/restructuring situations"
      red_flags:
        - "Adversarial behavior with struggling companies"
        - "Reputation for sharp dealing"
        - "Conflicts of interest concerns"
    scoring_rubric:
      5: "Impeccable integrity; founders and co-investors trust completely; gold standard"
      4: "Strong integrity; good reputation; trusted partner"
      3: "Adequate integrity; no major concerns"
      2: "Some concerns; mixed references"
      1: "Poor reputation; integrity issues documented"

  grip:
    name: "Grip"
    short_description: "Deep trust enables continued access in growth rounds"
    full_description: |
      After companies achieve breakout momentum, growth investors line up and
      compete to get into tightly controlled rounds. The best early-stage investors
      have deep trust with founders and board directors, so often get continued
      access to invest in the company even when others are locked out.
    evaluation_guidance:
      questions:
        - "What is the GP's follow-on investment rate in winners?"
        - "Do they maintain pro-rata in competitive growth rounds?"
        - "How strong are board relationships?"
        - "Do founders want them to continue investing?"
      evidence_sources:
        - "Follow-on investment data"
        - "Pro-rata maintenance in growth rounds"
        - "Board seat retention"
        - "Founder references on continued involvement"
      red_flags:
        - "Low follow-on rate in winners"
        - "Lost board seats"
        - "Squeezed out of growth rounds"
    scoring_rubric:
      5: "Exceptional grip; always maintains access; founders insist on continued participation"
      4: "Strong grip; usually maintains pro-rata; trusted board member"
      3: "Adequate grip; sometimes maintains access"
      2: "Weak grip; frequently loses access in growth rounds"
      1: "No grip; systematically squeezed out"

  judgement:
    name: "Judgement"
    short_description: "Codified systems for repeatable deal selection"
    full_description: |
      Firms with reputations will find themselves awash in opportunities. The
      resulting volume is incomprehensible without deliberate systems for repeating
      and scaling a codified sense of judgement — applied across screening, selecting,
      and securing access to those deals that best fit the firm and their strategy.
    evaluation_guidance:
      questions:
        - "Does the GP have a systematic investment process?"
        - "How do they filter high-volume deal flow?"
        - "Is their selection criteria consistently applied?"
        - "Can they articulate why they passed on deals?"
      evidence_sources:
        - "Investment process documentation"
        - "Screening criteria and metrics"
        - "Pattern analysis of investments"
        - "Pass decisions and rationale"
      red_flags:
        - "Ad hoc decision making"
        - "Inconsistent selection criteria"
        - "Can't explain passes"
    scoring_rubric:
      5: "Highly systematic; repeatable judgement at scale; clear criteria consistently applied"
      4: "Strong process; good filtering; mostly consistent"
      3: "Adequate process; some systematization"
      2: "Inconsistent; ad hoc decisions"
      1: "No system; chaotic decision making"

  discipline:
    name: "Discipline"
    short_description: "Purposeful focus despite distractions and peer pressure"
    full_description: |
      VC Firms will see a rise of distractions, hyped opportunities, and implicit
      peer-pressure. Inclinations to abandon process, retro-fit strategy to mirror
      haphazard portfolio construction, or neglect the important for the urgent.
      Firms must be purposeful with their limited focus and capital.
    evaluation_guidance:
      questions:
        - "Does the GP stick to their stated strategy?"
        - "How do they handle FOMO on hot deals outside their focus?"
        - "Is portfolio construction consistent with thesis?"
        - "Have they avoided strategy drift?"
      evidence_sources:
        - "Portfolio consistency analysis"
        - "Strategy drift evidence"
        - "Deals passed due to discipline"
        - "Response to market hype cycles"
      red_flags:
        - "Portfolio doesn't match thesis"
        - "Chased hot sectors outside expertise"
        - "Strategy changed without clear rationale"
    scoring_rubric:
      5: "Exceptional discipline; portfolio perfectly matches thesis; resists all distractions"
      4: "Strong discipline; mostly consistent; occasional strategic expansion"
      3: "Adequate discipline; some drift"
      2: "Limited discipline; portfolio inconsistent with thesis"
      1: "No discipline; chases every opportunity"

  positioning:
    name: "Positioning"
    short_description: "Differentiated, unique market position"
    full_description: |
      Long-term, multi-fund success requires partnerships to align their combined
      theses, strategy, and brand to a differentiated, unique positioning in the
      market. Firm positioning may difficult to distinguish from an industry outsider,
      but those with deep context can recall the positioning of dozens of firms from memory.
    evaluation_guidance:
      questions:
        - "What is the GP's unique positioning?"
        - "How differentiated are they from competitors?"
        - "Can ecosystem participants articulate their positioning?"
        - "Is their positioning defensible and authentic?"
      evidence_sources:
        - "Brand positioning analysis"
        - "Ecosystem perception"
        - "Competitive differentiation"
        - "Positioning consistency over time"
      red_flags:
        - "Generic positioning"
        - "Indistinguishable from peers"
        - "Inconsistent positioning"
    scoring_rubric:
      5: "Unique, defensible position; immediately recognizable; category-defining"
      4: "Clear differentiation; well-understood positioning"
      3: "Some differentiation; adequate positioning"
      2: "Limited differentiation; hard to distinguish"
      1: "No clear positioning; generic"

  prudence:
    name: "Prudence"
    short_description: "Outstanding prudence with struggling portfolio companies"
    full_description: |
      Limited Partner capital is often burned to support portfolio companies that
      do not fail, but continuously struggle to find breakout growth. The pressures
      to continue supporting these companies get the best of investors who can't
      exercise outstanding prudence, often at odds with interest of others around the table.
    evaluation_guidance:
      questions:
        - "How does the GP manage struggling portfolio companies?"
        - "Do they make rational follow-on decisions?"
        - "How do they handle sunk cost bias?"
        - "What is their approach to recycling capital from failures?"
      evidence_sources:
        - "Follow-on decision patterns"
        - "Handling of underperformers"
        - "Write-off timing"
        - "Capital recycling practices"
      red_flags:
        - "Throwing good money after bad"
        - "Inability to cut losses"
        - "Sunk cost bias in decisions"
    scoring_rubric:
      5: "Exceptional prudence; rational capital allocation; quick to recognize and act on failures"
      4: "Strong prudence; mostly rational follow-on decisions"
      3: "Adequate prudence; some sunk cost bias"
      2: "Limited prudence; continues supporting losers too long"
      1: "Poor prudence; systematically overinvests in failures"

# Output formatting
output_format:
  table_style: "markdown"
  columns:
    - field: "name"
      header: ""
      width: "20%"
    - field: "score"
      header: ""
      width: "10%"
      format: "{score}/5"
    - field: "percentile"
      header: ""
      width: "15%"
    - field: "full_description"
      header: ""
      width: "55%"

  visual_options:
    show_dimension_name: true
    show_score: true
    show_percentile: true
    show_description: true
    highlight_top_scores: true
    top_score_threshold: 5

# Agent integration
agent_context:
  research_agent:
    priority_topics:
      - "Gather evidence for each scoring dimension"
      - "Find founder references and testimonials"
      - "Research GP's track record and reputation"
      - "Look for evidence of the 12 dimensions"
    search_queries_template:
      - "{gp_name} founder references testimonials"
      - "{gp_name} investment thesis philosophy"
      - "{gp_name} deal flow reputation"
      - "{gp_name} portfolio company outcomes"

  writer_agent:
    section_guidance:
      executive_summary:
        include: "Brief mention of standout scorecard dimensions"
        tone: "Highlight exceptional scores with supporting rationale"
      fund_strategy_thesis:
        include: "Embed execution style scorecard after strategy discussion"
      track_record_analysis:
        include: "Embed portfolio management scorecard to contextualize track record"
```

---

## Workflow Integration

### Why Scorecard Runs Late in the Pipeline

The scorecard agent must run **after** the memo content is written and enriched because:

1. **Scoring requires context**: The scorecard evaluates the investment based on synthesized analysis, not raw research data
2. **Sections contain the evidence**: The written sections (Team, Track Record, Strategy) contain the structured analysis needed to score dimensions accurately
3. **Citations provide credibility**: Enriched citations give the scorer confidence in the underlying claims
4. **Holistic assessment**: The scorecard is a final synthesis layer, summarizing the memo's findings into structured scores

**Anti-pattern avoided**: Scoring before writing would force the scorecard agent to duplicate the writer's synthesis work, leading to inconsistency between scores and narrative.

### Updated Agent Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    UPDATED WORKFLOW                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CONTENT GENERATION PHASE:                                      │
│  [Deck Analyst] → [Research] → [Writer] → [Trademark] →         │
│                                                                 │
│  ENRICHMENT PHASE:                                              │
│  [Socials] → [Link Enrichment] → [Citation] → [TOC] →          │
│                                                                 │
│  SCORING & VALIDATION PHASE:                                    │
│  [Scorecard Agent] → [Scorecard Enrichment] →                   │
│  [Citation Validator] → [Fact Checker] → [Validator]           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight**: The scorecard runs in the "Scoring & Validation Phase" because it:
- Reads the completed, enriched memo sections
- Scores based on the synthesized content (not raw research)
- Inserts scorecard tables into the already-written sections
- Acts as a final analytical layer before validation

### New Agents

#### 1. Scorecard Agent (`src/agents/scorecard_agent.py`)

**Position in Pipeline**: After TOC, Before Citation Validator (late in pipeline)

**Why this position**:
- All sections are written and enriched with citations
- TOC has been generated (section structure is finalized)
- Scorecard can read the full memo content to generate accurate scores
- Scorecard tables will be inserted before final validation

**Responsibilities**:
1. Load appropriate scorecard template based on investment type
2. **Read completed memo sections** to evaluate each dimension
3. Score each dimension based on memo content + research data
4. Generate rationale that references specific memo content
5. Determine percentile rankings
6. Save scored scorecard to artifacts

**Input**:
- `state["research"]` - Research data (supplementary)
- `state["deck_analysis"]` - Deck analysis (supplementary)
- `state["investment_type"]` - "direct" or "fund"
- `state["scorecard_template"]` - Optional custom template name
- **Section files from `2-sections/`** - The actual written memo content

**Output**:
```python
{
    "scorecard": {
        "template_id": "hypernova-emerging-manager-v1",
        "scores": {
            "empathy": {"score": 4, "percentile": "Top 25%", "rationale": "..."},
            "theory_of_market": {"score": 4, "percentile": "Top 5%", "rationale": "..."},
            # ... all 12 dimensions
        },
        "dimension_groups": [
            {
                "group_id": "founder_dynamics",
                "dimensions": ["empathy", "theory_of_market", "ecosystem_imprint", "hustle"],
                "placement": {"section": "executive_summary", "position": "after"}
            },
            # ... other groups
        ],
        "overall_assessment": "Strong GP across all dimensions...",
        "confidence_notes": ["Limited data on X dimension", ...]
    },
    "messages": ["Scorecard generated: 12 dimensions scored"]
}
```

**Implementation Approach**:

```python
def scorecard_agent(state: MemoState) -> dict:
    """
    Score investment against firm's scorecard template.

    IMPORTANT: This agent runs LATE in the pipeline, after all sections
    are written and enriched. It reads the completed memo content to
    generate accurate scores based on the synthesized analysis.
    """
    # 1. Load scorecard template
    template = load_scorecard_template(
        state.get("scorecard_template") or get_default_template(state["investment_type"])
    )

    # 2. Load completed memo sections (the key difference!)
    output_dir = get_latest_output_dir(state["company_name"])
    sections_dir = output_dir / "2-sections"

    memo_sections = {}
    for section_file in sections_dir.glob("*.md"):
        memo_sections[section_file.stem] = section_file.read_text()

    # 3. Prepare context for scoring - includes WRITTEN CONTENT
    context = {
        "memo_sections": memo_sections,  # The written, enriched sections
        "research": state.get("research", {}),  # Supplementary
        "deck_analysis": state.get("deck_analysis", {}),  # Supplementary
        "company_name": state["company_name"],
    }

    # 4. Score each dimension against the memo content
    scores = {}
    for dim_id, dim_def in template["dimensions"].items():
        score_result = score_dimension(dim_id, dim_def, context, template)
        scores[dim_id] = score_result

    # 5. Generate overall assessment
    overall = generate_overall_assessment(scores, template)

    # 6. Save artifacts
    save_scorecard_artifacts(state["company_name"], scores, template)

    return {
        "scorecard": {
            "template_id": template["metadata"]["scorecard_id"],
            "scores": scores,
            "dimension_groups": template["dimension_groups"],
            "overall_assessment": overall
        },
        "messages": [f"Scorecard complete: {len(scores)} dimensions scored"]
    }


def score_dimension(dim_id: str, dim_def: dict, context: dict, template: dict) -> dict:
    """
    Score a single dimension using LLM with structured guidance.

    The scorer reads the COMPLETED MEMO SECTIONS to evaluate each dimension,
    not just raw research data. This ensures scores align with the narrative.
    """
    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    # Identify which memo sections are most relevant for this dimension
    relevant_sections = get_relevant_sections_for_dimension(dim_id, context["memo_sections"])

    prompt = f"""You are evaluating an investment based on the COMPLETED MEMO CONTENT.

DIMENSION: {dim_def['name']}
DESCRIPTION: {dim_def['full_description']}

EVALUATION GUIDANCE:
Questions to consider:
{format_list(dim_def['evaluation_guidance']['questions'])}

Evidence sources to look for:
{format_list(dim_def['evaluation_guidance']['evidence_sources'])}

Red flags to watch for:
{format_list(dim_def['evaluation_guidance']['red_flags'])}

SCORING RUBRIC:
5: {dim_def['scoring_rubric']['5']}
4: {dim_def['scoring_rubric']['4']}
3: {dim_def['scoring_rubric']['3']}
2: {dim_def['scoring_rubric']['2']}
1: {dim_def['scoring_rubric']['1']}

MEMO CONTENT TO EVALUATE:
{relevant_sections}

TASK:
1. Score this dimension from 1-5 based on evidence IN THE MEMO
2. Provide a 2-3 sentence rationale referencing specific memo content
3. Note confidence level (high/medium/low) based on how well the memo addresses this dimension
4. Identify any red flags mentioned or implied in the memo

Return JSON:
{{
  "score": <1-5>,
  "rationale": "...",
  "confidence": "high|medium|low",
  "evidence_found": ["...", "..."],
  "red_flags_observed": ["...", "..."]
}}
"""

    response = llm.invoke(prompt)
    result = json.loads(response.content)

    # Add percentile mapping
    result["percentile"] = template["scoring"]["percentile_mapping"][result["score"]]

    return result
```

#### 2. Scorecard Enrichment Agent (`src/agents/scorecard_enrichment.py`)

**Position in Pipeline**: After Writer, Before Trademark

**Responsibilities**:
1. Load scored scorecard from state
2. Format scorecard tables according to template
3. Insert tables into appropriate sections based on placement rules
4. Preserve existing section content

**Implementation**:

```python
def scorecard_enrichment_agent(state: MemoState) -> dict:
    """
    Insert scorecard tables into memo sections.

    Places formatted scorecard tables according to template placement rules.
    """
    scorecard = state.get("scorecard")
    if not scorecard:
        return {"messages": ["No scorecard data, skipping enrichment"]}

    # Get output directory
    output_dir = get_latest_output_dir(state["company_name"])
    sections_dir = output_dir / "2-sections"

    # Process each dimension group
    for group in scorecard["dimension_groups"]:
        section_file = get_section_file(group["placement"]["section"], sections_dir)
        if not section_file.exists():
            continue

        # Read current section content
        content = section_file.read_text()

        # Generate table for this group
        table = format_scorecard_table(group, scorecard["scores"])

        # Insert table according to placement rules
        updated_content = insert_table(content, table, group["placement"])

        # Save updated section
        section_file.write_text(updated_content)

    return {
        "messages": [f"Inserted {len(scorecard['dimension_groups'])} scorecard tables"]
    }


def format_scorecard_table(group: dict, scores: dict) -> str:
    """Format a dimension group as markdown table."""

    headers = []
    row1_scores = []  # Score row (e.g., "4/5")
    row2_percentiles = []  # Percentile row
    row3_descriptions = []  # Description row

    for dim_id in group["dimensions"]:
        dim_score = scores[dim_id]
        headers.append(dim_score.get("name", dim_id.replace("_", " ").title()))
        row1_scores.append(f"{dim_score['score']}/5")
        row2_percentiles.append(dim_score["percentile"])
        row3_descriptions.append(dim_score.get("full_description", dim_score.get("rationale", "")))

    # Build markdown table
    table = f"| {' | '.join(headers)} |\n"
    table += f"| {' | '.join(['---'] * len(headers))} |\n"
    table += f"| {' | '.join(row1_scores)} |\n"
    table += f"| {' | '.join(row2_percentiles)} |\n"
    table += f"| {' | '.join(row3_descriptions)} |\n"

    return table
```

---

## Research Agent Context Injection (Optional Enhancement)

### Rationale
Even though the scorecard is generated **late** in the pipeline (after writing), the **scorecard template** can still guide research **early**. The template defines what dimensions matter to the firm, so the research agent can proactively gather evidence for those dimensions.

This is a "forward-looking" optimization: the template informs research, and then the completed memo content (informed by that research) is scored later.

### Problem
The research agent currently doesn't know what the firm cares about. It performs generic research without guidance on what evidence to prioritize.

### Solution
Inject scorecard **template** dimensions (not scores) into research agent prompts to guide evidence collection.

**Modified Research Agent**:

```python
def research_agent_enhanced(state: MemoState) -> dict:
    """Enhanced research with scorecard awareness."""

    # Load scorecard template for context
    scorecard_template = None
    if state.get("scorecard_template"):
        scorecard_template = load_scorecard_template(state["scorecard_template"])
    elif state["investment_type"] == "fund":
        scorecard_template = load_scorecard_template("hypernova-emerging-manager")

    # Generate search queries
    base_queries = generate_standard_queries(state["company_name"])

    if scorecard_template:
        # Add scorecard-guided queries
        scorecard_queries = generate_scorecard_queries(
            state["company_name"],
            scorecard_template
        )
        all_queries = base_queries + scorecard_queries
    else:
        all_queries = base_queries

    # Execute searches...
    results = execute_searches(all_queries)

    # Synthesize with scorecard context
    if scorecard_template:
        synthesis = synthesize_with_scorecard_context(results, scorecard_template)
    else:
        synthesis = synthesize_standard(results)

    return {"research": synthesis}


def generate_scorecard_queries(company_name: str, template: dict) -> List[str]:
    """Generate research queries based on scorecard dimensions."""

    queries = []
    agent_context = template.get("agent_context", {}).get("research_agent", {})

    # Use template-defined queries
    for query_template in agent_context.get("search_queries_template", []):
        queries.append(query_template.format(gp_name=company_name))

    # Add dimension-specific queries
    for dim_id, dim_def in template["dimensions"].items():
        evidence_sources = dim_def.get("evaluation_guidance", {}).get("evidence_sources", [])
        for source in evidence_sources[:2]:  # Top 2 evidence sources
            queries.append(f"{company_name} {source.lower()}")

    return queries
```

---

## Writer Agent Context Injection (NOT Recommended)

### Why This Doesn't Work

In the original (incorrect) design, I proposed injecting scorecard scores into the writer prompts. This is **not possible** because:

1. **Scorecard runs after writing**: The scorecard agent needs the completed memo to generate scores
2. **Circular dependency**: Writer can't use scores that don't exist yet
3. **Duplication of effort**: If writer had scores, the scorecard agent would be redundant

### Alternative: Outline-Based Guidance

Instead of scorecard injection, the writer should receive guidance from the **outline** about what the firm values. The outline's `guiding_questions` and `vocabulary` serve this purpose.

If a firm wants the writer to emphasize certain dimensions, they should:
1. Add relevant guiding questions to the outline sections
2. Include dimension-related vocabulary guidance
3. NOT try to inject scorecard scores (which don't exist yet)

### The Correct Flow

```
Research (uses template dimensions to guide queries)
    ↓
Writer (uses outline guiding questions, NOT scores)
    ↓
[Enrichment agents]
    ↓
Scorecard Agent (reads completed memo, generates scores)
    ↓
Scorecard Enrichment (inserts score tables into sections)
```

---

## Outline Integration

### Updated Outline Schema

Outlines can now reference scorecard templates:

```yaml
# templates/outlines/custom/lpcommit-emerging-manager.yaml

metadata:
  outline_type: "fund_commitment"
  version: "1.0.0"
  extends: "../fund-commitment.yaml"

  # NEW: Scorecard integration
  scorecard:
    template: "hypernova-emerging-manager"
    required: true
    placement_enabled: true

# Section-specific scorecard notes
sections:
  - number: 1
    name: "Executive Summary"
    # ... standard fields ...

    scorecard_integration:
      include_summary: true
      highlight_dimensions: ["hustle", "ecosystem_imprint", "positioning"]
      summary_format: "Brief mention of standout scores"

  - number: 3
    name: "Fund Strategy & Thesis"
    # ... standard fields ...

    scorecard_integration:
      embed_group: "execution_style"
      position: "within"
      after_paragraph: 1
```

---

## Company Data Integration

### Updated Company Data Schema

Add scorecard template specification to company data files:

```json
{
  "type": "fund",
  "mode": "justify",
  "outline": "lpcommit-emerging-manager",
  "scorecard_template": "hypernova-emerging-manager",
  "description": "Class 5 Global Fund II LP commitment",
  "url": "https://class5global.com",
  "notes": "Focus on emerging markets, MENA region"
}
```

### Selection Logic

1. Check company data for `scorecard_template` field
2. If not specified, check outline for scorecard reference
3. If outline specifies required scorecard, load default for investment type
4. If no scorecard applicable, skip scorecard agents

---

## Artifact Trail

### New Artifacts

```
output/{Company-Name}-v0.0.x/
├── 0-deck-analysis.json
├── 0-deck-analysis.md
├── 1-research.json
├── 1-research.md
├── 1.5-scorecard.json          # NEW: Scored scorecard data
├── 1.5-scorecard.md            # NEW: Human-readable scorecard
├── 2-sections/
│   ├── 01-executive-summary.md  # May include scorecard table
│   ├── 03-fund-strategy--thesis.md  # May include scorecard table
│   └── 06-track-record-analysis.md  # May include scorecard table
├── 3-validation.json
├── 3-validation.md
├── 4-final-draft.md            # Includes all scorecard tables
└── state.json
```

### Scorecard Artifact Format

**File**: `1.5-scorecard.json`

```json
{
  "template_id": "hypernova-emerging-manager-v1",
  "company_name": "Class 5 Global Fund II",
  "generated_at": "2025-11-27T10:30:00Z",
  "scores": {
    "empathy": {
      "score": 4,
      "percentile": "Top 25%",
      "rationale": "Strong founder relationships evidenced by...",
      "confidence": "high",
      "evidence_found": ["Founder testimonials", "Follow-on rates"],
      "red_flags_observed": []
    }
    // ... all dimensions
  },
  "dimension_groups": [
    {
      "group_id": "founder_dynamics",
      "dimensions": ["empathy", "theory_of_market", "ecosystem_imprint", "hustle"]
    }
    // ... all groups
  ],
  "overall_assessment": "Class 5 Global demonstrates exceptional strength across...",
  "confidence_notes": [
    "Limited public data on early fund performance",
    "High confidence on ecosystem presence based on co-investor references"
  ]
}
```

**File**: `1.5-scorecard.md`

```markdown
# Scorecard: Class 5 Global Fund II

**Template**: Emerging Manager Evaluation Framework v1.0.0
**Generated**: November 27, 2025
**Overall Assessment**: Strong GP with exceptional ecosystem presence

## Founder & Deal Dynamics

| Dimension | Score | Percentile | Assessment |
|-----------|-------|------------|------------|
| Empathy | 4/5 | Top 25% | Strong founder relationships... |
| Theory of Market | 4/5 | Top 5% | Clear thesis on emerging markets... |
| Ecosystem Imprint | 5/5 | Top 5% | Exceptional MENA presence... |
| Hustle | 5/5 | Top 2% | Remarkable energy and presence... |

## Execution & Investment Style

| Dimension | Score | Percentile | Assessment |
|-----------|-------|------------|------------|
| Pull Force | 5/5 | Top 5% | Go-to investor for MENA... |
| Pounce | 4/5 | Top 10% | Quick decision-making... |
| Integrity | 4/5 | Top 20% | Strong reputation... |
| Grip | 4/5 | Top 10% | Maintained pro-rata access... |

## Portfolio Management & Discipline

| Dimension | Score | Percentile | Assessment |
|-----------|-------|------------|------------|
| Judgement | 5/5 | Top 5% | Systematic approach... |
| Discipline | 3/5 | Top 20% | Mostly consistent... |
| Positioning | 5/5 | Top 10% | Unique MENA focus... |
| Prudence | 4/5 | Top 10% | Rational follow-on decisions... |

## Confidence Notes

- Limited public data on early fund performance
- High confidence on ecosystem presence based on co-investor references
```

---

## State Schema Updates

### Updated MemoState

```python
# src/state.py additions

class ScorecardScore(TypedDict):
    """Score for a single dimension."""
    score: int  # 1-5
    percentile: str  # e.g., "Top 5%"
    rationale: str
    confidence: str  # "high", "medium", "low"
    evidence_found: List[str]
    red_flags_observed: List[str]

class DimensionGroup(TypedDict):
    """Grouping of dimensions for placement."""
    group_id: str
    dimensions: List[str]
    placement: Dict[str, str]

class ScorecardData(TypedDict):
    """Complete scorecard evaluation."""
    template_id: str
    scores: Dict[str, ScorecardScore]
    dimension_groups: List[DimensionGroup]
    overall_assessment: str
    confidence_notes: List[str]

class MemoState(TypedDict):
    # ... existing fields ...
    scorecard_template: Optional[str]  # NEW
    scorecard: Optional[ScorecardData]  # NEW
```

---

## Implementation Plan

### Phase 1: Schema & Templates (Week 1)

**Objective**: Create scorecard template schema and first template

**Tasks**:
- [ ] Create `templates/scorecards/` directory structure
- [ ] Create `templates/scorecards/scorecard-schema.json` (validation schema)
- [ ] Create `templates/scorecards/hypernova-emerging-manager.yaml` (12-dimension template)
- [ ] Create `templates/scorecards/README.md` (documentation)
- [ ] Add example scored output in `templates/scorecards/examples/`

**Deliverables**:
- Complete scorecard template schema
- Working Hypernova emerging manager template
- Documentation

---

### Phase 2: Scorecard Agent (Week 2)

**Objective**: Implement scoring agent

**Tasks**:
- [ ] Create `src/agents/scorecard_agent.py`
- [ ] Implement `load_scorecard_template()` utility
- [ ] Implement `score_dimension()` function
- [ ] Implement `generate_overall_assessment()` function
- [ ] Add artifact saving for scorecard
- [ ] Update `src/state.py` with scorecard types
- [ ] Unit tests for scorecard agent

**Deliverables**:
- Working scorecard agent
- Scorecard artifacts (JSON + MD)
- Tests passing

---

### Phase 3: Scorecard Enrichment Agent (Week 2-3)

**Objective**: Implement table insertion agent

**Tasks**:
- [ ] Create `src/agents/scorecard_enrichment.py`
- [ ] Implement `format_scorecard_table()` function
- [ ] Implement `insert_table()` function with placement logic
- [ ] Handle different placement types ("after", "within", "before")
- [ ] Unit tests for enrichment agent

**Deliverables**:
- Working enrichment agent
- Scorecard tables appearing in sections
- Tests passing

---

### Phase 4: Workflow Integration (Week 3)

**Objective**: Integrate new agents into pipeline

**Tasks**:
- [ ] Update `src/workflow.py` to include scorecard agents
- [ ] Add conditional routing (only if scorecard template specified)
- [ ] Update `src/main.py` to handle scorecard template selection
- [ ] Integration tests

**Deliverables**:
- End-to-end workflow with scorecards
- Integration tests passing

---

### Phase 5: Agent Context Injection (Week 3-4)

**Objective**: Enhance research and writer agents with scorecard awareness

**Tasks**:
- [ ] Update research agent to use scorecard-guided queries
- [ ] Update writer agent to incorporate scorecard context
- [ ] Update prompts to reference scored dimensions
- [ ] Quality testing on sample memos

**Deliverables**:
- Research agent generates scorecard-relevant evidence
- Writer agent references scorecard findings
- Improved memo quality

---

### Phase 6: Direct Investment Scorecard (Week 4)

**Objective**: Create scorecard template for direct investments

**Tasks**:
- [ ] Design direct investment scoring dimensions
- [ ] Create `templates/scorecards/hypernova-direct-investment.yaml`
- [ ] Test with sample direct investment
- [ ] Document direct investment scorecard usage

**Deliverables**:
- Working direct investment scorecard
- Documentation

---

## Example Output

### Before (Without Scorecard)

```markdown
## 1. Executive Summary

We committed capital to Class 5 Global's debut fund in 2018, backing a team
focused on early-stage technology investments across emerging markets...

[Standard narrative without structured evaluation]
```

### After (With Scorecard)

```markdown
## 1. Executive Summary

We committed capital to Class 5 Global's debut fund in 2018, backing a team
focused on early-stage technology investments across emerging markets with
particular emphasis on the Middle East and North Africa (MENA) region...

---

| Empathy | Theory of Market | Ecosystem Imprint | Hustle |
|---------|------------------|-------------------|--------|
| 4/5 | 4/5 | 5/5 | 5/5 |
| Top 25% | Top 5% | Top 5% | Top 2% |
| The ongoing privilege to invest in competitive early-stage deals rests on deep, insight-driven empathy with founders... | The ability to anticipate the performance horizon of companies at the earliest stages... | The first few investment rounds of any company are put together through deeply formed interpersonal relationships... | Rising above the world of existing early-stage venture firms requires sweat-inducing levels of energy... |

Our investment thesis centered on the GP's strategic positioning in underserved
emerging markets, differentiated access through Finkelstein's UAE base, and the
team's early-stage investment discipline...
```

---

## Success Criteria

### Must-Haves
- [ ] Scorecard templates loadable from YAML
- [ ] Scorecard agent scores all dimensions with rationale
- [ ] Scorecard tables inserted at correct positions in sections
- [ ] Research agent uses scorecard context for queries
- [ ] Writer agent references scorecard findings
- [ ] Artifacts include scorecard JSON and MD
- [ ] Works for both LP commitments and direct investments

### Nice-to-Haves
- [ ] Visual scorecard (radar chart) generation
- [ ] Scorecard comparison across investments
- [ ] Confidence intervals for scores
- [ ] Manual score override capability
- [ ] Scorecard version tracking

---

## Risk Mitigation

### Risk 1: Over-Scoring Bias
**Issue**: LLM might default to high scores
**Mitigation**:
- Strict rubrics with clear criteria for each level
- Require evidence citation for scores >3
- Confidence indicators for low-data dimensions
- Percentile context to calibrate expectations

### Risk 2: Inconsistent Scoring
**Issue**: Same GP might get different scores on re-run
**Mitigation**:
- Temperature=0 for scoring agent
- Deterministic prompt structure
- Evidence-based scoring (not vibes)
- Save and version scorecard artifacts

### Risk 3: Scorecard Placement Conflicts
**Issue**: Tables might break section flow
**Mitigation**:
- Clear placement rules in template
- "after" placement as safe default
- Human review before publishing
- Preview mode for testing

### Risk 4: Template Maintenance Burden
**Issue**: Scorecards require ongoing refinement
**Mitigation**:
- Version control for templates
- Inheritance system for custom templates
- Clear documentation
- Feedback loop from usage

---

## Related Documentation

- `Format-Memo-According-to-Template-Input.md` - Outline system architecture
- `Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` - Main agent architecture
- `templates/outlines/README.md` - Outline documentation
- `templates/scorecards/README.md` - Scorecard documentation (to be created)

---

## Appendix: Complete Dimension Definitions

The full 12-dimension emerging manager scorecard is defined in detail in this document's "Scorecard Template Schema" section. Each dimension includes:

1. **Name and descriptions** (short + full)
2. **Evaluation guidance** (questions, evidence sources, red flags)
3. **Scoring rubric** (1-5 scale with detailed criteria)
4. **Placement rules** (which section, where in section)

This structure ensures consistent, thoughtful evaluation while making the firm's investment framework explicit and reusable.

---

## Changelog

**2025-11-27**:
- Document created based on Class 5 Global memo scorecard analysis
- Full 12-dimension emerging manager scorecard specified
- Implementation plan outlined across 6 phases
- Agent architecture designed for scorecard integration
