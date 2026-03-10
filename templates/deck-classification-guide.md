# Deck Slide Classification Guide

This guide is used by the deck analyst agent when classifying pitch deck slides for screenshot extraction. Each slide should be assigned exactly **one category** based on its primary content, plus a short **slug** describing the specific slide.

## How to Use This Guide

1. Look at the slide's **primary visual content** — what is the main thing being communicated?
2. Read the slide **title/header** — deck creators usually label their slides accurately
3. Match to the **most specific category** below — prefer a narrow match over a broad one
4. When in doubt, use the **"Not this category"** notes and **Ambiguity Rules** at the bottom

## Output Format

For each slide selected for screenshot extraction, return:

```json
{
  "page_number": 2,
  "category": "fundraising",
  "slug": "pre-seed-use-of-funds",
  "description": "Pre-seed round status showing $1.8M target, $200K remaining, and allocation across R&D, clinical study, and manufacturing"
}
```

- **category**: One of the categories defined below (lowercase, hyphenated)
- **slug**: 2-5 word descriptor of this specific slide (lowercase, hyphenated). Should be unique across the deck.
- **description**: One sentence describing the specific visual content worth preserving

The resulting filename will be: `page-{number}-{category}-{slug}.png`
Example: `page-02-fundraising-pre-seed-use-of-funds.png`

---

## Categories

### overview
**Use for:** Company overview slides, "what we do" summaries, mission statements, one-liner descriptions, elevator pitch slides
**Visual signals:** Company logo prominently displayed, tagline, brief description of what the company does, sometimes a hero image
**Not this category:** If the slide dives deep into HOW the product works (that's `product-demo` or `technology`). Overview is the 30-second version.
**Example slugs:** `company-overview`, `mission-and-vision`, `what-we-do`, `elevator-pitch`
**Suggested Placement in Memo:** Place at the top of the Executive Summary or Business Overview section, before the written analysis begins. Sets visual context for the reader.

### problem
**Use for:** Market-level problems, industry inefficiencies, systemic issues, "why now" slides, status quo breakdowns, macro trends creating the opportunity
**Visual signals:** Industry statistics about current failures, systemic inefficiency diagrams, macro trend charts, regulatory gap illustrations, "the world is broken because..." framing
**Not this category:** If the slide focuses on a specific CUSTOMER'S daily frustrations (that's `customer-pain`). If it focuses on market SIZE rather than market PAIN (that's `market-size`). Problem is about what's broken at the market/industry level.
**Example slugs:** `industry-inefficiency`, `status-quo-failures`, `why-now`, `market-problem-scale`, `regulatory-gap`
**Suggested Placement in Memo:** Place near the opening of the Business Overview or Origins section, before the company's solution is introduced. The problem sets up the "why this company exists" narrative.

### customer-pain
**Use for:** Specific customer pain points, user frustrations, day-in-the-life scenarios, customer quotes/testimonials about suffering, persona-level problems, workflow friction
**Visual signals:** Customer quotes, persona illustrations, "a day in the life" narratives, survey results about user frustrations, specific workflow breakdowns showing where users struggle, empathy maps
**Not this category:** If the slide describes a broad market or industry problem (that's `problem`). If it describes who the customer IS rather than what they suffer (that's `ideal-customer-profile`). Customer-pain is about the FELT experience of the end user.
**Example slugs:** `user-frustrations`, `customer-pain-points`, `day-in-the-life`, `workflow-friction`, `patient-burden`, `consumer-struggle`
**Suggested Placement in Memo:** Place in the Business Overview or Origins section, immediately after the market-level problem and before the solution. Grounds the abstract problem in real human experience.

### ideal-customer-profile
**Use for:** Target customer descriptions, buyer personas, customer segmentation, "who we sell to" slides, beachhead market definitions, customer demographic/firmographic breakdowns, ideal user profiles
**Visual signals:** Persona cards with demographics, customer segment matrices, firmographic breakdowns (company size, industry, role), "our ideal customer" framing, beachhead market diagrams, segment-by-segment targeting
**Not this category:** If the slide focuses on what the customer SUFFERS (that's `customer-pain`). If it shows actual customer logos as proof of traction (that's `traction`). ICP is about WHO the customer is and how segments are defined, not their pain or your relationship with them.
**Example slugs:** `target-persona`, `customer-segments`, `beachhead-market`, `buyer-profile`, `ideal-user`, `target-demographics`
**Suggested Placement in Memo:** Place in the Business Overview, Market Context, or Opening section, near where the go-to-market strategy or market opportunity is discussed. Helps the reader understand who the company is building for.

### solution
**Use for:** "How we solve it" slides, solution overview, value proposition summary, before-and-after comparisons showing the fix
**Visual signals:** Solution diagrams, "our approach" framing, benefit lists tied to the problems identified earlier, transformation narratives
**Not this category:** If showing actual product UI/screenshots (that's `product-demo`). If listing feature bullets without visual context (that's `value-proposition`). Solution is the conceptual "how we fix it."
**Example slugs:** `our-approach`, `solution-overview`, `how-it-works-summary`
**Suggested Placement in Memo:** Place in the Business Overview or Origins section, immediately after the problem/customer-pain discussion. The solution is the narrative bridge from "what's broken" to "what we built."

### product-demo
**Use for:** Product screenshots, UI mockups, app interfaces, dashboard views, demo walkthroughs, physical product photos
**Visual signals:** Actual screenshots of the product, annotated UI, device mockups (phone/laptop frames), physical product photography, packaging shots
**Not this category:** If it's a technical architecture diagram (that's `technology`). If it's a conceptual solution diagram without showing the actual product (that's `solution`). Product-demo means you can SEE the product.
**Example slugs:** `dashboard-ui`, `mobile-app-screens`, `product-packaging`, `demo-walkthrough`, `platform-interface`
**Suggested Placement in Memo:** Place in the Technology & Product or Offering section, inline near where specific product capabilities are described. If multiple product-demo screenshots exist, distribute them near their relevant feature descriptions rather than clustering them all together.

### value-proposition
**Use for:** Key benefits, feature highlights with value framing, "why us" slides, unique selling points, offering differentiators
**Visual signals:** Benefit lists with icons, feature-value pairings, "what you get" breakdowns, customer outcome promises
**Not this category:** If showing actual product UI (that's `product-demo`). If comparing against competitors (that's `competitive-positioning` or `competition-landscape`). Value-prop is about YOUR strengths, not relative positioning.
**Example slugs:** `key-benefits`, `why-choose-us`, `core-value-props`, `feature-highlights`
**Suggested Placement in Memo:** Place in the Business Overview, Offering, or Technology & Product section, near where the product's core value is articulated. Works well after the solution overview and before deeper technical detail.

### technology
**Use for:** Technical architecture diagrams, system diagrams, infrastructure, science/mechanism explanations, IP/patent summaries, R&D track records, platform capability overviews, API/integration diagrams
**Visual signals:** Architecture boxes-and-arrows, flow diagrams, scientific mechanism illustrations, patent filings, technical specifications, research publication lists, lab/R&D imagery
**Not this category:** If it's a product UI screenshot (that's `product-demo`). Technology is about the HOW and the underlying innovation, not the user-facing product.
**Example slugs:** `platform-architecture`, `science-mechanism`, `ip-portfolio`, `rd-track-record`, `system-diagram`, `enzyme-engineering-pipeline`
**Suggested Placement in Memo:** Place in the Technology & Product or Offering section, inline near where the underlying technology or IP is discussed. Architecture diagrams work best adjacent to technical explanations; R&D track records work near IP/defensibility discussions.

### business-model
**Use for:** Revenue model, how the company makes money, pricing tiers, subscription model diagrams, marketplace dynamics, monetization strategy
**Visual signals:** Revenue flow diagrams, pricing tables, subscription tier comparisons, marketplace two-sided diagrams, "how we monetize" framing
**Not this category:** If showing unit economics with specific margin numbers (that's `unit-economics`). Business-model is the STRUCTURE of how money flows; unit-economics is the specific NUMBERS.
**Example slugs:** `revenue-model`, `pricing-tiers`, `monetization-strategy`, `marketplace-dynamics`, `subscription-model`
**Suggested Placement in Memo:** Place in the Business Overview or Opening section, near where the company's monetization approach is described. Should appear after the product/solution is introduced but before traction metrics.

### unit-economics
**Use for:** Unit economics tables, margin breakdowns, COGS analysis, LTV/CAC ratios, contribution margin, per-unit profitability, gross margin calculations
**Visual signals:** Tables with dollar amounts and percentages, COGS line items, margin calculations, LTV:CAC ratios, per-unit or per-customer economics
**Not this category:** If showing company-level financial projections (that's `financials`). If showing pricing without cost structure (that's `business-model`). Unit-economics is about the math of individual transactions.
**Example slugs:** `unit-margins`, `ltv-cac-analysis`, `cogs-breakdown`, `per-unit-profitability`, `contribution-margin`
**Suggested Placement in Memo:** Place in the Traction & Milestones, Opening, or Funding & Terms section, near where the business's financial viability is discussed. Unit economics visuals are high-value for investors — place them prominently where margin analysis appears in the text.

### market-size
**Use for:** TAM/SAM/SOM diagrams, market size estimates, market growth charts, addressable market breakdowns, industry size statistics
**Visual signals:** Concentric circles (TAM/SAM/SOM), large dollar figures with "B" or "T" suffixes, market growth rate charts, industry sizing from research firms
**Not this category:** If the slide is about competitive dynamics WITHIN the market (that's `competitive-positioning`). Market-size is about how BIG the opportunity is.
**Example slugs:** `tam-sam-som`, `market-growth-trajectory`, `addressable-market`, `industry-sizing`
**Suggested Placement in Memo:** Place in the Market Context or Opportunity section, near where TAM/SAM/SOM or market growth is discussed. These visuals anchor the market sizing narrative — place them at the opening of the market discussion.

### competitive-positioning
**Use for:** Competitive positioning matrices, 2x2 quadrant charts, feature comparison grids where the company is highlighted, "where we sit" in the market
**Visual signals:** 2x2 matrices with company plotted, positioning maps, Gartner-style quadrants, feature comparison tables with checkmarks, "us vs. them" with the company winning
**Not this category:** If just listing competitors without positioning (that's `competition-landscape`). Competitive-positioning shows WHERE you sit relative to others.
**Example slugs:** `positioning-matrix`, `competitive-quadrant`, `feature-comparison`, `market-positioning-map`
**Suggested Placement in Memo:** Place in the Market Context or Opportunity section, near competitive analysis discussion. If both `competitive-positioning` and `competition-landscape` exist, place the landscape first (context) and positioning second (the company's advantage).

### competition-landscape
**Use for:** Competitor lists, competitive landscape overviews, market map showing all players, logos of competitors, competitor category breakdowns
**Visual signals:** Grid of competitor logos, market map with segments, lists of companies by category, landscape diagrams showing who does what
**Not this category:** If the company is positioned against competitors in a matrix (that's `competitive-positioning`). Competition-landscape is a MAP of the field; competitive-positioning is WHERE YOU are on that map.
**Example slugs:** `competitor-overview`, `market-landscape`, `competitive-field`, `industry-players`
**Suggested Placement in Memo:** Place in the Market Context or Opportunity section, at the start of the competitive analysis subsection. Provides the field overview before the company's specific positioning is discussed.

### traction
**Use for:** Growth metrics, revenue charts, user/customer growth, KPI dashboards, milestone timelines, key achievements, MRR/ARR charts, engagement metrics
**Visual signals:** Line charts going up-and-to-the-right, bar charts showing growth, metric callouts with impressive numbers, milestone checklists, "progress to date" framing
**Not this category:** If showing financial projections into the FUTURE (that's `financials`). Traction is about what has ALREADY happened.
**Example slugs:** `revenue-growth`, `user-acquisition`, `key-milestones`, `kpi-dashboard`, `mrr-progression`, `customer-growth`
**Suggested Placement in Memo:** Place in the Traction & Milestones or 12Ps Scorecard Summary section, inline near the metrics being discussed. Growth charts are among the most valuable visuals for investors — place them where the text references the same metrics.

### team
**Use for:** Team slides, founder photos, advisor headshots, org charts, team background summaries, key hire highlights
**Visual signals:** Headshot photos, name/title/bio layouts, university and company logos for backgrounds, advisory board grids
**Not this category:** Rarely ambiguous. If a slide lists team members as part of a broader "why us" argument, it's still `team` if photos/bios are the primary content.
**Example slugs:** `founding-team`, `leadership-bios`, `advisory-board`, `key-hires`, `team-backgrounds`
**Suggested Placement in Memo:** Place at the top of the Team or Organization section, before the written team analysis. Team photos give the memo a personal, human dimension — they should be the first thing the reader sees in that section.

### go-to-market
**Use for:** GTM strategy, customer acquisition channels, distribution strategy, sales motion, marketing funnel, launch plan, partnership/distribution channels
**Visual signals:** Funnel diagrams, channel strategy layouts, customer journey maps, partnership logos, distribution network diagrams, launch timeline
**Not this category:** If showing traction RESULTS from GTM efforts (that's `traction`). GTM is about the PLAN and STRATEGY for reaching customers.
**Example slugs:** `gtm-strategy`, `acquisition-channels`, `distribution-plan`, `sales-motion`, `launch-roadmap`
**Suggested Placement in Memo:** Place in the Traction & Milestones, Business Overview, or Opening section, near where the go-to-market strategy is described. Funnel diagrams and channel strategies work best adjacent to the text explaining the company's distribution approach.

### fundraising
**Use for:** Round details, amount raising, use of funds breakdowns, cap table snapshots, investor logos, round terms, ask slides
**Visual signals:** Dollar amounts for the raise, pie charts for fund allocation, investor logo grids, term highlights, "the ask" framing, progress bars showing raise status
**Not this category:** If showing company financial performance (that's `traction` or `financials`). Fundraising is specifically about the capital raise itself.
**Example slugs:** `the-ask`, `use-of-funds`, `round-details`, `investor-roster`, `cap-table-summary`, `pre-seed-allocation`
**Suggested Placement in Memo:** Place in the Funding & Terms section, near where the round details and terms are discussed. Use-of-funds diagrams are especially useful placed right after the round size is mentioned in text.

### financials
**Use for:** Financial projections, P&L forecasts, revenue projections, burn rate, runway analysis, financial models, forward-looking financial charts
**Visual signals:** Multi-year projection tables, forecast charts, P&L summaries, runway calculations, "path to profitability" charts
**Not this category:** If showing historical traction metrics (that's `traction`). If showing per-unit economics (that's `unit-economics`). Financials is about forward-looking financial projections and company-level financial health.
**Example slugs:** `revenue-projections`, `financial-forecast`, `path-to-profitability`, `burn-and-runway`
**Suggested Placement in Memo:** Place in the Funding & Terms or Traction & Milestones section, near where financial projections or runway is discussed. Projection charts work well after historical traction data to show the forward trajectory.

### partnerships
**Use for:** Strategic partner logos, distribution partnerships, integration partners, ecosystem diagrams, channel partner grids, customer logos (when used to show partnerships not traction)
**Visual signals:** Partner logo grids, ecosystem/integration diagrams, co-branded content, "who we work with" framing
**Not this category:** If showing customer logos to demonstrate traction/adoption (that's `traction`). Partnerships implies strategic relationships, not just customers.
**Example slugs:** `strategic-partners`, `integration-ecosystem`, `distribution-partners`, `key-relationships`
**Suggested Placement in Memo:** Place in the Traction & Milestones, Business Overview, or Opening section, near where strategic relationships or distribution advantages are discussed.

### branding
**Use for:** Brand positioning, packaging design, D2C website screenshots, brand identity, marketing materials, consumer-facing brand story
**Visual signals:** Brand mockups, packaging renders, website screenshots showing brand (not product functionality), lifestyle imagery, brand guidelines elements
**Not this category:** If showing actual product functionality in the UI (that's `product-demo`). Branding is about how the company PRESENTS itself to consumers, not what the product does.
**Example slugs:** `brand-positioning`, `packaging-design`, `d2c-website`, `brand-identity`, `consumer-brand-story`
**Suggested Placement in Memo:** Place in the Technology & Product, Offering, or Business Overview section, near where the company's market positioning or consumer strategy is discussed. Packaging and brand visuals work well after the product is described but before traction data.

### vision
**Use for:** Big-picture vision slides, long-term roadmap, "where we're going" narratives, future state diagrams, multi-phase expansion plans, platform evolution
**Visual signals:** Timeline arrows stretching into the future, phased expansion diagrams, "today → tomorrow → future" framing, ambitious scope statements, moonshot narratives
**Not this category:** If it's a concrete product roadmap with feature dates (that's `traction` with a `roadmap` slug). Vision is about the ASPIRATIONAL big picture.
**Example slugs:** `long-term-vision`, `platform-evolution`, `expansion-roadmap`, `future-state`, `big-picture`
**Suggested Placement in Memo:** Place in the Investment Thesis, Closing Assessment, or Executive Summary section, near where the long-term opportunity is articulated. Vision visuals reinforce the "why this matters" narrative at the end of the memo.

### impact
**Use for:** Social impact, ESG metrics, sustainability data, "why this matters" beyond profit, environmental/health outcomes
**Visual signals:** Impact statistics, sustainability metrics, health outcome data, UN SDG alignment, environmental benefit quantification
**Not this category:** If impact metrics are used primarily to show traction (that's `traction`). Impact is about the broader significance beyond business metrics.
**Example slugs:** `social-impact`, `health-outcomes`, `sustainability-metrics`, `global-impact`
**Suggested Placement in Memo:** Place in the Investment Thesis, Closing Assessment, or Market Context section, near where broader significance or societal value is discussed. Impact visuals strengthen the "why this matters beyond returns" argument.

---

## Ambiguity Rules

When a slide could fit multiple categories, use these rules to pick one:

1. **Specific beats general.** A slide with a unit economics table AND a product photo is `unit-economics` — the table is the primary analytical content; the photo is decoration.

2. **Data beats narrative.** A slide with growth numbers AND a "vision" headline is `traction` — the numbers are what matters for the investment memo.

3. **Title/header is a strong signal.** If the slide says "Unit Economics" at the top, classify it as `unit-economics` even if it also shows product images. Deck creators label their slides intentionally.

4. **Distinguish problem from customer-pain.** "The metabolic health industry relies on outdated enzyme technology" = `problem` (systemic, market-level). "Consumers take 6 pills a day and still feel bloated" = `customer-pain` (personal, felt experience). Market dysfunction vs. human suffering.

5. **Distinguish customer-pain from ideal-customer-profile.** "Our users struggle with X" = `customer-pain` (what they suffer). "Our target customer is a health-conscious millennial earning $80K+" = `ideal-customer-profile` (who they are). Pain vs. identity.

6. **Distinguish problem from market-size.** "50% of Americans struggle with metabolic health" as a pain point = `problem`. "$340B metabolic health market growing 12% CAGR" = `market-size`. Pain vs. dollars.

7. **Distinguish traction from financials.** Historical metrics = `traction`. Forward projections = `financials`. If a slide shows both, classify based on which takes more visual space.

8. **Distinguish product-demo from branding.** If you can see the product's UI/functionality = `product-demo`. If you see the product's packaging, lifestyle positioning, or marketing = `branding`.

9. **Distinguish solution from product-demo.** Conceptual "how it works" diagram = `solution`. Actual screenshot of the working product = `product-demo`.

10. **Distinguish competitive-positioning from competition-landscape.** If the company is ON the chart = `competitive-positioning`. If it's a map of the whole field = `competition-landscape`.

11. **Distinguish business-model from unit-economics.** How money flows (structure) = `business-model`. What the margins are (numbers) = `unit-economics`.

12. **When genuinely ambiguous**, prefer the category that best serves the investment memo. An investor cares more about `unit-economics` than `product-demo`, more about `traction` than `branding`.

---

## Section Mapping Reference

These are the memo sections each category typically maps to. The deck analyst uses this to route screenshots into the correct memo sections.

### Direct Investment (10-section)

| Category | Primary Section | Secondary Section |
|---|---|---|
| overview | Executive Summary | Business Overview |
| problem | Business Overview | Market Context |
| customer-pain | Business Overview | Market Context |
| ideal-customer-profile | Market Context | Business Overview |
| solution | Business Overview | Technology & Product |
| product-demo | Technology & Product | — |
| value-proposition | Business Overview | Technology & Product |
| technology | Technology & Product | — |
| business-model | Business Overview | Traction & Milestones |
| unit-economics | Traction & Milestones | Funding & Terms |
| market-size | Market Context | — |
| competitive-positioning | Market Context | Risks & Mitigations |
| competition-landscape | Market Context | — |
| traction | Traction & Milestones | — |
| team | Team | — |
| go-to-market | Traction & Milestones | Business Overview |
| fundraising | Funding & Terms | — |
| financials | Funding & Terms | Traction & Milestones |
| partnerships | Traction & Milestones | Business Overview |
| branding | Technology & Product | Business Overview |
| vision | Investment Thesis | Executive Summary |
| impact | Investment Thesis | Market Context |

### Direct Early-Stage 12Ps

| Category | Primary Section | Secondary Section |
|---|---|---|
| overview | Executive Summary | Opening |
| problem | Origins | — |
| customer-pain | Origins | Opening |
| ideal-customer-profile | Opening | Opportunity |
| solution | Origins | Opening |
| product-demo | Offering | — |
| value-proposition | Offering | Opening |
| technology | Offering | Origins |
| business-model | Opening | — |
| unit-economics | Opening | Funding & Terms |
| market-size | Opportunity | — |
| competitive-positioning | Opportunity | Risks |
| competition-landscape | Opportunity | — |
| traction | 12Ps Scorecard Summary | — |
| team | Organization | — |
| go-to-market | Opening | — |
| fundraising | Funding & Terms | — |
| financials | Funding & Terms | — |
| partnerships | Opening | Offering |
| branding | Offering | Opening |
| vision | Closing Assessment | Executive Summary |
| impact | Closing Assessment | Opportunity |

### Fund Commitment

| Category | Primary Section | Secondary Section |
|---|---|---|
| overview | Executive Summary | Fund Strategy & Thesis |
| ideal-customer-profile | Fund Strategy & Thesis | Portfolio Construction |
| traction | Track Record Analysis | — |
| team | GP Background & Track Record | — |
| market-size | Fund Strategy & Thesis | — |
| competitive-positioning | Value Add & Differentiation | — |
| financials | Fee Structure & Economics | — |
| fundraising | Fee Structure & Economics | LP Base & References |
| partnerships | LP Base & References | — |
| vision | Fund Strategy & Thesis | — |

---

## Placement Rules

These rules govern how the `inject_deck_images` agent places screenshots into memo sections. They exist to prevent image spam and ensure each screenshot adds value where it appears.

### Rule 1: Maximum Two Placements Per Image

Every deck screenshot may appear in the memo **at most twice**:

1. **Primary placement**: In the body of its best-matching section, under the most relevant header
2. **Key Slides gallery**: Optionally in the `## Key Slides` section at the bottom of the Executive Summary

If an image has already been placed in its primary section AND in Key Slides, it must not appear anywhere else. The injection agent must track a global placement count per image path and refuse to place any image a third time.

### Rule 2: One Primary Section Per Image

Each screenshot is assigned to exactly **one primary section** based on the Section Mapping tables above. The "Primary Section" column determines where the image goes. The "Secondary Section" column is for fallback only — use it when the primary section file doesn't exist or when the primary section has no relevant header to place the image under.

An image must **never** be placed in both the Primary and Secondary sections. It gets one body placement, period.

### Rule 3: Place Under the Most Relevant Header

Do NOT prepend all images at the top of a section file. Instead:

1. Parse the section's markdown to find all headers (`#`, `##`, `###`, etc.)
2. For each image, find the header whose text best matches the image's category and slug
3. Insert the image on the line immediately after that header (before the paragraph text)

**Matching heuristics** (in priority order):
- Exact keyword match: a `team` image goes under a `### Team` or `### Founding Team` header
- Category match: a `unit-economics` image goes under `### Unit Economics` or `### Margins & COGS`
- Slug match: an image with slug `ltv-cac-analysis` goes under a header mentioning "LTV", "CAC", or "customer acquisition cost"
- If no header matches well, place the image after the first `##` header in the section (not before it)

**Example — CORRECT placement:**
```markdown
## Organization

### Founding Team

![Team slide from pitch deck — founding-team](deck-screenshots/page-12-team-founding-team.png)

The founding team brings deep expertise in enzyme engineering...
```

**Example — INCORRECT placement (do not do this):**
```markdown
![Team slide from pitch deck](deck-screenshots/page-12-team.png)
![Product slide from pitch deck](deck-screenshots/page-02-product.png)
![Market slide from pitch deck](deck-screenshots/page-10-market.png)

## Organization

### Founding Team

The founding team brings deep expertise...
```

### Rule 4: Executive Summary Key Slides Gallery

The `01-executive-summary.md` file gets a special `## Key Slides` section appended at its end. This gallery provides a visual overview of the most important deck content for readers who want the highlights.

**What goes in Key Slides:**
- Select up to **5 images** maximum from the full set of deck screenshots
- Prioritize high-signal categories: `traction`, `unit-economics`, `team`, `market-size`, `competitive-positioning`, `product-demo`
- Skip low-signal categories: `overview`, `branding`, `vision`, `impact`
- Each image in Key Slides still counts toward its 2-placement maximum

**Format:**
```markdown
## Key Slides

![Traction — revenue-growth (Slide 7)](deck-screenshots/page-07-traction-revenue-growth.png)

![Unit Economics — unit-margins (Slide 14)](deck-screenshots/page-14-unit-economics-unit-margins.png)

![Team — founding-team (Slide 12)](deck-screenshots/page-12-team-founding-team.png)
```

The `## Key Slides` header is created by the `inject_deck_images` agent, NOT by the writer or enrichment agents. No other agent should create or modify this section.

### Rule 5: Scorecard and Summary Sections Get No Images

Sections that synthesize across the entire memo should NOT receive deck screenshots:
- `08-12ps-scorecard-summary.md`
- `10-recommendation.md`
- `10-closing-assessment.md`
- `09-investment-thesis.md`

These sections are analytical summaries. Deck screenshots belong in the content sections they summarize, not in the summaries themselves.

---

## Slides to Skip

Do NOT extract screenshots for these slide types — they have no visual value for the investment memo:

- **Title/cover slides** — just the company name and logo, no analytical content
- **"Thank you" / closing slides** — no content
- **Table of contents / agenda slides** — just navigation
- **Dense text-only slides** — bullet points without visual elements (the text is already captured by text extraction)
- **Legal disclaimers** — boilerplate
- **Appendix divider slides** — no content
- **Contact information slides** — just email/phone
