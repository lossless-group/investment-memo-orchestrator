---
title: Format Memo According to Template Input
lede: Refactor the investment memo system to use YAML-based section templates that agents can reference for structure, guiding questions, and vocabulary.
date_authored_initial_draft: 2025-11-21
date_authored_current_draft: 2025-11-21
date_authored_final_draft:
date_first_published:
date_last_updated:
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Sonnet 4.5)
category: Architecture
tags: [Refactoring, Templates, YAML, Agent-Design, Workflow]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A modular system architecture with YAML configuration files feeding structured data into AI agents, showing clear separation between template definitions and agent logic. Visual elements include YAML file icons, agent nodes, and data flow arrows.
date_created: 2025-11-21
date_modified: 2025-11-21
---

# Format Memo According to Template Input

**Status**: Planned
**Date**: 2025-11-21
**Last Updated**: 2025-11-21
**Author**: AI Labs Team
**Related**: Multi-Agent-Orchestration-for-Investment-Memo-Generation.md, Improving-Memo-Output.md

## Executive Summary

This document specifies a refactoring initiative to move section definitions, guiding questions, and vocabulary from hardcoded markdown templates and agent logic into structured YAML configuration files. This will enable:

1. **Dynamic section generation** based on investment type (direct/fund) and mode (consider/justify)
2. **Consistent prompting** with guiding questions per section accessible to all agents
3. **Vocabulary control** with industry-specific terms and preferred language per section
4. **Easier template maintenance** without modifying agent code
5. **Multi-template support** for different firm styles or memo formats

The system will maintain backward compatibility with existing templates while gradually migrating to YAML-based configuration.

---

## Problem Statement

### Current Architecture Limitations

**Issue #1: Hardcoded Section Definitions**
- Section lists exist in multiple places:
  - `src/agents/writer.py:SECTION_ORDER` (hardcoded list)
  - `templates/memo-template-direct.md` (markdown headers)
  - `templates/memo-template-fund.md` (markdown headers)
- Adding a section requires editing 3+ files
- Section numbering must be manually synchronized
- No single source of truth for section structure

**Issue #2: No Centralized Guiding Questions**
- Writer agent has implicit knowledge of what each section should contain
- No structured guidance for what questions to answer per section
- Difficult to ensure consistency across memo generations
- New team members must reverse-engineer expectations from examples

**Issue #3: Vocabulary Scattered Across System**
- Style guide (`templates/style-guide.md`) contains general guidance
- Specific terminology preferences not codified
- No section-specific vocabulary control
- Agents may use inconsistent terminology

**Issue #4: Template Modifications Require Code Changes**
- Changing section order requires updating `SECTION_ORDER` constant
- Adding sections requires updating validation logic
- Renaming sections breaks file naming conventions
- Template changes coupled to agent logic

**Issue #5: No Mode-Specific Guidance**
- "Consider" vs "Justify" modes have different requirements
- Recommendation section should differ significantly by mode
- Currently handled implicitly in prompts, not declaratively

### Consequences

- **Maintenance burden**: Template changes require code changes
- **Inconsistency**: Different agents may interpret sections differently
- **Limited flexibility**: Cannot easily create custom memo formats
- **Poor documentation**: Section expectations not explicitly documented
- **Error-prone**: Manual synchronization between files leads to bugs

---

## Solution: YAML-Based Section Templates

### Core Concept

Replace hardcoded section definitions with structured YAML files that define:
- Section metadata (name, number, filename)
- Guiding questions (what to address in this section)
- Key vocabulary (preferred terms, phrases to use/avoid)
- Mode-specific variations (consider vs justify)
- Validation criteria (what makes a good section)

### Architecture Overview

```
templates/
├── sections/
│   ├── direct-investment-sections.yaml
│   ├── fund-commitment-sections.yaml
│   └── sections-schema.json (validation schema)
├── vocabulary/
│   ├── investment-vocabulary.yaml
│   ├── technical-vocabulary.yaml
│   └── style-preferences.yaml
└── memo-configs/
    ├── hypernova-direct-consider.yaml
    ├── hypernova-direct-justify.yaml
    ├── hypernova-fund-consider.yaml
    └── hypernova-fund-justify.yaml
```

**Data Flow**:
1. User specifies investment type + mode
2. System loads appropriate memo config YAML
3. Config references section definitions and vocabulary
4. Agents receive structured guidance for each section
5. Writer agent generates sections following YAML specifications
6. Validator checks against YAML criteria

---

## YAML Schema Design

### Section Definition Schema

**File**: `templates/sections/direct-investment-sections.yaml`

```yaml
# Direct Investment Section Definitions
# Used for startup/company investment analysis

metadata:
  template_type: "direct_investment"
  version: "1.0.0"
  description: "10-section structure for evaluating direct startup investments"
  date_created: "2025-11-21"
  compatible_modes: ["consider", "justify"]

sections:
  - number: 1
    name: "Executive Summary"
    filename: "01-executive-summary.md"
    target_length:
      min_words: 150
      max_words: 250
      ideal_words: 200

    description: |
      Concise overview of the investment opportunity, synthesizing key findings
      from all other sections. Written last, read first.

    guiding_questions:
      - "What problem does this company solve?"
      - "What is the solution and how is it differentiated?"
      - "Who are the founders and what relevant experience do they have?"
      - "What traction has been achieved to date?"
      - "What are the key risks and why are they manageable?"
      - "What is the investment recommendation (PASS/CONSIDER/COMMIT) and primary rationale?"

    mode_specific:
      consider:
        emphasis: "Objective assessment of opportunity with balanced risk discussion"
        recommendation_options: ["PASS", "CONSIDER", "COMMIT"]
        tone: "analytical, balanced"
      justify:
        emphasis: "Clear rationale for why investment was made with supporting evidence"
        recommendation_options: ["COMMIT"]
        tone: "confident, data-driven"

    key_vocabulary:
      preferred_terms:
        - "value proposition" (not "unique selling point")
        - "competitive advantage" (not "moat" unless technical context)
        - "go-to-market strategy" (not "GTM" on first use)
        - "traction" (not "progress" for metrics)

      required_elements:
        - Company name and brief description
        - Stage (Seed/Series A/B/C)
        - Investment type and mode
        - Specific traction metrics (ARR, customers, growth rate)
        - Clear recommendation with 1-sentence rationale

      avoid:
        - Promotional language: "revolutionary", "game-changing", "disruptive" without evidence
        - Vague claims: "significant traction", "strong team" without specifics
        - Undefined acronyms: Always define on first use
        - Speculation: "could potentially", "might be able to"

    validation_criteria:
      - "Length within target range (150-250 words)"
      - "Contains clear recommendation (PASS/CONSIDER/COMMIT)"
      - "Includes specific traction metrics (numbers, not adjectives)"
      - "Mentions founders by name with relevant credentials"
      - "Identifies 2-3 key risks"
      - "No promotional or speculative language"
      - "Reads as standalone summary without requiring other sections"

  - number: 2
    name: "Business Overview"
    filename: "02-business-overview.md"
    target_length:
      min_words: 400
      max_words: 600
      ideal_words: 500

    description: |
      Detailed description of what the company does, the problem it solves,
      its solution approach, business model, and current operational status.

    guiding_questions:
      - "What does the company do? (in plain language)"
      - "What specific problem are they solving for whom?"
      - "How does their solution work? (high-level, not deep technical)"
      - "What is the business model? (how do they make money?)"
      - "Who pays and why? (customer value proposition)"
      - "What is the current operational status? (live, beta, pilots, etc.)"
      - "What are the unit economics? (CAC, LTV, gross margin if available)"

    mode_specific:
      consider:
        emphasis: "Critical evaluation of business model viability and market fit"
        required_analysis:
          - "Business model sustainability assessment"
          - "Customer value proposition strength"
          - "Unit economics analysis (if data available)"
      justify:
        emphasis: "Clear articulation of why business model is compelling"
        required_analysis:
          - "Business model strengths that drove investment decision"
          - "Customer validation evidence"
          - "Path to profitability or scale"

    key_vocabulary:
      preferred_terms:
        - "business model" (not "revenue model" for broader concept)
        - "customer acquisition cost (CAC)" (define acronym)
        - "lifetime value (LTV)" (define acronym)
        - "gross margin" (not "gross profit margin" for conciseness)
        - "product-market fit" (not "PMF" on first use)

      required_elements:
        - Clear problem statement
        - Solution description (1-2 paragraphs)
        - Business model explanation
        - Current status (operational phase)
        - Pricing strategy (if known)

      section_structure:
        - "What they do: [1 sentence summary]"
        - "Problem they solve: [1-2 paragraphs]"
        - "Solution approach: [2-3 paragraphs]"
        - "Business model: [1-2 paragraphs]"
        - "Current status: [1 paragraph]"

    validation_criteria:
      - "Clear 1-sentence company description"
      - "Specific problem articulation with evidence of pain"
      - "Solution explanation understandable to non-technical reader"
      - "Business model includes who pays and how"
      - "Operational status explicitly stated"
      - "No undefined jargon or acronyms"

  - number: 3
    name: "Market Context"
    filename: "03-market-context.md"
    target_length:
      min_words: 500
      max_words: 700
      ideal_words: 600

    description: |
      Analysis of the total addressable market, market dynamics, competitive
      landscape, and company positioning within the market.

    guiding_questions:
      - "What is the total addressable market (TAM)? (with methodology)"
      - "How is the market growing? (CAGR, trends, drivers)"
      - "What are the key market dynamics? (regulatory, technological, behavioral)"
      - "Who are the direct competitors?"
      - "Who are the indirect competitors or alternative solutions?"
      - "How is the company differentiated from competitors?"
      - "What market position does the company occupy or target?"

    mode_specific:
      consider:
        emphasis: "Critical assessment of market size, growth, and competitive dynamics"
        required_analysis:
          - "TAM calculation with methodology (top-down or bottoms-up)"
          - "Market growth drivers with evidence"
          - "Competitive analysis with specific companies"
          - "Differentiation assessment (is it sustainable?)"
      justify:
        emphasis: "Market opportunity that justified investment with supporting data"
        required_analysis:
          - "TAM/SAM size that made market attractive"
          - "Market tailwinds that increase likelihood of success"
          - "Competitive advantages that position company for leadership"

    key_vocabulary:
      preferred_terms:
        - "total addressable market (TAM)" (define acronym)
        - "serviceable addressable market (SAM)" (define acronym)
        - "serviceable obtainable market (SOM)" (define acronym)
        - "compound annual growth rate (CAGR)" (define acronym)
        - "competitive advantage" (not "moat" unless technical moat)
        - "market dynamics" (not "market forces")

      required_elements:
        - TAM figure with source or methodology
        - Market growth rate (CAGR) with timeframe
        - 3-5 specific competitor names
        - Clear differentiation statement
        - Market positioning description

      avoid:
        - Vague market sizes: "billion-dollar market" without specifics
        - Unsupported growth claims: "rapidly growing" without CAGR
        - Generic competitors: "large incumbents" without names
        - Buzzwords: "blue ocean", "first mover advantage" without analysis

    validation_criteria:
      - "TAM stated with dollar figure and source/methodology"
      - "Market growth rate quantified (X% CAGR)"
      - "At least 3 specific competitors named"
      - "Differentiation explained with evidence, not just claims"
      - "Market dynamics supported by trends/data, not speculation"
      - "Competitive positioning clear and specific"

  - number: 4
    name: "Team"
    filename: "04-team.md"
    target_length:
      min_words: 400
      max_words: 600
      ideal_words: 500

    description: |
      Assessment of the founding team, key hires, advisors, investors,
      and overall team strengths and gaps.

    guiding_questions:
      - "Who are the founders? (names, titles, backgrounds)"
      - "What relevant experience do founders bring?"
      - "Have founders worked together before?"
      - "What domain expertise exists on the team?"
      - "What critical gaps exist in the team?"
      - "Who are the key hires beyond founders?"
      - "Who are the advisors and what value do they add?"
      - "Who are the investors and what does their involvement signal?"

    mode_specific:
      consider:
        emphasis: "Objective assessment of team strengths and gaps relative to opportunity"
        required_analysis:
          - "Founder-market fit assessment"
          - "Team completeness for execution"
          - "Critical gaps and hiring needs"
          - "Red flags or concerns about team"
      justify:
        emphasis: "Team capabilities that gave confidence in investment decision"
        required_analysis:
          - "Founder strengths that de-risked investment"
          - "Relevant experience that increases success probability"
          - "Team composition that enables execution"

    key_vocabulary:
      preferred_terms:
        - "founder-market fit" (not "founder fit")
        - "domain expertise" (not "industry experience" when technical knowledge matters)
        - "technical depth" (for engineering capabilities)
        - "go-to-market expertise" (for sales/marketing capabilities)
        - "operational experience" (for scaling/management capabilities)

      required_elements:
        - Founder names with titles
        - Previous companies/roles for each founder
        - Educational background (if relevant)
        - LinkedIn profile links (added by enrichment agent)
        - Key hires with roles
        - Advisors with credentials
        - Lead investors with fund names

      structure_template:
        - "Founders: [Name, title, background for each]"
        - "Strengths: [3-5 bullet points]"
        - "Gaps: [2-3 bullet points]"
        - "Key Hires: [if any]"
        - "Advisors: [if any]"
        - "Investors: [if known]"

    validation_criteria:
      - "All founders named with titles"
      - "Previous experience specified for each founder (company + role)"
      - "At least 3 specific strengths listed"
      - "At least 2 gaps or concerns identified (even in justify mode)"
      - "LinkedIn links present (added by enrichment agent)"
      - "No promotional language ('rockstar', 'world-class' without evidence)"

  - number: 5
    name: "Technology & Product"
    filename: "05-technology--product.md"
    target_length:
      min_words: 400
      max_words: 600
      ideal_words: 500

    description: |
      Overview of the product functionality, technology architecture,
      technical differentiation, and development roadmap.

    guiding_questions:
      - "What does the product do? (features and capabilities)"
      - "What is the core technology or technical approach?"
      - "What is technically differentiated or novel?"
      - "What is the technology stack? (if relevant)"
      - "What IP or proprietary technology exists?"
      - "What is the product development stage? (MVP, beta, GA, etc.)"
      - "What is on the product roadmap?"
      - "What are the technical risks?"

    mode_specific:
      consider:
        emphasis: "Critical assessment of technical feasibility and defensibility"
        required_analysis:
          - "Technical differentiation evaluation (is it real?)"
          - "Technology risk assessment"
          - "IP/moat analysis"
          - "Roadmap ambition vs team capability"
      justify:
        emphasis: "Technical capabilities that validated investment thesis"
        required_analysis:
          - "Technical innovation that creates competitive advantage"
          - "Product-market fit evidence"
          - "Technology scalability for growth"

    key_vocabulary:
      preferred_terms:
        - "product capabilities" (not "features" for strategic description)
        - "technology stack" (not "tech stack")
        - "intellectual property (IP)" (define acronym)
        - "minimum viable product (MVP)" (define acronym)
        - "generally available (GA)" (define acronym)
        - "technical moat" (acceptable when discussing defensibility)

      required_elements:
        - Product description (user-facing capabilities)
        - Core technology explanation (high-level)
        - Technical differentiation statement
        - Development stage
        - Key roadmap items (if known)

      avoid:
        - Excessive technical jargon without explanation
        - Claims of "AI-powered" without explaining the AI
        - "Proprietary algorithm" without any detail
        - "Patent-pending" without describing what's novel

    validation_criteria:
      - "Product description understandable to non-technical reader"
      - "Core technology explained at appropriate level"
      - "Technical differentiation articulated with specifics"
      - "Development stage explicitly stated"
      - "Technical claims supported by evidence, not just assertions"
      - "Roadmap items concrete, not vague aspirations"

  - number: 6
    name: "Traction & Milestones"
    filename: "06-traction--milestones.md"
    target_length:
      min_words: 400
      max_words: 600
      ideal_words: 500

    description: |
      Quantitative evidence of product-market fit, growth metrics,
      key customer wins, and major milestones achieved.

    guiding_questions:
      - "What revenue has been generated? (ARR, MRR, or total)"
      - "How many customers do they have?"
      - "What is the customer growth rate?"
      - "Who are the marquee customers? (logos)"
      - "What are the usage metrics? (DAU, MAU, transactions, etc.)"
      - "What growth has been achieved? (MoM, YoY)"
      - "What major milestones have been reached? (launches, partnerships, etc.)"
      - "What pilots or trials are in progress?"

    mode_specific:
      consider:
        emphasis: "Objective assessment of traction sufficiency for stage"
        required_analysis:
          - "Traction evaluation vs stage expectations"
          - "Growth rate assessment (accelerating or decelerating?)"
          - "Customer quality and retention analysis"
          - "Gaps in traction data and concerns"
      justify:
        emphasis: "Traction that validated product-market fit and investment decision"
        required_analysis:
          - "Traction metrics that exceeded expectations"
          - "Growth trajectory that indicated scale potential"
          - "Customer validation that de-risked investment"

    key_vocabulary:
      preferred_terms:
        - "annual recurring revenue (ARR)" (define acronym)
        - "monthly recurring revenue (MRR)" (define acronym)
        - "daily active users (DAU)" (define acronym)
        - "monthly active users (MAU)" (define acronym)
        - "customer acquisition" (not "customer acquisition" first use)
        - "retention rate" (not "churn" for positive framing when good)
        - "net revenue retention (NRR)" (define acronym)

      required_elements:
        - Revenue figure (ARR/MRR or total revenue)
        - Customer count
        - Growth rate (MoM or YoY with %)
        - 2-3 customer logos (if available)
        - Key milestones with dates

      critical:
        - "NEVER use vague terms: 'significant traction', 'strong growth'"
        - "ALWAYS quantify: '$500K ARR', '50 customers', '30% MoM growth'"
        - "If metrics unavailable, state explicitly: 'Revenue data not available'"
        - "Distinguish between pilots and paying customers"

    validation_criteria:
      - "At least one revenue metric (ARR/MRR/total) with dollar amount"
      - "Customer count specified numerically"
      - "Growth rate quantified (X% MoM/YoY)"
      - "At least 2 customer names or logos (if public)"
      - "Milestones include dates"
      - "NO vague language ('strong traction', 'significant customers')"
      - "Missing data explicitly stated, not glossed over"

  - number: 7
    name: "Funding & Terms"
    filename: "07-funding--terms.md"
    target_length:
      min_words: 300
      max_words: 500
      ideal_words: 400

    description: |
      Details on the current fundraise, valuation, proposed terms,
      use of funds, and funding history.

    guiding_questions:
      - "How much are they raising?"
      - "At what valuation? (pre-money or post-money)"
      - "What are the proposed terms? (equity stake, preferences, rights)"
      - "How will funds be used? (allocation breakdown)"
      - "What is the funding history? (previous rounds, amounts, investors)"
      - "What is the current runway?"
      - "When is the next fundraise expected?"

    mode_specific:
      consider:
        emphasis: "Critical assessment of valuation reasonableness and terms"
        required_analysis:
          - "Valuation vs comparables and stage"
          - "Terms assessment (investor-friendly or founder-friendly?)"
          - "Use of funds alignment with priorities"
          - "Runway sufficiency to next milestone"
      justify:
        emphasis: "Investment terms and rationale for participation"
        required_analysis:
          - "Valuation rationale (why price was acceptable)"
          - "Terms that made investment attractive"
          - "Use of funds that will drive value creation"

    key_vocabulary:
      preferred_terms:
        - "pre-money valuation" (not "valuation" ambiguously)
        - "post-money valuation" (specify which)
        - "equity stake" (not "ownership" for specific percentage)
        - "liquidation preference" (not "preference" alone)
        - "pro-rata rights" (not "pro rata")
        - "use of funds" (not "use of proceeds")

      required_elements:
        - Round size (dollar amount)
        - Valuation (pre or post-money)
        - Our proposed investment amount
        - Equity stake we'd receive
        - Use of funds breakdown
        - Previous funding rounds summary

      critical:
        - "If terms not available, state: 'Investment terms not yet available'"
        - "NEVER include terms that are uncertain or speculative"
        - "Distinguish between target raise and committed amount"

    validation_criteria:
      - "Round size specified in dollars"
      - "Valuation stated (pre or post-money specified)"
      - "Proposed investment amount stated"
      - "Use of funds includes allocation breakdown"
      - "Previous rounds summarized with amounts"
      - "Missing information explicitly noted, not implied"

  - number: 8
    name: "Risks & Mitigations"
    filename: "08-risks--mitigations.md"
    target_length:
      min_words: 400
      max_words: 600
      ideal_words: 500

    description: |
      Comprehensive identification of investment risks with
      assessment of mitigations, both existing and needed.

    guiding_questions:
      - "What are the market risks? (demand, competition, timing)"
      - "What are the execution risks? (team, product, operations)"
      - "What are the technical risks? (technology, scalability, security)"
      - "What are the financial risks? (unit economics, burn rate, fundraising)"
      - "What are the regulatory or legal risks?"
      - "For each risk, what mitigations exist or are planned?"
      - "Which risks are most concerning and why?"
      - "What would need to be true for this to fail?"

    mode_specific:
      consider:
        emphasis: "Balanced risk assessment with critical evaluation of mitigations"
        required_analysis:
          - "Identification of 5-7 key risks across categories"
          - "Assessment of mitigation adequacy (real vs aspirational)"
          - "Evaluation of which risks are dealbreakers"
          - "Honest assessment of risk tolerance required"
      justify:
        emphasis: "Risk acknowledgment with evidence of risk mitigation or acceptance rationale"
        required_analysis:
          - "Key risks that were considered in investment decision"
          - "Mitigations that reduced risk to acceptable level"
          - "Risks accepted and why (upside justifies downside)"

    key_vocabulary:
      preferred_terms:
        - "market risk" (not "market uncertainty")
        - "execution risk" (not "operational risk" for pre-scale companies)
        - "technical risk" (not "technology risk")
        - "regulatory risk" (not "compliance risk" for future regulations)
        - "mitigation" (not "mitigation strategy" for conciseness)

      required_elements:
        - 5-7 risks across multiple categories
        - Mitigation for each risk (even if "None implemented")
        - Assessment of mitigation adequacy
        - Identification of most critical risk

      structure_template:
        - "Market Risks: [2-3 risks with mitigations]"
        - "Execution Risks: [2-3 risks with mitigations]"
        - "Technical Risks: [1-2 risks with mitigations]"
        - "Financial Risks: [1-2 risks with mitigations]"
        - "Most Critical Risk: [1 risk with detailed assessment]"

      avoid:
        - Generic risks: "competitive risk", "market risk" without specifics
        - Aspirational mitigations: "Will hire CFO" (when not done)
        - Dismissive language: "This risk is unlikely" without evidence
        - Promotional framing: "Risks are minimal"

    validation_criteria:
      - "At least 5 specific risks identified"
      - "Risks span multiple categories (market, execution, technical, financial)"
      - "Each risk has mitigation statement (even if 'None')"
      - "Mitigations assessed as actual or aspirational"
      - "Most critical risk explicitly identified"
      - "No dismissive or promotional language"

  - number: 9
    name: "Investment Thesis"
    filename: "09-investment-thesis.md"
    target_length:
      min_words: 400
      max_words: 600
      ideal_words: 500

    description: |
      Synthesis of the investment case, articulating why this
      opportunity is compelling or why it should be passed.

    guiding_questions:
      - "What is the core investment thesis? (1-2 sentences)"
      - "Why is this opportunity compelling? (bull case)"
      - "What could go right? (upside scenarios)"
      - "What are the key risk factors? (bear case)"
      - "What could go wrong? (downside scenarios)"
      - "How does this fit our investment strategy?"
      - "What is the return potential and path to liquidity?"
      - "Why now? (timing considerations)"

    mode_specific:
      consider:
        emphasis: "Balanced investment case with both bull and bear scenarios"
        required_analysis:
          - "Clear articulation of investment thesis"
          - "Bull case with upside scenarios"
          - "Bear case with downside scenarios"
          - "Fit with fund strategy assessment"
          - "Return potential analysis"
      justify:
        emphasis: "Investment rationale that drove decision with supporting evidence"
        required_analysis:
          - "Thesis that justified investment"
          - "Why opportunity was too compelling to pass"
          - "How investment aligns with fund strategy"
          - "Return potential that made risk acceptable"

    key_vocabulary:
      preferred_terms:
        - "investment thesis" (not "investment rationale" for core argument)
        - "bull case" (acceptable for upside scenario)
        - "bear case" (acceptable for downside scenario)
        - "return potential" (not "return expectations" to avoid forward-looking issues)
        - "liquidity path" (not "exit" for M&A or IPO)
        - "strategic fit" (for portfolio alignment)

      required_elements:
        - 1-2 sentence core thesis
        - Bull case (3-4 points)
        - Bear case (3-4 points)
        - Fund strategy fit explanation
        - Return potential discussion

      avoid:
        - Overly promotional: "This will be a category winner"
        - Dismissive of risks: "Risks are minimal given..."
        - Vague thesis: "Strong team in large market"
        - Missing bear case (even in justify mode)

    validation_criteria:
      - "Core thesis stated in 1-2 sentences"
      - "Bull case includes 3+ specific points"
      - "Bear case includes 3+ specific points"
      - "Fund strategy fit explicitly discussed"
      - "Return potential addressed"
      - "Balanced tone (analytical, not promotional)"

  - number: 10
    name: "Recommendation"
    filename: "10-recommendation.md"
    target_length:
      min_words: 150
      max_words: 300
      ideal_words: 200

    description: |
      Clear investment recommendation with supporting rationale
      and next steps.

    guiding_questions:
      - "What is the recommendation? (PASS/CONSIDER/COMMIT)"
      - "What is the 1-sentence rationale?"
      - "What evidence most strongly supports this recommendation?"
      - "What concerns remain?"
      - "What next steps are required?"
      - "What would change the recommendation?"

    mode_specific:
      consider:
        recommendation_options: ["PASS", "CONSIDER", "COMMIT"]
        pass:
          rationale_focus: "Critical issues that make investment unattractive"
          required_elements:
            - "Primary reason for pass"
            - "What would need to change to reconsider"
        consider:
          rationale_focus: "Promise and concerns that warrant deeper diligence"
          required_elements:
            - "What is compelling about opportunity"
            - "What needs to be validated in next phase"
            - "Specific diligence questions to answer"
        commit:
          rationale_focus: "Strong conviction factors that justify investment"
          required_elements:
            - "Primary drivers of conviction"
            - "Why now is the right time"
            - "Next steps for closing investment"

      justify:
        recommendation_options: ["COMMIT"]
        commit:
          rationale_focus: "Clear explanation of why investment was made"
          required_elements:
            - "Key factors that drove decision"
            - "Evidence that validated thesis"
            - "Alignment with fund strategy"

    key_vocabulary:
      preferred_terms:
        - "PASS" (all caps, not "Pass" or "pass")
        - "CONSIDER" (all caps)
        - "COMMIT" (all caps, not "Invest" or "Recommend")
        - "rationale" (not "reasoning" for formal recommendation)
        - "due diligence" (not "DD" or "diligence" alone)

      required_format:
        opening: "Recommendation: [PASS/CONSIDER/COMMIT]"
        rationale: "[1-2 sentence rationale]"
        supporting_evidence: "[2-3 paragraphs with specific points]"
        next_steps: "[Bullet list of actions]"

      critical:
        - "Recommendation MUST be one of: PASS, CONSIDER, COMMIT"
        - "Rationale MUST be 1-2 sentences max"
        - "No hedging language: 'probably should', 'might be good to'"
        - "Next steps MUST be specific and actionable"

    validation_criteria:
      - "Recommendation stated explicitly (PASS/CONSIDER/COMMIT)"
      - "Rationale is 1-2 sentences"
      - "Supporting evidence includes specific points from memo"
      - "Next steps are actionable (not vague)"
      - "Tone matches recommendation (PASS = critical, COMMIT = confident)"
      - "No hedging or ambiguous language"

# Cross-Section Requirements
cross_section_requirements:
  citation_consistency:
    description: "Citations must follow Obsidian style across all sections"
    format: "[^1], [^2], [^3]"
    spacing: "One space before citation after punctuation"

  length_balance:
    description: "Sections should be roughly proportional"
    guideline: "No section should be 2x length of average section"

  terminology_consistency:
    description: "Use same terms throughout memo"
    examples:
      - "If 'Series A' in one section, not 'Series A round' in another"
      - "If 'ARR' defined once, use 'ARR' not 'annual recurring revenue' after"
      - "Consistent company name (not 'Acme' and 'Acme Corp' interchangeably)"

  narrative_flow:
    description: "Sections should build on each other logically"
    sequence:
      - "Executive Summary references all sections"
      - "Business Overview establishes foundation"
      - "Market Context expands to broader environment"
      - "Team/Technology/Traction provide evidence"
      - "Funding/Risks/Thesis synthesize analysis"
      - "Recommendation concludes with clarity"
```

### Vocabulary Configuration Schema

**File**: `templates/vocabulary/investment-vocabulary.yaml`

```yaml
# Investment Memo Vocabulary Guide
# Preferred terms, phrases to avoid, and style rules

metadata:
  version: "1.0.0"
  description: "Standard vocabulary for professional investment memos"
  date_created: "2025-11-21"

# Financial Terms
financial:
  preferred:
    - term: "annual recurring revenue (ARR)"
      definition: "Yearly value of recurring revenue contracts"
      first_use: "annual recurring revenue (ARR)"
      subsequent: "ARR"

    - term: "monthly recurring revenue (MRR)"
      definition: "Monthly value of recurring revenue contracts"
      first_use: "monthly recurring revenue (MRR)"
      subsequent: "MRR"

    - term: "customer acquisition cost (CAC)"
      definition: "Total sales and marketing cost to acquire one customer"
      first_use: "customer acquisition cost (CAC)"
      subsequent: "CAC"

    - term: "lifetime value (LTV)"
      definition: "Total revenue expected from a customer over relationship"
      first_use: "lifetime value (LTV)"
      subsequent: "LTV"

  avoid:
    - term: "revenue"
      instead: "Specify ARR, MRR, or total revenue"
      reason: "Ambiguous whether recurring or one-time"

    - term: "sales"
      instead: "Use 'revenue' or 'bookings'"
      reason: "'Sales' can mean revenue or sales team"

# Market Terms
market:
  preferred:
    - term: "total addressable market (TAM)"
      definition: "Total market demand for a product/service"
      first_use: "total addressable market (TAM)"
      subsequent: "TAM"

    - term: "compound annual growth rate (CAGR)"
      definition: "Annual growth rate over multiple years"
      first_use: "compound annual growth rate (CAGR)"
      subsequent: "CAGR"

  avoid:
    - term: "huge market"
      instead: "Provide TAM with $ figure and source"
      reason: "Vague and unprofessional"

    - term: "rapidly growing"
      instead: "Specify CAGR percentage"
      reason: "Subjective and imprecise"

# Team Terms
team:
  preferred:
    - term: "founder-market fit"
      definition: "Alignment between founder background and market opportunity"
      usage: "Assess whether founders uniquely positioned to solve this problem"

    - term: "domain expertise"
      definition: "Deep knowledge in specific industry or technical area"
      usage: "Use when discussing specialized knowledge"

  avoid:
    - term: "rockstar team"
      instead: "Describe specific credentials and experience"
      reason: "Promotional and meaningless"

    - term: "world-class"
      instead: "Cite specific achievements that demonstrate quality"
      reason: "Overused and subjective"

# Product Terms
product:
  preferred:
    - term: "minimum viable product (MVP)"
      definition: "Simplest version that delivers core value"
      first_use: "minimum viable product (MVP)"
      subsequent: "MVP"

    - term: "product-market fit"
      definition: "Evidence that product satisfies strong market demand"
      usage: "Require traction metrics as evidence, not assertion"

  avoid:
    - term: "revolutionary"
      instead: "Describe specific technical innovation"
      reason: "Promotional, used for everything"

    - term: "game-changing"
      instead: "Explain impact with evidence"
      reason: "Hyperbolic without substance"

# Recommendation Terms
recommendation:
  required:
    - "PASS" # Critical issues prevent investment
    - "CONSIDER" # Warrants deeper diligence
    - "COMMIT" # Conviction to invest

  forbidden:
    - "Maybe" # Ambiguous
    - "Likely" # Not decisive
    - "Strong Consider" # Not a defined option
    - "Soft Pass" # Either pass or don't

# Phrases to Avoid (General)
avoid_phrases:
  promotional:
    - phrase: "unique opportunity"
      reason: "Overused, everything is called unique"

    - phrase: "disruptive"
      reason: "Buzzword, define specific disruption"

    - phrase: "thought leader"
      reason: "Vague, cite specific contributions"

    - phrase: "passionate team"
      reason: "Expected, focus on competence not passion"

  vague:
    - phrase: "significant traction"
      reason: "Quantify with specific metrics"

    - phrase: "strong growth"
      reason: "Provide percentage and timeframe"

    - phrase: "experienced team"
      reason: "Specify years, previous companies, roles"

    - phrase: "large market"
      reason: "Provide TAM with dollar figure"

  speculative:
    - phrase: "could potentially"
      reason: "Anything 'could' happen, state what is likely"

    - phrase: "might be able to"
      reason: "Hedge language reduces credibility"

    - phrase: "has the potential to"
      reason: "Focus on what they have achieved"

# Writing Style Rules
style_rules:
  tone:
    - "Professional and analytical"
    - "Confident without being promotional"
    - "Critical without being dismissive"
    - "Balanced presentation of strengths and weaknesses"

  voice:
    - "Active voice preferred: 'The team built' not 'was built by'"
    - "Present tense for current state: 'The company has $2M ARR'"
    - "Past tense for completed actions: 'The founders raised $1M in 2023'"

  numbers:
    - "Spell out numbers one through nine"
    - "Use numerals for 10 and above"
    - "Use numerals for all metrics and financial figures"
    - "Use dollar signs: $5M not 5M dollars"
    - "Use percentages: 30% not thirty percent"

  abbreviations:
    - "Define all acronyms on first use"
    - "Use acronyms on subsequent uses for conciseness"
    - "Exception: Very common terms (CEO, IPO, VC) need not be defined"

  citations:
    - "Obsidian-style: [^1], [^2], [^3]"
    - "Place after punctuation with space: 'text. [^1]'"
    - "Multiple citations: 'text. [^1] [^2]' with spaces"
    - "Citation format: [^1]: YYYY, MMM DD. [Title](URL). Published: YYYY-MM-DD"
```

### Memo Configuration Schema

**File**: `templates/memo-configs/hypernova-direct-consider.yaml`

```yaml
# Hypernova Capital - Direct Investment - Consider Mode
# Configuration for prospective analysis of startup investments

metadata:
  firm: "Hypernova Capital"
  investment_type: "direct"
  mode: "consider"
  version: "1.0.0"
  date_created: "2025-11-21"

# Reference to section definitions
sections_source: "../sections/direct-investment-sections.yaml"

# Reference to vocabulary
vocabulary_sources:
  - "../vocabulary/investment-vocabulary.yaml"
  - "../vocabulary/technical-vocabulary.yaml"
  - "../vocabulary/style-preferences.yaml"

# Firm-specific overrides
firm_preferences:
  tone: "analytical, balanced, not promotional"
  recommendation_philosophy: "High bar for COMMIT, use CONSIDER liberally"
  emphasis:
    - "Team and founder-market fit"
    - "Product-market fit evidence"
    - "Capital efficiency"

  critical_questions:
    - "Why this team?"
    - "Why this market?"
    - "Why now?"
    - "Why us?" # Why should Hypernova invest?

# Mode-specific configuration
mode_config:
  recommendation_threshold:
    pass: "Critical issues prevent investment"
    consider: "Interesting but needs deeper diligence"
    commit: "Strong conviction, all key questions answered positively"

  risk_emphasis: "high" # Thorough risk discussion required

  required_diligence_items:
    - "Reference calls with at least 2 customers"
    - "Reference calls with all founders' previous managers"
    - "Technical architecture review"
    - "Unit economics deep dive"
    - "Market sizing validation"

# Section-specific overrides for this config
section_overrides:
  executive_summary:
    target_length:
      ideal_words: 175 # Shorter than default 200
    emphasis_additions:
      - "Why Hypernova is right partner (if COMMIT)"

  team:
    emphasis_additions:
      - "Assess founder coachability and self-awareness"
      - "Evaluate founder dynamics if multiple founders"

  risks_mitigations:
    minimum_risks: 7 # More than default 5
    emphasis_additions:
      - "What keeps founders up at night?"

# Report format preferences
format:
  header_include: true # Include firm logo/trademark
  footer_text: "Hypernova Capital - Confidential Investment Analysis"
  page_numbers: true
  table_of_contents: false # Short enough to not need TOC
```

---

## Implementation Plan

### Phase 1: Schema Design & Validation (Week 1-2)

**Objective**: Create and validate YAML schemas for sections, vocabulary, and memo configs

**Tasks**:

1. **Create Section Definition Schemas**
   - [ ] Write `templates/sections/direct-investment-sections.yaml` (complete with all 10 sections)
   - [ ] Write `templates/sections/fund-commitment-sections.yaml` (all 10 sections)
   - [ ] Create JSON schema for validation: `templates/sections/sections-schema.json`
   - [ ] Write unit tests for schema validation

2. **Create Vocabulary Schemas**
   - [ ] Write `templates/vocabulary/investment-vocabulary.yaml`
   - [ ] Write `templates/vocabulary/technical-vocabulary.yaml`
   - [ ] Write `templates/vocabulary/style-preferences.yaml`
   - [ ] Create JSON schema: `templates/vocabulary/vocabulary-schema.json`

3. **Create Memo Configuration Schemas**
   - [ ] Write `templates/memo-configs/hypernova-direct-consider.yaml`
   - [ ] Write `templates/memo-configs/hypernova-direct-justify.yaml`
   - [ ] Write `templates/memo-configs/hypernova-fund-consider.yaml`
   - [ ] Write `templates/memo-configs/hypernova-fund-justify.yaml`
   - [ ] Create JSON schema: `templates/memo-configs/memo-config-schema.json`

4. **Schema Validation Testing**
   - [ ] Create `tests/test_schemas.py`
   - [ ] Test all YAML files parse correctly
   - [ ] Test schema validation catches errors
   - [ ] Test circular reference detection

**Deliverables**:
- 3 section YAML files (direct, fund, + schema)
- 4 vocabulary YAML files (investment, technical, style, + schema)
- 5 memo config YAML files (4 configs + schema)
- Unit tests for validation
- Documentation for schema structure

---

### Phase 2: YAML Loader Utility (Week 2-3)

**Objective**: Create utility module to load and merge YAML configurations

**Tasks**:

1. **Create YAML Loader Module**
   - [ ] Create `src/template_loader.py`
   - [ ] Implement `load_section_definitions(investment_type: str) -> SectionDefinitions`
   - [ ] Implement `load_vocabulary() -> VocabularyGuide`
   - [ ] Implement `load_memo_config(firm, type, mode) -> MemoConfig`
   - [ ] Implement configuration merging logic (overrides)
   - [ ] Add caching for performance

2. **Create Data Classes**
   - [ ] Create `src/schemas/section_schema.py` with dataclasses:
     - `SectionDefinition`
     - `SectionMetadata`
     - `GuidingQuestions`
     - `KeyVocabulary`
     - `ValidationCriteria`
   - [ ] Create `src/schemas/vocabulary_schema.py`:
     - `VocabularyTerm`
     - `VocabularyCategory`
     - `StyleRule`
   - [ ] Create `src/schemas/memo_config_schema.py`:
     - `MemoConfig`
     - `FirmPreferences`
     - `SectionOverrides`

3. **Testing**
   - [ ] Unit tests for loader functions
   - [ ] Test configuration merging (overrides work correctly)
   - [ ] Test error handling (missing files, invalid YAML)
   - [ ] Performance tests (caching works)

**Deliverables**:
- Working YAML loader module
- Complete dataclass schemas
- Unit tests passing
- Performance benchmarks

---

### Phase 3: Writer Agent Integration (Week 3-4)

**Objective**: Refactor writer agent to use YAML-based section definitions

**Tasks**:

1. **Update Writer Agent**
   - [ ] Modify `src/agents/writer.py:write_sections_individually()`
   - [ ] Replace hardcoded `SECTION_ORDER` with dynamic loading
   - [ ] Load section definitions from YAML based on investment type
   - [ ] Generate prompts from YAML guiding questions
   - [ ] Include vocabulary guidance in prompts
   - [ ] Maintain backward compatibility with existing templates

2. **Prompt Generation from YAML**
   - [ ] Create `src/prompts/section_prompt_builder.py`
   - [ ] Implement `build_section_prompt(section_def, state, vocabulary) -> str`
   - [ ] Include guiding questions in prompt
   - [ ] Include key vocabulary in prompt
   - [ ] Include validation criteria in prompt
   - [ ] Add mode-specific emphasis

3. **Testing**
   - [ ] Test section loading for both investment types
   - [ ] Test prompt generation includes guiding questions
   - [ ] Test vocabulary integration in prompts
   - [ ] Compare output quality: YAML-based vs hardcoded
   - [ ] Regression tests (existing memos still generate correctly)

**Deliverables**:
- Refactored writer agent using YAML
- Prompt builder module
- Tests demonstrating quality maintenance
- Side-by-side comparison of outputs

---

### Phase 4: Validator Agent Integration (Week 4-5)

**Objective**: Enhance validator to use YAML validation criteria

**Tasks**:

1. **Update Validator Agent**
   - [ ] Modify `src/agents/validator.py:validate_memo()`
   - [ ] Load validation criteria from YAML
   - [ ] Check each section against YAML criteria
   - [ ] Generate detailed feedback based on YAML rules
   - [ ] Score sections using YAML-defined standards

2. **Validation Prompt Enhancement**
   - [ ] Update validation prompts to include YAML criteria
   - [ ] Add specific checks from vocabulary (avoid phrases, etc.)
   - [ ] Include length validation from YAML targets
   - [ ] Check terminology consistency across sections

3. **Testing**
   - [ ] Test validation against YAML criteria
   - [ ] Test feedback generation references YAML rules
   - [ ] Test length validation
   - [ ] Test vocabulary compliance checking
   - [ ] Regression tests (existing validation still works)

**Deliverables**:
- Enhanced validator using YAML criteria
- More specific validation feedback
- Tests demonstrating improved validation
- Documentation of validation rules

---

### Phase 5: CLI & Configuration Selection (Week 5-6)

**Objective**: Allow users to specify memo configuration via CLI

**Tasks**:

1. **Update CLI Arguments**
   - [ ] Modify `src/main.py` argument parser
   - [ ] Add `--memo-config` flag to specify config file
   - [ ] Add `--firm` flag to select firm configs
   - [ ] Default to Hypernova configs if not specified
   - [ ] Load memo config early in workflow

2. **Configuration Resolution**
   - [ ] Implement config resolution logic:
     - CLI `--memo-config` path → use directly
     - CLI `--firm` name → resolve to config file
     - Company data JSON `memo_config` → use if present
     - Default: `hypernova-{type}-{mode}.yaml`
   - [ ] Validate config file exists and is valid
   - [ ] Add helpful error messages for missing configs

3. **State Integration**
   - [ ] Add `memo_config: MemoConfig` to `MemoState`
   - [ ] Load config in `create_initial_state()`
   - [ ] Pass config to writer and validator agents
   - [ ] Save config reference in `state.json` artifact

4. **Testing**
   - [ ] Test CLI config selection
   - [ ] Test default config behavior
   - [ ] Test custom config loading
   - [ ] Test error handling for invalid configs
   - [ ] End-to-end test with custom config

**Deliverables**:
- CLI support for config selection
- Configuration resolution logic
- State integration complete
- User documentation for config usage

---

### Phase 6: Section File Naming (Week 6)

**Objective**: Use YAML-defined filenames for section artifacts

**Tasks**:

1. **Update Section Saving**
   - [ ] Modify `src/artifacts.py:save_section_artifact()`
   - [ ] Use `section_definition.filename` from YAML
   - [ ] Update reassembly logic to load in YAML-defined order
   - [ ] Handle legacy filenames for backward compatibility

2. **Update Enrichment Agents**
   - [ ] Update all enrichment agents to load section definitions
   - [ ] Use YAML filenames when loading sections
   - [ ] Update `src/utils.py:get_section_filename_map()` helper

3. **Migration Support**
   - [ ] Create migration script for old → new filenames
   - [ ] Add compatibility layer for old filenames
   - [ ] Document filename changes

4. **Testing**
   - [ ] Test new filename generation
   - [ ] Test backward compatibility with old filenames
   - [ ] Test enrichment agents with new filenames
   - [ ] End-to-end test generates correct filenames

**Deliverables**:
- YAML-driven filename generation
- Backward compatibility maintained
- Migration documentation
- All tests passing

---

### Phase 7: Multi-Firm Support (Week 7)

**Objective**: Enable multiple firms to use system with custom configs

**Tasks**:

1. **Create Example Firm Configs**
   - [ ] Create `templates/memo-configs/example-firm-direct-consider.yaml`
   - [ ] Document how to create firm-specific configs
   - [ ] Create config template generator script

2. **Firm-Specific Vocabulary**
   - [ ] Allow firm configs to reference custom vocabulary files
   - [ ] Create example: `templates/vocabulary/example-firm-vocabulary.yaml`
   - [ ] Implement vocabulary merging (firm overrides + base)

3. **Documentation**
   - [ ] Create `docs/CUSTOM_MEMO_CONFIGS.md`
   - [ ] Document YAML schema for all config types
   - [ ] Provide examples of common customizations
   - [ ] Create troubleshooting guide

4. **Testing**
   - [ ] Test with 2+ different firm configs
   - [ ] Test vocabulary overrides work correctly
   - [ ] Test section order customization
   - [ ] Test length target customization

**Deliverables**:
- Multi-firm support working
- Example configs for multiple firms
- Complete documentation
- Testing across configurations

---

### Phase 8: Template Deprecation (Week 8)

**Objective**: Deprecate old markdown templates in favor of YAML

**Tasks**:

1. **Migration Path**
   - [ ] Mark `templates/memo-template-direct.md` as deprecated
   - [ ] Mark `templates/memo-template-fund.md` as deprecated
   - [ ] Add deprecation warnings to code
   - [ ] Document migration for any custom templates

2. **Remove Template Dependencies**
   - [ ] Remove template loading logic from writer agent
   - [ ] Use only YAML for section generation
   - [ ] Keep style guide as separate reference

3. **Cleanup**
   - [ ] Archive old templates to `templates/archive/`
   - [ ] Update all documentation references
   - [ ] Remove deprecated code paths

4. **Validation**
   - [ ] Verify system works without old templates
   - [ ] Run full test suite
   - [ ] Generate sample memos with YAML only
   - [ ] Confirm quality maintained

**Deliverables**:
- Old templates deprecated
- System fully YAML-driven
- Documentation updated
- Quality verified

---

## Benefits of YAML-Based Templates

### For Developers

1. **Separation of Concerns**
   - Template structure separate from agent logic
   - Easier to modify sections without touching code
   - Reduced coupling between components

2. **Type Safety**
   - Dataclasses provide type checking
   - Schema validation catches errors early
   - Better IDE support and autocomplete

3. **Testability**
   - Configuration changes don't require code changes
   - Easier to test with different configs
   - Validation logic centralized and testable

4. **Maintainability**
   - Single source of truth for section structure
   - Changes propagate automatically to all agents
   - Versioned configurations (track template changes)

### For Users

1. **Consistency**
   - All agents use same section definitions
   - Guiding questions ensure comprehensive coverage
   - Vocabulary enforcement maintains professional tone

2. **Transparency**
   - Section expectations explicitly documented
   - Easy to understand what each section should contain
   - Validation criteria clear and actionable

3. **Flexibility**
   - Easy to customize for different firms
   - Can create specialized memo types without code
   - Experiment with different structures

4. **Quality**
   - Guiding questions improve section completeness
   - Vocabulary rules prevent common mistakes
   - Validation criteria ensure consistent standards

### For Firms

1. **Customization**
   - Create firm-specific memo formats
   - Override vocabulary for house style
   - Adjust section emphasis and length

2. **Branding**
   - Integrate with brand configurations
   - Consistent tone and terminology
   - Professional output matching firm standards

3. **Scaling**
   - Support multiple memo types per firm
   - Share configurations across team
   - Version control for template changes

4. **Compliance**
   - Ensure required sections present
   - Enforce disclosure requirements
   - Audit trail for template versions

---

## Migration Strategy

### Backward Compatibility

**Phase 1-3**: Dual Support
- Both YAML and markdown templates work
- Gradually migrate agents to YAML
- No breaking changes for existing users

**Phase 4-6**: YAML Preferred
- YAML is default, templates deprecated
- Warnings for template usage
- Migration documentation available

**Phase 7-8**: YAML Only
- Templates archived
- Full YAML-driven system
- All agents refactored

### Migration Checklist

**For Existing Users**:
- [ ] Review new YAML configs in `templates/`
- [ ] Test memo generation with default configs
- [ ] Customize firm configs if needed
- [ ] Verify output quality maintained
- [ ] Archive old template customizations

**For Developers**:
- [ ] Update agent code to load YAML configs
- [ ] Remove hardcoded section lists
- [ ] Update tests for YAML-based system
- [ ] Document YAML schema
- [ ] Create migration scripts if needed

---

## Success Criteria

### Must Have

- [ ] All 10 sections defined in YAML for both investment types
- [ ] Writer agent generates sections from YAML definitions
- [ ] Validator agent uses YAML validation criteria
- [ ] Guiding questions appear in agent prompts
- [ ] Vocabulary guidance enforced
- [ ] CLI supports config selection
- [ ] Backward compatibility maintained during transition
- [ ] Documentation complete
- [ ] Quality maintained or improved vs hardcoded templates

### Nice to Have

- [ ] Multiple firm configs available
- [ ] Config template generator tool
- [ ] Visual config editor
- [ ] Config version migration tool
- [ ] Config validation in CI/CD
- [ ] Performance benchmarks (YAML loading time)

---

## Technical Considerations

### Performance

**YAML Loading**:
- Load time: ~10ms per YAML file
- Caching: Load once per memo generation
- Impact: Negligible (< 0.1% of total time)

**Memory Usage**:
- YAML configs: ~50KB total
- Parsed structures: ~200KB in memory
- Impact: Negligible for modern systems

### Validation

**Schema Validation**:
- JSON schema for YAML structure
- Validates on load (fail fast)
- Helpful error messages for malformed YAML

**Circular References**:
- Check for circular config references
- Prevent infinite recursion in overrides
- Clear error messages

### Versioning

**Config Versions**:
- Each YAML has `version` field
- Track breaking changes
- Support migration between versions

**Compatibility**:
- Semantic versioning for configs
- Major version = breaking changes
- Minor version = additions
- Patch version = fixes

---

## Future Enhancements

### Dynamic Section Generation

Allow agents to dynamically add/remove sections based on company data:

```yaml
conditional_sections:
  - name: "International Expansion"
    condition: "company.countries > 1"
    insert_after: "Market Context"

  - name: "Regulatory Strategy"
    condition: "company.industry in ['fintech', 'healthcare', 'edu-tech']"
    insert_after: "Business Overview"
```

### Interactive Config Builder

Web-based tool to create memo configs visually:
- Select firm template
- Customize sections (add/remove/reorder)
- Override vocabulary
- Preview generated config
- Export YAML

### Config Analytics

Track which configs are used and memo quality:
- Most common configurations
- Quality scores by config
- Section completion rates
- Vocabulary compliance metrics

### AI-Generated Configs

Use LLM to generate configs from natural language:

```bash
python generate-config.py \
  --prompt "Create a memo config for early-stage SaaS companies with emphasis on product-market fit and capital efficiency"
```

---

## Related Documentation

- `Multi-Agent-Orchestration-for-Investment-Memo-Generation.md` - Main architecture
- `Improving-Memo-Output.md` - Section improvement features
- `templates/brand-configs/README.md` - Brand configuration guide
- `CLAUDE.md` - Developer guide

---

## Changelog

**2025-11-21**: Document created with comprehensive plan for YAML-based template system
