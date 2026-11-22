---
type: Plans
title: "Draft a Memo from Scratch in Claude"
lede: "A partner opens Claude, says they want a memo on a company, and MemoPop walks them through it: it asks the questions the pipeline needs, lets Claude read the deck and data room where they already sit (on the partner's drive or in Google Drive), records each one so citations have something to point to, and nudges, never forces, an upload of the exact file the memo cited."
publish: true
date_created: 2026-11-22
date_modified: 2026-11-22
date_authored_initial_draft: 2026-11-22
date_authored_current_draft: 2026-11-22
date_authored_final_draft:
authors:
  - Michael Staton
augmented_with:
  - Claude Code on Claude Opus 5.5
at_semantic_version: 0.0.0.1
status: Ready
spec_reference: context-v/specs/MemoPop-Connector-API.md
tags: [Plan, Connector, Onboarding, Materials, Claude-Chat]
loop_reference: context-v/loops/Run-the-Connector-Plans-With-a-VP-Eng-and-Subagents.md
branch: connector/draft-from-scratch
owns_test_ids: [CONN-START-01, CONN-START-02, CONN-START-03, CONN-START-04, CONN-REF-01, CONN-REF-02, CONN-REF-03, CONN-REF-04, CONN-REF-05, CONN-REF-06, CONN-REF-07]
---

# Draft a Memo from Scratch in Claude

## Why

Today partners use MemoPop from Claude to change memos that already exist. The next step is drafting a new one, with Claude's chat as the whole interface. The tools for it mostly exist (`create_new_deal`, `add_materials`, the `next_step` walk, `compile`, `preview`), but a partner has to already know them. Two things are missing:

1. **A first five minutes.** Nothing asks the questions a memo needs before research starts: which company, has the firm invested (`justify`) or is it deciding (`consider`), which outline. Our own rule is that mode and outline are asked, never defaulted. And nothing tells the partner what to say next.
2. **Materials where they already are.** Decks and data rooms sit on the partner's drive or in Google Drive. `add_materials` assumes the server can fetch a link or receive a file. A Drive link fails, because the server can't sign in to the partner's Drive, and is recorded as a skip. A file dropped into Claude's chat can be read by Claude but can't be handed to a tool.

## Decisions (2026-11-22)

- **Claude reads the materials itself.** It reads a file dropped in chat, or one in Drive through Claude's own Google Drive connector. Claude in chat writes and cites the drafts. MemoPop doesn't need the file to draft.
- **MemoPop records every material Claude uses, by reference.** A record holds the title, the kind, where it lives (a Drive link, or "attached in chat by <partner>"), who added it, and optionally text Claude extracted. It gives the material an id that citations point to, and tells the next partner, or that partner's Claude, what was used and where to find it.
- **Upload is offered, never required.** The point of an upload is a fixed copy, so the file matches the citation. Decks get revised and files get moved, so the nudge applies to Drive files too. Claude offers a one-time upload link when a material is registered, and again at compile for anything still only referenced. Nothing ever blocks on it.
- **The one-time upload page already exists** (`src/connector/materials/upload_page.py`). This plan reuses it for referenced materials. When an upload arrives, it replaces the reference with the stored file under the same material id, so citations stay put.
- **The server never fetches from Google Drive.** No Google sign-in, no Drive API. A server-side Drive fetch is a possible later addition; it isn't needed for this.

## Steps

### 1. `get_started`

A new read-only tool, plus server instructions that tell Claude to call it when a partner says anything like "set me up", "draft a memo", or "new deal".

- It returns, from `whoami` and the firm's config:
  - the partner's firm;
  - the firm's outlines and which is usual;
  - the deals already in progress;
  - the questions to ask before creating a deal: company name and website, `justify` or `consider` (always asked, with what each means), outline (the firm's usual one offered, not assumed);
  - then the playbook: create the deal, register materials, start the walk.
- It writes nothing. Claude asks, then calls `create_new_deal` with the answers.
- `create_new_deal` refuses a request missing `mode` or `outline`, returning `missing_setup` with the question to ask. It never fills in a default.

### 2. Suggested next steps

Every tool result gains `next: [ … ]`: two or three things the partner could say next, in their words, not tool names. For example "upload the deck", "what's next?", "show me the draft". The server instructions tell Claude to end each reply with one short line of them. This follows the pattern other connectors use.

### 3. Materials by reference

- `add_materials` items take a new `reference`: `{ kind, title, location, note? }`. `location` is an https link, or `chat:<who>` for a file attached in chat. A reference is never fetched. Its status is `referenced`, and it doesn't count as pending in `list_deals`.
- Optional `text` alongside a reference (up to the existing 100,000 characters) is stored as the material's text, so a later step, or a partner without the file, can read what Claude read.
- `next_step` lists each step's materials with their location and status. A step whose material is only referenced tells Claude to read it from its location.
- Citations may point at a referenced material, and the submit-time checks accept it.

### 4. The upload nudge

- Registering a reference returns `upload_url` and `upload_expires_at` for that material: a one-time page for its file. Claude offers it in one line ("If you want MemoPop to keep this exact version, drop the file here"), and it is not required.
- **Offer it again, once, later.** If the material is still only referenced after a bit more work, `next_step` adds a second offer with a fresh link to its `next`. "A bit more work" means after three more approved artifacts, or when the research phase finishes, whichever comes first. After that it stops asking until compile. The material records how many times it was offered and when.
- `compile` lists materials that are still only referenced in `next`, with a fresh upload link each. That's the last reminder. It never fails or warns for them.
- When a file arrives at a referenced material's page, it gets the uploader's treatment: stored once by hash, text extracted with OCR when needed, and a skip recorded if unreadable. The material keeps its id and its status becomes `ready`, with `location` kept as history.
- `list_deals` shows `referenced_count` per deal, so the firm can see what isn't archived yet.

### 5. Docs and skills

- Update the server instructions, `llms.txt`, and the partner playbooks under `src/connector/skills/` for the start-to-finish flow.
- Add a `draft-a-new-memo` playbook.
- API changelog entry and `SERVER_VERSION` bump.

## Tests

| ID | Checks |
|---|---|
| CONN-START-01 | `get_started` returns the partner's firm, its outlines with the usual one marked, deals in progress, and the setup questions including mode with both meanings. It writes nothing. |
| CONN-START-02 | `create_new_deal` without `mode` or `outline` returns `missing_setup` naming the question, and creates nothing. With both, it creates the deal as today. |
| CONN-START-03 | Every tool result carries `next` with 1–3 entries, none of which name a tool. |
| CONN-START-04 | The server instructions direct Claude to `get_started` for a new memo, and to end replies with a next-steps line. |
| CONN-REF-01 | `add_materials` with a `reference` stores a `referenced` material without fetching anything (no network call), and returns its id, `upload_url` and `upload_expires_at`. |
| CONN-REF-02 | A reference with `text` stores that text as the material's text, and a later `next_step` hands it out. |
| CONN-REF-03 | A section citing a referenced material passes the submit-time citation checks. |
| CONN-REF-04 | Uploading through a referenced material's link stores the file by hash, keeps the material id, sets `ready`, keeps `location` as history, and the link can't be used twice. |
| CONN-REF-05 | `compile` succeeds with referenced materials, and lists each in `next` with a fresh upload link. |
| CONN-REF-07 | A still-referenced material is offered again exactly once, with a fresh link: after three more approved artifacts, or at the end of research, whichever comes first. It isn't offered a third time before compile, and an uploaded material is never offered again. |
| CONN-REF-06 | A Google Drive link given as a `reference` is never fetched by the server. Given as a plain `link`, it is still fetched as today. |

## Not in this plan

- Server-side Google Drive access.
- A folder-at-once upload page. The existing page takes files; folders can come later.
- Server-side deck analysis and source verification. They make chat-drafted memos match the pipeline's guardrails, and get their own plan next.
- Team invites and per-partner settings.

## Related

- [[Serve-the-Method-from-the-Server]]
- [[Apply-the-Deal-Folder-Uploader]]
- [[Render-Previews-and-Exports-with-LFM]]
