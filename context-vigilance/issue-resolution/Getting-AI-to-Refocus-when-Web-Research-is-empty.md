You’re describing exactly the right behavior for mode: "justify": when the web is thin or noisy, do not block, just acknowledge it once and then lean fully on internal context.

Here’s how I’d encode that behavior in the system.

Behavioral rule for justify mode
For any type: "fund", mode: "justify" memo:

Primary sources
Deck (deck in the JSON)
Internal artifacts (1-research.md, earlier sections, internal notes)
data/<Fund>.json metadata
Web research role
Optional enhancer / sanity check
Never the gatekeeper that can veto a section
Fallback contract If the research agent concludes:
“Few/no fund-specific hits”
Or “conflicting entities (Watershed Health, climate platform, etc.)”
Then it must:
Emit a single, easy-to-find line, e.g.:
Web research returned limited fund-specific information; falling back to narrative based on internal materials.

And then still produce the best possible justify-mode narrative using:
Deck content
Existing memo sections
JSON metadata
It must not output long meta-paragraphs about being unable to complete the task.
Prompt shape for a justify-mode section agent
For the agents that draft or “improve/refocus” sections (e.g. Recommendation, Risks) in justify mode, I’d bake in something like:

text
You are writing a JUSTIFY-mode LP-facing memo section for an investment we already made.

Primary evidence:
- The attached deck summary and internal memo sections.
- The company JSON (name, URL, type, notes).

Web search is SECONDARY:
- Use it only to support or lightly augment internal analysis.
- If web search returns little or conflicting data, IGNORE it.

If web data is thin or conflicting, include ONE line near the top:

  "Web research returned limited fund-specific information; falling back to narrative based on internal materials."

After that, write a clear, confident justification based ONLY on the deck and internal analysis.
Do NOT:
- Question whether we should invest (the commitment is already made).
- Output meta-text about being unable to complete the task.
That gives you exactly the behavior you want:

Web-rich funds → memo leverages citations and external context.
Quiet/private funds → one small “web is thin” line, then a solid story grounded in what you already know.
How this helps the “half good, half cliff” problem
With this rule:

Early sections (already good) stay as-is.
Late sections that previously derailed into:
“I cannot complete this task because the search results…”

would instead:
Add that one fallback sentence, then
Reuse and synthesize the existing memo + deck into a coherent justification, rather than aborting.
If you want, next step I can:

Look at cli/improve_section.py and propose a --justify-mode / refocus variant with this exact prompt and behavior baked in, so you can run: