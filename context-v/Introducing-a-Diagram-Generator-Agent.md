---
title: Introducing a Diagram Generator Agent
lede: Add a diagram_generator.py agent that identifies opportunities to create visual diagrams explaining complex business concepts, starting with TAM/SAM/SOM market sizing and expanding to common finance and consulting visuals.
date_authored_initial_draft: 2026-03-09
date_authored_current_draft: 2026-03-09
date_authored_final_draft:
date_first_published:
date_last_updated: 2026-03-09
at_semantic_version: 0.1.0
status: Draft
augmented_with: Claude Code (Opus 4.6)
category: Architecture
tags: [Agent-Design, Diagrams, Visualization, Export, Mermaid, SVG]
authors:
  - Michael Staton
  - AI Labs Team
image_prompt: A layered concentric circle diagram showing TAM, SAM, and SOM market sizes with dollar amounts, surrounded by smaller diagram thumbnails of competitive landscapes, funding waterfalls, and org charts, all rendered in clean vector style.
date_created: 2026-03-09
date_modified: 2026-03-09
---

# Introducing a Diagram Generator Agent

**Status**: Draft
**Date**: 2026-03-09
**Last Updated**: 2026-03-09
**Author**: AI Labs Team
**Related**: Format-Memo-According-to-Template-Input.md, Multi-Agent-Orchestration-for-Investment-Memo-Generation.md, Table-Generator-Agent-Spec.md

---

## Executive Summary

Investment memos benefit enormously from visual diagrams that communicate complex concepts at a glance. This specification introduces a `diagram_generator.py` agent that scans memo sections for opportunities to insert visual diagrams, starting with TAM/SAM/SOM market sizing and expanding over time to include a catalog of diagrams commonly used in finance and consulting.

The key technical challenge is **cross-format export compatibility**: diagrams must render correctly in HTML, PDF, and DocX exports. This document evaluates rendering approaches and recommends a strategy.

---

## Goals

1. **Identify diagram opportunities** by analyzing section content for concepts that benefit from visualization
2. **Generate diagrams programmatically** from data extracted during research and writing phases
3. **Ensure export compatibility** across HTML, PDF, and DocX output formats
4. **Build a growing catalog** of diagram types mapped to common investment memo concepts

---

## Diagram Catalog

### Phase 1: TAM/SAM/SOM Market Sizing (Initial)

**Diagram type**: Concentric circles (nested)
**Sections where applicable**: Market Context
**Data sources**: Research phase market data, deck analysis
**Use case**: Show total addressable market, serviceable addressable market, and serviceable obtainable market as nested circles with dollar figures and growth rates.

**Example structure**:
- Outer circle: TAM ($50B)
- Middle circle: SAM ($12B)
- Inner circle: SOM ($800M)
- Annotations: CAGR percentages, year projections

### Phase 2: Finance and Consulting Diagrams (Future)

| Diagram Type | Use Case | Applicable Sections |
|---|---|---|
| **Competitive Landscape Matrix** | 2x2 quadrant positioning companies by two key dimensions | Market Context, Business Overview |
| **Blue Ocean Strategy Canvas** | Line chart comparing value curves across key competing factors, highlighting differentiation and uncontested market space | Market Context, Business Overview, Investment Thesis |
| **Funding Waterfall** | Visualize funding rounds, dilution, and cap table progression | Funding & Terms |
| **Revenue Model Breakdown** | Pie or treemap showing revenue streams | Business Overview, Traction & Milestones |
| **Organizational Chart** | Team structure and key hires | Team |
| **Technology Stack Diagram** | Architecture layers and integrations | Technology & Product |
| **Risk Heat Map** | Probability vs. impact matrix for identified risks | Risks & Mitigations |
| **Milestone Timeline** | Horizontal timeline of achieved and planned milestones | Traction & Milestones |
| **Porter's Five Forces** | Industry competitive dynamics | Market Context |
| **Value Chain Diagram** | Where the company sits in the value chain | Business Overview |
| **Unit Economics Funnel** | CAC, LTV, conversion rates through funnel stages | Traction & Milestones |
| **Fund Portfolio Construction** | Allocation pie chart or bar chart (for fund memos) | Portfolio Construction |
| **GP Track Record Chart** | Returns by vintage year or fund (for fund memos) | Track Record Analysis |

---

## Technology and Rendering Strategy

### The Core Problem

Diagrams must work in three export formats:
- **HTML**: Flexible, supports JavaScript libraries and SVG natively
- **PDF**: Generated via WeasyPrint from HTML/CSS; no JavaScript execution
- **DocX**: Generated via Pandoc from Markdown; limited to embedded images

JavaScript-based charting libraries (D3.js, Chart.js, Mermaid.js in-browser) only work in live HTML. They cannot render in PDF or DocX pipelines. We need a strategy that produces **static image assets** that all three formats can consume.

### Recommended Approach: Mermaid CLI + SVG/PNG Export

**Primary tool**: [Mermaid](https://mermaid.js.org/) via `@mermaid-js/mermaid-cli` (mmcli)

**Why Mermaid**:
- Text-based diagram definitions (easy for LLMs to generate)
- CLI tool (`mmdc`) renders to SVG or PNG without a browser
- Supports many diagram types: flowcharts, pie charts, quadrant charts, timelines, mindmaps
- Active ecosystem, widely adopted
- Diagrams are defined in Markdown-friendly syntax

**Rendering pipeline**:
1. Agent generates Mermaid diagram definition (text)
2. `mmdc` CLI renders definition to SVG (preferred) and PNG (fallback)
3. SVG/PNG saved to `output/{Company}-v0.0.x/diagrams/`
4. Markdown image reference inserted into section: `![TAM/SAM/SOM](diagrams/tam-sam-som.svg)`
5. Export pipelines consume the image file:
   - **HTML**: `<img>` tag referencing SVG (crisp at any scale)
   - **PDF**: WeasyPrint renders embedded SVG/PNG from HTML
   - **DocX**: Pandoc embeds PNG into Word document

**Mermaid limitations and workarounds**:
- Mermaid does not natively support concentric circle diagrams (TAM/SAM/SOM). For Phase 1, we may need a supplementary approach for this specific diagram type.
- **Fallback for unsupported types**: Use `matplotlib` or `plotly` (with `kaleido` for static export) to generate SVG/PNG for diagram types Mermaid cannot handle.

### Alternative/Supplementary: Python Libraries for Custom Diagrams

For diagrams that Mermaid cannot express (e.g., concentric circles, complex custom layouts):

| Library | Strengths | Output Formats |
|---|---|---|
| **matplotlib** | Full control, concentric circles easy, widely available | SVG, PNG, PDF |
| **plotly + kaleido** | Interactive HTML + static SVG/PNG export | SVG, PNG, HTML |
| **drawsvg** | Lightweight SVG generation, no heavy dependencies | SVG |
| **diagrams (mingrammer)** | Cloud architecture diagrams | PNG |

**Recommended hybrid approach**:
- Use **Mermaid** for structured diagrams (flowcharts, timelines, quadrants, pie charts)
- Use **matplotlib** for custom/quantitative diagrams (TAM/SAM/SOM circles, waterfalls, funnels)
- All output as **SVG** (primary) with **PNG** fallback
- Store all diagram assets in `output/{Company}-v0.0.x/diagrams/`

### File Format Decision: SVG vs PNG

| Factor | SVG | PNG |
|---|---|---|
| Scalability | Infinite (vector) | Fixed resolution |
| File size | Small for simple diagrams | Larger at high DPI |
| HTML support | Native | Native |
| WeasyPrint (PDF) | Supported | Supported |
| Pandoc (DocX) | Must convert to PNG | Native |
| Text searchability | Yes | No |

**Decision**: Generate both SVG and PNG. Use SVG as primary for HTML/PDF exports. Use PNG for DocX exports. The agent saves both formats; the export scripts select the appropriate one.

---

## Agent Design

### Placement in Pipeline

The diagram generator runs **after the Writer** and **before Citation Enrichment**, similar to the existing enrichment agents:

```
Writer → Trademark Enrichment → Socials Enrichment → Link Enrichment
       → Diagram Generator (NEW) → Citation Enrichment → ...
```

The agent needs access to:
- Written section content (to identify diagram opportunities)
- Research data (for quantitative values to populate diagrams)
- Deck analysis data (for extracted metrics)

### Agent Function Signature

```python
def diagram_generator(state: MemoState) -> dict:
    """Scan sections for diagram opportunities, generate and embed visual diagrams."""
    # 1. Load section files from 2-sections/
    # 2. Analyze each section for diagram opportunities
    # 3. Extract data points from research/deck analysis
    # 4. Generate diagram definitions (Mermaid text or matplotlib code)
    # 5. Render to SVG + PNG via mmdc or matplotlib
    # 6. Save to output/{Company}-v0.0.x/diagrams/
    # 7. Insert image references into section markdown
    # 8. Save updated sections back to files
    return {
        "messages": ["Generated N diagrams across M sections"],
        "diagrams_generated": diagram_manifest  # list of generated diagram metadata
    }
```

### Diagram Opportunity Detection

The agent uses an LLM call to analyze each section and determine:
1. Whether the section content would benefit from a diagram
2. Which diagram type is most appropriate
3. What data points are available to populate the diagram

This can be guided by the YAML outline system -- each section definition could include a `suggested_diagrams` field:

```yaml
sections:
  - number: 3
    name: "Market Context"
    suggested_diagrams:
      - type: "tam_sam_som"
        trigger: "market size data present"
      - type: "competitive_quadrant"
        trigger: "3+ competitors identified"
```

---

## Dependencies

### Required

```bash
# Mermaid CLI for structured diagrams
npm install -g @mermaid-js/mermaid-cli

# matplotlib for custom diagrams (already likely in Python deps)
uv pip install matplotlib
```

### Optional

```bash
# For interactive HTML diagrams with static export
uv pip install plotly kaleido

# For lightweight SVG-only generation
uv pip install drawsvg
```

Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
diagrams = ["matplotlib", "plotly", "kaleido"]
```

---

## Output Structure

```
output/{Company-Name}-v0.0.x/
├── diagrams/
│   ├── 03-tam-sam-som.svg
│   ├── 03-tam-sam-som.png
│   ├── 03-competitive-landscape.svg
│   ├── 03-competitive-landscape.png
│   ├── 06-funding-waterfall.svg
│   ├── 06-funding-waterfall.png
│   └── diagram-manifest.json    # metadata about all generated diagrams
├── 2-sections/
│   ├── 03-market-context.md     # now contains ![](diagrams/03-tam-sam-som.svg)
│   └── ...
└── ...
```

The `diagram-manifest.json` tracks what was generated:
```json
[
  {
    "section": "03-market-context",
    "type": "tam_sam_som",
    "renderer": "matplotlib",
    "svg_path": "diagrams/03-tam-sam-som.svg",
    "png_path": "diagrams/03-tam-sam-som.png",
    "data": {"tam": 50000000000, "sam": 12000000000, "som": 800000000}
  }
]
```

---

## Export Integration

### HTML Export (`export-branded.py`)

- SVG images render natively via `<img>` tags
- For inline SVG (better for theming), the export script can embed SVG content directly
- Diagrams inherit brand colors via CSS variables or by passing brand palette to the generator

### PDF Export (WeasyPrint)

- WeasyPrint renders SVG and PNG from `<img>` tags in the HTML intermediate
- No additional work needed if HTML export handles images correctly

### DocX Export (`md2docx.py` / Pandoc)

- Pandoc embeds PNG images from markdown `![](path.png)` syntax
- The export script should rewrite SVG references to PNG references before Pandoc processing
- Alternatively, use `cairosvg` to convert SVG to PNG at export time

---

## Open Questions

1. **Brand-aware diagrams**: Should diagrams use brand colors from the active brand config? This would make diagrams visually consistent with the exported memo but adds complexity.
2. **Diagram regeneration**: If a section is improved via `improve-section.py`, should diagrams be regenerated? Likely yes, but needs coordination.
3. **LLM-generated vs rule-based**: Should the agent use an LLM to generate Mermaid/matplotlib code, or should we build templates that get filled with data? LLM generation is more flexible but less predictable.
4. **Concentric circle rendering**: Mermaid lacks native concentric circle support. Confirm matplotlib is the right choice for TAM/SAM/SOM, or evaluate custom SVG generation with `drawsvg`.
5. **Diagram density**: How many diagrams per memo is appropriate? Too many may dilute impact. Consider a configurable maximum per memo or per section.

---

## Implementation Phases

### Phase 1: TAM/SAM/SOM (MVP)
- Implement `diagram_generator.py` agent
- matplotlib-based concentric circle renderer
- SVG + PNG output to `diagrams/` directory
- Image reference insertion into Market Context section
- Basic export integration (HTML + PDF)

### Phase 2: Mermaid Integration
- Add Mermaid CLI rendering pipeline
- Implement competitive landscape quadrant (Mermaid quadrant chart)
- Implement milestone timeline (Mermaid timeline)
- Add funding waterfall (matplotlib or Mermaid)

### Phase 3: Outline-Driven Diagram Suggestions
- Add `suggested_diagrams` field to YAML outlines
- Agent reads outline to determine which diagrams to attempt
- Implement remaining diagram types from catalog
- Brand-color-aware rendering

### Phase 4: DocX Export and Polish
- PNG fallback pipeline for Pandoc/DocX
- Diagram regeneration on section improvement
- Configurable diagram density limits
