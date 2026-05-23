---
# Codified-source workflow template.
#
# Copy this file to `deals/<deal>/inputs/Sources.md` and replace the
# example sources with the URLs you trust for this specific deal. When
# the file is present with `mode: codified`, the pipeline will SKIP
# broad Tavily/Perplexity search and use ONLY the URLs you list here.
#
# Validation (URL accessibility, gated-publisher allow-list, hallucination
# patterns) still runs on these URLs — so even codified sources hit the
# Phase 1 verdict ladder. The point is to bypass the LLM's tendency to
# invent plausible URLs and replace it with sources you've eyeballed.

mode: codified                # set to "search" (or remove) to fall back to legacy broad search
deal: ExampleDeal
firm: example-firm
date_curated_initial: 2026-05-22
date_curated_current: 2026-05-22
at_semantic_version: 0.0.0.1
curated_by:
  - Your Name
augmented_with: Claude Code (Opus 4.7)

# Each entry MUST have a `url`. Other fields are optional but useful.
#
# - sections: tags this source supports. Matching is forgiving — `team`
#   matches a section named `Team` or `04-Team` or `04 Team`. Use the
#   section short names from your outline (templates/outlines/*.yaml).
# - rank: 1 = primary; higher numbers = lower priority. Sort order
#   downstream and likely future hedge-calibration signal.
# - sensitivity: `citable_externally` (default) or `internal_only` — the
#   writer/export step will use this to decide whether a citation can
#   appear in an externally-shared memo.
# - note: free-form analyst comment; appears in the research file.

sources:

  # ────────────── Tier-1 primary sources ──────────────

  - url: https://www.example-company.com/blog/series-a-announcement
    sections: [funding-terms, traction-milestones, executive-summary]
    rank: 1
    sensitivity: citable_externally
    note: "Series A announcement — primary."

  - url: https://github.com/example-company/example
    sections: [technology-product, traction-milestones]
    rank: 1
    sensitivity: citable_externally
    note: "Canonical repo — stars, license, recent commits."

  # ────────────── Trade press / news ──────────────

  - url: https://techcrunch.com/2024/04/25/example-raises-18m/
    sections: [funding-terms, executive-summary]
    rank: 2
    sensitivity: citable_externally
    note: "TechCrunch coverage of the Series A."

  # ────────────── Analyst / market data ──────────────

  - url: https://www.example-research.com/market-report-2024
    sections: [market-context, opportunity]
    rank: 2
    sensitivity: citable_externally
    note: "Market sizing for the vertical."

  # ────────────── Internal (firm-only) sources ──────────────
  # These appear in the per-memo corpus but the export step should
  # strip or redact them when the memo leaves the firm.

  # - url: file:///io/alpha-partners/corpus/notes/founder-call-2026-03-15.md
  #   sections: [team, flags]
  #   rank: 1
  #   sensitivity: internal_only
  #   note: "Internal partner call notes — DO NOT cite externally."
---

# Curated Sources — ExampleDeal

## How this list was built

Replace this with the analyst's notes on the curation process: what
bar was held, what sources were prioritized, what's missing.

## Excluded — examined and rejected

Record what was looked at and *why it was dropped* so the next iteration
(or another analyst) doesn't re-add the same junk. This is the
institutional-memory layer that the seven-runs-of-curation pain was
missing.

- `https://example-aggregator.com/...` — secondary regurgitation of the
  primary source above.
- `https://example-hallucination.com/...` — URL doesn't resolve;
  fabricated by an earlier LLM run.
- `https://example.com/...` — placeholder URL.

## Open questions / coverage gaps

Sections where I couldn't find good sources — these are the
`<needs-source>` candidates and the right input to the harvester's next
query strategy.

- *Revenue / ARR.* No primary source found.
- *Founder LinkedIn profiles.* TODO: confirm titles.
