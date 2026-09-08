"""
Tests for moving base64-embedded images out of exported HTML onto the CDN.

pandoc's `--embed-resources` is what makes an export self-contained and also what
makes it enormous: a Metabologic memo is 17.3 MB, of which 15.5 MB (90%) is 36
base64 blobs. Deleting exports would fix the bytes and lose the artifact;
uploading the images keeps both.

No uploads happen here. The uploader is stubbed and what is under test is
detection, deduplication, the alt-text gate, URL parsing, and the swap.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src import export_cdn
from src.export_cdn import ALT_RE, DATA_URI_RE, IMG_TAG_RE, _parse_urls, externalize_embedded_images

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"a" * 200).decode()
PNG2 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"b" * 200).decode()


def html_with(*tags: str) -> str:
    return "<html><body>" + "".join(tags) + "</body></html>"


class TestDetection:
    def test_plain_alt_attribute(self):
        tag = f'<img src="data:image/png;base64,{PNG}" alt="A chart" />'
        assert IMG_TAG_RE.match(tag)
        assert DATA_URI_RE.search(tag)
        assert ALT_RE.search(tag).group("alt") == "A chart"

    def test_pandoc_aria_label_form(self):
        """Pandoc emits aria-label on figure images, which is the form that
        actually appears in every real export."""
        tag = f'<img role="img" aria-label="Product slide" src="data:image/png;base64,{PNG}" />'
        assert ALT_RE.search(tag).group("alt") == "Product slide"

    def test_remote_images_are_left_alone(self):
        tag = '<img src="https://ik.imagekit.io/x/already.jpg" alt="done" />'
        assert not DATA_URI_RE.search(tag)


class TestExternalize:
    def _stub_upload(self, monkeypatch, urls_by_stem):
        class Proc:
            returncode = 0
            stderr = ""
            stdout = "\n".join(
                f"https://ik.imagekit.io/test/{stem}.jpg" for stem in urls_by_stem
            )
        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        monkeypatch.setattr(export_cdn.subprocess, "run", lambda *a, **k: Proc())

    def test_identical_images_upload_once(self, tmp_path, monkeypatch):
        """A logo repeated on thirty pages is one asset, not thirty uploads."""
        f = tmp_path / "e.html"
        f.write_text(html_with(*[
            f'<img src="data:image/png;base64,{PNG}" alt="Logo" />' for _ in range(5)
        ]))
        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        r = externalize_embedded_images(f, company="X", dry_run=True)
        assert r.found == 1

    def test_distinct_images_are_counted_separately(self, tmp_path, monkeypatch):
        f = tmp_path / "e.html"
        f.write_text(html_with(
            f'<img src="data:image/png;base64,{PNG}" alt="One" />',
            f'<img src="data:image/png;base64,{PNG2}" alt="Two" />',
        ))
        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        assert externalize_embedded_images(f, company="X", dry_run=True).found == 2

    def test_image_without_a_description_stays_embedded(self, tmp_path, monkeypatch):
        """The prep-images skill treats alt text as mandatory, and an image
        nobody described is the one a reader will most need described."""
        f = tmp_path / "e.html"
        f.write_text(html_with(f'<img src="data:image/png;base64,{PNG}" />'))
        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        r = externalize_embedded_images(f, company="X", dry_run=True)
        assert r.found == 0
        assert r.skipped and "no alt text" in r.skipped[0]

    def test_swap_replaces_payload_and_shrinks_the_file(self, tmp_path, monkeypatch):
        f = tmp_path / "e.html"
        f.write_text(html_with(f'<img src="data:image/png;base64,{PNG}" alt="A chart" />'))
        before = f.stat().st_size

        captured = {}

        class Proc:
            returncode = 0
            stderr = ""
            stdout = ""

        def fake_run(cmd, **kw):
            stem = cmd[cmd.index("--name") + 1]
            captured["stem"] = stem
            Proc.stdout = f"https://ik.imagekit.io/test/{stem}.jpg"
            return Proc

        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        monkeypatch.setattr(export_cdn.subprocess, "run", fake_run)

        r = externalize_embedded_images(f, company="Metabologic", version="v0.0.2")
        text = f.read_text()
        assert r.replaced == 1 and not r.error
        assert "base64," not in text
        assert "https://ik.imagekit.io/test/" in text
        assert f.stat().st_size < before
        assert r.saved_pct > 50

    def test_alt_text_survives_the_swap(self, tmp_path, monkeypatch):
        """Only src changes; the description must still be on the tag."""
        f = tmp_path / "e.html"
        f.write_text(html_with(f'<img src="data:image/png;base64,{PNG}" alt="A chart" />'))

        class Proc:
            returncode = 0
            stderr = ""
            stdout = ""

        def fake_run(cmd, **kw):
            Proc.stdout = f"https://ik.imagekit.io/test/{cmd[cmd.index('--name')+1]}.jpg"
            return Proc

        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        monkeypatch.setattr(export_cdn.subprocess, "run", fake_run)
        externalize_embedded_images(f, company="X")
        assert 'alt="A chart"' in f.read_text()

    def test_no_cdn_leaves_the_file_untouched(self, tmp_path, monkeypatch):
        f = tmp_path / "e.html"
        original = html_with(f'<img src="data:image/png;base64,{PNG}" alt="A" />')
        f.write_text(original)
        monkeypatch.setattr(export_cdn, "cdn_available", lambda: False)
        r = externalize_embedded_images(f, company="X")
        assert "CDN unavailable" in r.error
        assert f.read_text() == original

    def test_upload_failure_leaves_the_file_untouched(self, tmp_path, monkeypatch):
        f = tmp_path / "e.html"
        original = html_with(f'<img src="data:image/png;base64,{PNG}" alt="A" />')
        f.write_text(original)

        class Proc:
            returncode = 1
            stdout = ""
            stderr = "boom"

        monkeypatch.setattr(export_cdn, "cdn_available", lambda: True)
        monkeypatch.setattr(export_cdn.subprocess, "run", lambda *a, **k: Proc())
        r = externalize_embedded_images(f, company="X")
        assert "exited 1" in r.error
        assert f.read_text() == original

    def test_missing_file_is_reported(self, tmp_path):
        assert externalize_embedded_images(tmp_path / "nope.html", company="X").error == "file not found"


class TestParseUrls:
    def test_plain_output(self):
        urls = _parse_urls("https://ik.imagekit.io/x/a-chart--abc123.jpg\n")
        assert urls["a-chart--abc123"].endswith("a-chart--abc123.jpg")

    def test_json_output(self):
        out = '{"images":[{"name":"a-chart--abc123","url":"https://ik.imagekit.io/x/a.jpg"}]}'
        assert _parse_urls(out)["a-chart--abc123"] == "https://ik.imagekit.io/x/a.jpg"

    def test_empty_output(self):
        assert _parse_urls("") == {}


class TestRealExportShape:
    """Against a genuinely produced export, if one is on disk."""

    def test_every_embedded_image_carries_a_description(self):
        candidates = list(Path("io").glob("*/deals/*/exports/*/*.html")) if Path("io").exists() else []
        if not candidates:
            pytest.skip("no exports on disk")
        html = candidates[0].read_text(encoding="utf-8", errors="replace")
        embedded = [t for t in IMG_TAG_RE.findall(html) if DATA_URI_RE.search(t)]
        if not embedded:
            pytest.skip("export carries no embedded images")
        assert all(ALT_RE.search(t) for t in embedded)
