"""
Deck HTML Export

Renders a transcribed deck as a single self-contained HTML file: every slide
image beside what the stenographer read off it.

**The reading instruction is the point.** A swipe deck tells a phone user to
turn sideways because the failure mode is a cramped viewport. This surface has a
different failure mode entirely — a reader trusting the transcription instead of
checking it. The image is the source of truth and the text is an agent's reading
of it, so the page is laid out to make comparison the default posture and says so
in a banner nobody can miss.

Images come from the CDN where they have been uploaded and fall back to relative
local paths. The HTML carries no scripts beyond keyboard navigation and no
external stylesheets, so it opens from a file:// URL, survives being emailed, and
works with the local server that serves the slide directory.
"""

from __future__ import annotations

import html
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# What a reader is told before they scroll. Written for this surface: the risk
# here is misplaced trust, not a cramped viewport.
READING_GUIDANCE = [
    ("The slide is the source. The text is a reading of it.",
     "Everything below each image was transcribed by an agent. Where they "
     "disagree, the image is right. Read them side by side."),
    ("Check anything marked <em>partial</em> or <em>illegible</em>.",
     "A slide whose transcription fidelity is not <em>verbatim</em> had text the "
     "agent could not read cleanly. Those are flagged in the slide header."),
    ("<em>Claims to verify</em> are unverified.",
     "They are assertions the deck makes, pulled out for a fact-checker. Nothing "
     "here has confirmed them."),
    ("Charts and figures are crops, and some are cut short.",
     "Bounding boxes around large diagrams sometimes stop before the visual's "
     "true edges. If a crop looks wrong, the full slide is directly above it."),
    ("Use <kbd>J</kbd> / <kbd>K</kbd> or <kbd>↓</kbd> / <kbd>↑</kbd> to move slide to slide.",
     "<kbd>T</kbd> collapses every transcription so the deck reads as a deck; "
     "press it again to bring the text back."),
]

_CSS = """
:root {
  --bg:#faf9f7; --panel:#fff; --ink:#1a1a1a; --muted:#6b6b6b; --line:#e2ded8;
  --accent:#7c5cff; --warn:#b45309; --warn-bg:#fef6e7; --code:#f4f2ee;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#16151a; --panel:#1e1d24; --ink:#eceaf0; --muted:#a09eaa;
          --line:#302e38; --accent:#a48cff; --warn:#fbbf24; --warn-bg:#2a2010;
          --code:#26242e; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif; }
.wrap { max-width:1180px; margin:0 auto; padding:2.5rem 1.25rem 6rem; }
header.deck { border-bottom:2px solid var(--line); padding-bottom:1.5rem; margin-bottom:1.5rem; }
header.deck h1 { margin:0 0 .3rem; font-size:1.9rem; letter-spacing:-.02em; }
.meta { color:var(--muted); font-size:.9rem; }
.meta strong { color:var(--ink); font-weight:600; }
.guide { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent);
  border-radius:10px; padding:1.1rem 1.3rem; margin:1.5rem 0 2.5rem; }
.guide h2 { margin:0 0 .7rem; font-size:.8rem; text-transform:uppercase;
  letter-spacing:.09em; color:var(--accent); }
.guide ol { margin:0; padding-left:1.2rem; }
.guide li { margin:.5rem 0; }
.guide li b { font-weight:600; }
.guide li span { color:var(--muted); display:block; font-size:.9rem; }
kbd { background:var(--code); border:1px solid var(--line); border-bottom-width:2px;
  border-radius:4px; padding:.05em .4em; font:600 .85em ui-monospace,Menlo,monospace; }
section.slide { background:var(--panel); border:1px solid var(--line); border-radius:12px;
  padding:1.4rem; margin-bottom:2rem; scroll-margin-top:1rem; }
section.slide:target { border-color:var(--accent); }
.slide-head { display:flex; flex-wrap:wrap; gap:.5rem 1rem; align-items:baseline;
  margin-bottom:.9rem; }
.idx { font:600 .85rem ui-monospace,Menlo,monospace; color:var(--muted); }
.type { background:var(--code); border-radius:99px; padding:.15em .7em;
  font-size:.78rem; font-weight:600; }
.flag { color:var(--warn); background:var(--warn-bg); border-radius:99px;
  padding:.15em .7em; font-size:.78rem; font-weight:600; }
.slide-img { display:block; width:100%; height:auto; border:1px solid var(--line);
  border-radius:8px; background:#fff; }
.core { font-size:1.05rem; margin:1rem 0 .4rem; }
.tags { color:var(--muted); font-size:.85rem; margin-bottom:.6rem; }
details { border-top:1px solid var(--line); padding-top:.7rem; margin-top:.9rem; }
details summary { cursor:pointer; font-weight:600; font-size:.9rem; color:var(--muted); }
details summary:hover { color:var(--ink); }
pre { background:var(--code); border-radius:8px; padding:.9rem; overflow-x:auto;
  font-size:.82rem; line-height:1.5; }
ul.claims { margin:.5rem 0; padding-left:1.2rem; }
ul.claims li { margin:.3rem 0; font-size:.92rem; }
.visuals { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
  gap:1rem; margin-top:.9rem; }
.visual figure { margin:0; }
.visual img { width:100%; border:1px solid var(--line); border-radius:6px; background:#fff; }
.visual figcaption { font-size:.8rem; color:var(--muted); margin-top:.35rem; }
.visual .kindtag { font-weight:600; color:var(--ink); }
.rejected { border:1px dashed var(--line); border-radius:6px; padding:.7rem;
  font-size:.8rem; color:var(--muted); }
nav.toc { position:sticky; top:0; background:var(--bg); padding:.6rem 0;
  border-bottom:1px solid var(--line); margin-bottom:1.5rem; font-size:.85rem;
  display:flex; gap:.4rem; flex-wrap:wrap; z-index:5; }
nav.toc a { color:var(--muted); text-decoration:none; padding:.1em .45em;
  border-radius:4px; font:600 .8rem ui-monospace,Menlo,monospace; }
nav.toc a:hover { background:var(--code); color:var(--ink); }
body.text-hidden details, body.text-hidden .core,
body.text-hidden .tags, body.text-hidden .visuals { display:none; }
@media print { nav.toc, .guide { display:none; } section.slide { break-inside:avoid; } }
"""

_JS = """
const slides = [...document.querySelectorAll('section.slide')];
let at = 0;
function go(step) {
  at = Math.max(0, Math.min(slides.length - 1, at + step));
  slides[at].scrollIntoView({behavior:'smooth', block:'start'});
}
document.addEventListener('keydown', e => {
  if (e.target.matches('input,textarea')) return;
  if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); go(1); }
  if (e.key === 'k' || e.key === 'ArrowUp')   { e.preventDefault(); go(-1); }
  if (e.key === 't') document.body.classList.toggle('text-hidden');
});
"""


def _esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


def _front(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    try:
        return yaml.safe_load(text.split("---", 2)[1]) or {}
    except yaml.YAMLError:
        return {}


def _body_after_frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.split("---", 2)[2] if text.startswith("---") else text


def _image_src(front: Dict[str, Any]) -> str:
    """CDN first so the file travels; local path as the fallback."""
    return front.get("slide_image_cdn") or front.get("slide_image_local") or ""


def _visual_html(entries: List[Dict[str, Any]], label: str) -> str:
    if not entries:
        return ""
    cards: List[str] = []
    for entry in entries:
        if entry.get("status") == "rejected":
            note = (entry.get("notes") or ["could not be isolated"])[0]
            cards.append(
                f'<div class="visual"><div class="rejected"><b>{_esc(entry.get("kind"))}</b> — '
                f'not cropped: {_esc(note)}</div></div>'
            )
            continue
        src = entry.get("cdn") or entry.get("local") or ""
        detail = entry.get("reads") or entry.get("depicts") or entry.get("alt") or ""
        axes = ""
        if entry.get("x_axis") or entry.get("y_axis"):
            axes = (f'<br><em>x:</em> {_esc(entry.get("x_axis"))} · '
                    f'<em>y:</em> {_esc(entry.get("y_axis"))}')
        cards.append(
            f'<div class="visual"><figure>'
            f'<img src="{_esc(src)}" alt="{_esc(entry.get("alt"))}" loading="lazy">'
            f'<figcaption><span class="kindtag">{_esc(entry.get("kind"))}</span> — '
            f'{_esc(detail)}{axes}</figcaption></figure></div>'
        )
    return f'<details open><summary>{label} ({len(entries)})</summary>' \
           f'<div class="visuals">{"".join(cards)}</div></details>'


def export_deck_html(
    deck_dir: str | Path,
    output_path: Optional[str | Path] = None,
) -> Path:
    """
    Render one transcribed deck to a single HTML file.

    Args:
        deck_dir: A stenographer output directory.
        output_path: Where to write. Defaults to ``<deck_dir>/<deck>.html``.
    """
    deck_dir = Path(deck_dir)
    slide_docs = sorted(deck_dir.glob("[0-9]*.md"))
    if not slide_docs:
        raise FileNotFoundError(f"no slide documents in {deck_dir}")

    deck_meta: Dict[str, Any] = {}
    if (deck_dir / "deck.yaml").exists():
        deck_meta = yaml.safe_load((deck_dir / "deck.yaml").read_text(encoding="utf-8")) or {}

    company = deck_meta.get("company") or deck_dir.parent.name
    title = f"{company} — {deck_meta.get('round', '')} {deck_meta.get('deck_variant', '')} deck".strip()

    guidance = "".join(
        f"<li><b>{head}</b><span>{body}</span></li>" for head, body in READING_GUIDANCE
    )

    toc: List[str] = []
    sections: List[str] = []

    for doc in slide_docs:
        front = _front(doc)
        index = doc.name.split("-")[0]
        toc.append(f'<a href="#s{index}">{index}</a>')

        flags: List[str] = []
        if front.get("transcription_fidelity") not in (None, "verbatim"):
            flags.append(f'<span class="flag">{_esc(front["transcription_fidelity"])}</span>')
        if front.get("reveal_sequence"):
            evidence = front.get("reveal_evidence", "")
            flags.append(
                f'<span class="flag">reveal {_esc(front["reveal_sequence"])}'
                f'{" · " + _esc(evidence) if evidence else ""}</span>'
            )
        for warning in front.get("extraction_warnings") or []:
            flags.append(f'<span class="flag">{_esc(warning[:70])}</span>')

        claims = front.get("claims_to_verify") or []
        claims_html = (
            f'<details><summary>Claims to verify ({len(claims)})</summary>'
            f'<ul class="claims">' + "".join(f"<li>{_esc(c)}</li>" for c in claims) + "</ul></details>"
        ) if claims else ""

        content = front.get("content")
        content_html = ""
        if content is None:
            body = _body_after_frontmatter(doc)
            if "```json-content" in body:
                raw = body.split("```json-content", 1)[1].split("```", 1)[0].strip()
                content_html = (
                    '<details><summary>Transcribed content</summary>'
                    f'<pre>{_esc(raw)}</pre></details>'
                )

        sections.append(f"""
<section class="slide" id="s{index}">
  <div class="slide-head">
    <span class="idx">{_esc(front.get('index_position', index))}</span>
    <span class="type">{_esc(front.get('slide_type', 'unknown'))}</span>
    {''.join(flags)}
  </div>
  <img class="slide-img" src="{_esc(_image_src(front))}"
       alt="{_esc(front.get('slide_image_alt'))}" loading="lazy">
  <p class="core">{_esc(front.get('core_message'))}</p>
  <p class="tags">{_esc(' · '.join(front.get('tags') or []))}</p>
  {_visual_html(front.get('charts') or [], 'Charts')}
  {_visual_html(front.get('imagery') or [], 'Imagery')}
  {claims_html}
  {content_html}
</section>""")

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<header class="deck">
  <h1>{_esc(title)}</h1>
  <p class="meta">
    <strong>{len(slide_docs)}</strong> slides ·
    dated <strong>{_esc(deck_meta.get('date_on_deck', 'unknown'))}</strong>
    ({_esc(deck_meta.get('date_source', '—'))}, {_esc(deck_meta.get('date_confidence', '—'))} confidence) ·
    authored by <strong>{_esc(deck_meta.get('authored_by', 'unknown'))}</strong><br>
    source: <code>{_esc(deck_meta.get('source_file', ''))}</code><br>
    transcribed {_esc(deck_meta.get('date_last_analyzed', ''))} by
    {_esc(deck_meta.get('analyzed_with', 'an agent'))} ·
    exported {date.today().isoformat()}
  </p>
</header>
<div class="guide">
  <h2>Reading this export</h2>
  <ol>{guidance}</ol>
</div>
<nav class="toc">{''.join(toc)}</nav>
{''.join(sections)}
</div><script>{_JS}</script></body></html>"""

    output_path = Path(output_path) if output_path else deck_dir / f"{deck_dir.name}.html"
    output_path.write_text(page, encoding="utf-8")
    return output_path


def export_all_decks(slides_root: str | Path) -> List[Path]:
    """Export every transcribed deck under a slides root."""
    slides_root = Path(slides_root)
    written: List[Path] = []
    for deck_yaml in sorted(slides_root.rglob("deck.yaml")):
        try:
            written.append(export_deck_html(deck_yaml.parent))
        except (FileNotFoundError, OSError) as e:
            print(f"   ⚠️  {deck_yaml.parent.name}: {e}")
    return written
