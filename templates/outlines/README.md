# Investment Memo Outlines

This directory contains **content structure definitions** (outlines) for investment memos. Outlines define:

- **Section structure**: What sections to include and in what order
- **Guiding questions**: What the LLM should address in each section
- **Vocabulary**: Preferred terms, phrases to avoid, style rules
- **Validation criteria**: How to evaluate section quality

## Distinction: Outlines vs Brand Configs

| Concept | Purpose | Location | Controls |
|---------|---------|----------|----------|
| **Outline** | Content structure | `templates/outlines/` | Sections, questions, vocabulary |
| **Brand Config** | Visual styling | `templates/brand-configs/` | Colors, fonts, logos, CSS |

**Outlines** define WHAT the memo says (content structure and guidance).
**Brand configs** define HOW the memo looks (visual styling).

## Default Outlines

### Direct Investment (`direct-investment.yaml`)
For evaluating startup/company investments.

**10 sections:**
1. Executive Summary
2. Business Overview
3. Market Context
4. Team
5. Technology & Product
6. Traction & Milestones
7. Funding & Terms
8. Risks & Mitigations
9. Investment Thesis
10. Recommendation

**Compatible modes:** `consider` (prospective analysis), `justify` (retrospective justification)

### Fund Commitment (`fund-commitment.yaml`)
For evaluating LP commitments to VC funds.

**10 sections:**
1. Executive Summary
2. GP Background & Track Record
3. Fund Strategy & Thesis
4. Portfolio Construction
5. Value Add & Differentiation
6. Track Record Analysis
7. Fee Structure & Economics
8. LP Base & References
9. Risks & Mitigations
10. Recommendation

**Compatible modes:** `consider` (prospective analysis), `justify` (retrospective justification)

## Outline Structure

Each outline YAML file contains:

```yaml
metadata:
  outline_type: "direct_investment" | "fund_commitment"
  version: "1.0.0"
  description: "Brief description"
  compatible_modes: ["consider", "justify"]

# Global vocabulary (applies to all sections)
vocabulary:
  financial:
    preferred: [...]
    avoid: [...]
  phrases_to_avoid: [...]
  style_rules: {...}

# Section definitions
sections:
  - number: 1
    name: "Executive Summary"
    filename: "01-executive-summary.md"
    target_length:
      min_words: 150
      max_words: 250
      ideal_words: 200

    description: "What this section covers"

    # GUIDING QUESTIONS: Tell LLM what to address
    guiding_questions:
      - "What problem does this company solve?"
      - "What is the solution?"
      # ... more questions

    # SECTION-SPECIFIC VOCABULARY
    section_vocabulary:
      preferred_terms: [...]
      required_elements: [...]
      avoid: [...]

    # MODE-SPECIFIC GUIDANCE
    mode_specific:
      consider:
        emphasis: "Objective assessment"
        required_analysis: [...]
      justify:
        emphasis: "Clear rationale"
        required_analysis: [...]

    # VALIDATION CRITERIA
    validation_criteria:
      - "Length within target range"
      - "Contains clear recommendation"
      # ... more criteria
```

## Custom Outlines

Create firm-specific or custom outlines in `templates/outlines/custom/`:

```yaml
# templates/outlines/custom/hypernova-direct-consider.yaml
metadata:
  firm: "Hypernova Capital"
  investment_type: "direct"
  mode: "consider"
  extends: "../direct-investment.yaml"  # Inherits from default

# Override/extend vocabulary
vocabulary:
  hypernova_preferred:
    - term: "founder-market fit"
      emphasis: "Critical for our thesis"

# Firm-specific philosophy
firm_preferences:
  tone: "Analytical, balanced"
  critical_questions:
    - "Why this team?"
    - "Why now?"
    - "Why Hypernova?"

# Override specific sections
section_overrides:
  executive_summary:
    target_length:
      ideal_words: 175  # Shorter than default 200

  team:
    guiding_questions_add:
      - "Assess founder coachability"
    emphasis: "Founder-market fit is critical"
```

## Usage

### With CLI

```bash
# Default outline (uses direct-investment.yaml or fund-commitment.yaml based on type)
python -m src.main "Avalanche"

# Custom firm outline
python -m src.main "Avalanche" --outline hypernova-direct-consider
```

### In Company Data Files

Specify outline in `data/{CompanyName}.json`:

```json
{
  "type": "direct",
  "mode": "consider",
  "outline": "hypernova-direct-consider",
  "description": "Company description..."
}
```

## How Agents Use Outlines

### Writer Agent
The writer agent loads the outline and uses:
- **Guiding questions** to construct prompts for each section
- **Section vocabulary** to guide terminology and style
- **Target length** to constrain output
- **Mode-specific guidance** to adjust tone and emphasis

Example prompt generation:
```python
def build_section_prompt(section_def, state):
    prompt = f"""
    Write the {section_def['name']} section.

    Target length: {section_def['target_length']['ideal_words']} words

    Address these guiding questions:
    {'\n'.join(f"- {q}" for q in section_def['guiding_questions'])}

    Vocabulary guidance:
    Preferred terms: {section_def['section_vocabulary']['preferred_terms']}
    Avoid: {section_def['section_vocabulary']['avoid']}
    """
    return prompt
```

### Validator Agent
The validator loads the outline and uses:
- **Validation criteria** to check section quality
- **Length targets** to ensure appropriate sizing
- **Required elements** to verify completeness
- **Vocabulary rules** to check compliance

### Citation Enrichment Agent
Uses the outline's:
- **Citation format** rules from vocabulary
- **Section structure** to process sections in order

## Validation

Use the JSON schema to validate outline files:

```bash
# Install a YAML/JSON validator
pip install pyjsonschema

# Validate an outline
jsonschema -i templates/outlines/direct-investment.yaml templates/outlines/sections-schema.json
```

## Creating Custom Outlines

### Option 1: Extend Default
Inherit from default outline and override specific sections:

```yaml
metadata:
  extends: "../direct-investment.yaml"

section_overrides:
  team:
    guiding_questions_add:
      - "Additional question for team section"
```

### Option 2: From Scratch
Define all sections independently (not recommended unless structure is very different).

## Best Practices

1. **Start with defaults**: Use `direct-investment.yaml` or `fund-commitment.yaml` as-is
2. **Create custom for firm differences**: Only create custom outlines when firm has specific needs
3. **Keep vocabulary embedded**: Don't split vocabulary into separate files
4. **Be specific in questions**: Guiding questions should be detailed and actionable
5. **Test validation**: Ensure validation criteria are checkable
6. **Version carefully**: Use semantic versioning (major.minor.patch)

## Outline Inheritance

Custom outlines can inherit from default outlines using the `extends` field:

1. **Load base outline** (e.g., `direct-investment.yaml`)
2. **Merge vocabulary** (custom additions + base vocabulary)
3. **Apply section overrides** (modify specific sections)
4. **Result**: Complete outline with customizations

## Future Enhancements

- **Dynamic sections**: Add/remove sections based on company data
- **Conditional questions**: Show questions based on data availability
- **Multi-language**: Support for non-English memos
- **Interactive builder**: Web UI to create custom outlines
- **Config analytics**: Track which outlines produce highest quality

## Related Documentation

- `../brand-configs/README.md` - Brand configuration for visual styling
- `/CLAUDE.md` - Main developer guide
- `/context-vigilance/Format-Memo-According-to-Template-Input.md` - Design document

---

**Version**: 1.0.0
**Last Updated**: 2025-11-21
**Status**: Ready for integration with agent system
