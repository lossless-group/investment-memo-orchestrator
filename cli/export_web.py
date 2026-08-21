"""
Export a memo as a WEBPAGE — distinct from the document/PDF export.

TWO EXPORT TYPES, DELIBERATELY
------------------------------
`export_branded.py` produces a DOCUMENT: 12pt print units, single file, styled
to become a PDF you send to a partner. A reading-position rail makes no sense
there — a paginated document answers "where am I" by itself.

This produces a WEBPAGE: responsive units, and the standard reading-position
table of contents from
`astro-knots/context-v/blueprints/Standard-Table-of-Contents-for-Every-Markdown-Collection.md`.

That blueprint is explicit that **the look is the site's business; the behaviour
is not.** So the ten requirements are implemented here in vanilla JS rather than
reinvented:

  1. outline from the PARSED TREE, never from text or the live DOM
  2. three viewport states: persistent rail / collapsed trigger / top bar
  3. reading-position tracking in all three
  4. the collapsed trigger names the current heading
  5. selecting a heading collapses the panel
  6. works with JavaScript disabled
  7. Esc and click-outside dismiss; focus returns to the trigger
  8. renders nothing below 3 entries
  9. header offset MEASURED, never hardcoded
 10. anchors come from the parser's ids, never recomputed locally

ON REQUIREMENT 1
----------------
The blueprint rejects regex/line-scanning (sees `# comment` inside a fence as a
heading) and DOM-scraping (client-side, can't see synthetic ids). We have
neither MDAST nor LFM here — but pandoc is a real markdown parser, and we read
its HTML **at build time**. By then a fence is `<pre><code>`, so a `#` comment
inside one cannot appear as a heading; and ids come from pandoc rather than a
local slugify. Verified: `## Market Context` + a fenced `# Install the package`
yields exactly one h2.

ON WIDE CONTENT
---------------
The blueprint warns that a reading-position ToC on a page that bleeds
horizontally "will look broken and the ToC will get the blame." Code, ASCII,
trees and tables each get their own scroll container here; code never wraps,
because wrapped code is misread code.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.branding import BrandConfig  # noqa: E402

MIN_TOC_ENTRIES = 3          # requirement 8
DEPTH_BAND = (2, 3)          # blueprint default: h2–h3; deeper is usually noise


@dataclass
class Heading:
    id: str
    text: str
    depth: int


def parse_markdown(md_path: Path) -> str:
    """Markdown -> HTML fragment, via a real parser."""
    out = subprocess.run(
        ["pandoc", "-f", "markdown+footnotes+pipe_tables", "-t", "html5",
         "--wrap=none", str(md_path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


_H_RE = re.compile(r'<h([1-6])\s+id="([^"]+)"[^>]*>(.*?)</h\1>', re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def extract_headings(fragment: str) -> List[Heading]:
    """Outline from the parsed output — requirement 1 and 10.

    Read at BUILD time from pandoc's HTML, so fenced code is already
    `<pre><code>` and cannot masquerade as a heading, and ids are the parser's.
    """
    out: List[Heading] = []
    for m in _H_RE.finditer(fragment):
        depth = int(m.group(1))
        if not (DEPTH_BAND[0] <= depth <= DEPTH_BAND[1]):
            continue
        text = html.unescape(_TAG.sub("", m.group(3))).strip()
        if not text:
            continue          # synthetic: keep the anchor, skip the entry
        out.append(Heading(id=m.group(2), text=text, depth=depth))
    return out


def wrap_wide_content(fragment: str) -> str:
    """Give every wide block its own scroll container — never widen the page."""
    fragment = re.sub(r"(<table\b)", r'<div class="ak-table-wrap">\1', fragment)
    fragment = re.sub(r"(</table>)", r"\1</div>", fragment)
    return fragment


def render_toc(headings: List[Heading]) -> str:
    if len(headings) < MIN_TOC_ENTRIES:
        return ""            # requirement 8
    items = "\n".join(
        f'<li class="toc-item toc-d{h.depth}">'
        f'<a href="#{html.escape(h.id)}" data-toc-link="{html.escape(h.id)}">'
        f"{html.escape(h.text)}</a></li>"
        for h in headings
    )
    return f'<ol class="toc-list">{items}</ol>'


CSS = """
:root{--toc-w:16rem;--header-h:0px;--gap:1.25rem;}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:var(--font-body);font-size:1.02rem;line-height:1.65;}
a{color:var(--accent)}
.site-header{position:sticky;top:0;z-index:40;display:flex;align-items:center;
  gap:.75rem;padding:.6rem 1.25rem;background:var(--bg);
  border-bottom:1px solid var(--border);}
.site-header img,.site-header svg{max-width:104px;height:auto;display:block}
.shell{display:grid;grid-template-columns:1fr;max-width:78rem;margin:0 auto;
  padding:0 1.25rem;gap:var(--gap);}
.prose{min-width:0;max-width:68ch;padding:1.5rem 0 6rem}
.prose h2,.prose h3{font-family:var(--font-head);color:var(--head);
  scroll-margin-top:calc(var(--header-h) + 1rem);}
.prose h2{font-size:1.7rem;margin:2.4rem 0 .8rem}
.prose h3{font-size:1.22rem;margin:1.8rem 0 .6rem}
.prose pre{overflow-x:auto;white-space:pre;background:var(--alt);
  padding:.9rem 1rem;border-radius:8px;border:1px solid var(--border)}
.prose code{font-family:ui-monospace,Menlo,monospace;font-size:.9em}
.ak-table-wrap{overflow-x:auto}
.ak-table-wrap table{min-width:34rem;border-collapse:collapse;width:100%}
.ak-table-wrap th,.ak-table-wrap td{border:1px solid var(--border);
  padding:.45rem .6rem;text-align:left}
.prose img{max-width:100%;height:auto}
.prose sup a{text-decoration:none;padding:0 .15em}

/* ---- ToC: three states render simultaneously; CSS decides ---- */
.toc-list{list-style:none;margin:0;padding:0;counter-reset:toc}
.toc-item a{display:block;padding:.28rem .55rem;border-radius:6px;
  color:var(--muted);text-decoration:none;font-size:.86rem;line-height:1.35;
  border-left:2px solid transparent}
.toc-d3 a{padding-left:1.4rem;font-size:.82rem}
.toc-item a:hover{color:var(--text);background:var(--alt)}
.toc-item a[aria-current="true"]{color:var(--accent);border-left-color:var(--accent);
  background:var(--alt)}

/* state A — persistent rail (wide only) */
.toc-rail{display:none}
@media (min-width:64rem){
  .shell{grid-template-columns:var(--toc-w) minmax(0,1fr)}
  .toc-rail{display:block;position:sticky;align-self:start;
    top:calc(var(--header-h) + 1rem);max-height:calc(100vh - var(--header-h) - 2rem);
    overflow-y:auto;padding:1.5rem .25rem 2rem}
  .toc-rail .toc-heading{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;
    color:var(--muted);padding:0 .55rem .5rem}
  .toc-bar,.toc-trigger{display:none!important}
}

/* state B — collapsed trigger + panel (narrow) */
.toc-trigger{position:fixed;right:1rem;bottom:1rem;z-index:50;display:flex;
  align-items:center;gap:.5rem;max-width:min(88vw,26rem);
  padding:.6rem .9rem;border-radius:999px;border:1px solid var(--border);
  background:var(--alt);color:var(--text);font:inherit;font-size:.84rem;
  cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.28)}
.toc-trigger .current{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--muted)}
.toc-panel{position:fixed;inset:auto 1rem 4.5rem 1rem;z-index:55;max-height:60vh;
  overflow-y:auto;padding:.75rem;border-radius:12px;border:1px solid var(--border);
  background:var(--bg);box-shadow:0 12px 40px rgba(0,0,0,.4)}
.toc-panel[hidden]{display:none}

/* state C — top bar (no-JS fallback and short viewports) */
.toc-bar{border-bottom:1px solid var(--border);padding:.5rem 0}
.toc-bar summary{cursor:pointer;font-size:.85rem;color:var(--muted)}
@media (min-width:64rem){ .toc-bar{display:none} }

/* requirement 6: with no JS the trigger is useless, the bar is not */
.no-js .toc-trigger,.no-js .toc-panel{display:none!important}
"""

JS = """
(function(){
  document.documentElement.classList.remove('no-js');
  var root=document.documentElement;
  var header=document.querySelector('.site-header');
  var links=[].slice.call(document.querySelectorAll('[data-toc-link]'));
  if(!links.length) return;

  // req 9 — the offset is MEASURED and published on :root. Never declared on
  // the component, where an own-declaration would shadow the inherited value.
  function measure(){
    var h=header?header.getBoundingClientRect().height:0;
    root.style.setProperty('--header-h', h+'px');
  }
  measure();
  window.addEventListener('resize',measure,{passive:true});

  var targets=links.map(function(a){return document.getElementById(a.dataset.tocLink);})
                   .filter(Boolean);
  var current=null;
  function setCurrent(id){
    if(id===current) return; current=id;
    links.forEach(function(a){
      var on=a.dataset.tocLink===id;
      if(on) a.setAttribute('aria-current','true'); else a.removeAttribute('aria-current');
    });
    var label=document.querySelector('.toc-trigger .current');   // req 4
    if(label){
      var hit=links.filter(function(a){return a.dataset.tocLink===id;})[0];
      label.textContent=hit?hit.textContent:'Contents';
    }
  }
  // req 3 — topmost VISIBLE heading wins; fall back to the last one scrolled
  // past, or the highlight goes blank between sections.
  function spy(){
    var top=(parseFloat(getComputedStyle(root).getPropertyValue('--header-h'))||0)+8;
    var visible=null,lastPassed=null;
    for(var i=0;i<targets.length;i++){
      var r=targets[i].getBoundingClientRect();
      if(r.top-top<=0) lastPassed=targets[i];
      if(visible===null && r.bottom>top && r.top<window.innerHeight) visible=targets[i];
    }
    var pick=visible||lastPassed||targets[0];
    if(pick) setCurrent(pick.id);
  }
  var tick=false;
  window.addEventListener('scroll',function(){
    if(tick) return; tick=true;
    requestAnimationFrame(function(){spy();tick=false;});
  },{passive:true});
  spy();

  // req 2/5/7 — collapsed trigger, dismiss, focus return
  var trigger=document.querySelector('.toc-trigger');
  var panel=document.querySelector('.toc-panel');
  if(trigger&&panel){
    function open(v){
      panel.hidden=!v;
      trigger.setAttribute('aria-expanded',String(v));
      if(!v) trigger.focus();
    }
    trigger.addEventListener('click',function(){open(panel.hidden);});
    panel.addEventListener('click',function(e){
      if(e.target.closest('a')) open(false);         // req 5
    });
    document.addEventListener('keydown',function(e){
      if(e.key==='Escape'&&!panel.hidden) open(false);   // req 7
    });
    document.addEventListener('click',function(e){
      if(panel.hidden) return;
      if(!panel.contains(e.target)&&!trigger.contains(e.target)) open(false);
    });
  }
})();
"""


def build_page(md_path: Path, brand: BrandConfig, dark: bool) -> str:
    fragment = wrap_wide_content(parse_markdown(md_path))
    headings = extract_headings(fragment)
    toc = render_toc(headings)

    theme = (brand.colors.dark_theme if dark else brand.colors.light_theme) or {}
    bg = theme.get("background", brand.colors.background)
    head_c = theme.get("text_header", brand.colors.text_dark)
    body_c = theme.get("text_body", brand.colors.text_light)
    alt = brand.colors.background_alt
    border = "rgba(255,255,255,.12)" if dark else "rgba(0,0,0,.12)"

    title = md_path.stem
    logo = ""
    lp = (brand.logo.dark_mode if dark else brand.logo.light_mode) if brand.logo else ""
    if lp and Path(lp).exists() and lp.endswith(".svg"):
        logo = Path(lp).read_text()

    rail = (f'<nav class="toc-rail" aria-label="Table of contents">'
            f'<div class="toc-heading">Contents</div>{toc}</nav>') if toc else ""
    bar = (f'<details class="toc-bar"><summary>Contents</summary>{toc}</details>') if toc else ""
    trigger = (
        '<button class="toc-trigger" aria-expanded="false" aria-controls="toc-panel">'
        '<span aria-hidden="true">☰</span><span class="current">Contents</span></button>'
        f'<div class="toc-panel" id="toc-panel" hidden>{toc}</div>'
    ) if toc else ""

    return f"""<!doctype html>
<html lang="en" class="no-js"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:wght@500;700&family=Figtree:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:{bg};--text:{body_c};--head:{head_c};--accent:{brand.colors.secondary};
--alt:{alt};--border:{border};--muted:{body_c};
--font-body:'{brand.fonts.family}',{brand.fonts.fallback};
--font-head:'{brand.fonts.header_family}',{brand.fonts.header_fallback};}}
{CSS}
</style></head>
<body>
<header class="site-header">{logo}</header>
{bar}
<div class="shell">{rail}<main class="prose">{fragment}</main></div>
{trigger}
<script>{JS}</script>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Export a memo as a webpage (reading-position ToC).")
    ap.add_argument("input", help="final-draft markdown")
    ap.add_argument("--brand", default="lossless")
    ap.add_argument("--firm", default=None)
    ap.add_argument("--mode", choices=["dark", "light"], default="dark")
    ap.add_argument("--output", default=None)
    a = ap.parse_args()

    md = Path(a.input)
    if not md.exists():
        print(f"✗ {md} not found"); return 1
    firm = a.firm or (md.parts[md.parts.index("io") + 1] if "io" in md.parts else None)
    brand = BrandConfig.load(brand_name=a.brand, firm=firm)

    page = build_page(md, brand, a.mode == "dark")
    n = len(extract_headings(parse_markdown(md)))

    out = Path(a.output) if a.output else md.parent.parent.parent / "exports" / "web" / a.mode / f"{md.stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)     # overwrite, unlike the document exporter
    print(f"✓ {out}  ({len(page)/1024:.0f} KB, {n} ToC entries, {a.mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
