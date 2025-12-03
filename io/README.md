# Firm-Scoped IO Directory

This directory contains firm-specific configurations, templates, deal data, and outputs. Each firm has its own isolated directory that can be managed as a private git submodule, enabling multi-tenant deployments while keeping sensitive data separate from the shared codebase.

## Table of Contents

- [Directory Structure](#directory-structure)
- [Setting Up a New Firm](#setting-up-a-new-firm)
- [Brand Configuration](#brand-configuration)
- [Templates & Scorecards](#templates--scorecards)
- [Managing Deals](#managing-deals)
- [Generating Memos](#generating-memos)
- [Exporting Branded Memos](#exporting-branded-memos)
- [CLI Reference](#cli-reference)
- [Git Submodule Management](#git-submodule-management)

---

## Directory Structure

```
io/
├── README.md                          # This file
└── {firm}/                            # e.g., "hypernova", "collide"
    ├── README.md                      # Firm-specific notes
    ├── .gitignore                     # Tracks outputs/exports, ignores caches
    ├── versions.json                  # Version tracking for all deals
    │
    ├── configs/                       # Runtime configurations
    │   └── brand-{firm}-config.yaml   # Brand styling (colors, fonts, logos)
    │
    ├── templates/                     # Content structure templates
    │   ├── outlines/                  # Memo section structures
    │   │   ├── direct-early-stage-12Ps.yaml
    │   │   └── lpcommit-emerging-manager.yaml
    │   └── scorecards/                # Evaluation frameworks
    │       └── direct-early-stage-12Ps/
    │           └── hypernova-early-stage-12Ps.yaml
    │
    └── deals/                         # Deal-specific data
        └── {deal}/                    # e.g., "Blinka", "Acme-Corp"
            ├── {deal}.json            # Deal configuration
            ├── inputs/                # Source materials
            │   ├── pitch-deck.pdf
            │   └── dataroom/
            ├── outputs/               # Generated memo artifacts
            │   └── {Deal}-v0.0.x/
            │       ├── 0-deck-analysis.json
            │       ├── 1-research/
            │       ├── 2-sections/
            │       ├── 3-validation.json
            │       ├── 4-final-draft.md
            │       └── state.json
            ├── exports/               # Branded HTML/PDF exports
            │   ├── dark/
            │   └── light/
            └── assets/                # Deal-specific assets
                └── company-logo.svg
```

---

## Setting Up a New Firm

### Step 1: Create the Firm Directory Structure

```bash
# From project root
mkdir -p io/{firm-name}/{configs,templates/outlines,templates/scorecards,deals}

# Example for "accel"
mkdir -p io/accel/{configs,templates/outlines,templates/scorecards,deals}
```

### Step 2: Create Brand Configuration

Create `io/{firm}/configs/brand-{firm}-config.yaml`:

```yaml
company:
  name: "Accel Partners"
  tagline: "Early-stage venture capital"
  confidential_footer: "This document is confidential and proprietary to {company_name}."

colors:
  primary: "#1a3a52"          # Main brand color (headers, accents)
  secondary: "#1dd3d3"        # Secondary color (links, highlights)
  text_dark: "#1a2332"        # Primary text color
  text_light: "#6b7280"       # Secondary/muted text
  background: "#ffffff"       # Light mode background
  background_alt: "#f0f0eb"   # Alternate backgrounds

fonts:
  family: "Inter"
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  google_fonts_url: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
  weight: 400
  header_weight: 700

logo:
  light_mode: "io/accel/configs/accel-logo-light.svg"
  dark_mode: "io/accel/configs/accel-logo-dark.svg"
  width: "180px"
  height: "60px"
  alt: "Accel Partners"
```

### Step 3: Add Templates (Optional)

Copy and customize outlines and scorecards:

```bash
# Copy from shared templates or another firm
cp templates/outlines/direct-investment.yaml io/accel/templates/outlines/
cp -r templates/scorecards/direct-early-stage-12Ps io/accel/templates/scorecards/
```

### Step 4: Initialize as Git Repository (Recommended)

For private data isolation:

```bash
cd io/accel
git init
git add .
git commit -m "Initial firm setup"

# Create private repo on GitHub/GitLab
git remote add origin https://github.com/your-org/accel-secure-data.git
git push -u origin main
```

### Step 5: Add as Submodule to Parent Project

```bash
cd ../..  # Back to project root
git submodule add https://github.com/your-org/accel-secure-data.git io/accel
git commit -m "feat(io): Add accel firm as git submodule"
```

---

## Brand Configuration

Brand configs control the visual styling of exported memos.

### Location

```
io/{firm}/configs/brand-{firm}-config.yaml
```

### Key Sections

#### Company Information
```yaml
company:
  name: "Your Firm Name"
  tagline: "Your firm's tagline or investment thesis"
  confidential_footer: "Confidential - {company_name}"
```

#### Color Palette
```yaml
colors:
  primary: "#1a3a52"      # Headers, dark mode background
  secondary: "#1dd3d3"    # Links, accents, highlights
  text_dark: "#1a2332"    # Body text
  text_light: "#6b7280"   # Muted/secondary text
  background: "#ffffff"   # Light mode background
  background_alt: "#f0f0eb"  # Code blocks, callouts
```

#### Typography
```yaml
fonts:
  # Body text
  family: "Inter"
  fallback: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
  google_fonts_url: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap"
  weight: 400

  # Headers (optional - defaults to body font)
  header_family: "Playfair Display"
  header_fallback: "Georgia, serif"
  header_google_fonts_url: "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&display=swap"
  header_weight: 700
```

#### Logo Configuration
```yaml
logo:
  # Theme-specific logos (SVG recommended)
  light_mode: "io/accel/configs/logo-light.svg"   # For light backgrounds
  dark_mode: "io/accel/configs/logo-dark.svg"     # For dark backgrounds

  # Or use URLs
  light_mode: "https://yourfirm.com/logo-light.svg"
  dark_mode: "https://yourfirm.com/logo-dark.svg"

  width: "180px"
  height: "60px"
  alt: "Firm Name"
```

### Full Documentation

See `templates/brand-configs/README.md` for complete brand configuration reference.

---

## Templates & Scorecards

### Outlines

Outlines define the memo structure—sections, questions, vocabulary, and preferred research sources.

**Location**: `io/{firm}/templates/outlines/`

**Types**:
- `direct-investment.yaml` - For startup investments
- `fund-commitment.yaml` - For LP/fund commitments
- `direct-early-stage-12Ps.yaml` - 12Ps framework for early-stage

**Key sections in an outline**:
```yaml
metadata:
  outline_type: "direct-investment"
  version: "1.0.0"
  firm: "hypernova"

sections:
  - number: 1
    name: "Executive Summary"
    filename: "01-executive-summary.md"
    target_length:
      ideal_words: 350
    guiding_questions:
      - "What does this company do?"
      - "Why is this a compelling investment?"
    preferred_sources:
      domains:
        include: ["crunchbase.com", "pitchbook.com"]
```

### Scorecards

Scorecards define evaluation dimensions and scoring rubrics.

**Location**: `io/{firm}/templates/scorecards/`

**Structure**:
```yaml
metadata:
  scorecard_id: "hypernova-early-stage-12Ps"
  name: "Early-Stage 12Ps Scorecard"
  version: "1.0.0"

dimensions:
  persona:
    name: "Persona"
    group: "origins"
    scoring_rubric:
      1: "Vague or undefined target customer"
      3: "Clear persona but limited validation"
      5: "Deeply understood, validated persona"
```

---

## Managing Deals

### Creating a New Deal

```bash
# Create deal directory
mkdir -p io/{firm}/deals/{DealName}/{inputs,outputs,exports,assets}

# Create deal config
touch io/{firm}/deals/{DealName}/{DealName}.json
```

### Deal Configuration File

Create `io/{firm}/deals/{DealName}/{DealName}.json`:

```json
{
  "type": "direct",
  "mode": "consider",
  "description": "AI-powered CRE lending marketplace",
  "url": "https://blinka.co",
  "stage": "Seed",
  "deck": "inputs/pitch-deck.pdf",
  "trademark_light": "https://blinka.co/logo-light.svg",
  "trademark_dark": "https://blinka.co/logo-dark.svg",
  "scorecard_name": "hypernova-early-stage-12Ps",
  "outline": "direct-early-stage-12Ps",
  "notes": "Focus on: competitive landscape, team depth, unit economics"
}
```

### Field Reference

| Field | Values | Description |
|-------|--------|-------------|
| `type` | `"direct"` / `"fund"` | Direct investment or LP fund commitment |
| `mode` | `"consider"` / `"justify"` | Prospective analysis or retrospective justification |
| `description` | string | Brief company description for research context |
| `url` | URL | Company website |
| `stage` | string | Investment stage (Seed, Series A, etc.) |
| `deck` | path | Relative path to pitch deck PDF |
| `trademark_light` | URL/path | Light mode company logo |
| `trademark_dark` | URL/path | Dark mode company logo |
| `scorecard_name` | string | Scorecard to use for evaluation |
| `outline` | string | Custom outline name (optional) |
| `memo_date` | date string | Custom date for memo header |
| `notes` | string | Research focus areas |

### Adding Source Materials

```bash
# Add pitch deck
cp ~/Downloads/company-deck.pdf io/{firm}/deals/{DealName}/inputs/

# Add dataroom
cp -r ~/Downloads/dataroom/ io/{firm}/deals/{DealName}/inputs/dataroom/

# Add company logo
cp ~/Downloads/logo.svg io/{firm}/deals/{DealName}/assets/
```

---

## Generating Memos

### Basic Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Generate memo with firm context
python -m src.main "{DealName}" --firm {firm}

# Examples
python -m src.main "Blinka" --firm hypernova
python -m src.main "Acme Corp" --firm accel --type direct --mode consider
```

### Generation Options

```bash
python -m src.main "{DealName}" --firm {firm} [OPTIONS]

Options:
  --type [direct|fund]     Investment type (default: from deal.json or "direct")
  --mode [consider|justify] Analysis mode (default: from deal.json or "consider")
  --scorecard NAME         Override scorecard from deal.json
```

### Output Location

Generated artifacts are saved to:
```
io/{firm}/deals/{DealName}/outputs/{DealName}-v0.0.x/
```

### Versioning

Each generation creates a new version (`v0.0.1`, `v0.0.2`, etc.). Previous versions are preserved.

---

## Exporting Branded Memos

### Export to HTML (Dark Mode - Default)

```bash
# Using --firm and --deal (recommended)
python cli/export_branded.py --firm hypernova --deal Blinka

# Using direct path (auto-detects firm from path)
python cli/export_branded.py io/hypernova/deals/Blinka/outputs/Blinka-v0.0.2/4-final-draft.md
```

### Export to PDF

```bash
python cli/export_branded.py --firm hypernova --deal Blinka --pdf
```

### Export to Light Mode

```bash
python cli/export_branded.py --firm hypernova --deal Blinka --mode light --pdf
```

### Specify Version

```bash
python cli/export_branded.py --firm hypernova --deal Blinka --version v0.0.1
```

### Override Brand

```bash
# Use a different brand config
python cli/export_branded.py --firm hypernova --deal Blinka --brand collide
```

### Export Location

Exports are saved to:
```
io/{firm}/deals/{DealName}/exports/{mode}/
  └── {DealName}-v0.0.x.html
  └── {DealName}-v0.0.x.pdf
```

---

## CLI Reference

### Main Pipeline

```bash
python -m src.main "{DealName}" --firm {firm} [--type direct|fund] [--mode consider|justify]
```

### Export Branded

```bash
python cli/export_branded.py [INPUT] [OPTIONS]

Arguments:
  INPUT                    Markdown file or directory (optional if --firm/--deal provided)

Options:
  --firm FIRM              Firm name (e.g., "hypernova")
  --deal DEAL              Deal name (e.g., "Blinka")
  --version VERSION        Specific version (e.g., "v0.0.1")
  --brand BRAND            Brand config name (defaults to firm name)
  --mode [light|dark]      Color mode (default: dark)
  --pdf                    Also generate PDF
  -o, --output DIR         Custom output directory
```

### Improve Section

```bash
python cli/improve_section.py --firm {firm} --deal {deal} "{Section Name}"

# Or with direct path
python cli/improve_section.py "{DealName}" "{Section Name}"
```

### Score Memo

```bash
python cli/score_memo.py --firm {firm} --deal {deal}
```

### Recompile Memo

```bash
python cli/recompile_memo.py --firm {firm} --deal {deal}
```

### Refocus Section

```bash
python cli/refocus_section.py --firm {firm} --deal {deal} "{Section Name}" --focus "{new focus}"
```

### Resume from Interruption

If memo generation is interrupted (e.g., network issues), resume from the last checkpoint:

```bash
python cli/resume_from_interruption.py --firm {firm} --deal {deal}

# Resume specific version
python cli/resume_from_interruption.py --firm {firm} --deal {deal} --version v0.0.1
```

The script detects the last successful checkpoint and resumes from there, avoiding redundant API calls.

### HTML to PDF Conversion

```bash
bash cli/html-to-pdf.sh io/{firm}/deals/{DealName}/exports/dark/{DealName}-v0.0.x.html
```

---

## Git Submodule Management

### Initial Clone with Submodules

```bash
git clone --recurse-submodules https://github.com/your-org/investment-memo-orchestrator.git
```

### Update Submodules

```bash
git submodule update --remote --merge
```

### Working Inside a Submodule

```bash
cd io/hypernova

# Make changes
git add .
git commit -m "Update Blinka memo"
git push

# Return to parent and update reference
cd ../..
git add io/hypernova
git commit -m "Update hypernova submodule reference"
git push
```

### Add New Submodule

```bash
git submodule add https://github.com/your-org/{firm}-secure-data.git io/{firm}
```

### Submodule .gitignore

Each firm submodule should have its own `.gitignore`:

```gitignore
# Python caches
__pycache__/
*.py[cod]

# OS files
.DS_Store

# Temp files
*.tmp
.temp_*

# NOTE: outputs/ and exports/ ARE tracked (not ignored)
```

---

## Environment Variables

Optional environment variables for default behavior:

```bash
# Set default firm (avoids --firm flag)
export MEMO_DEFAULT_FIRM=hypernova

# Then just run:
python -m src.main "Blinka"  # Uses hypernova as firm
```

---

## Troubleshooting

### Brand config not found

```
Error: Brand config not found: brand-accel-config.yaml
```

**Solution**: Ensure config exists at `io/{firm}/configs/brand-{firm}-config.yaml`

### Deal not found

```
Error: Outputs directory not found for hypernova/Blinka
```

**Solution**: Create the deal directory and config file:
```bash
mkdir -p io/hypernova/deals/Blinka/{inputs,outputs,exports}
# Create io/hypernova/deals/Blinka/Blinka.json
```

### Submodule not initialized

```
fatal: no submodule mapping found in .gitmodules for path 'io/hypernova'
```

**Solution**: Initialize submodules:
```bash
git submodule init
git submodule update
```

### Logo not appearing in export

1. Check logo path is correct in brand config
2. For URLs: Ensure the URL is accessible (not blocked by CDN)
3. For local files: Use absolute paths or paths relative to project root
4. Download logo locally if URL is blocked:
   ```bash
   curl -o io/{firm}/configs/logo.svg "https://company.com/logo.svg"
   ```

---

## Further Documentation

- **Main Project**: See `README.md` in project root
- **Brand Configuration**: See `templates/brand-configs/README.md`
- **Outline System**: See `templates/outlines/README.md`
- **Development Guide**: See `CLAUDE.md`
- **Changelog**: See `changelog/` directory
