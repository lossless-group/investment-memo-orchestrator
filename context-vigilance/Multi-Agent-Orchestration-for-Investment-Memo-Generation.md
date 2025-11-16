---
date_created: 2025-11-16
date_modified: 2025-11-16
publish: true
title: "Multi-Agent Orchestration for Investment Memo Generation"
slug: multi-agent-orchestration-investment-memo-generation
at_semantic_version: 0.0.1.0
authors:
  - Michael Staton
augmented_with: "Claude Code (Sonnet 4.5)"
site_uuid: d926a656-1323-456f-8b48-4195ca31d371
lede: "An exploration into using AI supervisors and specialized agents to generate high-quality content and documents."
---
# Multi-Agent Orchestration for Investment Memo Generation

*An exploration into using AI supervisors and specialized agents to generate high-quality investment analysis documents that maintain analytical rigor, structural consistency, and distinctive voice*

## Context

Investment memos at [[moc/Hypernova|Hypernova]] follow a specific analytical format developed through deals like [[client-content/Hypernova/Portfolio/Aalo Atomics|Aalo Atomics]] (Series B, nuclear microreactors) and [[client-content/Hypernova/Portfolio/Star Catcher|Star Catcher]] (Pre-Series A, space power infrastructure). These memos balance:
- **Enthusiasm** for frontier technology and macro tailwinds
- **Skepticism** about execution risks and market uncertainties
- **Specificity** over generalization (exact metrics, named investors, dated milestones)

Traditional AI-assisted writing approaches struggle to maintain this balance across all sections while ensuring consistency with firm standards.

## The Challenge

### Single-Prompt Limitations
- **Inconsistent quality** across memo sections
- **Vague generalizations** instead of specific metrics
- **Promotional tone** rather than analytical balance
- **Missing risk analysis** or superficial mitigation strategies
- **Format drift** from established templates
- **Poor source attribution** for market claims

### Manual Generation Problems
- **Time-intensive** research and drafting (8-12 hours per memo)
- **Inconsistent structure** when rushed
- **Knowledge gaps** in specialized domains (deep tech, regulatory)
- **Iteration overhead** for revisions and validation
- **Context switching** between research, writing, and validation modes

## Discovery: Supervisor Pattern for Document Generation

Rather than treating AI as a single monolithic writer, decompose the task into specialized agents supervised by an orchestrator:

```
┌──────────────────┐
│  Supervisor      │ ← Coordinates workflow, manages state
│  Agent           │
└────────┬─────────┘
         │
    ┌────┴─────────────────────┐
    │                          │
┌───┴────────┐         ┌───────┴──────┐
│ Research   │         │ Validation   │
│ Agent      │         │ Agent        │
└────────────┘         └──────────────┘
    │                          │
┌───┴────────┐         ┌───────┴──────┐
│ Writer     │         │ Revision     │
│ Agent      │         │ Agent        │
└────────────┘         └──────────────┘
```

This approach enables:
- **Specialization** by domain (market analysis vs. technical assessment)
- **Quality gates** through dedicated validation agents
- **Iterative refinement** with supervisor-managed revision loops
- **Consistency** through centralized template and style enforcement

## Solution Architecture

### 1. Model Context Protocol (MCP) for Data Access

**What it is**: Open protocol (Anthropic, late 2024) allowing AI models to connect to external data sources through standardized servers.

**Implementation for investment memos**:

```
┌─────────────────┐
│  Claude/GPT-4   │ ← Orchestrator Agent
└────────┬────────┘
         │
    ┌────┴────┐
    │   MCP   │
    └────┬────┘
         │
    ┌────┴────────────────────────┐
    │                             │
┌───┴────────┐           ┌────────┴────┐
│ MCP Server │           │ MCP Server  │
│ (Portfolio │           │ (Market     │
│  Data)     │           │  Research)  │
└────────────┘           └─────────────┘
```

**MCP servers to build**:
- **Portfolio Data Server**: Company data, previous memos, investment theses
- **Market Research Server**: Crunchbase, PitchBook APIs, public filings
- **Template Server**: Memo templates, style guides, reference examples
- **Validation Server**: Quality criteria, checklist enforcement

**Benefits:**
- **Secure data access** without prompt injection risks
- **Standardized interfaces** across different data sources
- **Version-controlled** schemas and resources
- **Audit trails** for data access

### 2. Agent Specialization Strategy

#### Research Agent
**Responsibility**: Gather comprehensive company and market data

**Tools**:
- Market sizing databases (PitchBook, Crunchbase)
- Company websites and public filings
- Competitor analysis frameworks
- Regulatory databases (FDA, NRC, FCC)

**Output**: Structured JSON with:
```json
{
  "company": {
    "name": "...",
    "stage": "...",
    "founders": [...],
    "funding_history": [...]
  },
  "market": {
    "tam": "...",
    "growth_drivers": [...],
    "competitive_landscape": [...]
  },
  "sources": [...]
}
```

#### Writer Agent
**Responsibility**: Draft memo sections following Hypernova format

**Context**:
- Memo template with section structure
- Style guide with good/bad examples
- 2-3 reference memos from similar stage/sector

**Specialization options**:
- **Market Writer**: Sections 2-3 (Business Overview, Market Context)
- **Technical Writer**: Sections 4-5 (Technology & Product, Traction)
- **Team Writer**: Section 6 (Team assessment)
- **Risk Writer**: Section 8 (Risks with mitigations)

**Output**: Draft sections with proper formatting and citation placeholders

#### Validator Agent
**Responsibility**: Ensure memos meet Hypernova standards

**Validation criteria**:
- [ ] Follows exact 10-section structure
- [ ] Includes specific metrics (not vague claims)
- [ ] Risk section has 4-6 items with mitigations
- [ ] All acronyms spelled out on first use
- [ ] Market sizing includes sources/caveats
- [ ] Team section includes prior exits/companies
- [ ] Analytical tone (not promotional)
- [ ] Information density matches reference memos

**Output**:
```json
{
  "score": 8.5,
  "needs_revision": true,
  "sections_to_revise": ["market_context", "risks"],
  "feedback": {
    "market_context": "Missing source for $250B TAM claim",
    "risks": "Need concrete mitigation for regulatory risk"
  }
}
```

#### Revision Agent
**Responsibility**: Fix specific issues identified by validator

**Input**: Original section + validator feedback

**Strategy**: Targeted fixes (not full rewrites) to preserve good content

**Output**: Revised section addressing specific feedback

### 3. Supervisor Orchestration Logic

**State management**:
```python
class MemoState(TypedDict):
    company_name: str
    company_data: dict
    research: dict
    draft_sections: dict
    validation_results: dict
    revision_count: int
    final_memo: str
```

**Control flow**:
```python
def supervisor_logic(state: MemoState) -> str:
    """Decides which agent to call next"""

    if not state.get("research"):
        return "research_agent"

    if not state.get("draft_sections"):
        return "writer_agent"

    if not state.get("validation_results"):
        return "validator_agent"

    if state["validation_results"]["needs_revision"]:
        if state["revision_count"] < 3:
            return "revision_agent"
        else:
            return "human_review"  # Escalate after 3 attempts

    return "finalize"
```

**Human-in-the-loop checkpoints**:
- After research (review data quality)
- After first draft (strategic direction)
- After validation failures (complex revisions)
- Before finalization (sign-off)

## Platform Options

### Language Choice: Python vs. JavaScript

Before selecting a specific framework, an important architectural decision is choosing the implementation language.

#### Python (Recommended for LangGraph)

**LangGraph (Python)** - The original and most mature implementation

**Advantages**:
- More examples and documentation
- Larger community and ecosystem
- Better integration with ML/AI tools (pandas, numpy, scikit-learn)
- Most MCP servers are Python-based
- Direct Claude/OpenAI SDK integration
- New features ship in Python first

**When to choose Python**:
- You're comfortable with Python or willing to learn it
- You want maximum flexibility and features
- You need ML/data analysis capabilities
- You're building backend services or scripts

#### JavaScript/TypeScript (Alternative)

**LangGraph.js** - Newer port of LangGraph to JS/TS

**Advantages**:
- Good if you're already in Node.js ecosystem
- Easier integration with existing web apps
- TypeScript types for better IDE support
- Can run in browser or edge workers

**Limitations**:
- Still maturing (fewer features than Python version)
- Smaller community and fewer examples
- Features lag behind Python implementation

**When to choose JavaScript**:
- You're already building in Node.js/TypeScript
- You want to run agents in browser or edge workers
- Your team is JS-first and wants to avoid Python

#### Hybrid Approach (Often Best)

Many teams use both languages strategically:

```
┌─────────────────────┐
│   Python Backend    │
│   (LangGraph)       │
│                     │
│ - Agent orchestration
│ - MCP servers       │
│ - Heavy processing  │
└──────────┬──────────┘
           │ REST/GraphQL API
           │
┌──────────┴──────────┐
│   Web Frontend      │
│   (Astro/Svelte)    │
│                     │
│ - UI for memo input │
│ - Progress display  │
│ - Review interface  │
└─────────────────────┘
```

**Benefits of hybrid approach**:
- Use Python's strengths for AI orchestration
- Use your preferred web stack for UI/UX
- Clean separation of concerns
- Each layer uses optimal tooling

#### Recommendation

**Start with Python LangGraph** for investment memo generation because:

1. **Better learning resources** - Most tutorials and examples are Python
2. **More stable** - Features are battle-tested in Python first
3. **MCP ecosystem** - Most servers are Python (easier integration)
4. **Future-proof** - New LangGraph features ship in Python first
5. **Production-ready** - More deployments in production

You can always:
- Expose Python agents via REST API
- Build web UI in your preferred framework
- Move to LangGraph.js later if needed (patterns transfer)

### Option 1: LangGraph (Recommended)

**Why it fits**:
- Python-based (easy integration)
- Explicit state management
- Built-in persistence (save/resume workflows)
- Human-in-the-loop support
- Conditional branching based on validation

**Example implementation**:
```python
from langgraph.graph import StateGraph, END

# Define workflow
workflow = StateGraph(MemoState)

# Add agent nodes
workflow.add_node("research", research_agent)
workflow.add_node("draft", writer_agent)
workflow.add_node("validate", validator_agent)
workflow.add_node("revise", revision_agent)

# Define control flow
workflow.add_edge("research", "draft")
workflow.add_edge("draft", "validate")
workflow.add_conditional_edges(
    "validate",
    lambda x: "revise" if x["validation_results"]["needs_revision"] else END,
    {"revise": "revise", END: END}
)
workflow.add_edge("revise", "validate")

# Set entry point
workflow.set_entry_point("research")

# Compile
app = workflow.compile()
```

**Benefits:**
- **Visual debugging** of agent transitions
- **Checkpoint recovery** if workflow fails
- **Parallel execution** of independent sections
- **Streaming output** for long-running tasks

### Option 2: AutoGen (Microsoft)

**Why it might fit**:
- Multi-agent conversation framework
- Agents critique each other's work
- Built-in group chat for coordination

**Example structure**:
```python
from autogen import AssistantAgent, GroupChat, GroupChatManager

research_agent = AssistantAgent(
    name="Researcher",
    system_message="Gather market data and competitive analysis",
    llm_config={"model": "gpt-4"}
)

writer_agent = AssistantAgent(
    name="Writer",
    system_message="Draft memo sections following Hypernova format",
    llm_config={"model": "claude-sonnet-4.5"}
)

critic_agent = AssistantAgent(
    name="Critic",
    system_message="Validate against Hypernova style guide",
    llm_config={"model": "gpt-4"}
)

groupchat = GroupChat(
    agents=[research_agent, writer_agent, critic_agent],
    messages=[],
    max_round=10
)

manager = GroupChatManager(groupchat=groupchat)
```

**Benefits:**
- **Conversational refinement** (agents debate approaches)
- **Emergent collaboration** patterns
- **Flexible agent interactions**

**Drawbacks:**
- Less explicit control flow
- Harder to debug multi-agent conversations
- Can be verbose with many iterations

### Option 3: CrewAI

**Why it might fit**:
- Role-based agent design
- Opinionated structure (fast to prototype)
- Built-in task management

**Example configuration**:
```python
from crewai import Agent, Task, Crew

researcher = Agent(
    role='Investment Researcher',
    goal='Gather comprehensive company and market data',
    backstory='Expert at finding reliable market sizing',
    tools=[crunchbase_tool, pitchbook_tool]
)

writer = Agent(
    role='Investment Analyst',
    goal='Draft memos following Hypernova format',
    backstory='Former VC associate with 50+ memos written',
    tools=[memo_template_tool]
)

crew = Crew(
    agents=[researcher, writer, validator],
    tasks=[research_task, write_task, validate_task],
    verbose=True
)

result = crew.kickoff(inputs={'company_name': 'Aalo Atomics'})
```

**Benefits:**
- **Fast prototyping** with minimal boilerplate
- **Role-based thinking** matches VC workflows
- **Sequential or hierarchical** process support

**Drawbacks:**
- Less flexible than LangGraph
- Abstractions may hide important details
- Younger ecosystem (fewer examples)

### Option 4: Custom with Claude API + MCP

**Why it might fit**:
- Maximum control over workflow
- No framework overhead
- Direct Claude integration

**Minimal implementation**:
```python
import anthropic

class MemoOrchestrator:
    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)

    async def generate_memo(self, company_data: dict) -> dict:
        state = {
            "company": company_data["name"],
            "research": None,
            "draft": None,
            "validation": None,
            "iterations": 0
        }

        while state["iterations"] < 5:
            # Call supervisor
            supervisor_response = await self.client.messages.create(
                model="claude-sonnet-4.5",
                messages=[{
                    "role": "user",
                    "content": f"State: {state}. Next action?"
                }],
                tools=[
                    research_tool,
                    write_tool,
                    validate_tool,
                    finalize_tool
                ]
            )

            # Execute tool calls
            for tool_use in supervisor_response.content:
                if tool_use.name == "research":
                    state["research"] = await self.research(company_data)
                elif tool_use.name == "write":
                    state["draft"] = await self.write(state["research"])
                elif tool_use.name == "validate":
                    state["validation"] = await self.validate(state["draft"])
                elif tool_use.name == "finalize":
                    return state["draft"]

            state["iterations"] += 1

        return state["draft"]
```

**Benefits:**
- **Complete control** over execution
- **Minimal dependencies**
- **Easy to customize** for specific needs

**Drawbacks:**
- More code to maintain
- Manual state persistence
- No built-in debugging tools

## Implementation Roadmap

### Week 1: Proof of Concept
1. **Choose framework**: LangGraph (recommended) or CrewAI (faster start)
2. **Define 3 core agents**: Researcher, Writer, Validator
3. **Create simple tools**:
   - `get_template()` - returns memo template
   - `get_style_guide()` - returns good/bad examples
   - `validate_section(section, criteria)` - checks one section
4. **Test with existing portfolio company**
5. **Compare output** to manual memos

**Success criteria**:
- Generates complete 10-section memo
- Validates against checklist
- Identifies at least 3 quality issues automatically

### Week 2: MCP Integration
1. **Build Portfolio Data MCP server**:
   ```
   /resources/companies/{company_id}
   /resources/memos/templates
   /resources/memos/examples
   ```
2. **Connect agents to MCP server**
3. **Test data retrieval** vs. manual copy/paste
4. **Add Market Research MCP server** (Crunchbase API)

**Success criteria**:
- Agents can fetch company data automatically
- Templates loaded from MCP (not hardcoded)
- External API data integrated seamlessly

### Week 3: Specialized Section Writers
1. **Split Writer Agent** into domain specialists:
   - Market Writer (sections 2-3)
   - Technical Writer (sections 4-5)
   - Risk Writer (section 8)
2. **Add parallel execution** for independent sections
3. **Implement revision loop** (validator → revision agent → validator)

**Success criteria**:
- Section quality improves with specialization
- Parallel execution reduces total time
- Revision loop successfully fixes common issues

### Week 4: Production Deployment
1. **Build simple UI** (Streamlit or Gradio):
   - Company data input form
   - Progress visualization
   - Section-by-section review
   - Export to PDF
2. **Add version tracking**:
   - Save all agent outputs
   - Track iterations and revisions
   - Compare versions side-by-side
3. **Human-in-the-loop checkpoints**:
   - Approve research before drafting
   - Review validation feedback
   - Final sign-off before export

**Success criteria**:
- Non-technical users can generate memos
- All outputs logged for audit
- Human review integrated smoothly

## Technical Implementation Details

### MCP Server Example (Portfolio Data)

```python
# portfolio_mcp_server.py
from mcp.server import Server
from mcp.types import Resource, Tool
import json

server = Server("hypernova-portfolio")

@server.list_resources()
async def list_resources():
    return [
        Resource(
            uri="portfolio://companies",
            name="Portfolio Companies",
            mimeType="application/json"
        ),
        Resource(
            uri="portfolio://templates/investment-memo",
            name="Investment Memo Template",
            mimeType="text/markdown"
        )
    ]

@server.read_resource()
async def read_resource(uri: str):
    if uri == "portfolio://companies":
        with open("data/companies.json") as f:
            return json.load(f)
    elif uri == "portfolio://templates/investment-memo":
        with open("templates/memo-template.md") as f:
            return f.read()

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="get_company_data",
            description="Fetch detailed data for a portfolio company",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"}
                },
                "required": ["company_name"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "get_company_data":
        company_name = arguments["company_name"]
        # Fetch from database or API
        return get_company_from_db(company_name)

if __name__ == "__main__":
    server.run()
```

### Agent Prompt Engineering

**Research Agent System Prompt**:
```
You are an investment research specialist gathering data for venture capital memos.

TASK: Collect comprehensive information about {company_name}

REQUIRED DATA:
1. Company fundamentals (stage, HQ, founding team)
2. Market sizing with sources (TAM, growth projections)
3. Competitive landscape (alternatives, positioning)
4. Funding history (rounds, investors, amounts)
5. Traction metrics (revenue, LOIs, partnerships)

OUTPUT FORMAT: Structured JSON with sources cited for all claims

QUALITY STANDARDS:
- Prioritize recent data (last 12 months preferred)
- Include source URLs for all market sizing
- Note data gaps explicitly (don't fabricate)
- Flag conflicting information between sources
```

**Writer Agent System Prompt**:
```
You write investment memo sections for Hypernova following strict format and style.

TEMPLATE: {section_template}

REFERENCE EXAMPLES: {good_examples}

STYLE REQUIREMENTS:
- Analytical, not promotional
- Specific metrics over vague claims
- Bullet format for scannability
- Sources cited for market data
- Balanced (acknowledge risks alongside opportunities)

AVOID:
- Superlatives ("revolutionary", "game-changing")
- Vague growth claims without numbers
- Missing risk acknowledgment
- Promotional tone

OUTPUT: One complete section matching template structure
```

**Validator Agent System Prompt**:
```
You validate investment memos against Hypernova quality standards.

CHECKLIST: {validation_checklist}

SCORING CRITERIA:
- Structure adherence (0-2 points)
- Metric specificity (0-3 points)
- Risk analysis depth (0-2 points)
- Tone/voice match (0-2 points)
- Source attribution (0-1 point)

TOTAL: 10 points maximum

OUTPUT: JSON with score, needs_revision flag, and specific feedback per section

BE RIGOROUS: High-quality memos score 8+. Don't inflate scores.
```

### State Management Schema

```python
from typing import TypedDict, List, Dict, Optional

class CompanyData(TypedDict):
    name: str
    stage: str
    hq_location: str
    website: str
    founders: List[Dict[str, str]]

class ResearchData(TypedDict):
    company: CompanyData
    market: Dict[str, any]
    technology: Dict[str, any]
    team: Dict[str, any]
    traction: Dict[str, any]
    sources: List[str]

class SectionDraft(TypedDict):
    section_name: str
    content: str
    word_count: int
    citations: List[str]

class ValidationFeedback(TypedDict):
    section_name: str
    score: float
    issues: List[str]
    suggestions: List[str]

class MemoState(TypedDict):
    company_name: str
    research: Optional[ResearchData]
    draft_sections: Dict[str, SectionDraft]
    validation_results: Dict[str, ValidationFeedback]
    revision_count: int
    overall_score: float
    final_memo: Optional[str]
```

### Artifact Trail System for Transparency

**Purpose**: Create a persistent record of all intermediate outputs during memo generation to enable transparency, targeted improvements, and citation preservation.

**Directory Structure**:
```
output/
└── {Company-Name}-v0.0.x/
    ├── 1-research.json          # Raw structured research data
    ├── 1-research.md            # Human-readable research summary
    ├── 2-sections/              # Individual section drafts
    │   ├── 01-executive-summary.md
    │   ├── 02-business-overview.md
    │   ├── 03-market-context.md
    │   ├── 04-technology-product.md
    │   ├── 05-traction-milestones.md
    │   ├── 06-team.md
    │   ├── 07-funding-terms.md
    │   ├── 08-risks-mitigations.md
    │   ├── 09-investment-thesis.md
    │   └── 10-recommendation.md
    ├── 3-validation.json        # Validation scores and feedback
    ├── 3-validation.md          # Human-readable validation report
    ├── 4-final-draft.md         # Complete assembled memo
    └── state.json               # Full workflow state for debugging
```

**Benefits**:

1. **Transparency**: Expose all intermediate steps that occur during generation, making the AI's research and reasoning visible
2. **Targeted Re-runs**: Re-generate specific sections without re-running entire workflow
3. **Citation Tracking**: Preserve web search sources and citations through all editing stages
4. **Manual Editing**: Enable human intervention at any stage (edit research, revise individual sections)
5. **Version Comparison**: Easily diff sections between versions to track improvements
6. **Quality Assurance**: Review validation feedback in detail to understand scoring rationale
7. **Debugging**: Full state export enables troubleshooting and iteration on prompts

**Implementation Approaches**:

**Option 1: Agent-Level Persistence** (Recommended)
- Each agent saves its output immediately after execution
- Research agent writes `1-research.json` and `1-research.md`
- Writer agent saves each section to `2-sections/`
- Validator agent writes `3-validation.json` and `3-validation.md`
- Finalize step assembles `4-final-draft.md`

```python
def research_agent_enhanced(state: MemoState) -> dict:
    # ... perform research ...

    # Save artifacts
    company_safe_name = sanitize_filename(state["company_name"])
    version = get_current_version(company_safe_name)
    output_dir = Path(f"output/{company_safe_name}-{version}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save structured data
    with open(output_dir / "1-research.json", "w") as f:
        json.dump(research_data, f, indent=2)

    # Save human-readable summary
    with open(output_dir / "1-research.md", "w") as f:
        f.write(format_research_summary(research_data))

    return {"research": research_data}
```

**Option 2: Workflow-Level Hooks**
- LangGraph checkpointing with custom serializers
- Automatically save state after each node execution
- Requires implementing custom persistence layer

**Option 3: Post-Processing Export**
- Generate entire memo first
- Extract artifacts from final state at end of workflow
- Simpler but doesn't enable mid-workflow intervention

**Option 4: Hybrid Approach** (Best for Week 2+)
- Real-time artifact saving during execution (Option 1)
- Plus LangGraph checkpointing for resume capability (Option 2)
- Enables both transparency and fault tolerance

**Citation Preservation Strategy**:

To ensure citations from web search (Perplexity/Tavily) are retained throughout edits:

1. **Research Phase**: Store citations with each data point in structured format
```json
{
  "funding": {
    "total_raised": "$136M",
    "citation": {
      "source": "Crunchbase",
      "url": "https://crunchbase.com/organization/aalo-atomics",
      "retrieved": "2025-11-16",
      "context": "Aalo has raised $136M across 3 rounds..."
    }
  }
}
```

2. **Writing Phase**: Include inline citations in markdown that reference research data
```markdown
Aalo has raised $136M across three rounds[^1], with the most recent Series B...

[^1]: [Crunchbase - Aalo Atomics](https://crunchbase.com/organization/aalo-atomics), retrieved 2025-11-16
```

3. **Validation Phase**: Check that all claims have citations, flag unsupported statements

4. **Artifact Trail**: Preserve original research.json so citations can always be traced back to source

**Enhanced Linking for Context**:

Automatically enrich mentions of people and organizations with relevant links:

- **Team Members**: Add LinkedIn profile links when available
  ```markdown
  **Matt Loszak** ([LinkedIn](https://linkedin.com/in/matt-loszak)) - CEO, previously...
  ```

- **Investors**: Link to firm websites and portfolio pages
  ```markdown
  **Valor Equity Partners** ([website](https://valorep.com)) led the Series B...
  ```

- **Government Agencies**: Link to official websites
  ```markdown
  Partnership with **Idaho National Laboratory** ([INL](https://inl.gov))...
  ```

- **Implementation**: Research agent extracts URLs during web search, stores in structured data, writer agent formats as markdown links

---

### ✅ Implementation Status Update (2025-11-16)

**Artifact Trail System: IMPLEMENTED**
- ✅ Agent-level persistence (Option 1) fully functional
- ✅ All agents save artifacts immediately after execution
- ✅ Research artifacts: `1-research.json` and `1-research.md`
- ✅ Section artifacts: `2-sections/*.md` (all 10 sections)
- ✅ Validation artifacts: `3-validation.json` and `3-validation.md`
- ✅ Final output: `4-final-draft.md` with citations
- ✅ State snapshot: `state.json` for debugging
- ✅ Version directory structure: `output/{Company-Name}-v0.0.x/`

**Citation System: IMPLEMENTED**
- ✅ New Citation-Enrichment Agent added to workflow
- ✅ Workflow: Research (Tavily) → Write (Claude) → Cite (Perplexity) → Validate (Claude)
- ✅ Perplexity Sonar Pro model integration for citation generation
- ✅ Inline citation format: `[^1]`, `[^2]`, etc. with full citation list
- ✅ Citation format: `[^1]: YYYY, MMM DD. [Source Title](URL). Published: YYYY-MM-DD | Updated: YYYY-MM-DD`
- ✅ Industry sources prioritized: TechCrunch, Medium, Sifted, Crunchbase, press releases
- ✅ Narrative preservation: Citations added WITHOUT rewriting content
- ✅ Successfully tested with Aalo Atomics (8 citations, 8.5/10 quality score)

**Test Results (Aalo Atomics v0.0.5)**:
- Research data: Comprehensive company information from 4 web searches
- Draft quality: Well-written 10-section memo with proper structure
- Citations: 8 inline citations with full source attribution at bottom
- Validation score: 8.5/10 (auto-finalized)
- Artifact count: 16 files (1 research.json, 1 research.md, 10 section files, 1 validation.json, 1 validation.md, 1 final-draft.md, 1 state.json)

**Key Implementation Details**:

*Hybrid Research + Citation Approach*:
- **Tavily** for research phase (fast, reliable, broad coverage)
- **Perplexity Sonar Pro** for citation enrichment (high-quality sources with publication dates)
- This hybrid approach combines reliability (Tavily) with citation quality (Perplexity)

*Citation-Enrichment Agent System Prompt*:
- Strict instruction: DO NOT rewrite or change narrative
- ONLY insert `[^1]`, `[^2]` citations to support existing factual claims
- Prioritize industry sources over academic papers
- Generate comprehensive citation list with exact format specification

*Files Created*:
- `src/artifacts.py`: Central module for artifact trail functionality
- `src/agents/citation_enrichment.py`: New agent for adding citations
- Updated: `src/workflow.py` to include citation step
- Updated: `src/agents/research_enhanced.py` to use sonar-pro model
- Updated: All agents to save artifacts during execution

**Remaining Work**:
- LinkedIn profile links (planned)
- Organization links for investors, government bodies (planned)
- Chart/visualization inclusion (planned)

---

## Lessons Learned

### What Works Well

**Specialization beats generalization**:
- Dedicated research agent produces higher-quality data than "write a memo" prompts
- Section-specific writers maintain better tone consistency
- Validation as separate agent catches issues generic prompts miss

**Explicit state management is critical**:
- LangGraph's StateGraph prevents context loss between agents
- Tracking iterations prevents infinite revision loops
- Checkpointing enables resume after failures

**Human-in-the-loop increases trust**:
- Review checkpoints catch edge cases agents miss
- Builds confidence in output quality
- Enables learning from corrections

**MCP reduces prompt complexity**:
- Agents fetch fresh data vs. stale prompt examples
- Centralized template management (no copy/paste)
- Secure API access without credentials in prompts

### Potential Challenges

**Over-orchestration overhead**:
- Simple memos don't need 5 agents
- Balance automation with manual speed for small tasks

**Agent coordination complexity**:
- More agents = more potential failure points
- Clear error handling and recovery needed

**Quality vs. speed tradeoffs**:
- Validation loops improve quality but increase latency
- May need "fast draft" vs. "rigorous review" modes

**Framework lock-in risks**:
- LangGraph, CrewAI evolving rapidly
- Abstract core logic to minimize migration pain

### Best Practices Discovered

**Start with supervisor pattern**:
- 3-4 specialized agents better than one generalist
- Supervisor coordinates workflow, agents focus on domain

**Make validation a first-class agent**:
- Don't treat quality as afterthought
- Explicit criteria and scoring
- Trigger revisions automatically

**Build MCP servers for repeated access**:
- Portfolio data (accessed every memo)
- Templates and style guides (version-controlled)
- External APIs (market research, company databases)

**Prompt engineering per agent role**:
- Research agent: "Gather and cite"
- Writer agent: "Follow template and examples"
- Validator agent: "Be rigorous, score honestly"

**Iterate on prompts based on output**:
- Track common validation failures
- Update system prompts to address patterns
- Maintain prompt version history

## Future Considerations

### Advanced Orchestration

**Dynamic agent selection**:
- Supervisor chooses specialist based on company sector
- Bio/pharma companies → regulatory specialist agent
- Space tech → technical validation expert

**Multi-model optimization**:
- Use GPT-4 for structured data extraction
- Use Claude for nuanced writing and analysis
- Use specialized models for domain tasks (financial analysis)

**Parallel section generation**:
- Independent sections drafted simultaneously
- Cross-reference validation in second pass
- Reduces total generation time

### Enhanced MCP Integration

**Expanding data sources**:
- PitchBook API for market sizing
- Crunchbase for funding history
- Company Glassdoor/LinkedIn for team validation
- Regulatory databases (FDA, NRC, FCC)

**Real-time data refresh**:
- Market data updated automatically
- Competitor tracking alerts
- Funding announcement notifications

**Collaborative MCP servers**:
- Shared across investment team
- Centralized knowledge base
- Audit logs for compliance

### Quality Improvements

**Learning from corrections**:
- Track human edits to agent outputs
- Identify systematic weaknesses
- Fine-tune prompts based on feedback patterns

**A/B testing frameworks**:
- Compare different agent configurations
- Measure quality improvements quantitatively
- Optimize for specific memo types (Seed vs. Series B)

**Automated citation verification**:
- Validate URLs are accessible
- Check data freshness
- Flag stale statistics

### Production Features

**Team collaboration**:
- Multi-user access with permissions
- Comment/review workflows
- Version control with diff views

**Export and distribution**:
- PDF generation with brand styling
- Email delivery to stakeholders
- Integration with deal management systems

**Analytics and monitoring**:
- Track generation time per section
- Monitor validation failure rates
- Measure human edit frequency (quality proxy)

## Conclusion

Multi-agent orchestration represents a paradigm shift from "AI as autocomplete" to "AI as collaborative team." By decomposing complex document generation into specialized roles supervised by an orchestrator, we can achieve:

- **Higher quality outputs** through domain specialization
- **Consistent formatting** through centralized templates and validation
- **Reduced manual effort** while maintaining analytical rigor
- **Scalable processes** that improve with use

The key insight is that **agent architecture matters as much as model capability**. A well-orchestrated set of specialized agents using Claude Sonnet can outperform a single GPT-4 prompt for complex, structured outputs like investment memos.

Three critical design principles emerge:

1. **Specialize agents by domain**, not just task (Market Analyst vs. Generic Writer)
2. **Make validation explicit** with dedicated agents and clear criteria
3. **Use MCP for data access** to keep prompts focused on reasoning, not context

The supervisor pattern, implemented via LangGraph or similar frameworks, provides the right balance of control and flexibility. It enables human oversight at critical checkpoints while automating the repetitive research, drafting, and validation cycles.

For organizations producing structured analytical documents at scale—whether investment memos, due diligence reports, or research briefs—multi-agent orchestration is not just an optimization. It's a fundamental capability that enables AI to augment human expertise rather than merely automate writing.

---

*This exploration synthesizes current best practices in multi-agent systems (as of November 2024) with practical requirements for venture capital document generation. Recommendations are based on real investment memo structures from Hypernova's portfolio analysis workflows.*
