"""Themed memo export: a firm's design system as a self-contained theme folder.

The legacy path in export_branded.py splices brand colours into
templates/base-style.css. A theme instead owns the whole document: a real
pandoc template, its own stylesheet and fonts, and its marks. A theme lives at

    templates/themes/<name>/                (shared)
    io/<firm>/templates/themes/<name>/      (firm-private; wins if both exist)

and contains:

    template.html      pandoc HTML template (cover, $table-of-contents$, $body$)
    style.css          shared styles; fonts referenced relative to this file
    page-paper.css     @page rules for the light ground (literal colours)
    page-deep.css      @page rules for the dark ground (literal colours)
    marks/             images the template references by bare filename

A brand config opts in with a top-level `theme: <name>`; `--theme` on the
command line overrides it (`--theme none` forces the legacy path).

The memo is cleaned before pandoc sees it, because the assembled final draft
carries its own cover and contents that the theme draws properly:
- the header block (logo line, `# Title`, the bold meta lines, the rule) is
  lifted into the cover's metadata;
- the hand-written `## Table of Contents` is dropped in favour of pandoc's,
  which the PDF numbers with real page numbers;
- top-level `#` parts are moved to `##` when the memo numbers its sections at
  `##`, so every part sits at one level in the contents.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ORCHESTRATOR = Path(__file__).resolve().parent.parent


@dataclass
class MemoHeader:
    title: Optional[str] = None
    prepared_by: Optional[str] = None
    date: Optional[str] = None


def find_theme(name: str, firm: Optional[str] = None) -> Path:
    candidates = []
    if firm:
        candidates.append(ORCHESTRATOR / "io" / firm / "templates" / "themes" / name)
    candidates.append(ORCHESTRATOR / "templates" / "themes" / name)
    for c in candidates:
        if (c / "template.html").exists() and (c / "style.css").exists():
            return c
    raise FileNotFoundError(
        f"Theme '{name}' not found (looked in: {', '.join(str(c) for c in candidates)})"
    )


_META = re.compile(r"^\*\*(Prepared by|Date):\*\*\s*(.+?)\s*$", re.I)


def clean_memo(markdown: str) -> tuple[str, MemoHeader]:
    """Strip the assembled header and hand-written contents; return body + header."""
    header = MemoHeader()
    lines = markdown.splitlines()

    # 1. Header block: everything before the first `---` rule, provided it
    #    contains the `# Title` line and no section heading.
    try:
        rule = next(i for i, l in enumerate(lines) if l.strip() == "---")
    except StopIteration:
        rule = None
    if rule is not None and rule < 25:
        block = lines[:rule]
        titles = [l for l in block if re.match(r"^#\s+\S", l)]
        if len(titles) == 1 and not any(re.match(r"^##+\s", l) for l in block):
            header.title = titles[0].lstrip("#").strip()
            for l in block:
                m = _META.match(l.strip())
                if m:
                    key = m.group(1).lower()
                    if key == "date":
                        header.date = m.group(2)
                    else:
                        header.prepared_by = m.group(2)
            lines = lines[rule + 1:]

    # 2. Hand-written contents: `## Table of Contents` up to the next rule or
    #    the next heading, whichever comes first.
    out, skipping = [], False
    for l in lines:
        if re.match(r"^#{1,3}\s+Table of Contents\s*$", l, re.I):
            skipping = True
            continue
        if skipping:
            if l.strip() == "---":
                skipping = False
                continue
            if re.match(r"^#{1,6}\s", l):
                skipping = False
            else:
                continue
        out.append(l)
    body = "\n".join(out).lstrip("\n")
    from cli.export_branded import strip_memo_mode_label
    body = strip_memo_mode_label(body)

    # 3. A "Citations"/"References" heading whose section holds nothing but
    #    footnote definitions: pandoc moves the definitions into the Sources
    #    list, which would leave the heading stranded on an empty page.
    body = re.sub(
        r"^#{1,6}\s+(?:Citations|References|Footnotes|Notes)\s*\n"
        r"(?=(?:\s*\n|\[\^[^\]]+\]:[^\n]*\n(?:[ \t]+[^\n]*\n)*)*(?:#{1,6}\s|\Z))",
        "", body, flags=re.M | re.I)

    # 4. One level for every part.
    if re.search(r"^##\s+\d+\.\s", body, re.M):
        body = re.sub(r"^#\s+(?=\S)", "## ", body, flags=re.M)

    return body + "\n", header


def _pandoc() -> str:
    for p in (shutil.which("pandoc"), "/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc"):
        if p and Path(p).exists():
            return p
    raise RuntimeError("pandoc not found")


def convert_with_theme(
    md_file: Path,
    html_path: Path,
    brand,
    theme_dir: Path,
    dark_mode: bool,
    company_name: Optional[str] = None,
    version: Optional[str] = None,
) -> Path:
    """Render one memo to a single self-contained HTML file using a theme."""
    body, header = clean_memo(md_file.read_text(encoding="utf-8"))

    title = header.title or company_name or md_file.stem
    prepared_by = header.prepared_by or brand.company.name
    confidential = (brand.company.confidential_footer or "").format(company_name=brand.company.name)
    page_css = theme_dir / ("page-deep.css" if dark_mode else "page-paper.css")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "memo.md"
        src.write_text(body, encoding="utf-8")
        args = [
            _pandoc(), str(src),
            "-f", "markdown",
            "-t", "html5",
            "--standalone",
            "--embed-resources",
            f"--template={theme_dir / 'template.html'}",
            f"--css={theme_dir / 'style.css'}",
            f"--css={page_css}",
            "--toc", "--toc-depth=3",
            f"--resource-path={md_file.parent}:{theme_dir / 'marks'}:{theme_dir}",
            "-M", f"title={title}",
            "-M", "subtitle=Investment memo",
            "-M", "lang=en-GB",
            "-V", f"mode={'dark-mode' if dark_mode else 'light-mode'}",
            "-V", f"prepared-by={prepared_by}",
            "-o", str(html_path),
        ]
        if header.date:
            args += ["-V", f"date={header.date}"]
        if version:
            args += ["-V", f"version={version}"]
        if confidential:
            args += ["-V", f"confidential={confidential}"]
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"pandoc failed: {result.stderr.strip()}")
        for line in result.stderr.splitlines():
            if line.strip():
                print(f"  pandoc: {line.strip()}")

        # Reuse the legacy exporter's footnote repairs: restore definitions pandoc
        # dropped, then merge duplicate sources Obsidian-style.
        utils = Path(__file__).parent / "utils"
        for script, extra in (("restore_uncited_footnotes.py", [str(src)]), ("fix_citations.py", [])):
            path = utils / script
            if path.exists():
                r = subprocess.run([sys.executable, str(path), str(html_path), *extra],
                                   capture_output=True, text=True)
                if r.stdout.strip():
                    print(f"  {r.stdout.strip()}")

    return html_path
