# Connect Claude to MemoPop

How a partner adds MemoPop to Claude, what they see when they sign in, and how
the operator runs the real-Claude test (CONN-PLUG-02). Checked against Claude's
docs on 2026-10-10: *Plugin structure and testing*
(https://claude.com/docs/plugins/build), *Plugin feature support across
platforms* (https://claude.com/docs/plugins/platform-support), and *Build an MCP
server for Claude* (https://claude.com/docs/connectors/building).

## Two ways in

| | Connector only | Plugin (connector + skill) |
|---|---|---|
| What Claude gets | MemoPop's eight tools and the server's short instructions | The same tools, plus the `memopop` skill that keeps Claude on the method |
| Recommended | For a quick try | **Yes**, for real memos |

The connector URL is always **`https://memopop.didi.sh/mcp`**, path included.

## Add the connector by URL (Claude Desktop or claude.ai)

1. **Customize > Connectors > Add custom connector.**
2. Name it `MemoPop` and paste `https://memopop.didi.sh/mcp`. Leave the advanced
   OAuth fields empty: Claude registers itself with id.didi.sh.
3. Select **Connect**. A browser window opens on **id.didi.sh**:
   - **Sign in** with your didi.sh account.
   - The **consent screen** names Claude as the app asking for access, and asks
     which **firm** to connect. Pick your firm (most people have one) and allow.
4. Back in Claude, the connector shows as connected with its eight tools.

On Team and Enterprise plans an Owner adds the connector for the organization
once; each member then connects and signs in with their own account.

Until didi.sh OAuth is deployed, step 3 cannot complete. The interim static
keys work only for Claude Code and the health check, and are never given to a
partner.

## Install the plugin

The plugin lives in `plugin/` in this repository:

```
plugin/
  .claude-plugin/plugin.json   # the manifest
  .mcp.json                    # the connector: https://memopop.didi.sh/mcp, no secrets
  skills/memopop/SKILL.md      # the thin skill: the method's rules
  README.md
```

No build step. To install it on your own account:

1. Zip the folder: `cd plugin && zip -r ../memopop-plugin.zip . -x '.DS_Store'`.
2. In claude.ai or Claude Desktop: **Customize > Plugins > Add > Upload plugin**,
   and pick the zip.
3. Open the plugin's **Connectors** tab and connect MemoPop (sign-in as above).
4. Ask Claude which skills it has from plugins; `memopop` should be listed.

For a team, push the folder to a Git repository set up as a marketplace and have
each person add it from **Customize > Plugins > Add > Add marketplace**. In Claude
Code, `claude --plugin-dir ./plugin` loads it for one session.

Before releasing a change, run `claude plugin validate plugin` (the test suite
runs it when Claude Code is installed) and raise `version` in `plugin.json`.

Where it loads: skills load in chat, Cowork, and Claude Code. The remote
connector appears on the plugin's **Connectors** tab in chat and Cowork and
works once connected; Claude Code connects directly.

## What the partner sees in a memo

They say *start a memo on Acme*. Claude checks `list_deals`, creates the deal,
then works step by step from `next_step`. After each section's research, Claude
shows it in full and waits; nothing is drafted until the partner approves. If the
server skips an optional step, Claude says so in one line and carries on. If
MemoPop is down, Claude stops and says so. At the end Claude compiles and gives
links to the HTML and PDF, which work for seven days.

## The real-Claude test (CONN-PLUG-02)

Real Claude, through the Claude API's MCP connector, runs a three-section deal
against the **deployed** server with the plugin's skill as its system prompt. A
scripted partner approves research only after it has been shown. The test checks
the server's record: tools in order, research approved before any draft, one
forced skip mentioned and passed, and one forced `down` that stops the run.
It is not part of CI; run it before a release.

### One-time server setup

The forced skip and `down` come from a test-only hook (`src/connector/faults.py`)
that fires only when **both** of these are true, so it can never touch a real firm:

1. The service has `MEMOPOP_FAULT_FIRMS=test-firm`. Never add any other firm.
2. `test-firm` has the `real-claude-three` outline in its own folder. Install it
   where the volume is mounted (on Railway, `railway ssh`):

   ```
   python -m src.connector.faults install-outline test-firm
   ```

That outline turns off `research.sources` and makes `next_step` return
`service_unavailable` at the first enhancement. Deals on any other outline,
including the health check's, are untouched.

### Run it

```
ANTHROPIC_API_KEY=... \
MEMOPOP_LIVE_URL=https://memopop.didi.sh \
MEMOPOP_HEALTH_KEY=<test-firm static key> \
uv run pytest -s -p no:cacheprovider tests/connector/test_real_claude.py -k real_claude_runs
```

Optional: `MEMOPOP_REAL_CLAUDE_MODEL` (default `claude-haiku-5-5`),
`MEMOPOP_REAL_CLAUDE_MAX_REQUESTS` (default 24), `MEMOPOP_REAL_CLAUDE_REPORT`
(path for the JSON report: every tool call, the partner's turns, tokens, and an
estimated cost). A preflight checks the key and the outline before any token is
spent. Each run leaves one deal named `Fixture Co <UTC timestamp>` in `test-firm`.
