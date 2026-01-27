---
title: "Vision for Production-Grade MemoPop Monorepo"
lede: "Strategic architecture for github.com/lossless-group/memopop-ai — a multi-app monorepo with Astro marketing site, Svelte web app, and Python agent orchestrator."
date_authored_initial_draft: 2025-12-26
date_authored_current_draft: 2025-12-26
date_authored_final_draft: null
date_first_published: null
date_last_updated: null
at_semantic_version: 0.0.1.2
usage_index: 1
publish: false
category: Specification
date_created: 2025-12-26
date_modified: 2025-12-26
tags: [Architecture, Monorepo, Astro, Svelte, Python, Bun, Vercel, Railway, SuperTokens, Baserow]
authors:
  - Michael Staton
augmented_with: "Claude Code with Claude Opus 4.5"
---

# Vision for Production-Grade MemoPop Monorepo

> Strategic architecture for `github.com/lossless-group/memopop-ai`

---

## The Problem

The current `investment-memo-orchestrator` is a powerful CLI tool buried in a larger monorepo. To become a production-grade product, MemoPop needs:

1. **A marketing presence** - SEO, content marketing, changelog, top-of-funnel
2. **A web interface** - Interactive UI for non-technical users (no CLI)
3. **The agent engine** - The Python orchestration system (what we have now)

These should live together as a coherent monorepo with shared tooling, versioning, and deployment infrastructure.

---

## Monorepo Structure

```
memopop-ai/
├── apps/
│   ├── memopop-site/              # Astro - Marketing & Content
│   ├── memopop-web-app/           # Svelte - Interactive Web App
│   └── memopop-agent-orchestrator/ # Python - AI Agent Engine
│
├── packages/
│   ├── shared-types/              # TypeScript types shared across apps
│   ├── shared-ui/                 # Svelte component library (if needed)
│   └── api-client/                # Client SDK for agent orchestrator API
│
├── infrastructure/
│   ├── docker/                    # Containerization
│   ├── terraform/                 # Cloud infrastructure (optional)
│   └── kubernetes/                # K8s manifests (optional)
│
├── docs/                          # Documentation site content
│
├── package.json                   # Bun workspaces config
├── bun.lockb                      # Bun lockfile
└── README.md
```

---

## The Three Apps

### 1. `memopop-site` — Astro Marketing Site

**Purpose**: Marketing, SEO, content, documentation, changelog UI

**Stack**:
- **Framework**: Astro (pure, no React)
- **Styling**: Tailwind CSS
- **Content**: MDX for docs, Astro content collections for changelog
- **Deployment**: Vercel, Netlify, or Cloudflare Pages

**Key Features**:
- Landing page (per existing spec in `MemoPop-Landing-Page-Specification.md`)
- Changelog with view toggling (Timeline/Cards/Releases like dark-matter)
- Documentation pages
- Blog/content marketing
- Pricing page
- SEO-optimized, static generation for speed

**Design Principles**:
- **NO REACT** - Pure Astro components, islands architecture only where needed
- **Content-first** - Static generation, MDX for rich content
- **Performance** - Lighthouse 95+, fast initial load
- **SSG by default** - Pre-render everything possible

**Routes**:
```
/                    # Landing page
/features            # Feature deep-dives
/pricing             # Pricing tiers
/changelog           # Changelog UI (Timeline/Cards/Releases views)
/changelog/[slug]    # Individual changelog entry
/docs                # Documentation
/docs/[...slug]      # Doc pages
/blog                # Content marketing
/blog/[slug]         # Blog posts
```

---

### 2. `memopop-web-app` — Svelte Web Application

**Purpose**: Interactive UI for memo generation, accessible via browser

**Stack**:
- **Framework**: SvelteKit (Svelte 5)
- **Styling**: Tailwind CSS
- **State**: Svelte stores, possibly Svelte Query for API state
- **Auth**: Clerk, Auth.js, or Supabase Auth
- **Deployment**: Vercel, Cloudflare, or Docker

**Key Features**:
- User authentication and workspace management
- Deck upload and analysis
- Real-time memo generation progress
- Section-by-section editing
- Export to HTML/PDF/DOCX
- Scorecard evaluation interface
- Firm branding configuration
- Usage dashboard and billing

**Design Principles**:
- **NO REACT** - Svelte components only, no React patterns
- **Progressive enhancement** - Works without JS where possible
- **Real-time feedback** - WebSocket/SSE for generation progress
- **Responsive** - Mobile-friendly for on-the-go review

**Routes**:
```
/app                 # Dashboard
/app/memos           # Memo list
/app/memos/new       # New memo wizard
/app/memos/[id]      # Memo detail/editor
/app/memos/[id]/edit # Section editing
/app/settings        # User/firm settings
/app/branding        # Brand configuration
/app/team            # Team management
/app/billing         # Subscription/usage
```

**Integration with Agent Orchestrator**:
- REST API for memo creation, status, retrieval
- WebSocket for real-time progress updates
- Signed URLs for deck upload to object storage
- Background job queue for long-running generations

---

### 3. `memopop-agent-orchestrator` — Python Agent Engine

**Purpose**: AI agent orchestration, the "brains" of MemoPop

**Stack**:
- **Language**: Python 3.11+
- **Framework**: LangGraph for agent orchestration
- **API**: FastAPI for REST endpoints
- **Queue**: Celery, Dramatiq, or simple Redis queue
- **Storage**: PostgreSQL (metadata), S3/R2 (files)
- **Deployment**: Docker, fly.io, Railway, or cloud VM

**Current State** (what we have):
- CLI-driven memo generation
- 12+ specialized agents
- Section-by-section processing
- Citation enrichment, fact-checking, validation
- Multi-brand export

**Production Evolution**:
- Wrap existing workflow in FastAPI
- Add authentication/authorization
- Add job queue for async generation
- Add PostgreSQL for memo metadata/history
- Add S3/R2 for deck storage and memo artifacts
- Add WebSocket for progress streaming
- Add API versioning

**API Endpoints** (proposed):
```
POST   /api/v1/memos                    # Create new memo job
GET    /api/v1/memos                    # List user's memos
GET    /api/v1/memos/{id}               # Get memo status/content
DELETE /api/v1/memos/{id}               # Delete memo
POST   /api/v1/memos/{id}/sections/{n}  # Improve specific section
GET    /api/v1/memos/{id}/export        # Export memo (HTML/PDF/DOCX)

POST   /api/v1/decks                    # Upload pitch deck
GET    /api/v1/decks/{id}               # Get deck analysis

GET    /api/v1/outlines                 # List available outlines
POST   /api/v1/outlines                 # Create custom outline

WS     /api/v1/memos/{id}/stream        # Real-time progress
```

---

## Shared Infrastructure

### Changelog System (Distributed + Aggregated)

**Philosophy**: Each app has its own changelog folder. Work stays localized to where it happens. The marketing site aggregates all changelogs via GitHub raw API at build time.

**Structure**:
```
apps/
├── memopop-site/
│   └── changelog/              # Site-specific changes (design, content, SEO)
│       └── 2025-12-26_01.md
├── memopop-web-app/
│   └── changelog/              # Web app changes (UI, features, auth)
│       └── 2025-12-26_01.md
└── memopop-agent-orchestrator/
    └── changelog/              # Agent/API changes (agents, pipeline, exports)
        └── 2025-12-26_01.md
```

**Aggregation Pattern**:
```typescript
// In memopop-site, at build time or via API route
const repos = [
  'lossless-group/memopop-ai/apps/memopop-site/changelog',
  'lossless-group/memopop-ai/apps/memopop-web-app/changelog',
  'lossless-group/memopop-ai/apps/memopop-agent-orchestrator/changelog',
];

// Fetch via raw.githubusercontent.com with access token
const entries = await Promise.all(repos.map(fetchChangelogEntries));
const unified = entries.flat().sort((a, b) => b.date - a.date);
```

**Benefits**:
- Work stays localized (less navigation errors, clearer context)
- No merge conflicts on shared files
- Each app owns its changelog
- Unified view on marketing site when needed
- Access token management required (GitHub fine-grained PAT)

**UI** (dark-matter pattern):
- Three views: Timeline, Cards, Releases
- CSS-first view toggling (no JS flash)
- Shareable URLs with `?view=` parameter
- Filter by app: `?app=orchestrator`

**Changelog Entry Schema**:
```yaml
---
title: "Feature: Section Improvement CLI"
date: 2025-12-25
authors: ["Claude", "Human"]
augmented_with: "Claude Opus 4.5"
category: Feature  # Feature, Fix, Refactor, Breaking, Security
tags: [CLI, Perplexity, Sections]
summary: "One-line summary"
app: memopop-agent-orchestrator  # Which app this belongs to
files_added: []
files_modified: []
breaking: false
---
```

### TypeScript Types (`packages/shared-types`)

Shared interfaces for API contracts:
```typescript
interface Memo {
  id: string;
  company_name: string;
  investment_type: 'direct' | 'fund';
  memo_mode: 'consider' | 'justify';
  status: 'pending' | 'processing' | 'completed' | 'failed';
  sections: Section[];
  citations: Citation[];
  scorecard?: Scorecard;
  created_at: string;
  updated_at: string;
}

interface Section {
  number: number;
  name: string;
  content: string;
  word_count: number;
}

interface GenerationProgress {
  stage: string;
  agent: string;
  progress: number;  // 0-100
  message: string;
}
```

### API Client (`packages/api-client`)

TypeScript client for the agent orchestrator API:
```typescript
import { MemoPopClient } from '@memopop/api-client';

const client = new MemoPopClient({
  baseUrl: 'https://api.memopop.ai',
  apiKey: 'mp_...',
});

const memo = await client.memos.create({
  company_name: 'Acme Corp',
  deck_url: 'https://...',
});

client.memos.onProgress(memo.id, (progress) => {
  console.log(`${progress.agent}: ${progress.message}`);
});
```

---

## Deployment Strategy

### Phase 1: Static Site Launch
- Deploy `memopop-site` to Vercel/Cloudflare
- Marketing site live with changelog
- Link to waitlist/contact form

### Phase 2: API Launch
- Deploy `memopop-agent-orchestrator` as Docker container
- PostgreSQL + Redis for job queue
- S3/R2 for file storage
- Basic API authentication

### Phase 3: Web App Launch
- Deploy `memopop-web-app` to Vercel
- Connect to production API
- User authentication via Clerk/Auth.js
- Stripe for billing

### Phase 4: Scale
- Add worker scaling for parallel memo generation
- Add CDN caching for exports
- Add monitoring/alerting
- Add usage analytics

---

## Migration Plan

### Moving from Current Location

The current `investment-memo-orchestrator` lives at:
```
/Users/mpstaton/code/lossless-monorepo/ai-labs/investment-memo-orchestrator
```

**To migrate**:
1. Clone the new `memopop-ai` repo
2. Create monorepo structure
3. Move orchestrator code to `apps/memopop-agent-orchestrator/`
4. Update all internal paths
5. Set up Bun workspaces + Turborepo
6. Create Astro site skeleton
7. Create SvelteKit app skeleton
8. Move changelog files with updated frontmatter

### Preserving Git History

Option A: Subtree merge (preserves history)
```bash
git subtree add --prefix=apps/memopop-agent-orchestrator \
  git@github.com:original/investment-memo-orchestrator.git main
```

Option B: Fresh start (cleaner, loses history)
```bash
cp -r investment-memo-orchestrator/* apps/memopop-agent-orchestrator/
git add . && git commit -m "Initial import of agent orchestrator"
```

---

## Decided

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Package manager** | Bun + Bun workspaces | Fast, modern, native workspace support. Add Turborepo later if builds become slow. |
| **Svelte version** | Svelte 5 (runes) | Latest features, better to adopt now than migrate later |
| **Deployment** | Vercel | Existing paid account, great Astro + SvelteKit support, free for low-traffic projects |
| **Shared styling** | Yes | Single Tailwind config in `packages/shared-styles/`, both apps consume. Divergence allowed but periodic refactoring to converge. |
| **Changelog** | Distributed | Each app has own `/changelog/` folder. Marketing site aggregates via GitHub raw API. Localized work, no merge conflicts. |
| **Auth** | SuperTokens on Railway | Open source, self-hosted, full control. Easy to migrate if needed. |
| **Database** | Baserow on Railway | Open source, self-hosted, backend control. Easy migration path if scaling beyond lifestyle project. |

## Open Questions

1. **Domain structure**: Subdomains (`app.memopop.ai`) vs paths (`memopop.ai/app/`)?
2. **Current GitHub Pages**: What's deployed now that we're porting?
3. **File storage**: S3 vs Cloudflare R2 vs Supabase Storage?
4. **Job queue**: Celery vs Dramatiq vs simple Redis + Python workers?

---

## Why This Architecture?

| Decision | Rationale |
|----------|-----------|
| **Astro for site** | Best static site perf, content collections for changelog, no React baggage |
| **Svelte for app** | Modern, fast, less boilerplate than React, great DX |
| **Python for agents** | LangGraph ecosystem, existing code, ML/AI libraries |
| **Monorepo** | Shared changelog, atomic deployments, unified versioning |
| **No React** | Reduces complexity, better performance, avoids ecosystem churn |
| **Bun workspaces** | Native monorepo support, fast installs. Turborepo/Nx as escape hatch if builds slow down. |
| **SuperTokens** | Open source auth, self-hosted on Railway, full data ownership |
| **Baserow** | Open source database UI, self-hosted, easy data management, migration flexibility |

---

## Next Steps

1. [x] Create GitHub repo: `lossless-group/memopop-ai`
2. [x] Decide: Bun for package manager
3. [x] Decide: Svelte 5 with runes
4. [x] Decide: Vercel for deployment
5. [x] Decide: Shared Tailwind config
6. [x] Decide: Changelog distributed per app, aggregated via GitHub raw API
7. [x] Decide: SuperTokens on Railway for auth
8. [x] Decide: Baserow on Railway for database
9. [ ] **DECIDE**: Domain structure (subdomains vs paths)
10. [ ] **DECIDE**: Current GitHub Pages to port
11. [ ] Set up monorepo structure with Bun workspaces
12. [ ] Create `packages/shared-styles/` with Tailwind config
13. [ ] Initialize Astro site (`apps/memopop-site/`)
14. [ ] Port current GitHub Pages content to Astro
15. [ ] Create changelog content collection (dark-matter pattern)
16. [ ] Initialize SvelteKit app skeleton (`apps/memopop-web-app/`)
17. [ ] Migrate orchestrator code (`apps/memopop-agent-orchestrator/`)
18. [ ] Set up Vercel project linking
19. [ ] Deploy SuperTokens on Railway
20. [ ] Deploy Baserow on Railway
21. [ ] Design API contract between web app and orchestrator

---

*Document Version: 0.0.1.2*
*Created: 2025-12-26*
*Updated: 2025-12-26*
*Author: Michael Staton + Claude Code with Claude Opus 4.5*
