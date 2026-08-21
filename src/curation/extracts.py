"""
The `# Extracts` body section — render and parse.

WHY MARKDOWN AND NOT JSON
-------------------------
Quotes, stats and claims are punctuation-heavy strings full of `: " $ % [ ] |` —
every character that breaks YAML — so they live in the body rather than the
frontmatter. They are LFM container directives rather than prose so that **the
parse IS the extraction**: there is no second structured copy to keep in sync.
See `agent-skills/source-with-extracts-md/SKILL.md` and
`corpora-builder/context-v/blueprints/Source-File-Schema-Reconciliation.md`,
which instructs adopters not to re-invent this as YAML.

A compiled JSON sidecar was considered and rejected. Its only real job would be
structured querying, and that belongs in the shared SurrealDB registry, where it
is cross-deal and cross-app — not in a per-deal file that only memopop reads and
that goes stale the moment an analyst edits an extract by hand.

THE COST THIS ACCEPTS
---------------------
Parsing becomes load-bearing: a malformed directive means a silently dropped
extract. memopop already paid for that lesson once — a stray `---` inside
`Sources.md` hid 13 sources from every consumer for three weeks while the file
looked fine to grep and to diff. So this parser **warns loudly** on anything it
cannot read rather than skipping quietly.

SHAPE
-----
    # Extracts

    ## Quotes
    :::quote{page="12" grounded="true" topic="pricing"}
    "Installed capacity will reach 10 GW by 2030."
    :::

    ## Claims
    :::claim{confidence="high" topic="competition"}
    Routing layers are exposed to provider margin compression.
    :::

    ## Stats
    :::stat{unit="USD" period="2026" grounded="true"}
    $113M Series B at ~$1.3B valuation.
    :::
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

EXTRACTS_HEADING = "# Extracts"

# kind -> the `## Heading` it files under, in render order.
KIND_SECTIONS = [
    ("quote", "Quotes"),
    ("claim", "Claims"),
    ("stat", "Stats"),
    ("reference", "References"),
]
KINDS = {k for k, _ in KIND_SECTIONS}

_OPEN = re.compile(r"^:::(?P<kind>[a-z_]+)(?:\{(?P<attrs>[^}]*)\})?\s*$", re.M)
_CLOSE = ":::"
_ATTR = re.compile(r'(?P<key>[a-zA-Z_][\w-]*)\s*=\s*"(?P<val>[^"]*)"')

# Anything that looks like it wants to be a directive but is not parseable.
_SUSPECT = re.compile(r"^:::(?!\s*$)(?P<rest>.*)$", re.M)
# The closing fence must be a line that is EXACTLY `:::`. Matching a bare "\n:::"
# lets an unterminated block swallow the NEXT directive's opening fence — and any
# headings between them — producing garbage items and no warning at all.
_CLOSE_LINE = re.compile(r"^:::\s*$", re.M)


def _fmt_attrs(attrs: Dict[str, Any]) -> str:
    clean = {k: v for k, v in (attrs or {}).items()
             if v not in (None, "", [], {}) and k != "text"}
    if not clean:
        return ""
    inner = " ".join(f'{k}="{str(v).replace(chr(34), chr(39))}"' for k, v in clean.items())
    return "{" + inner + "}"


def render_extracts(items: List[Dict[str, Any]]) -> str:
    """Render items into an `# Extracts` section. Empty items -> empty string."""
    if not items:
        return ""
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        kind = (it.get("kind") or "").strip().lower()
        # insight / point_of_view have no directive of their own in the spec;
        # file them as claims rather than inventing vocabulary.
        if kind in ("insight", "point_of_view", "pov"):
            it = {**it, "kind": "claim", "subtype": kind}
            kind = "claim"
        if kind not in KINDS:
            continue
        by_kind.setdefault(kind, []).append(it)

    if not by_kind:
        return ""

    lines = [EXTRACTS_HEADING, ""]
    for kind, heading in KIND_SECTIONS:
        group = by_kind.get(kind)
        if not group:
            continue
        lines.append(f"## {heading}")
        lines.append("")
        for it in group:
            text = " ".join(str(it.get("text") or "").split())
            if not text:
                continue
            attrs = {k: v for k, v in it.items()
                     if k not in ("kind", "text", "verbatim")}
            lines.append(f":::{kind}{_fmt_attrs(attrs)}")
            lines.append(text)
            lines.append(_CLOSE)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_extracts(body: str, *, source_label: str = "") -> List[Dict[str, Any]]:
    """Parse an `# Extracts` section back into items.

    Warns loudly — to stdout — on directive-looking lines it cannot read. A
    silently dropped extract is the failure mode this whole format has to avoid.
    """
    if not body:
        return []
    idx = body.find(EXTRACTS_HEADING)
    if idx == -1:
        return []
    region = body[idx:]

    items: List[Dict[str, Any]] = []
    consumed: List[tuple] = []
    for m in _OPEN.finditer(region):
        kind = m.group("kind").lower()
        attrs = {a.group("key"): a.group("val")
                 for a in _ATTR.finditer(m.group("attrs") or "")}
        rest = region[m.end():]
        close_m = _CLOSE_LINE.search(rest)
        close = close_m.start() if close_m else -1
        # A close fence that sits past another directive's opening means this
        # block was never terminated.
        nxt = _OPEN.search(rest)
        if close != -1 and nxt and nxt.start() < close:
            close = -1
        if close == -1:
            print(f"  ⚠️  extracts: unterminated :::{kind} block"
                  + (f" in {source_label}" if source_label else "")
                  + " — extract dropped")
            continue
        text = rest[:close].strip()
        consumed.append((m.start(), m.end() + close_m.end()))
        if not text:
            print(f"  ⚠️  extracts: empty :::{kind} block"
                  + (f" in {source_label}" if source_label else ""))
            continue
        if kind not in KINDS:
            print(f"  ⚠️  extracts: unknown directive :::{kind}"
                  + (f" in {source_label}" if source_label else "")
                  + " — kept, but not a spec'd kind")
        items.append({"kind": kind, "text": text, **attrs})

    # Anything ::: -ish that no successful parse covered.
    for m in _SUSPECT.finditer(region):
        pos = m.start()
        if any(a <= pos < b for a, b in consumed):
            continue
        frag = m.group("rest").strip()[:60]
        if frag and not frag.startswith(":"):
            print(f"  ⚠️  extracts: unparseable directive line ':::{frag}'"
                  + (f" in {source_label}" if source_label else ""))
    return items


def split_body(body: str) -> tuple:
    """(content_before_extracts, extracts_section). Either may be empty."""
    if not body:
        return "", ""
    idx = body.find(EXTRACTS_HEADING)
    if idx == -1:
        return body, ""
    return body[:idx].rstrip(), body[idx:].strip()


def merge_extracts(body: str, items: List[Dict[str, Any]]) -> str:
    """Replace (or append) the `# Extracts` section, leaving content untouched.

    The fetched content is sacrosanct — stored verbatim, never rewritten. Only
    the extracts section is regenerated.
    """
    content, _ = split_body(body)
    rendered = render_extracts(items)
    if not rendered:
        return content
    return f"{content.rstrip()}\n\n{rendered}" if content.strip() else rendered
