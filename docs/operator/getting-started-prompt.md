# Getting-started prompt for partners

Partners who add MemoPop by URL get no plugin skill, and Claude keeps
connector tools deferred until a request names the connector. So each partner
gets one short message to paste into Claude **once**, after connecting. It
loads MemoPop, lists the playbooks, and has Claude say what it can do. After
that, "fix the citation in the market section of the Acme memo" finds the
right tools and playbook without naming MemoPop.

The server serves the playbooks (`list_skills`, `get_skill`) and four prompts
in the connector's menu (Edit a memo, Fix a citation, Change the outline for
this memo, Check the memo on the site). See
`context-v/specs/MemoPop-Connector-API.md`, "How partners get the method".

## The prompt

Paste exactly this:

```text
I've connected MemoPop, which holds my firm's investment memos. Load MemoPop's tools, call list_skills, and tell me in a few lines what you can do with my memos. From now on, when I ask to change a memo (fix a citation, rewrite a section, change wording, change the outline, check it on the site), use MemoPop and load the matching skill with get_skill first.
```

## The onboarding email

Send with the connector link. Replace the bracketed parts.

```text
Subject: MemoPop in Claude

Hi [name],

MemoPop is ready for you in Claude. It holds [firm]'s investment memos, and you can ask Claude to change them: fix a citation, rewrite a section, change the wording, check the memo on the site.

1. In Claude (desktop or claude.ai): Customize > Connectors > Add custom connector. Name it MemoPop and paste:
   https://memopop.didi.sh/mcp
2. Select Connect and sign in with your didi.sh account. Pick [firm] if asked.
3. In a new chat, paste this once:

   I've connected MemoPop, which holds my firm's investment memos. Load MemoPop's tools, call list_skills, and tell me in a few lines what you can do with my memos. From now on, when I ask to change a memo (fix a citation, rewrite a section, change wording, change the outline, check it on the site), use MemoPop and load the matching skill with get_skill first.

After that, just say what you want changed, e.g. "fix the citation in the market section of the [company] memo". You'll also find MemoPop's prompts (Edit a memo, Fix a citation, ...) in the chat's + menu under the connector.

[sign-off]
```

Keep the two copies of the prompt identical. Untested with a real partner as
of 2026-11-21 (plan step 6, the operator's retest).
