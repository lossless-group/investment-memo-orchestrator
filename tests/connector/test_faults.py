"""The test-fault hook the real-Claude run uses (src/connector/faults.py).

It forces one skip and one ``down`` on a live server, so it must be impossible to
reach by accident. It fires only when **both** keys turn: the firm is listed in
``MEMOPOP_FAULT_FIRMS`` (empty by default), and the deal's outline is the firm's
own and carries a ``test_faults`` block. MemoPop's shared outlines never fire
it, a required step is never skipped by it, and a ``down`` saves nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from src.connector.config import ConnectorSettings
from src.connector.errors import ConnectorError
from src.connector.workspace import open_workspace

from .conftest import REPO, TEMPLATE, call, provision
from .fake_claude import Direct, FakeClaude

OUTLINE = "real-claude-three"


@pytest.fixture
def faults():
    from src.connector import faults

    return faults


def _settings(tmp_path, root, **kw) -> ConnectorSettings:
    return ConnectorSettings(io_root=root, bucket_local_root=tmp_path / "buckets", **kw)


@pytest.fixture
def root(tmp_path, faults):
    root = tmp_path / "firms"
    provision(root, "test-firm", default_template=TEMPLATE)
    provision(root, "real-firm", default_template=TEMPLATE)
    faults.install_outline(root, "test-firm")
    return root


def _walk_to_enhance(ws, template=OUTLINE):
    fake = FakeClaude(Direct(ws))
    deal = fake.create(template=template)
    walk = fake.walk(deal, until=lambda step: step["phase"] == "enhance", compile=False)
    return deal, walk


def test_the_outline_is_installed_firm_local(root):
    path = root / "test-firm" / "templates" / "outlines" / f"{OUTLINE}.yaml"
    assert path.is_file()
    assert not (root / "real-firm" / "templates" / "outlines" / f"{OUTLINE}.yaml").exists()


def test_with_both_keys_the_skip_and_the_down_fire(tmp_path, root):
    ws = open_workspace(_settings(tmp_path, root, fault_firms={"test-firm"}), "test-firm")
    fake = FakeClaude(Direct(ws))
    deal = fake.create(template=OUTLINE)
    walk = fake.walk(deal, until=lambda step: step["step_id"] == "draft.section", compile=False)
    assert ("research.sources", None) not in walk.handed_out
    assert walk.stopped_at["skipped_since_last_call"] == [
        {
            "step_id": "research.sources",
            "section": None,
            "code": "step_disabled",
            "reason": "Consolidate the research sources is turned off on this server.",
        }
    ]
    # Past the drafts, next_step is down at the first enhancement.
    with pytest.raises(AssertionError, match="service_unavailable"):
        fake.walk(deal, compile=False)


def test_the_down_saves_nothing_and_list_deals_still_answers(tmp_path, root):
    ws = open_workspace(_settings(tmp_path, root, fault_firms={"test-firm"}), "test-firm")
    fake = FakeClaude(Direct(ws))
    deal = fake.create(template=OUTLINE)
    with pytest.raises(AssertionError, match="service_unavailable"):
        fake.walk(deal, compile=False)
    before = (ws.root / "deals" / deal / "deal.json").read_text()
    with pytest.raises(ConnectorError) as err:
        call(ws, "next_step", deal=deal)
    assert err.value.code == "service_unavailable" and err.value.kind == "down"
    assert (ws.root / "deals" / deal / "deal.json").read_text() == before
    state = json.loads(before)
    assert not any(key.startswith("enhance.") for key in state["handed_out"])
    summary = call(ws, "list_deals")["deals"][0]
    assert summary["phase"] == "enhance"
    assert [s["step_id"] for s in summary["skips"]] == ["research.sources"]


def test_without_the_env_key_the_outline_is_inert(tmp_path, root):
    ws = open_workspace(_settings(tmp_path, root), "test-firm")
    deal, walk = _walk_to_enhance(ws)
    assert ("research.sources", None) in walk.handed_out
    assert walk.stopped_at["step_id"] == "enhance.tables"  # handed out, not down


def test_a_firm_not_listed_is_never_faulted(tmp_path, root, faults):
    faults.install_outline(root, "real-firm")
    ws = open_workspace(_settings(tmp_path, root, fault_firms={"test-firm"}), "real-firm")
    deal, walk = _walk_to_enhance(ws)
    assert ("research.sources", None) in walk.handed_out
    assert walk.stopped_at["step_id"] == "enhance.tables"


def test_memopops_shared_outlines_never_fault(tmp_path, root, faults):
    shared = tmp_path / "shared-outlines"
    shared.mkdir()
    shutil.copy(faults.OUTLINE_PATH, shared / "shared-faulty.yaml")
    settings = _settings(tmp_path, root, fault_firms={"test-firm"}, templates_dir=shared)
    ws = open_workspace(settings, "test-firm")
    deal, walk = _walk_to_enhance(ws, template="shared-faulty")
    assert ("research.sources", None) in walk.handed_out
    assert walk.stopped_at["step_id"] == "enhance.tables"


def test_a_required_step_is_never_skipped_and_other_deals_run(tmp_path, root, faults):
    outline = root / "test-firm" / "templates" / "outlines" / "greedy.yaml"
    text = faults.OUTLINE_PATH.read_text().replace(
        "disable: [research.sources]", "disable: [research.sources, draft.section]"
    )
    assert "draft.section" in text
    outline.write_text(text)
    ws = open_workspace(_settings(tmp_path, root, fault_firms={"test-firm"}), "test-firm")
    fake = FakeClaude(Direct(ws))
    deal = fake.create(template="greedy")
    walk = fake.walk(deal, until=lambda step: step["phase"] == "enhance", compile=False)
    assert ("draft.section", "01-overview") in walk.handed_out
    # The same firm's deal on an ordinary outline is untouched.
    other = fake.create(company="Plain Co", url="https://plain.example", template=TEMPLATE)
    plain = fake.walk(other, until=lambda step: step["phase"] == "enhance", compile=False)
    assert ("research.sources", None) in plain.handed_out
    assert plain.stopped_at["step_id"] == "enhance.tables"


def test_a_malformed_block_is_ignored(tmp_path, root, faults):
    outline = root / "test-firm" / "templates" / "outlines" / "broken.yaml"
    outline.write_text(
        faults.OUTLINE_PATH.read_text().split("test_faults:")[0] + "test_faults: [oops]\n"
    )
    ws = open_workspace(_settings(tmp_path, root, fault_firms={"test-firm"}), "test-firm")
    deal, walk = _walk_to_enhance(ws, template="broken")
    assert walk.stopped_at["step_id"] == "enhance.tables"


def test_the_env_var_lists_the_fault_firms():
    settings = ConnectorSettings.from_env({"MEMOPOP_FAULT_FIRMS": " test-firm , ,other "})
    assert settings.fault_firms == {"test-firm", "other"}
    assert ConnectorSettings.from_env({}).fault_firms == set()


def test_the_install_command(tmp_path):
    root = tmp_path / "firms"
    provision(root, "test-firm")
    result = subprocess.run(
        [sys.executable, "-m", "src.connector.faults", "install-outline", "test-firm"],
        cwd=REPO,
        env={"MEMO_IO_ROOT": str(root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (root / "test-firm" / "templates" / "outlines" / f"{OUTLINE}.yaml").is_file()
    missing = subprocess.run(
        [sys.executable, "-m", "src.connector.faults", "install-outline", "no-such-firm"],
        cwd=REPO,
        env={"MEMO_IO_ROOT": str(root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert missing.returncode != 0
    assert not (root / "no-such-firm").exists()
