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
    assert (
        out / "firms/acme-vc/deals/widget-com/compiled/1/memo.md"
    ).read_text() == "# Newest memo\n"

    plan = json.loads((out / "plan.json").read_text())
    assert len(plan["blobs"]) == 1  # three copies of the same bytes, one blob
    binaries = [m for m in state["materials"] if m.get("bucket_key")]
    # three copies of the same bytes are one material carrying all three paths (CONN-UPL-04)
    assert len(binaries) == 1 and binaries[0]["bucket_key"] == f"blobs/{plan['blobs'][0]}"
    assert len(binaries[0]["local_paths"]) == 3
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


# ------------------------------------------------------------------ uploaded binaries get text


def make_unfinished_firm(root: Path) -> Path:
    """A deal the local pipeline didn't finish: one section researched, no drafts, no memo.

    Its inputs are a real deck (a PDF with text) and a logo (no text to extract).
    """
    from tests.connector.fixtures.materials import two_page_pdf

    firm = make_finished_firm(root)
    deal = firm / "deals" / "Widget"
    shutil.rmtree(deal / "outputs")
    research = deal / "outputs" / "Widget-v0.0.1" / "1-research"
    research.mkdir(parents=True)
    (research / "01-overview-research.md").write_text("# Research for 01-overview\n")
    (deal / "inputs" / "deck.pdf").write_bytes(two_page_pdf())
    (deal / "inputs" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n not really an image")
    return firm


def open_staged(tmp_path: Path, out: Path):
    from src.connector.config import ConnectorSettings
    from src.connector.workspace import open_workspace

    settings = ConnectorSettings(
        io_root=out / "firms",
        bucket_backend="local",
        bucket_local_root=tmp_path / "buckets",
        static_keys={},
    )
    return open_workspace(settings, "acme-vc")


@pytest.mark.spec("CONN-UPL-03")
def test_an_imported_unfinished_deal_walks_through_the_materials_brief(tmp_path):
    from src.connector.tools import invoke
    from tests.connector.fixtures.materials import PAGE_MARKERS

    firm = make_unfinished_firm(tmp_path)
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)

    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    by_file = {m["filename"]: m for m in state["materials"] if m.get("bucket_key")}
    deck, logo = by_file["deck.pdf"], by_file["logo.png"]
    # the deck's text was extracted with the connector's own reader, so it is ready
    assert deck["status"] == "ready" and deck["chars"] > 0
    text = (out / f"firms/acme-vc/deals/widget-com/materials/{deck['material_id']}.md").read_text()
    assert all(marker in text for marker in PAGE_MARKERS)
    # the logo has no text: skipped with a reason, never ready without a text file
    assert logo["status"] == "skipped" and logo["error"]
    assert any(s.get("material_id") == logo["material_id"] for s in state["skips"])

    ws = open_staged(tmp_path, out)
    step = invoke("next_step", {"deal": "widget-com"}, ws)
    assert step["step_id"] == "materials.brief"
    deck_input = next(
        i for i in step["inputs"] if i["artifact_id"] == f"material:{deck['material_id']}"
    )
    assert PAGE_MARKERS[0] in deck_input["text"]


@pytest.mark.spec("CONN-UPL-03")
def test_a_ready_material_with_no_text_file_is_a_notice_not_an_error(tmp_path):
    """Deals staged before the fix recorded binaries ready with no text; they must still walk."""
    from src.connector.tools import invoke

    firm = make_unfinished_firm(tmp_path)
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)
    deal_json = out / "firms/acme-vc/deals/widget-com/deal.json"
    state = json.loads(deal_json.read_text())
    deck = next(m for m in state["materials"] if m.get("filename") == "deck.pdf")
    (out / f"firms/acme-vc/deals/widget-com/materials/{deck['material_id']}.md").unlink(
        missing_ok=True
    )

    ws = open_staged(tmp_path, out)
    step = invoke("next_step", {"deal": "widget-com"}, ws)
    assert step["step_id"] == "materials.brief"
    notice = next(
        i for i in step["inputs"] if i["artifact_id"] == f"material:{deck['material_id']}"
    )
    assert "deck.pdf" in notice["text"] and "no text" in notice["text"].lower()


# ------------------------------------------------------------------ known blobs (CONN-UPL-01)


def deck_sha(firm: Path) -> str:
    return upload_firm.file_sha(firm / "deals/Widget/inputs/deck.pdf")


@pytest.mark.spec("CONN-UPL-01")
def test_known_blobs_are_not_staged_but_still_recorded(tmp_path):
    firm = make_firm(tmp_path)
    digest = deck_sha(firm)
    known = tmp_path / "known-blobs.txt"
    known.write_text(f"hashing imported/ keys...\n{digest}\n\n{'0' * 64}\n")
    out = tmp_path / "stage"
    upload_firm.main(
        [str(firm), "--firm", "acme-vc", "--out", str(out), "--known-blobs", str(known)]
    )

    plan = json.loads((out / "plan.json").read_text())
    assert plan["blobs"] == []
    assert digest in plan["known_blobs"]
    assert not (out / "blobs" / digest).exists()

    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    binaries = [m for m in state["materials"] if m.get("bucket_key")]
    assert len(binaries) == 1 and binaries[0]["bucket_key"] == f"blobs/{digest}"
    assert len(binaries[0]["local_paths"]) == 3
    manifest = yaml.safe_load((out / "manifests/deals/Widget/binaries-on-server.yaml").read_text())
    assert {e["sha256"] for e in manifest["files"].values()} == {digest}
    assert len(manifest["files"]) == 3
    assert "known" in (out / "report.md").read_text()


@pytest.mark.spec("CONN-UPL-01")
def test_read_known_blobs_takes_only_whole_hash_lines(tmp_path):
    good = "a" * 64
    path = tmp_path / "known.txt"
    path.write_text(f"{good}\n  {good.upper()}  \nnot a hash\ncopied {'b' * 64}\n{'c' * 63}\n")
    assert upload_firm.read_known_blobs(path) == {good}


@pytest.mark.spec("CONN-UPL-01")
def test_fold_copies_each_imported_hash_to_blobs_once(tmp_path):
    import hashlib

    import fold_imported_blobs

    from src.connector.bucket import LocalBucket

    bucket = LocalBucket(tmp_path / "bucket")
    deck, other = b"%PDF-1.4 the deck", b"a spreadsheet"
    bucket.put("imported/widget/v0.0.1/inputs/deck.pdf", deck)
    bucket.put("imported/widget/v0.0.2/inputs/deck.pdf", deck)
    bucket.put("imported/widget/v0.0.2/inputs/model.xlsx", other)
    bucket.put("materials/mat-1/notes.pdf", b"not imported")
    hashes = {hashlib.sha256(b).hexdigest() for b in (deck, other)}

    dry = fold_imported_blobs.fold(bucket, dry_run=True)
    assert set(dry.hashes) == hashes and not bucket.list("blobs/")

    result = fold_imported_blobs.fold(bucket)
    assert set(result.hashes) == hashes
    assert result.copied == 2 and result.objects == 3
    assert sorted(bucket.list("blobs/")) == sorted(f"blobs/{h}" for h in hashes)
    for h, data in (
        (hashlib.sha256(deck).hexdigest(), deck),
        (hashlib.sha256(other).hexdigest(), other),
    ):
        assert bucket.get(f"blobs/{h}") == data
    assert len(bucket.list("imported/")) == 3  # never deleted here

    again = fold_imported_blobs.fold(bucket)
    assert again.copied == 0 and set(again.hashes) == hashes


@pytest.mark.spec("CONN-UPL-01")
def test_apply_refuses_when_a_known_blob_is_not_in_the_bucket(tmp_path):
    import apply_upload

    from src.connector.bucket import LocalBucket

    bucket = LocalBucket(tmp_path / "bucket")
    bucket.put("blobs/" + "a" * 64, b"x")
    plan = {"known_blobs": ["a" * 64, "b" * 64]}
    assert apply_upload.missing_known(bucket, plan) == ["b" * 64]
    assert apply_upload.missing_known(bucket, {}) == []


# ------------------------------------------------------------------ the check (CONN-UPL-02)


def staged_and_applied(tmp_path: Path):
    """Stage a finished firm, then play the server: put the blobs, copy the manifests home."""
    from src.connector.bucket import LocalBucket

    firm = make_finished_firm(tmp_path)
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)
    bucket = LocalBucket(tmp_path / "bucket")
    for blob in (out / "blobs").iterdir():
        bucket.put(f"blobs/{blob.name}", blob.read_bytes())
    shutil.copy2(
        out / "manifests/deals/Widget/binaries-on-server.yaml",
        firm / "deals/Widget/binaries-on-server.yaml",
    )
    return firm, out / "firms" / "acme-vc", bucket


@pytest.mark.spec("CONN-UPL-02")
def test_check_reports_a_matching_deal_as_ok(tmp_path):
    import check_upload

    firm, server, bucket = staged_and_applied(tmp_path)
    snap = check_upload.snapshot(server, bucket)
    rows = check_upload.compare(firm, snap)

    assert len(rows) == 1
    row = rows[0]
    assert row["deal"] == "widget-com" and row["ok"]
    assert row["compiled"] == {"local": "v0.0.3", "server": "v0.0.3", "ok": True}
    assert row["sections"]["outline"] == 2 and row["sections"]["drafted"] == 2
    assert row["sections"]["ok"]
    assert row["materials"]["manifest"] == 1 and row["materials"]["matched"] == 1
    assert row["materials"]["ok"]

    snap_file = tmp_path / "snap.json"
    snap_file.write_text(json.dumps(snap))
    assert check_upload.main(["compare", str(firm), "--snapshot", str(snap_file)]) == 0


@pytest.mark.spec("CONN-UPL-02")
def test_check_reports_each_difference(tmp_path):
    import check_upload

    firm, server, bucket = staged_and_applied(tmp_path)
    deal_json = server / "deals/widget-com/deal.json"
    state = json.loads(deal_json.read_text())
    state["compiled"]["label"] = "v0.0.2"
    del state["artifacts"]["draft.section:02-market"]
    binary = next(m for m in state["materials"] if m.get("bucket_key"))
    state["materials"].remove(binary)
    deal_json.write_text(json.dumps(state))
    # a second local deal the server never got
    other = firm / "deals" / "Gadget"
    other.mkdir()
    (other / "Gadget.json").write_text(json.dumps({"name": "Gadget", "domain": "gadget.io"}))

    snap = check_upload.snapshot(server, bucket)
    rows = {r["local"]: r for r in check_upload.compare(firm, snap)}

    widget = rows["Widget"]
    assert not widget["ok"]
    assert widget["compiled"] == {"local": "v0.0.3", "server": "v0.0.2", "ok": False}
    assert widget["sections"]["drafted"] == 1 and not widget["sections"]["ok"]
    assert widget["sections"]["missing_drafts"] == ["02-market"]
    assert widget["materials"]["missing"] == ["inputs/deck.pdf"]
    assert not widget["materials"]["ok"]
    assert rows["Gadget"]["server"] is None and not rows["Gadget"]["ok"]

    text = check_upload.render(list(rows.values()))
    assert "v0.0.2" in text and "02-market" in text and "inputs/deck.pdf" in text

    snap_file = tmp_path / "snap.json"
    snap_file.write_text(json.dumps(snap))
    assert check_upload.main(["compare", str(firm), "--snapshot", str(snap_file)]) == 1


@pytest.mark.spec("CONN-UPL-02")
def test_check_flags_a_blob_missing_from_the_bucket(tmp_path):
    import check_upload

    from src.connector.bucket import LocalBucket

    firm, server, _ = staged_and_applied(tmp_path)
    snap = check_upload.snapshot(server, LocalBucket(tmp_path / "empty-bucket"))
    row = check_upload.compare(firm, snap)[0]
    assert row["materials"]["not_in_bucket"] == ["inputs/deck.pdf"]
    assert not row["ok"]


# ------------------------------------------------------------------ one material per content (CONN-UPL-04)

WIDGET_PATHS = [
    "inputs/deck.pdf",
    "outputs/Widget-v0.0.1/images/deck-copy.pdf",
    "outputs/Widget-v0.0.2/images/deck-copy.pdf",
]


@pytest.mark.spec("CONN-UPL-04")
def test_the_same_bytes_at_two_paths_are_one_material(tmp_path):
    firm = make_firm(tmp_path)
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)

    state = json.loads((out / "firms/acme-vc/deals/widget-com/deal.json").read_text())
    binaries = [m for m in state["materials"] if m.get("bucket_key")]
    assert len(binaries) == 1
    material = binaries[0]
    assert material["local_paths"] == WIDGET_PATHS
    ids = [m["material_id"] for m in state["materials"]]
    assert len(ids) == len(set(ids))  # no id appears twice in deal.json
    # the unreadable bytes are one skip, not one per path
    assert len([s for s in state["skips"] if s.get("material_id") == material["material_id"]]) == 1

    manifest = yaml.safe_load((out / "manifests/deals/Widget/binaries-on-server.yaml").read_text())
    assert sorted(manifest["files"]) == WIDGET_PATHS
    assert {e["material_id"] for e in manifest["files"].values()} == {material["material_id"]}


@pytest.mark.spec("CONN-UPL-04")
def test_the_check_matches_every_path_of_a_shared_material(tmp_path):
    import check_upload

    from src.connector.bucket import LocalBucket

    firm = make_firm(tmp_path)
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)
    bucket = LocalBucket(tmp_path / "bucket")
    for blob in (out / "blobs").iterdir():
        bucket.put(f"blobs/{blob.name}", blob.read_bytes())
    shutil.copy2(
        out / "manifests/deals/Widget/binaries-on-server.yaml",
        firm / "deals/Widget/binaries-on-server.yaml",
    )

    row = check_upload.compare(firm, check_upload.snapshot(out / "firms/acme-vc", bucket))[0]
    assert row["materials"]["manifest"] == 3 and row["materials"]["matched"] == 3
    assert row["materials"]["extra"] == [] and row["materials"]["missing"] == []
    assert row["materials"]["ok"]


# ------------------------------------------------------------------ no macOS metadata (CONN-UPL-05)


@pytest.mark.spec("CONN-UPL-05")
def test_staging_leaves_out_macos_metadata_files(tmp_path):
    firm = make_firm(tmp_path)
    (firm / "configs" / "._brand.yaml").write_bytes(b"\x00\x05\x16\x07 appledouble")
    (firm / "configs" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
    deal = firm / "deals" / "Widget"
    (deal / "._Widget.json").write_bytes(b"\x00\x05\x16\x07 appledouble")
    (deal / "outputs" / "Widget-v0.0.2" / "._7-Widget-v0.0.2.md").write_bytes(b"\x00\x05\x16\x07")
    out = tmp_path / "stage"
    upload_firm.upload_firm(firm, "acme-vc", out)

    names = [p.name for p in out.rglob("*")]
    assert not [n for n in names if n.startswith("._") or n == ".DS_Store"]
    plan = json.loads((out / "plan.json").read_text())
    assert not [p for p in plan["firm_paths"] if Path(p).name.startswith("._")]


@pytest.mark.spec("CONN-UPL-05")
def test_apply_packs_the_staging_without_macos_metadata(tmp_path, monkeypatch):
    out = tmp_path / "stage"
    out.mkdir()
    (out / "plan.json").write_text(json.dumps({"firm": "acme-vc"}))
    seen = {}

    class FakeTar:
        def __init__(self, cmd, stdout=None, env=None):
            seen["cmd"], seen["env"] = cmd, env or {}
            self.stdout = open(__file__, "rb")

        def wait(self):
            return 0

    class Done:
        returncode = 0

    monkeypatch.setattr(upload_firm.subprocess, "Popen", FakeTar)
    monkeypatch.setattr(upload_firm.subprocess, "run", lambda *a, **k: Done())
    upload_firm.apply(out, tmp_path / "firm", "connector")

    assert seen["env"].get("COPYFILE_DISABLE") == "1"
    assert "--exclude=._*" in seen["cmd"] and "--exclude=.DS_Store" in seen["cmd"]


@pytest.mark.spec("CONN-UPL-05")
def test_the_server_drops_macos_metadata_before_copying(tmp_path):
    import apply_upload

    staged = tmp_path / "upload" / "firms" / "acme-vc"
    sections = staged / "deals" / "widget-com" / "local" / "sections"
    sections.mkdir(parents=True)
    (sections / "01-overview.md").write_text("# Overview\n")
    (sections / "._01-overview.md").write_bytes(b"\x00\x05\x16\x07")
    (staged / ".DS_Store").write_bytes(b"Bud1")

    dropped = apply_upload.drop_macos_metadata(tmp_path / "upload")

    assert dropped == 2
    assert (sections / "01-overview.md").exists()
    assert not (sections / "._01-overview.md").exists()
    assert not (staged / ".DS_Store").exists()
