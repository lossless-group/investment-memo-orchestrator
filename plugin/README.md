# MemoPop

Write a MemoPop investment memo from a conversation with Claude. The plugin
bundles the MemoPop connector with a short skill that keeps Claude on
MemoPop's method: one step at a time, research shown to you and approved
section by section before anything is drafted, and a branded HTML and PDF
memo at the end.

## Use it

Connect the bundled MemoPop connector from the plugin's **Connectors** tab and
sign in with your didi.sh account, choosing your firm on the consent screen.
Then ask Claude to "start a memo on Acme" or "carry on with the Acme memo".
Claude shows you each section's research and waits for your approval.

To change a finished memo, tell Claude what you want: "we have new market
research for the Acme memo" or "take the Opportunity section from this angle".
Claude reopens just those sections, redoes them with you, and compiles the next
version (v0.2.3 becomes v0.2.4). If you change your mind, ask Claude to cancel
the revision and the memo goes back as it was.

## Data

The plugin sends the company names, materials, research, and drafts you work
on to your firm's private MemoPop workspace at memopop.didi.sh, which keeps
every version. It sends nothing anywhere else and stores nothing itself.
