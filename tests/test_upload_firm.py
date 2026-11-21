"""upload_firm: the finished memo becomes compiled v1, binaries go up once, a re-run sends nothing new."""

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import upload_firm  # noqa: E402


def make_firm(root: Path) -> Path:
    firm = root / "io" / "acme"
    deal = firm / "deals" / "Widget"
    (firm / "configs").mkdir(parents=True)
    (firm / "configs" / "brand.yaml").write_text("name: Acme\n")
    (deal / "inputs").mkdir(parents=True)
    (deal / "Widget.json").write_text(
        json.dumps(
            {
                "name": "Widget",
                "url": "https://www.widget.com/",
                "domain": "widget.com",
                "memopop_deal": {"firm": "acme-vc", "deal": "widget-com"},
            }
        )
    )
    deck = b"%PDF-1.4 same bytes in two places"
    (deal / "inputs" / "deck.pdf").write_bytes(deck)
    for v in ("Widget-v0.0.1", "Widget-v0.0.2"):
        out = deal / "outputs" / v
        (out / "images").mkdir(parents=True)
        (out / "images" / "deck-copy.pdf").write_bytes(deck)
    (deal / "outputs" / "Widget-v0.0.1" / "7-Widget-v0.0.1.md").write_text("# Old memo\n")
    (deal / "outputs" / "Widget-v0.0.2" / "7-Widget-v0.0.2.md").write_text("# Newest memo\n")
    return firm


def test_finished_memo_is_compiled_v1_and_binaries_go_once(tmp_path):
    firm = make_firm(tmp_path)
    out = tmp_path / "stage"
    reports = upload_firm.upload_firm(firm, "acme-vc", out)

    assert reports[0]["deal"] == "widget-com"
    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    assert state["compiled"]["version"] == 1
    assert state["compiled"]["label"] == "v0.0.2"
    assert (out / "firms/acme-vc/deals/widget-com/compiled/1/memo.md").read_text() == "# Newest memo\n"

    plan = json.loads((out / "plan.json").read_text())
    assert len(plan["blobs"]) == 1  # three copies of the same bytes, one blob
    binaries = [m for m in state["materials"] if m.get("bucket_key")]
    assert len(binaries) == 3 and {m["bucket_key"] for m in binaries} == {f"blobs/{plan['blobs'][0]}"}
    assert (out / "firms/acme-vc/configs/brand.yaml").is_file()
    assert "configs/brand.yaml" in plan["firm_paths"]

    manifest = yaml.safe_load((out / "manifests/deals/Widget/binaries-on-server.yaml").read_text())
    assert manifest["deal"] == "widget-com"
    assert set(manifest["files"]) == {
        "inputs/deck.pdf",
        "outputs/Widget-v0.0.1/images/deck-copy.pdf",
        "outputs/Widget-v0.0.2/images/deck-copy.pdf",
    }


def test_rerun_with_manifest_stages_no_binaries(tmp_path):
    firm = make_firm(tmp_path)
    first = tmp_path / "first"
    upload_firm.upload_firm(firm, "acme-vc", first)
    shutil.copy2(
        first / "manifests/deals/Widget/binaries-on-server.yaml",
        firm / "deals/Widget/binaries-on-server.yaml",
    )

    second = tmp_path / "second"
    upload_firm.upload_firm(firm, "acme-vc", second)
    plan = json.loads((second / "plan.json").read_text())
    assert plan["blobs"] == []
    assert not (second / "firms/acme-vc/deals/widget-com/local/binaries-on-server.yaml").exists()


TINY_OUTLINE = {
    "sections": [
        {"number": 1, "name": "Overview", "filename": "01-overview.md"},
        {"number": 2, "name": "Market", "filename": "02-market.md"},
    ]
}


def make_finished_firm(root: Path, **config) -> Path:
    """A firm with one deal the local pipeline finished: research, drafts, and a final memo."""
    firm = root / "io" / "acme"
    outlines = firm / "templates" / "outlines"
    outlines.mkdir(parents=True)
    (outlines / "tiny.yaml").write_text(yaml.safe_dump(TINY_OUTLINE))
    deal = firm / "deals" / "Widget"
    (deal / "inputs").mkdir(parents=True)
    (deal / "Widget.json").write_text(
        json.dumps(
            {
                "name": "Widget",
                "url": "https://www.widget.com/",
                "domain": "widget.com",
                "outline": "tiny",
                **config,
            }
        )
    )
    (deal / "inputs" / "deck.pdf").write_bytes(b"%PDF-1.4 a deck")
    out = deal / "outputs" / "Widget-v0.0.3"
    (out / "1-research").mkdir(parents=True)
    (out / "2-sections").mkdir(parents=True)
    for key in ("01-overview", "02-market"):
        (out / "1-research" / f"{key}-research.md").write_text(f"# Research for {key}\n")
        (out / "2-sections" / f"{key}.md").write_text(f"# Draft of {key}\n")
    (out / "7-Widget-v0.0.3.md").write_text("# The finished memo\n")
    return firm


@pytest.mark.spec("CONN-PT-03")
def test_the_trading_name_is_the_deals_company(tmp_path):
    firm = make_finished_firm(tmp_path, legal_name="Old Name Inc.", trading_name="Widget AI")
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)

    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    assert state["company"] == "Widget AI"
    assert state["legal_name"] == "Old Name Inc."


@pytest.mark.spec("CONN-PT-03")
def test_without_a_trading_name_the_name_beats_the_legal_name(tmp_path):
    firm = make_finished_firm(tmp_path, legal_name="Old Name Inc.")
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)

    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    assert state["company"] == "Widget"
    assert state["legal_name"] == "Old Name Inc."


@pytest.mark.spec("CONN-PT-05")
def test_a_finished_deal_gets_a_brief_and_research_sees_it(tmp_path):
    from src.connector import flow
    from src.connector.config import ConnectorSettings
    from src.connector.registry import load_registry
    from src.connector.workspace import open_workspace

    firm = make_finished_firm(tmp_path)
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)

    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    assert not [s for s in state["skips"] if s["step_id"] == "materials.brief"]
    record = state["artifacts"]["materials.brief"]
    brief = (out / "firms/acme-vc/deals/widget-com" / record["path"]).read_text()
    assert "v0.0.3" in brief  # the finished memo's version and the run it came from
    assert "inputs/deck.pdf" in brief  # the deal's materials, listed

    settings = ConnectorSettings(
        io_root=out / "firms",
        bucket_backend="local",
        bucket_local_root=tmp_path / "buckets",
        static_keys={},
    )
    ws = open_workspace(settings, "acme-vc")
    registry = load_registry()
    state = ws.read_deal("widget-com")
    research = flow.Instance(registry.step("research.section"), "01-overview")
    inputs = flow.gather_inputs(registry, ws, state, research)
    ids = [i["artifact_id"] for i in inputs]
    assert "materials.brief" in ids
    assert "research.section:01-overview" in ids
    assert next(i for i in inputs if i["artifact_id"] == "materials.brief")["text"] == brief
