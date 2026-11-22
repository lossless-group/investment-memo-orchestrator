"""Previews and exports rendered with LFM (CONN-LFM-01 to CONN-LFM-06).

Plan: context-v/plans/Render-Previews-and-Exports-with-LFM.md. The renderer is
a Node script (src/connector/render/lfm_render.mjs) on @lossless-group/lfm,
pinned to one release; these tests run it for real, so they need Node and
``npm ci --prefix src/connector/render``.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import sys

import pytest

from src.connector.config import ConnectorSettings
from src.connector.errors import ConnectorError
from src.connector.mcp_app import INSTRUCTIONS
from src.connector.render import lfm
from src.connector.workspace import open_workspace

from .conftest import REPO, call, deal_json, key_headers, new_deal
from .fake_claude import Direct, FakeClaude

SKILLS_DIR = REPO / "src" / "connector" / "skills"

#: Hex keys defined in one order and cited in another, with a callout.
HEX_MEMO = """## Executive Summary

Fixture Co counts stock by camera.[^b7k2m9] Its market is growing.[^a3f9b2] The camera
claim again.[^b7k2m9]

> [!warning] Unverified
> The growth figure comes from one survey.

### Citations

[^a3f9b2]: 2025, Mar 03. [Synthetic Industry Note](https://example.org/fixture/note). Fixture Press. Published: 2025-03-03 | Updated: N/A

[^b7k2m9]: 2025, Jan 08. [Synthetic Retail Survey](https://example.org/fixture/survey). Fixture Press. Published: 2025-01-08 | Updated: N/A
"""


def _numbers(html: str) -> list[tuple[str, str]]:
    """(hex key, number shown) for every inline citation, in reading order."""
    return re.findall(r'href="#user-content-fn-([a-z0-9]+)"[^>]*>(\d+)</a>', html)


def _sources(html: str) -> list[str]:
    block = html[html.index('<ol class="sources">') :]
    return re.findall(r'<li id="user-content-fn-([a-z0-9]+)"', block)


def drafted(ws) -> str:
    """fixture-co with every section drafted, never compiled."""
    fake = FakeClaude(Direct(ws))
    deal = fake.create()
    fake.walk(deal, until=lambda s: s["phase"] == "enhance", compile=False)
    return deal


# ------------------------------------------------------------------ CONN-LFM-01


@pytest.mark.spec("CONN-LFM-01")
def test_renderer_numbers_hex_citations_by_first_citation_and_renders_callouts():
    html = lfm.render_markdown(HEX_MEMO)

    # Numbered in first-cited order, whatever order the definitions are in.
    assert _numbers(html) == [("b7k2m9", "1"), ("a3f9b2", "2"), ("b7k2m9", "1")]
    assert _sources(html) == ["b7k2m9", "a3f9b2"]
    assert '<a href="https://example.org/fixture/survey">Synthetic Retail Survey</a>' in html
    # No definition is left as raw markdown, and the sources list sits under the heading.
    assert "[^" not in html
    assert re.search(r'Citations</h3>\s*<ol class="sources">', html)

    # The callout is plain HTML with its title; no Astro component.
    assert re.search(r'<div class="callout callout-warning">\s*<p class="callout-title">', html)
    assert "Unverified" in html and "one survey" in html


@pytest.mark.spec("CONN-LFM-01")
def test_the_lfm_package_is_pinned_exactly():
    package = json.loads((lfm.RENDER_DIR / "package.json").read_text())
    assert package["dependencies"]["@lossless-group/lfm"] == lfm.LFM_VERSION == "0.11.0"
    for name, version in package["dependencies"].items():
        assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{name} is not pinned: {version}"

    lock = json.loads((lfm.RENDER_DIR / "package-lock.json").read_text())
    assert lock["packages"]["node_modules/@lossless-group/lfm"]["version"] == "0.11.0"
    installed = json.loads(lfm.LFM_PACKAGE.read_text())
    assert installed["version"] == "0.11.0"


# ------------------------------------------------------------------ CONN-LFM-02


@pytest.mark.spec("CONN-LFM-02")
def test_missing_node_or_package_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMOPOP_NODE_BIN", "no-such-node-binary")
    with pytest.raises(lfm.LfmUnavailable, match="Node.js"):
        lfm.render_markdown("# Hello")

    monkeypatch.delenv("MEMOPOP_NODE_BIN")
    monkeypatch.setattr(lfm, "LFM_PACKAGE", tmp_path / "missing" / "package.json")
    with pytest.raises(lfm.LfmUnavailable, match=r"npm ci --prefix src/connector/render"):
        lfm.render_markdown("# Hello")


@pytest.mark.spec("CONN-LFM-02")
def test_compile_and_preview_report_service_unavailable_without_the_renderer(
    settings, monkeypatch
):
    ws = open_workspace(dataclasses.replace(settings, export_renderer="lfm"), "test-firm")
    deal = drafted(ws)
    monkeypatch.setenv("MEMOPOP_NODE_BIN", "no-such-node-binary")

    with pytest.raises(ConnectorError) as raised:
        call(ws, "compile", deal=deal, formats=["html"])
    assert raised.value.code == "service_unavailable"

    with pytest.raises(ConnectorError) as raised:
        call(ws, "preview", deal=deal, artifact="01-overview")
    assert raised.value.code == "service_unavailable"


# ------------------------------------------------------------------ CONN-LFM-03


@pytest.mark.spec("CONN-LFM-03")
def test_the_export_renderer_setting_defaults_to_pandoc_and_accepts_lfm():
    assert ConnectorSettings().export_renderer == "pandoc"
    assert ConnectorSettings.from_env({}).export_renderer == "pandoc"
    assert ConnectorSettings.from_env({"MEMOPOP_EXPORT_RENDERER": "lfm"}).export_renderer == "lfm"
    with pytest.raises(ValueError, match="MEMOPOP_EXPORT_RENDERER"):
        ConnectorSettings.from_env({"MEMOPOP_EXPORT_RENDERER": "markdown-it"})


@pytest.mark.spec("CONN-LFM-03")
def test_compile_with_lfm_keeps_the_brand_page_and_prints_the_pdf_from_it(settings):
    ws = open_workspace(dataclasses.replace(settings, export_renderer="lfm"), "test-firm")
    deal = drafted(ws)
    body = call(ws, "compile", deal=deal)

    html = ws.bucket.get(f"compiled/{deal}/{body['version']}/memo.html").decode()
    # The firm's branded page and brand CSS ...
    assert '<div class="memo-header">' in html and "--brand-primary" in html
    assert "$body$" not in html
    # ... around LFM's body: citations numbered from the hex keys, one sources list.
    assert "data-footnote-ref" in html and '<ol class="sources">' in html
    assert "[^" not in html
    numbers = _numbers(html)
    assert numbers and numbers[0][1] == "1"
    assert set(_sources(html)) == {key for key, _ in numbers}

    pdf = ws.bucket.get(f"compiled/{deal}/{body['version']}/memo.pdf")
    assert pdf.startswith(b"%PDF")


@pytest.mark.spec("CONN-LFM-03")
def test_compile_by_default_still_renders_with_pandoc(ws):
    deal = drafted(ws)
    body = call(ws, "compile", deal=deal, formats=["html"])
    html = ws.bucket.get(f"compiled/{deal}/{body['version']}/memo.html").decode()
    assert '<div class="memo-header">' in html
    assert "data-footnote-ref" not in html and '<ol class="sources">' not in html


# ------------------------------------------------------------------ CONN-LFM-04


@pytest.mark.spec("CONN-LFM-04")
def test_export_branded_renders_with_lfm_and_inlines_local_images(tmp_path):
    from cli.export_branded import convert_to_branded_html
    from src.branding import BrandConfig

    folder = tmp_path / "Fixture-v0.0.1"
    (folder / "deck-screenshots").mkdir(parents=True)
    (folder / "deck-screenshots" / "page-01.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    memo = folder / "memo.md"
    memo.write_text(
        "# Investment Memo: Fixture Co\n\n"
        + HEX_MEMO.replace("### Citations", "![Slide 1](deck-screenshots/page-01.png)\n\n### Citations")
    )
    out = tmp_path / "out.html"
    convert_to_branded_html(
        memo,
        out,
        BrandConfig.get_default_config(),
        REPO / "templates" / "base-style.css",
        renderer="lfm",
    )
    html = out.read_text()
    assert '<div class="memo-header">' in html
    assert _numbers(html)[0] == ("b7k2m9", "1")
    assert 'src="data:image/png;base64,' in html
    assert not list(folder.glob(".temp_*")), "temp files left behind"


@pytest.mark.spec("CONN-LFM-04")
def test_export_branded_cli_has_a_renderer_option():
    done = subprocess.run(
        [sys.executable, "cli/export_branded.py", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert re.search(r"--renderer \{pandoc,lfm\}", done.stdout), done.stdout


# ------------------------------------------------------------------ CONN-LFM-05


@pytest.mark.spec("CONN-LFM-05")
def test_preview_renders_a_section_before_compile_with_a_signed_link(ws, client):
    deal = drafted(ws)
    body = call(ws, "preview", deal=deal, artifact="01-overview")

    assert body["ok"] is True
    assert body["source"].endswith(":01-overview")
    assert body["title"].startswith("Section: ")
    html = body["html"]
    assert '<div class="memo-header">' in html and "data-footnote-ref" in html
    assert '<ol class="sources">' in html and "[^" not in html

    page = client.get(body["html_url"])
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.text == html

    # Nothing in the deal changed: no compiled version, no new artifact.
    state = json.loads(deal_json(ws, deal).read_text())
    assert not state.get("compiled")
    assert "compile.assemble" not in state["artifacts"]


@pytest.mark.spec("CONN-LFM-05")
def test_preview_the_memo_assembles_the_sections_without_saving_a_version(ws):
    deal = drafted(ws)
    before = deal_json(ws, deal).read_text()
    body = call(ws, "preview", deal=deal, artifact="memo")
    assert body["source"] == "sections"
    assert body["html"].count("<h2") >= 3
    assert deal_json(ws, deal).read_text() == before

    # After compile, the compiled memo is an artifact like any other.
    call(ws, "compile", deal=deal, formats=["html"])
    compiled = call(ws, "preview", deal=deal, artifact="compile.assemble")
    assert compiled["source"] == "compile.assemble"
    assert "data-footnote-ref" in compiled["html"]


@pytest.mark.spec("CONN-LFM-05")
def test_preview_errors_follow_the_envelope(ws, client):
    deal = new_deal(ws)
    with pytest.raises(ConnectorError) as raised:
        call(ws, "preview", deal=deal, artifact="memo")
    assert raised.value.code == "drafts_incomplete"

    with pytest.raises(ConnectorError) as raised:
        call(ws, "preview", deal=deal, artifact="no-such-thing")
    assert raised.value.code == "artifact_not_found"
    assert "memo" in raised.value.details["available"]

    response = client.get(
        f"/v1/deals/{deal}/preview", params={"artifact": "no-such-thing"}, headers=key_headers()
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "artifact_not_found"


@pytest.mark.spec("CONN-LFM-05")
def test_preview_over_rest_and_mcp_matches_and_is_read_only(ws, client, mcp):
    deal = drafted(ws)
    direct = call(ws, "preview", deal=deal, artifact="01-overview")

    response = client.get(
        f"/v1/deals/{deal}/preview", params={"artifact": "01-overview"}, headers=key_headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["html"] == direct["html"]

    tools = {t["name"]: t for t in mcp.rpc("tools/list")["tools"]}
    assert tools["preview"]["annotations"]["readOnlyHint"] is True
    assert tools["preview"]["annotations"]["destructiveHint"] is False
    result = mcp.call("preview", {"deal": deal, "artifact": "01-overview"})
    assert result.get("isError") is not True
    assert result["structuredContent"]["html"] == direct["html"]


# ------------------------------------------------------------------ CONN-LFM-06


@pytest.mark.spec("CONN-LFM-06")
def test_instructions_send_agents_to_preview_and_forbid_rendering_themselves():
    sentence = next((s for s in re.split(r"(?<=\.)\s+", INSTRUCTIONS) if "preview" in s), None)
    assert sentence is not None, "the server's instructions don't name preview"
    text = INSTRUCTIONS.lower()
    assert "never render" in text and "citation numbers" in text


@pytest.mark.spec("CONN-LFM-06")
def test_the_preview_a_memo_playbook_exists_and_skills_that_show_a_memo_use_preview():
    playbook = (SKILLS_DIR / "preview-a-memo.md").read_text()
    assert "never" in playbook.lower() and "citation numbers" in playbook.lower()
    assert playbook.strip().splitlines()[-1].count("`preview`") == 1

    for name in ("compile-and-check-the-site", "rewrite-a-section-from-its-research"):
        text = (SKILLS_DIR / f"{name}.md").read_text()
        assert "`preview`" in text, f"{name} doesn't send the agent to preview"
