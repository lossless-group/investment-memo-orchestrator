---
name: setup-new-firm
description: >-
  End-to-end procedure for onboarding a new VC firm into the memopop
  investment-memo orchestrator. Five phases — (1) brand acquisition via
  Firecrawl with analyst-override on the primary-color heuristic, (2)
  firm-directory scaffolding under io/<firm>/ with the canonical
  configs/templates/assets/deals layout and the strict brand-config YAML
  schema, (3) investment-framework outline selection (typically forking an
  existing outline like alpha-partners-7-Cs and customizing — section
  reordering, preambles, preferred-source swaps, stage-aware fallbacks),
  (4) first deal setup with deck-input handling (DocSend capture via
  cli/capture_docsend.py, ImageMagick screenshot stitching for NDA-gated
  decks, deal-config JSON, codified Sources.md), and (5) optional
  private-repo split via gh CLI with submodule re-add for confidential firm
  data. Use whenever the user says "I have a new client/firm/VC," "set up
  <firm name>," "add <firm> to memopop," "we need brand configs for <firm>,"
  or pastes a VC firm's URL with implicit intent to generate memos for
  them. Encodes lessons from the alpha-jwc onboarding on 2026-06-07 —
  don't trust Firecrawl's primary-color field blindly, verify against the
  logo palette; the deck analyst will extract DocSend watermarks as the
  company name if you feed it watermarked screenshots; agents leak
  firm-geography context into company-analysis prose (Alpha JWC = Indonesia
  VC → Portland-OR company memo gained Indonesia/rupiah risks);
  citation-enrichment fabricates example.com URLs even in codified-source
  mode — codified Sources.md only constrains the upstream researcher, not
  the downstream enricher. Cross-references [[crawl-fetch-ingest]] for
  portfolio/team data, [[sources-md-curation]] for the Sources.md file
  mechanics, and the open issues in context-v/issue-resolution/
  ([[Limiting-or-Omitting-Investor-Judgement]],
  [[Competitive-Research-Generated-But-Not-In-Prose]],
  [[Including-Comparable-Exits-Valuations-IPOs]]) for known failure modes
  the new firm's first run will hit.
---

# Setting Up a New Firm in MemoPop

> The analyst has a new VC client. The orchestrator needs to know who they are
> (brand), how they think (outline), and what the first deal looks like
> (deck + sources). This skill is the procedure that gets a new firm from
> "we have their URL" to "ready to run `python -m src.main` for their first
> deal," ideally in one focused session.

## When this skill activates

The signal pattern is **new firm + intent to generate memos**:

- "I have a new client — `<firm-url>`"
- "Set up `<firm name>` in memopop"
- "We don't yet have brand configs for `<firm>`"
- "Add `<firm>` and let's run their first deal through"
- Plain URL paste of a VC homepage in a conversation about memo generation

Do NOT activate this skill for:

- Adding a new **deal** to an existing firm (no skill needed — copy the deal-JSON pattern from a sibling deal directory).
- Modifying an existing firm's outline (use `[[sources-md-curation]]` mechanics for source-file edits; outline edits are direct YAML work).
- Per-deal source curation (delegate to `[[sources-md-curation]]` or `[[user-adds-adhoc-sources]]`).

## The five phases

```
Phase 1 — Brand acquisition       (~10 min, Firecrawl + analyst override)
Phase 2 — Directory scaffolding   (~5 min, fixed layout)
Phase 3 — Outline customization   (~15-60 min, analyst-driven)
Phase 4 — First deal setup        (~15-30 min, deck handling varies)
Phase 5 — Private-repo split      (~5 min, optional)
```

Run them in order. Phases 1–4 are usually one session; Phase 5 is often a
follow-up after the first run looks reasonable.

---

## Phase 1 — Brand acquisition

The firm's homepage is the source of truth for colors, fonts, and logos.
Firecrawl's `branding` format does most of the work but **its `primary:`
field is unreliable for VC sites** — it tends to pick CTA-button colors over
brand-identity colors. Always sanity-check against the logo palette.

### Step 1.1 — Fetch the homepage with the branding extractor

```python
# Via the firecrawl MCP server
firecrawl_scrape(
    url="https://<firm-homepage>",
    formats=["branding"]
)
```

Read carefully:

- `branding.colors.primary` / `secondary` / `accent` — candidates, not truth.
- `branding.fonts[]` — body + heading families; usually correct.
- `branding.images.logo` — often a `data:image/...;base64,...` data URI for
  WordPress/Divi sites. Decode and save.
- `branding.images.favicon` — usually a direct URL; `curl -o` it.

### Step 1.2 — Reconcile primary color against the logo palette

Look at the actual logo image. If the dominant color in the logo is different
from Firecrawl's `primary:`, **trust the logo, not Firecrawl**. Concrete example:

> Alpha JWC's homepage has amber (`#FFAC00`) CTA buttons and a deep-navy
> (`#13294B`) wordmark logo. Firecrawl picked `primary: #FFAC00` because
> button frequency dominates the CSS. The brand-identity color is the navy.
> Final mapping: `primary: #13294B`, `secondary: #FFAC00`, `accent: #8B1B40`
> (their burgundy 10th-anniversary palette accent).

### Step 1.3 — Save logo + favicon

```bash
# For base64 data URIs:
python3 -c "
import base64, urllib.parse
uri = '<data:image/png;base64,...>'  # or image/svg+xml;utf8,<urlencoded>
# For SVG-utf8: urllib.parse.unquote(uri.split(',',1)[1])
# For base64:   base64.b64decode(uri.split(',',1)[1])
open('assets/trademark__<Firm>--Brand.png', 'wb').write(decoded_bytes)
"
curl -sL -o assets/favicon__<Firm>--Brand.png "<favicon-url>"
```

Naming convention is load-bearing for the downstream brand-application step.
Match the pattern from `io/alpha-partners/assets/`:

```
trademark__<Firm>--Brand.png         ← light-mode default
trademark__<Firm>--Dark-Mode.svg     ← dark-mode (when available)
favicon__<Firm>--Brand.png
```

### Phase 1 anti-patterns

- **Don't accept Firecrawl's primary blindly.** Always look at the logo.
- **Don't scrape colors from inline-base64 logos themselves** — the palette
  is encoded but parsing PNGs to extract dominant colors adds complexity for
  little gain. Eyeballing the logo + comparing to Firecrawl's candidates is
  faster and more honest.
- **Don't fetch the homepage with `firecrawl_scrape(formats=["markdown"])`
  hoping to find the logo URL** — most modern VC sites inline the logo as
  base64 in the rendered HTML, and the markdown rendering loses the data URI.
  Use `formats=["branding"]` specifically.

---

## Phase 2 — Directory scaffolding

The orchestrator expects every firm under `io/<firm>/` to follow a fixed
layout. Deviating breaks downstream pipeline assumptions.

### Canonical layout

```
io/<firm-slug>/
├── README.md                          ← what's in here, sensitivity notes
├── .gitignore                         ← canonical entries below
├── versions.json                      ← starts as `{}`; pipeline writes here
├── configs/
│   └── brand-<firm-slug>-config.yaml  ← THE brand-application source
├── assets/
│   ├── trademark__<Firm>--Brand.png
│   ├── favicon__<Firm>--Brand.png
│   └── fonts/                         ← (empty unless custom fonts dropped)
├── templates/
│   ├── outlines/                      ← firm-specific memo outlines
│   └── scorecards/                    ← firm-specific scorecards
└── deals/                             ← per-deal subdirectories (Phase 4)
```

### Brand config YAML schema (strict)

Mirror `io/alpha-partners/configs/brand-alpha-partners-config.yaml`. The
schema is consumed by `src/branding.py` — extra fields are tolerated but the
following keys are required exactly:

```yaml
company:
  name: <Firm Full Legal Name>
  tagline: <one-sentence positioning>
  confidential_footer: This document is confidential and proprietary to {company_name}.
colors:
  primary: '#XXXXXX'        # the navy/blue/dark from the LOGO
  secondary: '#XXXXXX'      # the accent/CTA color
  accent: '#XXXXXX'
  text_dark: '#1A2332'      # body text
  text_light: '#6B7280'     # muted text
  background: '#FFFFFF'
  background_alt: '#F7F8FA'
colors_dark:                # dark-mode variants (invert primary/secondary)
  primary: '#XXXXXX'
  secondary: '#XXXXXX'
  accent: '#XXXXXX'
  text_dark: '#F7F7F7'
  text_light: '#9CA3AF'
  background: '#0E1A33'
  background_alt: '#16294B'
fonts:
  family: <body font name>
  fallback: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif
  google_fonts_url: https://fonts.googleapis.com/css2?family=...
  weight: 400
  header_family: <heading font name>
  header_fallback: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif
  header_google_fonts_url: https://fonts.googleapis.com/css2?family=...
  header_weight: 700
logo:
  light_mode: io/<firm-slug>/assets/trademark__<Firm>--Brand.png
  dark_mode: io/<firm-slug>/assets/trademark__<Firm>--Brand.png
  width: 180px
  height: 60px
  alt: <Firm> Logo
```

### Canonical .gitignore

```gitignore
__pycache__/
*.pyc
.venv/
.DS_Store
Thumbs.db

# Raw deck captures — the canonical input is the stitched PDF in inputs/.
# Loose screenshots at the deal root are redundant and bloat the repo.
deals/*/Screenshot *.png
deals/*/Screen Shot *.png

# Intermediate working files (uncomment if you don't want to track them)
# deals/*/outputs/
# deals/*/inputs/dataroom/
```

The `Screenshot *.png` pattern uses the Unicode narrow no-break space
(`U+202F`) that macOS screenshots use by default — but standard
filename-glob in `.gitignore` matches it as a regular `*` wildcard, so the
literal pattern with a regular space works.

### versions.json

Start as `{}`. The pipeline mutates it on every run.

### README.md

Use `io/alpha-jwc/README.md` as a structural template. Sections to include:

- One-line confidentiality header
- "How it's consumed" — submodule mount point under
  `apps/memopop-orchestrator/io/<firm>/`
- "Directory layout" — the canonical structure with notes
- "Investment framework" — the firm's outline summary
- "Branding" — color/font choices with rationale
- "Deal status" table — populated as deals come in
- "Submodule lifecycle (notes for re-cloning)" — the
  `git submodule add ...` recipe
- "Sensitivity notes" — what's confidential, what's not

---

## Phase 3 — Outline customization

VC firms each have a preferred frame for evaluating opportunities. The
orchestrator's `templates/outlines/` system supports per-firm outlines that
override the global default. Three paths:

1. **Use the global default** (`templates/outlines/direct-investment.yaml`) —
   fastest, but the firm reads the memo and immediately notices the framing
   isn't theirs.
2. **Fork an existing firm outline** (most common) — copy
   `alpha-partners-7-Cs-memo-template.yaml` or another firm's, rename, and
   customize.
3. **Author from scratch** — only if the firm has a published framework that
   doesn't compose with any existing outline.

### The fork-and-customize pattern (typical case)

```bash
cp io/alpha-partners/templates/outlines/alpha-partners-7-Cs-memo-template.yaml \
   io/<firm>/templates/outlines/<firm>-7Cs-customized.yaml
```

Then iterate with the analyst on what to change. Common customizations,
from the alpha-jwc case:

- **Section reordering** — Alpha JWC wanted Risks + Diligence front-loaded
  as sections 1–2, with the 7 Cs sliding to 3–9. Renumbering touches:
  - `sections[].number`
  - `sections[].filename` (the `NN-` prefix)
  - `cross_section_requirements.narrative_flow.sequence`
- **Verbatim preambles** — Alpha JWC supplied analyst-authored preamble text
  for Risks and Diligence sections to appear verbatim at the top. Implement
  by adding a `preamble:` field on the section + embedding the preamble text
  in the `description:` (so the LLM sees it) + listing
  `"Preamble paragraph rendered verbatim at top of section"` in
  `section_vocabulary.required_elements` + adding a validation criterion.
- **Stage-aware fallbacks** — For early-stage firms, sections like CAGR and
  Cash on Cash Return Probability won't have own-company data. Add an
  explicit "Stage-aware fallback" paragraph in the section's `description:`
  telling the writer to pivot to category-level evidence (public + growth-
  stage comps in the same sector/geography) rather than fabricate company
  numbers.
- **Preferred-source swaps** — Replace the source list with firm-relevant
  databases. SEA-focused firms get `@dealstreetasia`, `@techinasia`, `@e27`;
  US growth-stage firms get `@pitchbook`, `@sacra`, `@cbinsights`.
- **Recommendation lexicon** — Default is `PASS / CONSIDER / COMMIT`. Some
  firms use different verdict terms. Update
  `vocabulary.recommendation.required_terms`.
- **Mode emphasis** — Default supports `consider` (prospective) and
  `justify` (retrospective). If a firm only ever runs one mode, mark the
  other in `metadata.compatible_modes` for clarity (does not enforce).

### Renumbering sed pattern (when reordering sections)

For renumbering N existing sections to start at offset K:

```bash
# Reverse order to avoid double-renumbering (e.g., 1→3, 2→4 — if you ran 1→3
# first, then 3→5 would catch your renamed 1.)
for old in 7 6 5 4 3 2 1; do
  new=$((old + 2))
  sed -i '' "s/^  - number: ${old}$/  - number: ${new}/" "$OUTLINE"
  sed -i '' "s/filename: \"0${old}-/filename: \"0${new}-/" "$OUTLINE"
done
```

### Phase 3 anti-patterns

- **Don't reshape the section taxonomy mid-run.** Per AGENTS.md §1 and
  CLAUDE.md architectural direction #3, the outline is the section
  taxonomy contract. Finalize it in Phase 3, before Phase 4.
- **Don't add a `Team` section to a 7Cs derivative without thinking about
  where it folds.** The 7 Cs treat team quality implicitly (Capital
  Syndicate for investors, Category Leadership for founder-market-fit).
  Alpha JWC decided team affiliations land in Category Leadership.
- **Don't trust the writer to render an analyst-supplied preamble verbatim
  without three reinforcements** (description + structure_template +
  validation_criteria) — see Phase 3's "Verbatim preambles" note above.
  Even with all three, LLM rendering of "verbatim" is probabilistic; for
  hard guarantees, add a small preamble-injection step in
  `src/agents/writer.py` that prepends `section.preamble + "\n\n"` to the
  saved output.

---

## Phase 4 — First deal setup

Each deal gets its own subdirectory under `io/<firm>/deals/<DealName>/`.
The directory name **matters operationally** — it's parsed for display, and
renaming it later requires sweeping multiple files (see "Operational rename
checklist" below).

### Naming convention

`<CompanyName>-Deck-<Stage>` — example: `Panthalassa-Deck-Series-B`. Confirm
the stage with the analyst before creating; getting it wrong forces a rename.

### Per-deal layout

```
deals/<DealName>/
├── <DealName>.json                    ← deal config (schema below)
├── inputs/
│   ├── <deck>.pdf                     ← canonical deck input
│   └── Sources.md                     ← codified analyst-curated sources
├── assets/
│   ├── trademark__<Company>--Light.svg
│   └── trademark__<Company>--Dark.svg
└── outputs/                           ← pipeline writes here per version
```

### Deal config JSON schema

```json
{
  "type": "direct",                                 // "direct" | "fund"
  "mode": "consider",                               // "consider" | "justify"
  "description": "<one-paragraph company summary for agent context>",
  "url": "<company-homepage>",
  "stage": "<Seed | Series A | Series B | ...>",
  "deck": "io/<firm>/deals/<DealName>/inputs/<deck>.pdf",
  "outline": "<firm>-7Cs-customized",               // resolves to io/<firm>/templates/outlines/<name>.yaml
  "trademark_light": "io/<firm>/deals/<DealName>/assets/trademark__<Company>--Light.svg",
  "trademark_dark":  "io/<firm>/deals/<DealName>/assets/trademark__<Company>--Dark.svg",
  "socials": {
    "x": "<https://x.com/...>",
    "linkedin": "<https://www.linkedin.com/company/...>"
  },
  "notes": "<analyst research-focus notes; flag firm-vs-company-geography mismatches here>"
}
```

The `notes:` field is where the analyst should call out anything that might
otherwise leak from firm-context into company-analysis prose. Example for
Panthalassa (Portland-OR company in an Alpha JWC = Indonesia VC firm
directory):

> *"Geography: US-headquartered; for Alpha JWC this is a cross-regional play
> rather than an Indonesia/SEA-domiciled deal — flag this in Risks
> (regulatory regime is US/maritime, not OJK/SEA)."*

Even with this note, **expect the writer to leak firm-geography into
company-risk reasoning**. See
`[[Limiting-or-Omitting-Investor-Judgement]]` and the broader pattern in
`context-v/issue-resolution/`.

### Company-level brand acquisition

For the company logo + tagline, compose with the `[[crawl-fetch-ingest]]`
skill — same Firecrawl `branding` extraction as Phase 1, but applied to the
company URL rather than the firm URL. Save extracted SVGs to
`deals/<DealName>/assets/` with the `trademark__<Company>--Light.svg` /
`--Dark.svg` naming convention.

### Deck input — three paths

The deck is the single most load-bearing input. Three paths depending on
what the analyst received:

#### Path A — Founder sent a PDF

Drop it in `inputs/<deck>.pdf`. Done.

#### Path B — DocSend without an NDA gate

Use `cli/capture_docsend.py` (built 2026-06-07; written for the alpha-jwc
Panthalassa deal):

```bash
source .venv/bin/activate
python cli/capture_docsend.py \
  --url "https://docsend.com/view/<deck-token>/d/<page-token>" \
  --out "io/<firm>/deals/<DealName>/inputs/<deck>.pdf"
# Optional flags: --email <addr> --max-pages N --keep-pngs
```

The script drives headless Chromium via Playwright, loops through slides,
screenshots each as PNG, stitches to PDF via PyMuPDF. Saves directly to
the pipeline's expected input location.

#### Path C — DocSend with an NDA gate (or analyst-captured screenshots)

The capture CLI cannot bypass NDA eSignature gates. The analyst captures
manually inside an authenticated browser, drops the screenshots in the deal
directory, and the skill stitches them:

```bash
cd io/<firm>/deals/<DealName>
ls Screenshot*.png | sort > /tmp/png-list.txt
magick @/tmp/png-list.txt -resize 1920x -quality 85 -compress JPEG \
  inputs/<deck>.pdf
```

**Critical:** verify the slide order before trusting it. macOS screenshot
timestamps sort lexicographically into capture order (which equals deck
order if the analyst paged forward through the deck). If the analyst paged
backwards, `ls -r` is correct. Spot-check the first and last slides against
the deck's slide indicator.

**Sizing:** `-resize 1920x -quality 85` produces ~10MB PDFs from ~150MB of
retina screenshots without losing analytical fidelity (Claude Vision
re-renders at 150 DPI internally either way).

### Sources.md initial seed

Set `mode: codified` in the frontmatter. Codified mode confines the
research-phase agents to the listed URLs — broad search is disabled.

The frontmatter schema, with concrete defaults:

```yaml
---
mode: codified
deal: <DealName>
firm: <firm-slug>
date_curated_initial: YYYY-MM-DD
date_curated_current: YYYY-MM-DD
at_semantic_version: 0.0.0.1
curated_by:
  - <Analyst Name>
augmented_with: Claude Code (Opus 4.7)
sources:
  - url: https://...
    title: "..."
    publisher: "..."
    published_date: YYYY-MM-DD
    sections: [<tag>, <tag>]
    rank: 1                       # 1 = primary; 2 = secondary
    sensitivity: citable_externally
    note: "Analyst-added <date>. <why this source matters>"
---
```

Section tags are the filename slug between the `NN-` prefix and `-research.md`
(e.g., `01-risks-research.md` → tag `risks`). Tag a source for every section
where it's load-bearing; over-tagging is fine.

See `[[sources-md-curation]]` for the full file-mechanics discipline.

### Phase 4 anti-patterns

- **Don't feed watermarked screenshots to the deck analyst.** It will
  extract the watermark as the company name. Alpha-jwc's first run produced
  `"company_name": "Dropbox (Content)"` because every captured slide had a
  Dropbox DocSend watermark bar at top. If the source is DocSend-watermarked,
  either (a) crop the watermark from each screenshot before stitching, or
  (b) live with the issue and manually fix the extracted company name in
  the pipeline state before the writer runs.
- **Don't expect codified `Sources.md` to prevent citation hallucination
  downstream.** Codified mode only constrains the upstream researcher.
  `citation_enrichment.py` still calls Perplexity Sonar Pro post-writing to
  add citations to drafted prose — and that pass fabricates `example.com`
  URLs at scale (alpha-jwc's v0.0.2 had 65 of them). See
  `[[Faked-Sources-from-Perplexity]]`.
- **Don't run with a deal directory whose name doesn't match the actual
  stage.** Renaming after the first run requires updating: `versions.json`
  key, deal JSON internal paths (`deck`, `trademark_light`,
  `trademark_dark`), `inputs/Sources.md` `deal:` field,
  `outputs/<v>/Sources-aggregated.md` `deal:` field + the H1 header. See
  "Operational rename checklist" below.

### Operational rename checklist

If the deal name has to change post-creation (e.g., Series-C → Series-B
because the actual round is different):

1. `mv deals/<OldName> deals/<NewName>`
2. `mv deals/<NewName>/<OldName>.json deals/<NewName>/<NewName>.json`
3. In that JSON, rewrite the `deck`, `trademark_light`, `trademark_dark`
   paths (any string containing `<OldName>` → `<NewName>`)
4. In `inputs/Sources.md` frontmatter, update `deal: <NewName>`
5. In every `outputs/<v>/Sources-aggregated.md`, update `deal: <NewName>`
   in frontmatter + the `# Aggregated Sources — <NewName>` H1
6. In `io/<firm>/versions.json`, rekey the `"<OldName>"` entry to `"<NewName>"`
   and update the `file_path` field in each history entry
7. **Don't bother** scrubbing `<OldName>` from generated prose inside
   `2-sections/*.md`, `1-research/*.md`, etc. — those are versioned outputs
   that affect re-runs, not future runs.

---

## Phase 5 — Private-repo split (optional but recommended for confidential firms)

If the firm directory contains NDA material, deal-stage confidential
analysis, or any data that shouldn't sit in the orchestrator's main repo
history, split it into its own private repo under `lossless-group` and
re-add as a submodule.

### Step 5.1 — Audit before pushing

```bash
cd io/<firm>
test -d .git && echo "ALREADY A REPO — investigate" || echo "clean, proceed"
find . -type f \( -name '.env*' -o -name '*.secrets*' \) 2>&1 | head
du -sh .
gh auth status
gh api user/memberships/orgs/lossless-group | head -3   # confirm admin/member
```

### Step 5.2 — Create the remote

```bash
gh repo create lossless-group/<firm>-secure \
  --private \
  --description "<Firm> firm data for the MemoPop investment-memo orchestrator. Consumed as a git submodule by apps/memopop-orchestrator/io/<firm>/."
```

### Step 5.3 — Init, commit, push

```bash
cd io/<firm>
git init -b main
git add .
git commit -m "initial commit: <firm>-secure firm data layer

<descriptive commit body>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"

git remote add origin https://github.com/lossless-group/<firm>-secure.git
git push -u origin main
```

### Step 5.4 — Verify on GitHub before continuing

Have the analyst load `https://github.com/lossless-group/<firm>-secure` in a
browser and confirm:

- Privacy: private (not public)
- Tree: README, configs/, templates/, assets/, deals/, versions.json all
  present
- No accidentally-included secrets

If anything's wrong (e.g., screenshots committed that shouldn't have been),
the cleanest fix on a fresh repo with one commit is **squash + force-push**:

```bash
git reset --soft $(git rev-list --max-parents=0 HEAD)
git commit --amend -m "<new clean message>"
git push --force-with-lease origin main
```

Force-push to `main` is normally risky; on a private brand-new repo with
zero collaborators and one commit, it's the right tool. Confirm with the
user before force-pushing if any doubt exists.

### Step 5.5 — Re-add as submodule

```bash
cd apps/memopop-orchestrator
rm -rf io/<firm>
git submodule add https://github.com/lossless-group/<firm>-secure.git io/<firm>
git commit -m "feat(io): add <firm> as private submodule"
git submodule update --init --recursive
```

Collaborators without read access to the private repo will see `io/<firm>`
empty on clone — that's the intended access boundary.

### Phase 5 anti-patterns

- **Don't push raw deck screenshots.** They're already in the stitched PDF
  and add ~100MB per deal. The canonical `.gitignore` from Phase 2 catches
  them automatically.
- **Don't force-push to `main` on a non-fresh repo.** This is only safe on a
  brand-new private repo with one commit and no collaborators. After that,
  use a deletion commit + regular push, or rewrite with `git filter-repo`
  and coordinate with collaborators.
- **Don't forget to update the parent repo's `.gitmodules` and submodule
  pointer commit**. `git submodule add` does this automatically; just don't
  skip the commit step in 5.5.

---

## Known failure modes to flag during onboarding

The first run on a new firm will hit several known issues that are documented
but not yet fixed. Warn the analyst proactively:

- **`example.com` fabricated URLs** — `citation_enrichment.py` invents
  citations at scale. Even with codified `Sources.md`. Track via
  `[[Faked-Sources-from-Perplexity]]` and the broader
  `[[Separating-Retrieval-from-Generation-in-Agent-Pipelines]]` exploration.
- **Firm-geography leaks into company analysis** — Alpha JWC's Indonesia/SEA
  context leaked into Panthalassa's (Portland-OR) Risks section: rupiah FX,
  OJK regulatory references, "Indonesian island markets." See
  `[[Limiting-or-Omitting-Investor-Judgement]]`.
- **Unsolicited `PASS` verdicts** — the writer renders PASS/CONSIDER/COMMIT
  in `mode: consider` even when the analyst is preparing the memo for IC
  advocacy. See `[[Limiting-or-Omitting-Investor-Judgement]]` for the
  resolution direction (`intent:` field on per-deal focal points).
- **Competitive landscape evaluator output orphaned from writer** — the
  competitive-landscape agent runs cleanly and produces named competitors,
  but the writer never sees its output. Category Leadership section ends up
  with `<needs-source>` markers despite having competitor data on disk. See
  `[[Competitive-Research-Generated-But-Not-In-Prose]]`.
- **No comparable-exits harvester** — Cash on Cash Return Probability
  section needs IPO/M&A comps to anchor scenarios; no dedicated agent
  produces them. See `[[Including-Comparable-Exits-Valuations-IPOs]]`.

---

## Composes with

- **`[[crawl-fetch-ingest]]`** — Phase 1 firm brand acquisition + Phase 4
  company brand acquisition both delegate to this skill's Firecrawl
  patterns.
- **`[[sources-md-curation]]`** — Phase 4 `inputs/Sources.md` authoring
  mechanics live there.
- **`[[user-adds-adhoc-sources]]`** — the post-run workflow when the analyst
  wants to weave new URLs into existing memo research without a full re-run.
- **`[[Per-Deal-Focal-Points]]`** (spec) — the proposed analyst-supplied
  emphasis layer that the orchestrator should consume per deal; will
  eventually compose with this skill when implemented.
- **`changelog-conventions`** — when a new firm is meaningful enough to
  warrant a changelog entry, follow that skill's format.

## See also

- `apps/memopop-orchestrator/io/README.md` — the firm-scoped IO pattern
  documentation
- `apps/memopop-orchestrator/io/alpha-partners/` — the reference fully-wired
  firm directory (use as visual template)
- `apps/memopop-orchestrator/io/alpha-jwc/` — the most recent onboarding
  (the worked example this skill was extracted from)
- `apps/memopop-orchestrator/cli/capture_docsend.py` — the DocSend → PDF
  capture CLI (written 2026-06-07 during the alpha-jwc onboarding)
