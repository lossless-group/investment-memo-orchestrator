---
title: Generate Investment Memo for Portfolio Company
lede: Create investment opportunity briefs that match Hypernova's analytical voice, format, and depth using AI-assisted generation with structured inputs and validation.
date_authored_initial_draft: 2025-11-16
date_authored_current_draft: 2025-11-16
date_authored_final_draft:
date_first_published:
date_last_updated:
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Sonnet 4.5)
category: Prompts
tags: [Workflow, Investment-Analysis, Content-Generation, Venture-Capital, AI-Assisted-Writing]
authors:
  - Michael Staton
  - Tugce Ergul
image_prompt: An investment analyst reviewing multiple data streams and documents, with charts, metrics, and strategic insights flowing into a polished investment memo. Visual elements include financial charts, technology diagrams, and a sense of rigorous analytical process.
date_created: 2025-11-16
date_modified: 2025-11-16
---

# Goal

Generate investment opportunity briefs for [[moc/Hypernova|Hypernova]] portfolio companies that maintain the firm's distinctive analytical voice, structural consistency, and investment rigor.

# Context

Hypernova's investment memos follow a specific format developed through deals like [[client-content/Hypernova/Portfolio/Aalo Atomics|Aalo Atomics]] (Series B, nuclear microreactors) and [[client-content/Hypernova/Portfolio/Star Catcher|Star Catcher]] (Pre-Series A, space power infrastructure). The memos balance:
- **Enthusiasm** for frontier technology and macro tailwinds
- **Skepticism** about execution risks and market uncertainties
- **Specificity** over generalization (exact metrics, named investors, dated milestones)

# Required Inputs

Before prompting the AI model, gather the following information:

## Company Fundamentals
- Company name, stage, headquarters location
- Founding team backgrounds (prior companies, exits, relevant experience)
- Origin story (lab spinout, second-time founders, strategic pivot)
- Current status (prototype, pilot, commercial, etc.)

## Market Intelligence
- Total Addressable Market (TAM) with sources
- Market growth drivers (technological, regulatory, economic)
- Current market size and projected growth (with timeframes)
- Target customer segments and use cases
- Competitive landscape and alternative approaches

## Technology & Product
- Core technology description (what it does, how it works)
- Key differentiators vs. alternatives
- Development stage (prototype, validated, production-ready)
- Technical risk factors and mitigation strategies
- IP position (patents filed/granted, FTO analysis)

## Traction Metrics
- Revenue (ARR, bookings, pilots)
- Letters of Intent (LOIs) - with caveats about non-binding nature
- Customer pipeline (named if possible, anonymized if sensitive)
- Technical milestones achieved
- Regulatory progress (if applicable)
- Partnership announcements

## Team Assessment
- CEO/Co-Founders: prior exits, relevant domain expertise
- Key executives: previous companies, specialized skills
- Board composition and advisor network
- Team gaps and hiring roadmap

## Deal Specifics
- Round type (Seed, Series A, Series B, etc.)
- Round size and pre-money valuation
- Lead investor(s) and key participants
- Hypernova allocation target
- Use of proceeds (specific, prioritized)
- Deal timeline and closing date

## Risk Analysis
- Technology risks (validation, scale-up, dependencies)
- Market risks (adoption cycles, competitive response)
- Regulatory risks (licensing, permitting, export controls)
- Execution risks (capital intensity, team gaps)
- For each risk: concrete mitigation strategies

## Strategic Context
- Alignment with Hypernova thesis
- Exit scenarios (strategic acquirers, public markets, timeframe)
- Key value inflection points (licensing, pilots, partnerships)

# Structural Template

Generate the memo using this exact section structure:

## Header Block
```
[Stage] Opportunity Brief
Date: [Month Day, Year]
by Michael Staton & Tugce Ergul

[Company Name] Investment Memo
```

## 1. Executive Summary
- **Opening statement**: One-sentence value proposition
- **Stage & Status**: Current funding round and traction
- **Focus**: Core technology/market category
- **HQ**: Location
- **Use of Proceeds**: Specific allocations

## 2. Business Overview
- Company mission and approach
- Target market(s) - prioritized
- Key differentiators (3-5 bullet points)
- Business model (hardware sales, SaaS, licensing, service contracts)
- Early commercial traction

## 3. Market Context & Macro Drivers
- Market size metrics (current and projected, with sources)
- Growth drivers (3-5 bullets, each with specific evidence)
- Regulatory/policy tailwinds (if applicable)
- Target customer economics and pain points

## 4. Technology & Product
- Product description (features, capabilities, form factor)
- Technical architecture (high-level, non-jargon)
- Development lineage (lab origins, key innovations)
- Current status (prototype, pilot, production)
- Competitive advantages

## 5. Traction & Investors
- Previous funding rounds (amounts, leads, dates)
- Select investor highlights (with portfolio examples)
- Commercial traction (LOIs, pilots, revenue)
- Notable partnerships or validations

## 6. Team
- CEO & Co-Founders (backgrounds, prior exits)
- Key executives (C-suite, VP-level with relevant expertise)
- Board and advisors (if notable)
- Team narrative: Why this team can execute

## 7. Deal Terms
- Round type and status
- Lead investor(s)
- Strategic investors
- Use of funds (prioritized bullets)

## 8. Risks
Numbered list (typically 4-6 risks), each with:
1. **Risk category**: Specific concern
   - **Mitigation**: Concrete mitigation strategy

## 9. Strategic Fit & Exit Scenarios
- Alignment with Hypernova thesis
- Potential strategic acquirers (with rationale)
- Public market pathway and timeline
- Key value drivers to monitor

## 10. Conclusion
- 2-3 sentence summary of investment case
- Emphasis on convergence of technology, timing, and team
- Forward-looking statement on company's positioning

# Style Guide

## Voice & Tone
- **Analytical, not promotional**: Present evidence, acknowledge uncertainties
- **Balanced**: Highlight strengths AND risks with equal rigor
- **Specific**: Use exact numbers, named entities, dates
- **Confident but measured**: Avoid superlatives ("revolutionary," "game-changing")

## Formatting Preferences
- **Bullets over paragraphs**: Maximize scannability
- **High information density**: Every sentence should add new information
- **Acronyms**: Spell out on first use, then abbreviate consistently
- **Sources cited**: Especially for market sizing ("WEF/McKinsey project...")
- **Dates included**: For all milestones, projections, and commitments

## Good vs. Bad Examples

### Market Sizing
✅ **Good**: "The addressable market for distributed industrial power solutions is projected to exceed $250 Billion by 2030, with SMRs capturing an estimated $50 Billion segment as data-center operators and heavy-industry customers seek off-grid solutions. [^1]"

❌ **Bad**: "The market opportunity is enormous and growing rapidly."

### Risk Assessment
✅ **Good**: "**LOI conversion risk**: $14B in signed LOIs are non-binding.
   - **Mitigation**: Stage-gated contracts and pilot-to-production paths."

❌ **Bad**: "There are some risks around customer adoption, but the team is experienced."

### Team Description
✅ **Good**: "**CTO**: Former Head of [MARVEL Program at Idaho National Lab](https://inl.gov/marvel/); previously led [Westinghouse eVinci microreactor](https://westinghousenuclear.com/energy-systems/evinci-microreactor/)."

❌ **Bad**: "The CTO has extensive experience in nuclear technology."

### Traction Metrics
✅ **Good**: "Aalo's Series A round was led by Valor Equity Partners ($30M), alongside Hitachi Ventures, Nucleation Capital, and Fifty Years VC."

❌ **Bad**: "The company has raised significant funding from top-tier investors."

# Prompt Template for AI Model

Use this structure when prompting:

```
You are an investment analyst at Hypernova, a venture capital firm focused on frontier technology that enables the next industrial infrastructure cycle. You are writing an opportunity brief for [Company Name]'s [Stage] round.

CONTEXT DOCUMENTS:
1. Review the attached reference memos (Aalo Atomics, Star Catcher) for structural template and voice
2. Match the analytical tone: balanced, specific, investor-focused (not promotional)
3. Follow the exact section structure provided in the template

RAW COMPANY DATA:
[Paste organized inputs from the Required Inputs checklist]

TASK:
Generate a complete investment memo following the structural template and style guide.

SPECIFIC EMPHASIS FOR THIS DEAL:
[Customize based on deal-specific priorities, e.g.:]
- Regulatory pathway is critical - deep dive on NRC licensing timeline
- Technical validation risk - need detailed mitigation in Risks section
- Market timing is key driver - emphasize macro tailwinds in Market Context

CONSTRAINTS:
- Include 4-6 specific risks, each with concrete mitigations
- All market sizing must include sources or caveats
- Maintain analytical balance (acknowledge execution challenges)
- Use bullet format for scannability (minimize paragraph blocks)
- Match information density of reference memos
- Acronyms spelled out on first use

OUTPUT REQUIREMENTS:
- Complete memo following all 10 sections
- 4-6 page target length (equivalent to reference memos)
- Ready for review by Michael Staton & Tugce Ergul
```

# Iterative Refinement Workflow

After initial generation, refine with targeted prompts:

## Pass 1: Structural Completeness
"Review the memo against the template. Are all required sections present? Flag any missing elements."

## Pass 2: Specificity Audit
"Review the memo for vague claims. Replace generalities with specific metrics, dates, and named entities. Flag any unsupported market sizing claims."

## Pass 3: Risk Rigor
"Strengthen the Risks section. Ensure each risk has a concrete mitigation strategy. Add any missing risk categories (technical, market, regulatory, execution, competitive)."

## Pass 4: Voice Consistency
"Compare tone and density to the reference memos. Adjust any sections that are too promotional or too sparse. Match the analytical, balanced voice."

## Pass 5: Source Validation
"Identify all market claims, growth projections, and competitive assertions. Add source citations or flag for manual verification."

# Validation Checklist

Before finalizing the memo, verify:

- [ ] Follows exact 10-section structure
- [ ] Includes specific metrics throughout (not vague "strong growth") along with citations.
- [ ] Risk section has 4-6 items, each with mitigation
- [ ] All acronyms spelled out on first use
- [ ] Market sizing includes sources or caveats along with citations.
- [ ] Team section includes prior companies/exits, including citations and or links.
- [ ] Deal terms section is complete and accurate, if Deal terms provided.  
- [ ] Deal terms section follows template, if Deal terms not provided.
- [ ] Maintains analytical tone (not promotional)
- [ ] Information density matches reference memos
- [ ] Clear investment recommendation in Conclusion
- [ ] No unsupported superlatives or generalizations
- [ ] Dates included for milestones and projections

# Edge Cases & Special Scenarios

## Earlier Stage (Seed/Pre-Seed)
- Emphasize team backgrounds and technical validation over traction
- Market sizing can be broader, but acknowledge uncertainty
- Risks section should include "market validation" as primary concern

## Later Stage (Series B+)
- Require revenue metrics and customer names (if not confidential)
- Deeper competitive analysis
- More detailed unit economics
- Clearer path to profitability or exit

## Deep Tech / Regulated Markets
- Add dedicated "Regulatory Pathway" subsection under Technology & Product
- Expand risk mitigation on technical validation and approval timelines
- Include government partnerships or non-dilutive funding (SBIR, grants)

## International Companies
- Note regulatory environment differences (EU vs. US)
- Address currency and cross-border considerations
- Identify strategic rationale for Hypernova geography

# Related Files

## Reference Memos
- `/Users/mpstaton/content-md/lossless/client-content/Hypernova/Files/Investment_Memo_Aalo_Atomics_SeriesB.pdf`
- `/Users/mpstaton/content-md/lossless/client-content/Hypernova/Files/Starcatcher Investment Memo.pdf`

## Potential Supporting Documents (to be created if needed)
- `Master-Investment-Memo-Template.md` - Fillable template with field descriptions
- `Hypernova-Voice-and-Style-Guide.md` - Expanded good/bad examples
- `Investment-Memo-Input-Checklist.md` - Data gathering worksheet
- `Validation-Criteria.md` - Quality review rubric

# Usage Notes

- **Garbage in, garbage out**: The quality of the generated memo depends entirely on the quality and completeness of the input data. Do not skip the Required Inputs checklist.
- **AI as draft, not final**: Always expect to iterate 3-5 times to match Hypernova voice and rigor.
- **Human judgment required**: AI cannot assess deal quality, only format the analysis. Investment thesis, risk assessment, and recommendation require human expertise.
- **Update reference library**: As new high-quality memos are written, add them to the reference set to improve AI training.
- **Maintain consistency**: Use the same structural template across all deals to enable comparative analysis.

---

**Outcome**: Investment memos that maintain Hypernova's analytical rigor, structural consistency, and distinctive voice while accelerating first-draft generation and ensuring comprehensive coverage of required analysis areas.
