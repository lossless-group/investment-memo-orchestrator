---
name: memopop
description: Write an investment memo with MemoPop. Use when the partner asks to start, continue, or check on a memo about a company, mentions MemoPop or a deal, approves research, or wants the memo compiled.
---

# Writing a memo with MemoPop

MemoPop is a multi-step pipeline with an artifact trail: every research file,
draft, and enhancement is saved on the server, version by version. The method
lives on the server, not here, and it hands you one step at a time.

- Start with `list_deals` to find the deal, or call `create_new_deal` if the
  partner names a company it doesn't show.
- Always call `next_step` and do only what it says. Call it again after every
  `submit_artifact`, and at the start of every conversation about a deal.
- Show the partner every research file in full and wait for their approval
  before you go on.
- Submit research with `partner_approved: true` only after the partner has
  approved it, and pass their comments in `partner_notes`.
- When `next_step` reports a step as `skipped`, tell the partner in one line
  which step and why, then continue.
- On a `down` error, stop and tell the partner MemoPop is unavailable. Don't
  retry in a loop or work around it; their work so far is saved.
- An `invalid` error says what to do next in its `next` text. Do that.
- When `next_step` says the deal is done, call `compile` and give the partner
  the links.
