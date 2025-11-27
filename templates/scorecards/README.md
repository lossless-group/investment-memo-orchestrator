# Scorecard Templates

Proprietary scoring frameworks for systematic investment evaluation.

## Directory Structure

```
scorecards/
├── README.md
├── lp-commits_emerging-managers/       # LP commitments to emerging VC managers
│   ├── hypernova-scorecard.yaml        # Machine-readable (for agents)
│   └── hypernova-scorecard.md          # Human-readable (for manual use)
│
├── lp-commits_established-funds/       # (Planned) LP commitments to established funds
├── direct_seed/                        # (Planned) Direct seed investments
├── direct_series-a/                    # (Planned) Direct Series A investments
└── direct_growth/                      # (Planned) Direct growth investments
```

## Two Formats Per Scorecard

| Format | Purpose | Used By |
|--------|---------|---------|
| **YAML** | Machine-readable template | Scorecard Agent, validation |
| **Markdown** | Human-readable reference | Team onboarding, manual scoring, LP sharing |

## Usage

### Automated (System)
Specify in company data:
```json
{
  "type": "fund",
  "scorecard_template": "lp-commits_emerging-managers/hypernova-scorecard"
}
```

### Manual (Human)
Open the `.md` file for the scoring framework and rubrics.
