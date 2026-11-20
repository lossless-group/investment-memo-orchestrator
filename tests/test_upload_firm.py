"""upload_firm: the finished memo becomes compiled v1, binaries go up once, a re-run sends nothing new."""

import json
import shutil
import sys
from pathlib import Path

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
