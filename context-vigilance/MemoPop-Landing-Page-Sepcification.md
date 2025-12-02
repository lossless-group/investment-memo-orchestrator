# MemoPop Landing Page Spec

> A comprehensive spec for building the MemoPop marketing landing page.
> Designed for implementation by AI code assistants (Claude Code, Cursor, etc.)

---

## 1. Product Identity

- **Name**: MemoPop
- **Tagline**: "Investment memos that write themselves, in the style and to the standards of your firm."
- **One-liner**: AI-powered investment memo generation for venture capital firms
- **Target Audience**:
  - Primary: Busy Solo GPs, small VCs that don't have a big staff, and VC analysts and associates who write investment memos.
  - Secondary: GP/Partners who review memos and want consistent quality, quick drafts, and want to save firm time for higher-value tasks.
  - Tertiary: Family offices, angel syndicates, corporate VC teams

---

## 2. Visual Direction

### Mood
- **Professional** - This is enterprise B2B for finance
- **Modern** - Cutting-edge AI, not legacy software
- **Trustworthy** - Handling sensitive deal data
- **Clean** - Information-dense output needs clean presentation
- **Confident** - Premium positioning, not cheap/scrappy

### Color Palette
```
Primary:      #1a3a52  (Deep navy - trust, professionalism)
Secondary:    #1dd3d3  (Cyan/teal - modern, AI, innovation)
Accent:       #f59e0b  (Amber - CTAs, highlights)
Background:   #ffffff  (White - clean)
Background Alt: #f8fafc (Subtle gray - section breaks)
Text Dark:    #1a2332  (Near-black - readability)
Text Light:   #64748b  (Slate - secondary text)
```

### Typography
- **Headlines**: Inter or similar geometric sans-serif, bold weights
- **Body**: Inter or system fonts, 400/500 weights
- **Code/Technical**: JetBrains Mono or similar monospace (for showing output examples)

### Inspiration Sites (for visual feel)
- https://linear.app - Clean, professional SaaS
- https://vercel.com - Modern developer tooling
- https://notion.so - Document-focused product
- https://stripe.com - Enterprise trust + modern design

---

## 3. Page Structure

### 3.1 Navigation (Sticky Header)
```
[Logo: MemoPop]                    [Features] [How It Works] [Pricing] [Docs]  [Get Started →]
```
- Logo: Text-based "MemoPop" or simple logomark + text
- Links scroll to sections (Features, How It Works, Pricing)
- "Docs" links to documentation (external or /docs)
- "Get Started" is primary CTA button (accent color)
- Header becomes slightly translucent/blurred on scroll
- Changelog: Auto-updates to show latest version and release notes as they are added to the changelog and changelog/releases dir.

---

### 3.2 Hero Section

**Purpose**: Instant clarity + emotional hook. Visitor understands value in <5 seconds.

**Layout**: Split - copy on left, visual on right (or stacked on mobile)

**Content**:
```
[Eyebrow - small caps, secondary color]
AI-POWERED INVESTMENT MEMOS

[Headline - large, bold]
From pitch deck to
investment memo in 10 minutes or less.

[Subheadline - regular weight, text-light color]
MemoPop orchestrates 12 specialized AI agents to research, write,
cite, and validate institutional-quality draft investment memos.
Stop spending 20+ hours per memo!

[CTA Buttons]
[Get Started Free]  [Watch Demo →] [Contribute ->]
     ↑ Primary           ↑ Secondary/ghost           ↑ Tertiary/ghost

[Social Proof - small, below CTAs]
"Trusted by analysts at 50+ venture firms"
OR
Logos: [Firm1] [Firm2] [Firm3] [Firm4]
```

**Visual Element (Right Side)**:
- Animated or static mockup showing:
  - A pitch deck PDF on the left
  - Arrow/flow animation
  - Beautiful formatted memo on the right
- Dark mode aesthetic for the output preview
- Show real section headers from memo (Executive Summary, Team, Market Context, etc.)

---

### 3.3 Problem Section

**Purpose**: Validate the pain. Make them feel understood.

**Layout**: Centered text, possibly with subtle background color change

**Content**:
```
[Section Label]
THE PROBLEM

[Headline]
Investment memos shouldn't take 20 hours.

[Body - 2-3 short paragraphs or bullet points]
Every deal requires the same grind:
• Hours digging through pitch decks, extracting key data points
• Endless browser tabs researching market size, competitors, team backgrounds
• Struggling to maintain consistent quality and formatting across memos
• Scrambling to add citations and fact-check claims before partner review

Your time should be spent on judgment calls—not copy-paste research.
```

**Visual Element**:
- Optional: Simple illustration of overwhelmed analyst OR
- Stats callout: "Average time to write one memo: 15-25 hours"

---

### 3.4 Solution Section (How It Works)

**Purpose**: Show the magic. Make the complex feel simple.

**Layout**: 3-step horizontal flow (stacks vertically on mobile)

**Content**:
```
[Section Label]
HOW IT WORKS

[Headline]
Three steps. One exceptional memo.

[Step 1]
📄 Upload Your Deck
Drop in a pitch deck PDF. MemoPop extracts company info,
metrics, team details, and funding terms automatically.

[Step 2]
🔍 AI Agents Research & Write
12 specialized agents work in parallel—researching markets,
validating claims, writing sections, adding citations,
and scoring quality.

[Step 3]
✨ Export & Share
Get a polished, citation-rich memo in your firm's branded
template. Export to HTML, PDF, or Word.
```

**Visual Element**:
- Animated diagram showing the agent pipeline
- OR: Three cards/panels with icons
- Consider showing actual agent names: "Deck Analyst → Research Agent → Writer → Citation Enrichment → Validator"

---

### 3.5 Features Section

**Purpose**: Comprehensive capability overview. Address specific needs.

**Layout**: Grid of feature cards (2x4 or 4x2)

**Content**:
```
[Section Label]
FEATURES

[Headline]
Everything you need. Nothing you don't.

[Feature Cards - 8 total]

┌─────────────────────────────────────┐
│ 🗣️ Voice of the Firm, Voice of You  │
│ Custom outlines encode your memo    │
│ structure, guiding questions, and   │
│ firm vocabulary. Scorecards quantify│
│ conviction, synthesizing research.  │
│                                     │
│ → Define section order & naming     │
│ → Set word counts per section       │
│ → Create custom scoring rubrics     │
│ → Auto-generate diligence questions │
│   from low-scoring dimensions       │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🎯 Pitch Deck or Dataroom Analysis  │
│ Extracts metrics, team, market      │
│ sizing, and traction data           │
│ automatically from any PDF deck.    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🔬 Deep Research                    │
│ Searches the web for market data,   │
│ competitor intel, team backgrounds, │
│ and recent news—all cited.          │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 📝 Section-by-Section Writing       │
│ Each memo section written by        │
│ specialized agents following your   │
│ firm's outline and style guide.     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🔗 Auto-Citations                   │
│ Every claim backed by sources.      │
│ Inline citations with full          │
│ reference list—no hallucinations.   │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ ✅ Quality Validation               │
│ Built-in fact-checker and validator │
│ scores each memo 0-10 before you    │
│ ever see it.                        │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ 🎨 Custom Branding                  │
│ Your firm's logo, colors, fonts.    │
│ Export to branded HTML, PDF, or     │
│ DOCX in light or dark mode.         │
└─────────────────────────────────────┘

```

**Feature Card Detail: Voice of the Firm**

The "Voice of the Firm, Voice of You" card is a key differentiator. When expanded or on hover, show:

```
┌─────────────────────────────────────────────────────────────────────┐
│ 🗣️ VOICE OF THE FIRM, VOICE OF YOU                                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  CUSTOM OUTLINES              │  EVALUATION SCORECARDS              │
│                               │                                     │
│  📋 Define Your Memo Structure│  📊 Quantify Your Conviction        │
│                               │                                     │
│  • Section order & naming     │  • Multi-dimensional scoring (1-5)  │
│    "Founder-Market Fit"       │    Rate across 12+ dimensions       │
│    not "Team"                 │                                     │
│                               │  • Custom rubrics per dimension     │
│  • Guiding questions          │    "What does a '5' look like?"     │
│    "Why this team? Why now?"  │                                     │
│                               │  • Automatic percentile mapping     │
│  • Target word counts         │    "Score 4 = Top 10-25% of deals"  │
│    "Exec Summary: 200 max"    │                                     │
│                               │  • Group synthesis                  │
│  • Firm vocabulary            │    "Origins avg: 4.2/5"             │
│    "conviction" not           │                                     │
│    "confidence"               │  • Auto diligence questions         │
│                               │    Low scores → follow-up Qs        │
│                               │                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Built-in: Direct Investment • Fund/LP Commitment • 12Ps Scorecard  │
│  Or create your own from scratch.                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 3.6 Output Showcase Section

**Purpose**: Show the quality of output. Build confidence.

**Layout**: Large visual showcase, possibly tabbed or scrollable

**Content**:
```
[Section Label]
THE OUTPUT

[Headline]
Memos your partners will actually read.

[Subheadline]
Clean formatting. Real citations. Consistent structure.
```

**Visual Element** (CRITICAL - this sells the product):
- Large, detailed screenshot/mockup of an actual memo
- Show both light and dark mode versions (toggle?)
- Highlight specific elements with callouts:
  - "Auto-generated table of contents"
  - "Inline citations from real sources"
  - "12Ps scorecard evaluation"
  - "Team section with LinkedIn links"
- Consider an interactive demo where they can scroll through a real memo

---

### 3.7 Agent Architecture Section (Optional - for technical buyers)

**Purpose**: Differentiate from simple GPT wrappers. Show sophistication.

**Layout**: Visual diagram + explanation

**Content**:
```
[Section Label]
UNDER THE HOOD

[Headline]
12 specialized agents. One orchestrated workflow.

[Body]
MemoPop isn't a chatbot—it's a coordinated system of purpose-built
AI agents, each optimized for a specific task in the memo pipeline.

[Agent List - visual flow diagram]
Deck Analyst → Research Agent → Section Researcher → Writer →
Trademark Enrichment → Socials Enrichment → Link Enrichment →
Citation Enrichment → TOC Generator → Citation Validator →
Fact Checker → Validator → Scorecard Evaluator
```

**Visual Element**:
- Flow diagram showing agents as nodes
- Arrows showing data flow between agents
- Each agent could have a small icon/avatar

---

### 3.8 Social Proof Section

**Purpose**: Build trust through third-party validation.

**Layout**: Testimonial cards + logo bar

**Content**:
```
[Section Label]
TRUSTED BY ANALYSTS

[Testimonial 1]
"MemoPop cut our memo turnaround from 3 days to 3 hours.
The citation quality is better than what we produced manually."
— Associate, [Firm Name]

[Testimonial 2]
"Finally, consistent memo quality across our entire team.
Partners actually read these now."
— Principal, [Firm Name]

[Testimonial 3]
"The 12Ps scorecard alone is worth it. Quantified conviction
before we even get to IC."
— VP, [Firm Name]

[Logo Bar]
Logos of VC firms using the product (anonymized if needed)
```

---

### 3.9 Pricing Section

**Purpose**: Clear pricing, reduce friction.

**Layout**: 2-3 pricing tiers in cards

**Content**:
```
[Section Label]
PRICING

[Headline]
Start free. Scale as you grow.

┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    STARTER      │  │      PRO        │  │   ENTERPRISE    │
│                 │  │   Most Popular  │  │                 │
│     Free        │  │   $99/month     │  │    Custom       │
│                 │  │                 │  │                 │
│ • 3 memos/month │  │ • 25 memos/mo   │  │ • Unlimited     │
│ • Basic export  │  │ • All exports   │  │ • SSO/SAML      │
│ • Community     │  │ • Custom brand  │  │ • Dedicated CS  │
│   support       │  │ • Priority      │  │ • Custom agents │
│                 │  │   support       │  │ • API access    │
│                 │  │ • Scorecards    │  │ • On-prem option│
│                 │  │                 │  │                 │
│ [Get Started]   │  │ [Start Trial]   │  │ [Contact Sales] │
└─────────────────┘  └─────────────────┘  └─────────────────┘

[Below pricing]
All plans include: Unlimited team members • SOC 2 compliant •
Data never used for training
```

---

### 3.10 FAQ Section

**Purpose**: Overcome objections. Reduce support load.

**Layout**: Accordion/expandable list

**Content**:
```
[Section Label]
FAQ

[Questions]

Q: Is my deal data secure?
A: Yes. We're SOC 2 Type II compliant. Your data is encrypted at rest
   and in transit, never used for model training, and you can delete
   it at any time.

Q: Can I customize the memo template?
A: Absolutely. Define your own outline, section structure, guiding
   questions, and firm vocabulary. Upload your brand assets for
   consistent exports.

Q: What's the quality of the research?
A: We use Perplexity and Tavily for real-time web research, with
   automatic citation verification. Every claim links to its source.

Q: Does it work for fund commitments (LP memos)?
A: Yes. MemoPop supports both direct investment memos and fund/LP
   commitment memos with different templates and evaluation criteria.

Q: Can I edit the output?
A: Yes. Export to Markdown, HTML, PDF, or DOCX. Edit in any tool
   you prefer, or use our improvement CLI to refine specific sections.

Q: What if the memo needs corrections?
A: Use our corrections workflow to fix inaccuracies, add missing
   information, or adjust narrative tone—then regenerate cleanly.
```

---

### 3.11 Final CTA Section

**Purpose**: Last chance conversion. Strong close.

**Layout**: Centered, full-width background (gradient or solid)

**Content**:
```
[Background: Gradient from primary to slightly lighter]

[Headline - white text]
Ready to 10x your memo velocity?

[Subheadline - white/light text]
Join 50+ VC firms already using MemoPop.
Start free, upgrade when you're ready.

[CTA Button - Large, accent color]
[Get Started Free →]

[Below button - small text]
No credit card required • 3 free memos • Cancel anytime
```

---

### 3.12 Footer

**Layout**: Standard multi-column footer

**Content**:
```
[Column 1: Brand]
MemoPop
AI-powered investment memos

[Column 2: Product]
Features
Pricing
Documentation
Changelog
Status

[Column 3: Company]
About
Blog
Careers
Contact

[Column 4: Legal]
Privacy Policy
Terms of Service
Security
SOC 2 Report

[Bottom Bar]
© 2025 MemoPop. All rights reserved.     [Twitter] [LinkedIn] [GitHub]
```

---

## 4. Technical Requirements

### Framework & Stack
- **Framework**: Next.js 14+ (App Router) OR Astro (for pure static)
- **Styling**: Tailwind CSS
- **Components**: Prefer shadcn/ui or Radix primitives
- **Animations**: Framer Motion (subtle, not excessive)
- **Icons**: Lucide React or Heroicons

### Responsive Behavior
- **Breakpoints**: Mobile-first, standard Tailwind breakpoints
- **Mobile**: Stack all horizontal layouts, hamburger nav
- **Tablet**: 2-column grids where appropriate
- **Desktop**: Full layouts as designed

### Performance Requirements
- Lighthouse score: 90+ on all metrics
- No layout shift (CLS < 0.1)
- LCP < 2.5s
- Bundle size < 200KB initial JS

### Accessibility
- WCAG 2.1 AA compliance
- Keyboard navigation
- Screen reader friendly
- Sufficient color contrast

---

## 5. Assets Needed

### Must Have Before Build
- [ ] Logo (SVG, both light and dark versions)
- [ ] 2-3 screenshot mockups of memo output
- [ ] Favicon (SVG or ICO)

### Nice to Have
- [ ] Agent icons/illustrations
- [ ] Customer logos (or placeholders)
- [ ] Demo video or GIF
- [ ] Open Graph image for social sharing

### Can Generate During Build
- [ ] Placeholder testimonials (mark as examples)
- [ ] Feature icons (use icon library)
- [ ] Background patterns/gradients

---

## 6. What NOT to Do

### Design Anti-Patterns
- ❌ No stock photos of "business people shaking hands"
- ❌ No excessive animations or parallax effects
- ❌ No dark patterns (fake urgency, hidden pricing)
- ❌ No walls of text without visual breaks
- ❌ No carousel sliders for critical content

### Technical Anti-Patterns
- ❌ No client-side rendering for above-fold content
- ❌ No massive hero images (optimize/lazy load)
- ❌ No blocking third-party scripts
- ❌ No custom fonts without font-display: swap

### Content Anti-Patterns
- ❌ No vague buzzwords without specifics ("leverage AI to synergize")
- ❌ No claims without backing ("10x faster" needs context)
- ❌ No hiding the product behind "request demo" walls
- ❌ No placeholder "Lorem ipsum" in production

---

## 7. Implementation Notes for AI Assistants

When implementing this spec:

1. **Start with the layout skeleton** - Get all sections in place with placeholder content before styling

2. **Use semantic HTML** - `<header>`, `<main>`, `<section>`, `<footer>`, proper heading hierarchy

3. **Component structure**:
   ```
   /components
     /ui          # Reusable primitives (Button, Card, etc.)
     /sections    # Page sections (Hero, Features, Pricing, etc.)
     /layout      # Header, Footer, Container
   ```

4. **Copy is provided** - Use the exact copy from this spec, don't improvise

5. **Colors are defined** - Use CSS variables or Tailwind config, reference the palette above

6. **Mobile-first** - Build mobile layout first, then enhance for larger screens

7. **Test the CTA flow** - All buttons should have clear destinations (even if placeholder)

---

## 8. Success Criteria

The landing page is complete when:

- [ ] All 12 sections are implemented
- [ ] Responsive at all breakpoints (test 375px, 768px, 1280px, 1440px)
- [ ] All links/buttons are functional (or clearly marked as placeholder)
- [ ] Lighthouse performance score > 90
- [ ] No console errors
- [ ] Looks professional enough to share with potential customers
- [ ] Copy matches this spec exactly (unless explicitly changed)

---

*Spec Version: 1.0*
*Last Updated: December 2024*
*Author: Claude + Human Collaboration*
