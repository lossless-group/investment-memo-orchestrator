"""Turn a material's bytes into text, reusing the orchestrator's document text layer.

PDFs, Word, Excel, CSV, PowerPoint, markdown, and plain text go through
``src/agents/dataroom/document_text.py`` (PyMuPDF first, with its OCR fallback
for scans). That module is loaded by file path rather than imported through
``src.agents.dataroom``, whose package ``__init__`` loads ``.env`` and imports
the model-calling agents; the connector needs neither. HTML pages (a link to a
web page) are reduced to their visible text with BeautifulSoup.

No model is called here.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
from pathlib import Path, PurePosixPath

from ..config import REPO_ROOT

DOCUMENT_TEXT = REPO_ROOT / "src" / "agents" / "dataroom" / "document_text.py"

#: Extracted text kept per material; longer text is cut and the cut is noted.
MAX_CHARS = 400_000

#: Content types we can name an extension for when the filename has none.
_BY_TYPE = {
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "text/html": ".html",
    "application/xhtml+xml": ".html",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
}


class Unextractable(Exception):
    """No text could be had from the file. ``str(exc)`` is the reason, for the partner."""


_MODULE_NAME = "memopop_connector_document_text"
_LOAD_LOCK = threading.Lock()


def _document_text():
    with _LOAD_LOCK:
        module = sys.modules.get(_MODULE_NAME)
        if module is None:
            spec = importlib.util.spec_from_file_location(_MODULE_NAME, DOCUMENT_TEXT)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules[_MODULE_NAME] = module  # dataclasses look their module up here
            try:
                spec.loader.exec_module(module)
            except BaseException:
                del sys.modules[_MODULE_NAME]
                raise
        return module


def supported_suffixes() -> set[str]:
    return set(_document_text().supported_extensions()) | {".html", ".htm"}


def suffix_for(filename: str | None, content_type: str | None, data: bytes = b"") -> str:
    """The extension that decides how a file is read."""
    suffix = PurePosixPath(filename or "").suffix.lower()
    if suffix in supported_suffixes():
        return suffix
    if data.startswith(b"%PDF-"):
        return ".pdf"
    by_type = _BY_TYPE.get((content_type or "").lower())
    if by_type:
        return by_type
    return suffix


def _html_text(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    body = "\n".join(line for line in lines if line)
    return f"# {title}\n\n{body}" if title else body


def extract(data: bytes, filename: str | None, content_type: str | None = None) -> str:
    """Return the material's text, or raise :class:`Unextractable`."""
    if not data:
        raise Unextractable("The file is empty.")
    suffix = suffix_for(filename, content_type, data)
    if suffix in (".html", ".htm"):
        text = _html_text(data)
    elif suffix in supported_suffixes():
        with tempfile.TemporaryDirectory(prefix="memopop-material-") as tmp:
            path = Path(tmp) / f"material{suffix}"
            path.write_bytes(data)
            result = _document_text().extract_text(path, max_chars=MAX_CHARS, use_cache=False)
        if result.error:
            raise Unextractable(f"The file could not be read: {result.error}.")
        text = result.text
        if result.truncated:
            text += f"\n\n[Cut at {MAX_CHARS:,} characters.]"
    else:
        shown = suffix or content_type or "this file type"
        raise Unextractable(f"MemoPop can't read {shown} files yet.")
    text = text.strip()
    if not text:
        raise Unextractable("No text could be found in the file (it may be images only).")
    if len(text) > MAX_CHARS + 100:
        text = text[:MAX_CHARS] + f"\n\n[Cut at {MAX_CHARS:,} characters.]"
    return text
