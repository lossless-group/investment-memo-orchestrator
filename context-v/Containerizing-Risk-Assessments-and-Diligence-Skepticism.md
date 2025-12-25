# Containerizing Risk Assessments and Diligence Skepticism

**Status**: Specification
**Priority**: HIGH
**Created**: 2025-11-28
**Triggered By**: LLM outputs heavily weighted toward risk analysis, undermining memo utility for syndication and LP review

---

## Problem Statement

LLM probabilistic reasoning naturally gravitates toward risk assessment and skeptical analysis. When generating investment memos, Claude and other models produce extensive content on:

- Identified risks and mitigations
- Due diligence questions and priorities
- Hanging uncertainties and data gaps
- Skeptical assessments of claims
- Conditional recommendations ("CONSIDER with caveats")

This analytical thoroughness is intellectually rigorous but **undermines the business utility of investment memos** across their actual use cases.

---

## Investment Memo Lifecycle and Audience Analysis

Investment memos serve fundamentally different purposes at different stages:

### Stage 1: Internal Discussion (Pre-Decision)
**Audience**: Investment Committee, Partners
**Purpose**: Facilitate decision-making
**Risk content utility**: HIGH - skepticism helps surface blind spots
**Current output fitness**: Good (risks useful for debate)

### Stage 2: Decision Preservation (Post-Decision)
**Audience**: Future self, firm records, legal documentation
**Purpose**: Document rationale and conviction at time of investment
**Risk content utility**: LOW - decision is made; excessive doubt looks indecisive
**Current output fitness**: Poor (reads like "we weren't sure")

### Stage 3: Syndication and Co-Investment
**Audience**: Other VCs, angels, strategic investors
**Purpose**: Build conviction, attract co-investors
**Risk content utility**: HARMFUL - signals weakness, invites lowball terms
**Current output fitness**: Poor (undermines deal positioning)

### Stage 4: LP Review and Fundraising
**Audience**: Limited Partners, prospective LPs, fund administrators
**Purpose**: Demonstrate investment judgment and conviction
**Risk content utility**: HARMFUL - LPs want to see decisiveness, not hand-wringing
**Current output fitness**: Poor (creates impression of uncertain decision-making)

**Conclusion**: The memo most useful for Stage 1 (internal discussion) is actively harmful for Stages 2-4. We need content separation.

---

## The LLM Behavioral Pattern

Large language models, particularly in analytical contexts, exhibit predictable patterns:

### 1. Risk Enumeration
Models naturally generate lists of risks because:
- Training data includes analyst reports, due diligence frameworks, and risk matrices
- "Thorough analysis" in training examples typically includes risk sections
- Probabilistic reasoning surfaces uncertainties as first-class outputs

**Example symptom:**
```markdown
### Critical Gaps and Organizational Risk
- Domain Expertise Misalignment: Neither founder has disclosed direct experience...
- Organizational Capacity vs. Execution Scope: A two-person team is addressing...
- Regulatory and Compliance Leadership Absence: ...represents material execution risk...
```

### 2. Conditional Language
Models hedge recommendations with extensive caveats:
- "CONSIDER with conditions"
- "Investment should be contingent on..."
- "Revisit after validation of..."

**Example symptom:**
```markdown
## Recommendations for Investment Diligence

**Priority Questions:**
1. Has Sava engaged a Chief Compliance Officer...?
2. Has Sava assembled an advisory board...?
3. Who is leading engineering...?
```

### 3. Skeptical Framing
Models emphasize uncertainty over conviction:
- "The absence of X is notable"
- "This gap is material"
- "Investors should prioritize understanding..."

**Result**: Memos read like due diligence checklists rather than conviction documents.

---

## Proposed Solution: Dual-Output Architecture

### Content Separation Model

**Critical Insight**: LLMs have been trained on analytical content that includes risk assessment and skepticism. If we try to suppress this during memo writing, the skepticism *leaks* into the conviction content anyway. The model needs to externalize its chain-of-thought skepticism *before* it can focus on conviction.

**Solution**: Diligence comes *before* section writing, not after. The model expresses all risks, gaps, and questions first (cathartic), then writes the conviction-focused memo with skepticism already externalized.

```
output/{Company}-v0.0.x/
├── 0-deck-sections/               # Deck/dataroom analysis
│   ├── 01-executive-summary.md
│   └── ...
│
├── 1-research/                    # Web research outputs
│   ├── research.json
│   └── research.md
│
├── 2-diligence/                   # EXPRESS ALL SKEPTICISM HERE FIRST
│   ├── risk-assessment.md         # Full risk enumeration
│   ├── due-diligence-questions.md # Hanging questions, things to verify
│   ├── team-gaps-analysis.md      # Missing capabilities, hiring needs
│   ├── competitive-threats.md     # Competitive concerns
│   ├── valuation-notes.md         # Pricing sensitivity, negotiation leverage
│   └── deal-breaker-checklist.md  # Conditions that would kill the deal
│
├── 3-sections/                    # NOW write conviction-focused memo
│   ├── 01-executive-summary.md    # (skepticism already externalized)
│   ├── 04-team.md
│   └── 08-risks--mitigations.md   # Bounded: 3-5 risks with mitigations
│
├── 4-final-draft.md               # Assembled from 3-sections/ only
└── state.json
```

**Pipeline Flow**:
```
Deck Analysis → Research → Diligence (cathartic) → Sections (conviction) → Final Draft
     ↓              ↓            ↓                       ↓                    ↓
  0-deck/      1-research/   2-diligence/           3-sections/         4-final-draft.md
                              (internal)             (exportable)
```

This ordering acknowledges that the LLM's probabilistic reasoning will pursue risk assessment regardless—we just give it a proper place to do so *before* asking for conviction-focused output.

### Processing Model

**Phase 1: Generate with Full Analysis**
Allow the LLM to generate comprehensive analysis including all risks, skepticism, and diligence questions. Don't suppress this—it's valuable analytical work.

**Phase 2: Triage and Containerize**
A post-processing agent separates content into two buckets:

| Bucket | Content Type | Destination |
|--------|--------------|-------------|
| **Conviction** | Strengths, thesis, team credentials, market opportunity, strategic rationale | `2-sections/` → Export |
| **Skepticism** | Risks, gaps, diligence questions, conditional recommendations, hanging uncertainties | `3-diligence/` → Internal only |

**Phase 3: Bounded Risk Inclusion**
The public memo (`4-final-draft.md`) includes a `Risks & Mitigations` section, but it is:
- **Bounded**: Limited to 3-5 key risks, not exhaustive enumeration
- **Mitigated**: Each risk paired with mitigation strategy
- **Confident**: Framed as "acknowledged and addressed" rather than "concerning"

---

## Content Guidelines by Section

### Sections That Should Be Conviction-Focused (2-sections/)

| Section | Conviction Content | Remove/Containerize |
|---------|-------------------|---------------------|
| Executive Summary | Investment thesis, key strengths, recommendation | Risk caveats, conditional language |
| Team | Credentials, relevant experience, founder-market fit | "Gaps analysis", missing roles, skeptical assessments |
| Technology & Product | Differentiation, technical moat, product vision | Unproven claims, technical debt concerns |
| Traction & Milestones | Achievements, growth metrics, validation signals | "Pre-revenue" emphasis, unmet milestones |
| Investment Thesis | Why we invested, strategic rationale, upside potential | Downside scenarios, failure modes |
| Recommendation | COMMIT with conviction, deployment rationale | Conditional language, "revisit after X" |

### Sections That Absorb Bounded Risk Content

| Section | Appropriate Risk Content |
|---------|-------------------------|
| Risks & Mitigations | 3-5 key risks with explicit mitigations, framed as "acknowledged and managed" |
| Market Context | Competitive dynamics (framed as opportunity, not threat) |

### Content That Goes to 3-diligence/ (Internal Only)

- Exhaustive risk enumeration beyond the bounded 3-5
- Due diligence questions and investigation priorities
- Hanging uncertainties and unverified claims
- Team gaps and missing capabilities analysis
- Skeptical competitive positioning analysis
- Conditional recommendation logic and thresholds
- Deal-breaker scenarios and kill criteria
- Pricing/valuation concerns and negotiation leverage

---

## Implementation Approach

### Option A: Post-Processing Separation Agent

Create a new agent that runs after section generation:

```python
def diligence_separator_agent(state: MemoState) -> dict:
    """
    Separates conviction content from skepticism content.

    For each section:
    1. Identify risk/skepticism content blocks
    2. Extract to 3-diligence/ files
    3. Rewrite section with conviction focus
    4. Preserve analytical depth in internal files
    """
```

**Pros**: Clean separation, preserves all analysis
**Cons**: Additional API calls, potential context loss

### Option B: Prompt-Level Separation

Modify section prompts to generate two outputs:

```
Generate two versions of the {section_name} section:

VERSION A (CONVICTION - for export):
- Lead with strengths and thesis
- Acknowledge risks briefly, pair with mitigations
- Use confident, decisive language
- Recommendation without caveats

VERSION B (DILIGENCE - internal only):
- Full risk enumeration
- Due diligence questions
- Hanging uncertainties
- Skeptical assessment
```

**Pros**: Single API call per section
**Cons**: Longer prompts, may reduce quality of each version

### Option C: Section-Specific Prompts

Different prompts for conviction sections vs. diligence sections:

- Sections 1-7, 9-10: Conviction-focused prompts (suppress risk enumeration)
- Section 8 (Risks): Bounded risk prompt (3-5 with mitigations)
- New Section 11 (internal): Diligence/skepticism collection point

**Pros**: Simplest implementation
**Cons**: Risk content may leak into conviction sections anyway

### Recommended: Hybrid Approach

1. **Prompt modification**: Add conviction-focused instructions to all section prompts
2. **Bounded risk section**: Limit Section 8 to 3-5 risks with mitigations
3. **Separate diligence pass**: Run a dedicated diligence agent that generates internal analysis
4. **Never export 3-diligence/**: Export scripts only touch 2-sections/

---

## Prompt Language Modifications

### Current Prompt Pattern (Problematic)

```
Write the {section_name} section...
- Be analytical, not promotional or dismissive
- Include specific metrics and evidence
```

### Revised Prompt Pattern (Conviction-Focused)

```
Write the {section_name} section for an investment memo that will be shared
with co-investors and reviewed by Limited Partners.

FRAMING:
- This memo documents our conviction and investment rationale
- Lead with strengths, credentials, and strategic opportunity
- Acknowledge challenges briefly but pair each with mitigation
- Use confident, decisive language befitting a firm that has committed capital
- Avoid extensive risk enumeration, conditional recommendations, or "things to investigate"
- The audience assumes we've done our diligence; the memo demonstrates our conclusions

DO NOT INCLUDE:
- Exhaustive risk lists (keep to 3-5 key risks max, with mitigations)
- Due diligence questions or "priority investigation items"
- Conditional language like "CONSIDER with caveats" or "revisit after X"
- Gap analysis or "missing capabilities" emphasis
- Skeptical framing of team, market, or product

If you identify risks, uncertainties, or diligence questions during your analysis,
note them mentally but do not include them in this output. A separate internal
analysis document will capture that content.
```

---

## Export Behavior

### Current Behavior

`export-branded.py` exports `4-final-draft.md` which contains all sections including potentially risk-heavy content.

### Proposed Behavior

1. `4-final-draft.md` assembled from `2-sections/` only (conviction content)
2. `5-internal-analysis.md` assembled from `3-diligence/` only (never exported)
3. Export scripts explicitly exclude `3-diligence/` and `5-internal-analysis.md`
4. Version control can include both, but firm distribution uses exports only

---

## File Naming Convention for Diligence Content

```
3-diligence/
├── 00-deal-summary.md           # Quick internal reference
├── 01-risk-assessment.md        # Full risk enumeration
├── 02-due-diligence-questions.md # Things we still need to verify
├── 03-team-gaps.md              # Missing capabilities, hiring needs
├── 04-competitive-threats.md    # Competitive concerns not for LP eyes
├── 05-valuation-analysis.md     # Pricing sensitivity, negotiation notes
├── 06-deal-breakers.md          # Conditions that would kill the deal
└── 07-follow-up-items.md        # Post-close monitoring priorities
```

---

## Testing and Validation

### Before/After Comparison

For each generated memo, assess:

1. **Risk density**: Count risk-related paragraphs in exportable sections
2. **Conditional language**: Count instances of "if", "should X be validated", "contingent on"
3. **Conviction signals**: Count instances of "we believe", "demonstrates", "positions the company"
4. **LP readability**: Would an LP reading this feel we were decisive or uncertain?

### Target Metrics

| Metric | Current (Problematic) | Target (Conviction-Focused) |
|--------|----------------------|---------------------------|
| Risk paragraphs in 2-sections/ | 15-25 | 5-8 (bounded to Section 8) |
| Conditional language instances | 20+ | <5 |
| "Gap" or "missing" mentions | 10+ | <3 |
| Due diligence questions | 10+ | 0 (moved to 3-diligence/) |

---

## Related Documentation

- `context-vigilance/Disambiguation-Management-across-Agents.md` - Entity confusion prevention
- `context-vigilance/Anti-Hallucination-Fact-Checker-Agent.md` - Fact verification
- `templates/style-guide.md` - Should be updated with conviction-focused language

---

## Implementation Priority

1. **Immediate**: Update section prompts with conviction-focused language
2. **Short-term**: Create `3-diligence/` output structure and separation logic
3. **Medium-term**: Build dedicated diligence agent for internal analysis
4. **Ongoing**: Refine based on LP and co-investor feedback on memo quality

---

## Summary

The core insight is that **analytical thoroughness and business utility are in tension** for investment memos. The solution is not to suppress the LLM's analytical capabilities, but to **containerize skepticism** in internal documents while ensuring exportable memos project conviction and decisiveness appropriate for their downstream audiences.

LLMs will always want to enumerate risks—our job is to give that content a proper home that doesn't undermine the firm's positioning with LPs and co-investors.
