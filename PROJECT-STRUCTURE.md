# Project Structure

This document provides a visual overview of the investment-memo-orchestrator project organization.

**Last Updated**: 2025-11-23

---

## Directory Tree

```
.
├── .claude/
│   ├── project-instructions.md
│   └── settings.local.json
├── .env
├── .env.example
├── .gitignore
├── changelog/                      # Version history and release notes
│   ├── 2025-11-16_01.md
│   ├── 2025-11-16_02.md
│   ├── ... (17 changelog files)
│   └── releases/
├── CLAUDE.md                       # Claude Code project instructions
├── cli/                            # User-facing CLI commands
│   ├── export_branded.py          # Branded HTML/PDF export
│   ├── export_formats.py          # Multi-format converter
│   ├── improve_section.py         # Section improvement tool
│   ├── markdown_to_pdf.py         # PDF conversion
│   ├── md2docx.py                # Word conversion
│   ├── rewrite_key_info.py       # Correction application
│   ├── export-all-html.sh        # Batch HTML export
│   ├── export-all-modes.sh       # Batch dual-mode export
│   ├── html-to-pdf.sh           # HTML to PDF wrapper
│   ├── md-to-pdf.sh             # Markdown to PDF wrapper
│   └── utils/                    # CLI support utilities
│       ├── fix_citations.py
│       ├── fix_markdown_citations.py
│       └── restore_uncited_footnotes.py
├── context-vigilance/             # Design docs and explorations
│   ├── Anti-Hallucination-Fact-Checker-Agent.md
│   ├── Citation-Reminders.md
│   ├── Format-Memo-According-to-Template-Input.md
│   ├── issue-resolution/
│   └── ... (9 markdown files)
├── data/                          # Company data and configurations
│   ├── Aito.json
│   ├── Avalanche.json
│   ├── Class5-Global.json
│   ├── sample-company.json
│   └── ... (24 company data files)
├── docs/                          # User documentation
│   ├── BRAND-CONFIG-REFERENCE.md
│   ├── CASUAL_USER_GUIDE.md
│   ├── CUSTOM-BRANDING.md
│   ├── EXPORT-GUIDE.md
│   ├── SETUP.md
│   ├── TROUBLESHOOTING.md
│   ├── WEB_SEARCH_SETUP.md
│   └── WORD-BRANDING-GUIDE.md
├── exports/                       # Exported memos (HTML, PDF, DOCX)
│   ├── branded/
│   ├── dark/
│   ├── light/
│   └── ... (various export directories)
├── output/                        # Generated memo artifacts
│   ├── Aalo-Atomics-v0.0.5/
│   ├── Avalanche-v0.0.4/
│   ├── Class5-Global-v0.0.2/
│   ├── logs/                     # Test run logs
│   │   ├── dayone-test.log
│   │   ├── harmonic-nodeck-test.log
│   │   └── workflow-workback.log
│   └── ... (50+ versioned memo directories)
├── pyproject.toml                 # Package configuration
├── README.md                      # Main project documentation
├── requirements.txt               # Python dependencies (frozen)
├── scripts/                       # One-off utilities and fixes
│   ├── data/                     # Data migration scripts
│   │   ├── add-fund-sources.py
│   │   └── create-word-reference.py
│   ├── fixes/                    # One-off fix scripts
│   │   ├── enrich-citations.py
│   │   ├── fix-powerline-citations.py
│   │   ├── fix_yaml_quotes.py
│   │   └── run-citations-now.py
│   └── legacy/                   # POC and experimental code
│       └── poc-perplexity-section-research.py
├── src/                           # Main Python package
│   ├── __init__.py
│   ├── agents/                   # LangGraph agents
│   │   ├── citation_enrichment.py
│   │   ├── citation_validator.py
│   │   ├── deck_analyst.py
│   │   ├── key_info_rewrite.py
│   │   ├── link_enrichment.py
│   │   ├── research_enhanced.py
│   │   ├── researcher.py
│   │   ├── socials_enrichment.py
│   │   ├── trademark_enrichment.py
│   │   ├── validator.py
│   │   ├── visualization_enrichment.py
│   │   └── writer.py
│   ├── artifacts.py              # Artifact trail system
│   ├── branding.py              # Brand configuration loader
│   ├── corrections.py           # Corrections YAML loader
│   ├── main.py                  # CLI entry point
│   ├── outline_loader.py        # YAML outline loader
│   ├── schemas/                 # JSON schemas
│   │   └── outline-schema.json
│   ├── state.py                 # TypedDict state definitions
│   ├── utils.py                 # Utility functions
│   ├── versioning.py            # Version management
│   └── workflow.py              # LangGraph orchestration
├── templates/                     # Templates and configurations
│   ├── base-style.css           # Base CSS for exports
│   ├── brand-configs/           # VC firm branding configs
│   │   ├── brand-config.example.yaml
│   │   ├── brand-hypernova-config.yaml
│   │   └── ... (brand configs)
│   ├── corrections-template.yaml
│   ├── fonts/                   # Custom font files
│   ├── hypernova-reference.docx # Word template
│   ├── memo-template-direct.md  # Direct investment template
│   ├── memo-template-fund.md    # Fund commitment template
│   ├── outlines/                # YAML content outlines
│   │   ├── direct-investment.yaml
│   │   ├── fund-commitment.yaml
│   │   ├── sections-schema.json
│   │   ├── README.md
│   │   └── custom/             # Custom outline overrides
│   ├── style-guide.md          # Writing standards
│   └── trademarks/             # Company logos
├── tools/                         # Development and testing tools
│   ├── test_anthropic.py
│   ├── test_outline_sources.py
│   ├── test_perplexity.py
│   ├── test_perplexity_at_syntax.py
│   ├── test_premium_partners.py
│   ├── test_premium_sources.py
│   ├── test_source_integration.py
│   ├── test-perplexity-curl.sh
│   └── validate_outlines.py
├── uv.lock                        # uv dependency lock file
└── WARP.md                        # Warp Terminal quick reference

```

---

## Directory Descriptions

### **Core Directories**

| Directory | Purpose |
|-----------|---------|
| `src/` | Main Python package with agents, workflow, and utilities |
| `cli/` | User-facing command-line tools for generation and export |
| `templates/` | Content outlines, brand configs, and style templates |
| `data/` | Company data files (JSON) with research context |
| `output/` | Generated memos with full artifact trails |

### **Development Directories**

| Directory | Purpose |
|-----------|---------|
| `tools/` | Testing and validation scripts for development |
| `scripts/` | One-off utilities, fixes, and legacy code |
| `docs/` | User documentation and guides |
| `context-vigilance/` | Design documents, context engineering, and explorations |
| `changelog/` | Version history and release notes |

### **Export Directories**

| Directory | Purpose |
|-----------|---------|
| `exports/` | Exported memos in various formats (HTML, PDF, DOCX) |
| `output/` | Source artifacts (versioned directories with sections) |

---

## Key Files

| File | Purpose |
|------|---------|
| `README.md` | Main project documentation and setup guide |
| `CLAUDE.md` | Project instructions for Claude Code |
| `WARP.md` | Quick reference for Warp Terminal users |
| `pyproject.toml` | Package configuration and dependencies |
| `requirements.txt` | Frozen Python dependencies |
| `uv.lock` | uv dependency lock file |

---

## File Organization Principles

1. **CLI Tools** (`cli/`) - User-facing commands that generate, improve, or export memos
2. **Development Tools** (`tools/`) - Testing, validation, and debugging scripts
3. **One-off Scripts** (`scripts/`) - Data migration, fixes, and experimental code
4. **Source Code** (`src/`) - Core package with agents and workflow logic
5. **Configuration** (`templates/`, `data/`) - Templates, outlines, and company data
6. **Output** (`output/`, `exports/`) - Generated artifacts and exported memos

---

**Generated**: 2025-11-23  
**Tool**: `tree -L 3 -a -I '.venv|__pycache__|*.egg-info|.git|.DS_Store'`
