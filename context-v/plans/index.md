# Plans

* [Apply the Deal-Folder Uploader](Apply-the-Deal-Folder-Uploader.md) - Run the written-and-tested uploader on the first firm, fold the 901 imported keys into blobs, and check every deal against its local folder.
* [Citation Coverage Promoter: Surface the Long Tail of Cited Sources](Citation-Coverage-Promoter.md) - ChromaDB v0.0.10: 33 curated URLs in scope, 7 cited, 26 ignored. A citation-additive second pass between draft and assemble.
* [Closing the Open Issues — September 2026](Closing-The-Open-Issues-2026-09.md) - Seven steps across four open issues, worked one at a time: implement, test, check off, move on. Ordered so the thing that gates actually running a thesis frame lands first, and the two quality gates that currently read from the wrong place are fixed before anyone trusts their scores again.
* [Edit Tools for Finished Memos](Edit-Tools-for-Finished-Memos.md) - edit_section, edit_final, edit_outline, and a compile that refuses to overwrite untracked edits: Plan 9's routing table, made real.
* [Finish Turning the Agents into Connector Steps](Finish-Turning-Agents-into-Connector-Steps.md) - 13 of about 40 agents are connector steps. Revision and correction agents come next.
* [Fix Citation Collisions in Final Assembly](Fix-Citation-Collisions-in-Final-Assembly.md) - Route assemble_citations() through consolidate_citations() so each section's [^N] keeps its own source, and repair affected memos before upload.
* [Fix What the First Partner Test Found](Fix-What-the-First-Partner-Test-Found.md) - A lean list_deals, a sentence for deals with no URL, trading names, whoami, and steps on imported deals that get their inputs.
* [Generic competitor analysis enhancement, post-hoc and re-runnable](Generic-Competitor-Analysis-Enhancement.md) - Move competitor research/evaluation from a one-shot pipeline step into a re-runnable, configurable enhancement — driven by `.md` + frontmatter schemas, applicable to any version of any memo, surfaced in memopop-native.
* [Generic scorecard generation across firms and outlines](Generic-Scorecard-Generation.md) - Refactor the scorecard agent + CLI from hardcoded Hypernova/fund-only to a generic renderer driven by `.md` + frontmatter scorecards, then surface it in memopop-native on the deal page.
* [MemoPop Connector API, Phase 1: Foundation](MemoPop-Connector-API-Phase-1-Foundation.md) - The registry, errors, auth, storage, five tools, the docs generators, the ledger, and CI. Every later phase builds on this one.
* [MemoPop Connector API, Phase 2: Deploy](MemoPop-Connector-API-Phase-2-Deploy.md) - A container with every system tool the memo needs, running on Railway at memopop.didi.sh, watched by a health check every 30 minutes.
* [MemoPop Connector API, Phase 4: Materials](MemoPop-Connector-API-Phase-4-Materials.md) - Decks, datarooms, notes, and links reach the server three ways, become text the steps can read, and never block the memo.
* [MemoPop Connector API, Phase 5: Enhancements, Compile, and the Full Flow](MemoPop-Connector-API-Phase-5-Enhancements-Compile-and-Flow.md) - Every enhancement becomes a step that can skip, compile turns sections into a branded PDF, and a scripted client walks the whole memo.
* [MemoPop Connector API, Phase 6: History and Snapshots](MemoPop-Connector-API-Phase-6-History-and-Snapshots.md) - Every saved artifact becomes a jj change the client never sees, and one save backs the firm's whole workspace up to its bucket.
* [MemoPop Connector API, Phase 7: The Plugin and Real Claude](MemoPop-Connector-API-Phase-7-Plugin-and-Real-Claude.md) - A thin skill that keeps Claude on the method, packaged with the connector, and a test where real Claude writes the fixture memo.
* [MemoPop Landing Page Specification](MemoPop-Landing-Page-Specification.md) - Comprehensive spec for building the MemoPop marketing landing page, designed for implementation by AI code assistants.
* [Hex-Code Citations, and a Tool to Repair Memos Cited by Number](Hex-Code-Citations-and-a-Repair-Tool.md) - Draft with source-derived hex keys as LFM requires, and repair memos whose numbered keys collided across sections.
* [Migrate `studies/open-specs-and-standards/` into its own pseudo-monorepo](Migrating-Study-to-its-own-Pseudomonrepo.md)
* [Reconciling Perplexity Citations Against Retrieved Sources](Reconciling-Perplexity-Citations-Against-Retrieved-Sources.md) - Sonar hands us the sources it actually retrieved on every call, and we throw them away — so every URL in every memo is a guess.
* [Reorganize Context-V Into Canonical Categories](Reorganize-Context-V-Into-Canonical-Categories.md) - Step-by-step prompt for reclassifying all context-v files into the four canonical categories: Specification, Reminder, Prompt, Blueprint.
* [Render Previews and Exports with LFM](Render-Previews-and-Exports-with-LFM.md) - Render once on the server with LFM, so exports, previews and firm sites match, and agents in Claude or ChatGPT call a preview tool instead of rendering themselves.
* [Notify Firm Sites When a Memo Compiles](Notify-Firm-Sites-When-a-Memo-Compiles.md) - A signed memo.compiled event to the firm's site after each new compiled version, so the site can cache memos and drop a deal's copy when it changes.
* [Serve Compiled Memos to Firm Sites](Serve-Compiled-Memos-to-Firm-Sites.md) - A site-keyed read endpoint for a deal's latest compiled memo, so a partner's edit shows on the firm's LP page after a refresh.
* [Serve the Method from the Server](Serve-the-Method-from-the-Server.md) - list_skills, get_skill, MCP prompts and editing-first server instructions, so Claude finds MemoPop without the plugin.
* [Trustworthy Citations: Source Harvester Rollout](Trustworthy-Citations-Source-Harvester-Rollout.md) - Why the existing anti-hallucination work hasn't held, and the six-phase plan that ends in a Source Harvester / Section Writer split.
* [Wire memopop-native to the FastAPI sidecar](Wire-Memopop-Native-To-The-FastAPI-Sidecar.md) - End-to-end plan for closing the loop from Tauri click to live log stream — Rust dispatcher forwards JSON, browser EventSource handles SSE, sidecar spawns lazily.

## Order of work: connector fixes from the first partner test (2026-11-21)

1. [Fix What the First Partner Test Found](Fix-What-the-First-Partner-Test-Found.md) and [Fix Citation Collisions in Final Assembly](Fix-Citation-Collisions-in-Final-Assembly.md), in parallel. Neither depends on anything.
2. [Apply the Deal-Folder Uploader](Apply-the-Deal-Folder-Uploader.md), after the citation repair, so memos with wrong citations aren't uploaded as compiled version 1.
3. [Serve the Method from the Server](Serve-the-Method-from-the-Server.md), steps 1–2, any time.
4. [Finish Turning the Agents into Connector Steps](Finish-Turning-Agents-into-Connector-Steps.md), step 1 (the rewrite step), then [Edit Tools for Finished Memos](Edit-Tools-for-Finished-Memos.md).
5. [Serve Compiled Memos to Firm Sites](Serve-Compiled-Memos-to-Firm-Sites.md) once compiled versions are on the server, and the rest of the skills once the edit tools exist.
