# Blueprints

* [Preferred Sources Implementation Summary](Anti-Hallucination-Fact-Checker-Agent.md) - Integration of Perplexity @source syntax into the research and citation pipeline for premium, authoritative data sources.
* [Anti-Hallucination: Source Validation and Removal](Anti-Hallucination-Source-Validation-and-Removal.md) - Architecture for detecting and removing hallucinated citations from Perplexity Sonar Pro, distinguishing between citation format validation and source truthfulness.
* [Company Timeline and Month-Indexed Time Series](Company-Timeline-And-Month-Indexed-Time-Series.md) - A transcription contract. Rewrite each company's series into our columns and our grid, unchanged — and compute nothing.
* [Context-V System Blueprint](Context-V-System-Blueprint.md) - Blueprint for the context-v documentation system: a structured approach to maintaining project context, design decisions, and institutional knowledge across AI-assisted development sessions.
* [Disambiguation Management Across Agents](Disambiguation-Management-across-Agents.md) - System for preventing entity confusion across agents when companies share similar names, ensuring the correct company's data is used throughout memo generation.
* [Example Memos](Document-Examples.md) - Reference directory for example investment memos used as quality benchmarks.
* [Dark Mode Export Guide](Export-Style-Templates.md) - Guide for light and dark mode HTML export support in branded investment memos.
* [Firm and Deal-Based File Organization System](Firm-and-Deal-based-File-Organization-System.md) - Implementation progress for migrating output artifacts to firm-scoped directories with git submodule support for private data.
* [Git Submodules for Private Data and Exports](Git-Submodules-for-Private-Data-and-Exports.md) - Configure git submodules to enable private GitHub repositories for sensitive company data inputs and branded memo exports, while keeping the main orchestrator repo public/shareable.
* [Ideal Information Hierarchy Applied to Markdown Headings](Ideal-Information-Hierarchy-Applied-to-Markdown-Headings.md)
* [Model Scorecard Agent and Template System](Model-Scorecard-Agent-and-Template-System.md) - Add proprietary investment scoring frameworks to memo generation, enabling VC firms to systematically evaluate and communicate their differentiated investment thesis.
* [Transport Contract and API Conventions](Transport-Contract-and-API-Conventions.md) - Defines the API shape the Tauri GUI talks to. Same contract today (local IPC dispatch) as tomorrow (remote HTTP server). Designed so the v1→v3 switch is a transport swap, not a rewrite.
