# Commands Cheat Sheet

Complete reference for all CLI commands in the Investment Memo Orchestrator.

> **Prerequisites**: Always activate the virtual environment first:
> ```bash
> source .venv/bin/activate
> ```

---

## Table of Contents

- [Main Workflow](#main-workflow)
- [Section Improvement](#section-improvement)
- [Corrections & Rewrites](#corrections--rewrites)
- [Assembly & Validation](#assembly--validation)
- [Export Commands](#export-commands)
- [Scorecard Generation](#scorecard-generation)
- [Environment Variables](#environment-variables)

---

## Main Workflow

### Generate Investment Memo

The primary command to generate a complete investment memo.

```bash
python -m src.main "Company Name"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `company_name` | positional | (required) | Name of the company to analyze |
| `--type` | `direct` \| `fund` | `direct` | Investment type |
| `--mode` | `consider` \| `justify` | `consider` | Memo mode |
| `--resume` | flag | - | Resume from last checkpoint |
| `--version` | string | - | Specific version to resume (use with `--resume`) |

#### Investment Types

- **`direct`**: Direct startup investment (default)
- **`fund`**: LP commitment to a venture fund

#### Memo Modes

- **`consider`**: Prospective analysis for potential investment - recommendation is PASS/CONSIDER/COMMIT
- **`justify`**: Retrospective justification for existing investment - recommendation is always COMMIT with rationale

#### Examples

```bash
# Basic usage (direct investment, prospective analysis)
python -m src.main "Acme Corp"

# Fund commitment, retrospective justification
python -m src.main "Sequoia Capital Fund XV" --type fund --mode justify

# Direct investment with retrospective justification
python -m src.main "Stripe" --type direct --mode justify

# Interactive mode (prompts for company name)
python -m src.main

# Resume interrupted workflow
python -m src.main "Acme Corp" --resume

# Resume specific version
python -m src.main "Acme Corp" --resume --version v0.0.3
```

#### Company Data File (Optional)

Create `data/{CompanyName}.json` to provide additional context:

```json
{
  "type": "direct",
  "mode": "justify",
  "description": "AI-powered logistics platform",
  "url": "https://acmecorp.com",
  "stage": "Series B",
  "deck": "data/AcmeCorp-deck.pdf",
  "trademark_light": "https://acmecorp.com/logo-light.svg",
  "trademark_dark": "https://acmecorp.com/logo-dark.svg",
  "notes": "Focus on unit economics and competitive moat"
}
```

---

## Section Improvement

### Improve Section (Perplexity Research)

Improve a specific section using Perplexity Sonar Pro for real-time research and automatic citation addition.

```bash
python -m cli.improve_section "Company" "Section Name"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `target` | positional | (required) | Company name or path to artifact directory |
| `section` | positional | (required) | Section name to improve |
| `--version` | string | latest | Specific version (e.g., `v0.0.2`) |

#### Examples

```bash
# Improve Team section (uses latest version)
python -m cli.improve_section "Avalanche" "Team"

# Improve specific version
python -m cli.improve_section "Avalanche" "Market Context" --version v0.0.1

# Use direct path to artifact directory
python -m cli.improve_section output/Avalanche-v0.0.1 "Technology & Product"

# Fund memo sections
python -m cli.improve_section "Sequoia Fund" "GP Background & Track Record"
```

#### Notes

- Requires `PERPLEXITY_API_KEY` in `.env`
- Automatically adds inline citations (`[^1]`, `[^2]`)
- Automatically reassembles `4-final-draft.md` after improvement
- Section names must match files in `2-sections/` directory

---

### Improve Team Section (Deep Research)

Specialized team research using a sequential approach: LinkedIn → Website → Individual deep dives.

```bash
python -m cli.improve_team_section "Company"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `target` | positional | (required) | Company name or path to artifact directory |
| `--version` | string | latest | Specific version (e.g., `v0.0.2`) |

#### Examples

```bash
# Deep team research (uses latest version)
python -m cli.improve_team_section "Acme Corp"

# Specific version
python -m cli.improve_team_section "Acme Corp" --version v0.0.1
```

#### Notes

- Uses 3-phase research: Primary sources → Individual deep dives → Synthesis
- Better for team sections that need comprehensive background research
- Requires `PERPLEXITY_API_KEY` in `.env`

---

### Refocus Section

Repair a section when web research is thin or noisy. Especially useful for `justify` mode memos.

```bash
python -m cli.refocus_section "Company" "Section Name"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `target` | positional | (required) | Company name or path to artifact directory |
| `section` | positional | (required) | Section name to refocus |
| `--version` | string | latest | Specific version |

#### Examples

```bash
# Refocus Recommendation section
python -m cli.refocus_section "WatershedVC" "Recommendation"

# Refocus using direct path
python -m cli.refocus_section output/WatershedVC-v0.0.1 "Risks & Mitigations"
```

#### Notes

- Uses internal materials (deck, existing sections) as primary source
- Web research is treated as optional signal only
- Ideal for entity disambiguation issues (e.g., multiple companies with same name)

---

## Corrections & Rewrites

### Rewrite Key Info

Apply YAML-based corrections across multiple sections. Use when a key fact needs to be updated throughout the memo.

```bash
python -m cli.rewrite_key_info --corrections path/to/corrections.yaml
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--corrections` | path | (required) | Path to corrections YAML file |
| `--preview` | flag | - | Preview changes without saving (dry run) |
| `--output-mode` | `new_version` \| `in_place` | from YAML | Override output mode |
| `--source-version` | string | from YAML | Override source version |
| `--source-path` | path | - | Direct path to source artifact directory |

#### Examples

```bash
# Basic usage
python -m cli.rewrite_key_info --corrections data/Avalanche-corrections.yaml

# Preview changes (dry run)
python -m cli.rewrite_key_info --corrections data/Avalanche-corrections.yaml --preview

# Force in-place update
python -m cli.rewrite_key_info --corrections data/Avalanche-corrections.yaml --output-mode in_place

# Use specific source version
python -m cli.rewrite_key_info --corrections data/Avalanche-corrections.yaml --source-version v0.0.2
```

#### Corrections YAML Format

```yaml
company_name: "Avalanche"
source_version: "latest"  # or "v0.0.2"
output_mode: "new_version"  # or "in_place"

corrections:
  - type: "factual"
    field: "fund_size"
    incorrect: "$50M fund"
    correct: "$10M fund"
    sections: ["all"]  # or specific sections

  - type: "incomplete"
    field: "team_member"
    addition: "John Smith joined as CTO in 2024"
    sections: ["Team"]
```

---

## Assembly & Validation

### Assemble Draft

Rebuild `4-final-draft.md` from section files. Run this after manually editing sections.

```bash
python -m cli.assemble_draft "Company"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `target` | positional | (required) | Company name or path to artifact directory |
| `--version` | string | latest | Specific version |

#### Examples

```bash
# Reassemble latest version
python -m cli.assemble_draft "Sava"

# Reassemble specific version
python -m cli.assemble_draft "Sava" --version v0.0.2

# Use direct path
python -m cli.assemble_draft output/Sava-v0.0.2
```

#### What It Does

1. Loads `header.md` (company trademark) if exists
2. Loads all sections from `2-sections/` in order
3. Renumbers citations globally (`[^1]`, `[^2]`... sequentially)
4. Consolidates all citation references at document end
5. Generates/updates Table of Contents
6. Saves polished `4-final-draft.md`

---

### Evaluate Memo

Re-run validation on an existing memo to get quality scores and improvement suggestions.

```bash
python -m cli.evaluate_memo "Company"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `target` | positional | (required) | Company name or path to artifact directory |
| `--version` | string | latest | Specific version |

#### Examples

```bash
# Evaluate latest version
python -m cli.evaluate_memo "Sava"

# Evaluate specific version
python -m cli.evaluate_memo "Sava" --version v0.0.2

# Use direct path
python -m cli.evaluate_memo output/Sava-v0.0.2
```

#### Output

- Per-section quality scores (0-10)
- Fact-checking (claims vs citations)
- Specific issues and improvement suggestions
- Overall memo quality assessment

---

## Export Commands

### Export to Branded HTML

Export memo to styled HTML with customizable branding.

```bash
python export-branded.py <input> [options]
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `input` | path | (required) | Markdown file or directory |
| `-o, --output` | path | `exports/` | Output directory |
| `--brand` | string | `hypernova` | Brand config name |
| `--mode` | `light` \| `dark` | `light` | Color mode |
| `--pdf` | flag | - | Also generate PDF |
| `--all` | flag | - | Export all files in directory |

#### Examples

```bash
# Export single memo (light mode, default brand)
python export-branded.py output/Acme-Corp-v0.0.1/4-final-draft.md

# Export with dark mode
python export-branded.py output/Acme-Corp-v0.0.1/4-final-draft.md --mode dark

# Export with custom brand
python export-branded.py output/Acme-Corp-v0.0.1/4-final-draft.md --brand sequoia

# Export to specific directory
python export-branded.py output/Acme-Corp-v0.0.1/4-final-draft.md -o exports/branded/

# Export with PDF
python export-branded.py output/Acme-Corp-v0.0.1/4-final-draft.md --pdf

# Export all memos in directory
python export-branded.py output/ --all -o exports/light/

# Export all memos in dark mode
python export-branded.py output/ --all --mode dark -o exports/dark/
```

#### Brand Configuration

Create custom brands in `templates/brand-configs/brand-{name}-config.yaml`:

```yaml
company:
  name: "Your Firm Name"
  tagline: "Investing in the future"

colors:
  primary: "#1a3a52"
  secondary: "#1dd3d3"
  background: "#ffffff"

fonts:
  family: "Inter"
  fallback: "sans-serif"
```

---

### Export to Word (.docx)

Convert markdown to Microsoft Word format.

```bash
python md2docx.py <input> [options]
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `input` | path | (required) | Markdown file or directory |
| `-o, --output` | path | same as input | Output directory |
| `--toc` | flag | - | Include table of contents |

#### Examples

```bash
# Convert single file
python md2docx.py output/Acme-Corp-v0.0.1/4-final-draft.md

# Convert to specific directory
python md2docx.py output/Acme-Corp-v0.0.1/4-final-draft.md -o exports/

# Convert with table of contents
python md2docx.py output/Acme-Corp-v0.0.1/4-final-draft.md --toc

# Convert all markdown files in directory
python md2docx.py output/Acme-Corp-v0.0.1/2-sections/ -o exports/
```

---

### Batch Export (Both Modes)

Export all memos in both light and dark modes.

```bash
./export-all-modes.sh
```

#### Output Structure

```
exports/
├── light/    # Light mode HTML files
│   ├── Acme-Corp-v0.0.1.html
│   └── ...
└── dark/     # Dark mode HTML files
    ├── Acme-Corp-v0.0.1.html
    └── ...
```

---

## Scorecard Generation

### Generate Scorecard

Generate a structured scorecard from YAML templates.

```bash
python -m cli.generate_scorecard "Company"
```

#### Arguments

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `target` | positional | (required) | Company name or path to artifact directory |
| `--version` | string | latest | Specific version |
| `--template` | string | default | Scorecard template name |

#### Examples

```bash
# Generate scorecard for latest version
python -m cli.generate_scorecard "Avalanche"

# Generate for specific version
python -m cli.generate_scorecard "Avalanche" --version v0.0.5

# Use direct path
python -m cli.generate_scorecard output/Avalanche-v0.0.5
```

#### Output

Creates `scorecard.md` in the artifact directory with:
- Scored dimensions based on template criteria
- Evidence from memo content
- Summary scores by category

---

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (required for all operations) |

### Recommended

| Variable | Description |
|----------|-------------|
| `TAVILY_API_KEY` | Tavily API key for research phase |
| `PERPLEXITY_API_KEY` | Perplexity API key for citations and section improvement |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_WEB_SEARCH` | `true` | Enable/disable web search |
| `RESEARCH_PROVIDER` | `tavily` | Research provider (`tavily`, `perplexity`, `claude`) |
| `MAX_SEARCH_RESULTS` | `10` | Results per search query |
| `DEFAULT_MODEL` | `claude-sonnet-4-5-20250929` | Default LLM model |

### Example `.env` File

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Recommended
TAVILY_API_KEY=tvly-...
PERPLEXITY_API_KEY=pplx-...

# Optional
USE_WEB_SEARCH=true
RESEARCH_PROVIDER=tavily
MAX_SEARCH_RESULTS=10
```

---

## Quick Reference

### Common Workflows

```bash
# 1. Generate new memo
python -m src.main "Company Name" --type direct --mode consider

# 2. Improve weak sections
python -m cli.improve_section "Company Name" "Team"
python -m cli.improve_section "Company Name" "Market Context"

# 3. Apply corrections
python -m cli.rewrite_key_info --corrections data/Company-corrections.yaml

# 4. Export final memo
python export-branded.py output/Company-Name-v0.0.1/4-final-draft.md --brand hypernova
python export-branded.py output/Company-Name-v0.0.1/4-final-draft.md --mode dark
```

### Target Resolution

Most commands accept either:
- **Company name**: `"Acme Corp"` → resolves to `output/Acme-Corp-v{latest}/`
- **Direct path**: `output/Acme-Corp-v0.0.1` → uses exact path

### Version Specification

- **Omit `--version`**: Uses latest version from `output/versions.json`
- **`--version v0.0.2`**: Uses specific version
- **`--version latest`**: Explicit latest (same as omitting)

---

*Last updated: 2025-11-28*
