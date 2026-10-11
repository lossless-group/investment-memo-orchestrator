"""Layer 7, snapshots: save_snapshot archives the firm's workspace to its
bucket under snapshots/, with change counts against the previous snapshot
(CONN-HIST-03)."""

from __future__ import annotations

import io
import json
import os
import re
import tarfile

import pytest

from src.connector.errors import ConnectorError

from .conftest import SECTIONS, call, key_headers, new_deal, rest
from .fixtures import canned
from .test_history import jj  # noqa: F401  (the fixture: skips locally without jj)

SNAPSHOT_KEY = re.compile(r"^snapshots/(\d{8}T\d{6}Z(?:-[a-z0-9-]+)?)\.tar\.gz$")


def workspace_files(root) -> set[str]:
    """Every regular file a partner's workspace holds, jj's internals and locks aside."""
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir.split(os.sep)[0] in (".jj", ".locks"):
            continue
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.isfile(path) and not os.path.islink(path):
                found.add(os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/"))
    return found


def archives(ws) -> list[str]:
    return [k for k in ws.bucket.list("snapshots/") if k.endswith(".tar.gz")]


def members(ws, key: str) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(ws.bucket.get(key)), mode="r:gz") as tar:
        return {
            m.name: (tar.extractfile(m).read() if m.isfile() else b"") for m in tar.getmembers()
        }


@pytest.mark.spec("CONN-HIST-03")
def test_save_snapshot_archives_the_workspace_with_change_counts(ws, jj):  # noqa: F811
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    call(
        ws,
        "submit_artifact",
        deal=deal,
        step_id=step["step_id"],
        section=step["section"],
        content=canned.research(step["section"]),
        partner_approved=True,
    )
    scratch = ws.root / "deals" / deal / "scratch.md"
    scratch.write_text("A note that will be gone by the next snapshot.\n")

    expected = workspace_files(ws.root)
    first = call(ws, "save_snapshot", label="Before IC meeting")

    # The fields the spec promises.
    assert first["ok"] is True and first["api_version"] == "1"
    assert first["label"] == "Before IC meeting"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", first["created_at"])
    assert first["snapshot_id"].endswith("-before-ic-meeting")
    assert (first["files_added"], first["files_changed"], first["files_removed"]) == (
        len(expected),
        0,
        0,
    )

    # The archive is in the firm's bucket under snapshots/, and holds the
    # workspace, jj's repository included.
    keys = archives(ws)
    assert len(keys) == 1
    match = SNAPSHOT_KEY.match(keys[0])
    assert match and match.group(1) == first["snapshot_id"]
    raw = ws.bucket.get(keys[0])
    assert first["bytes"] == len(raw)
    files = members(ws, keys[0])
    for rel in expected:
        assert f"test-firm/{rel}" in files, f"{rel} missing from the archive"
    assert files[f"test-firm/deals/{deal}/research/{SECTIONS[0]}.md"] == (
        canned.research(SECTIONS[0]).encode()
    )
    assert any(name.startswith("test-firm/.jj/") for name in files), "jj's repo must be archived"
    assert not any(name.startswith("test-firm/.locks") for name in files)

    # The workspace itself is unchanged by a snapshot.
    assert workspace_files(ws.root) == expected

    # One added, one changed, one removed since the first snapshot.
    (ws.root / "deals" / deal / "added.md").write_text("New since the first snapshot.\n")
    firm_json = ws.root / "firm.json"
    firm_json.write_text(json.dumps({**json.loads(firm_json.read_text()), "note": "edited"}))
    scratch.unlink()

    second = call(ws, "save_snapshot")
    assert second["label"] is None
    assert (second["files_added"], second["files_changed"], second["files_removed"]) == (1, 1, 1)
    assert second["previous_snapshot_id"] == first["snapshot_id"]
    assert second["snapshot_id"] != first["snapshot_id"]
    assert len(archives(ws)) == 2

    # Nothing changed: all zeros, against the second.
    third = call(ws, "save_snapshot", label="again")
    assert (third["files_added"], third["files_changed"], third["files_removed"]) == (0, 0, 0)
    assert third["previous_snapshot_id"] == second["snapshot_id"]
    assert len(archives(ws)) == 3


@pytest.mark.spec("CONN-HIST-03")
def test_save_snapshot_over_rest_matches_the_direct_call_shape(client):
    response = rest(client, "save_snapshot", {"label": "rest check"}, headers=key_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    for field in (
        "snapshot_id",
        "label",
        "created_at",
        "bytes",
        "files_added",
        "files_changed",
        "files_removed",
    ):
        assert field in body, field
    assert body["label"] == "rest check"


def test_a_failing_bucket_is_down_and_leaves_no_manifest(ws, monkeypatch):
    """Not a spec ID: the storage-failure path (spec layer 6) for save_snapshot."""
    new_deal(ws)

    def broken_put(key, data, content_type=None):
        raise ConnectorError("storage_unavailable", details={"bucket": "local"})

    monkeypatch.setattr(ws.bucket, "put", broken_put)
    with pytest.raises(ConnectorError) as err:
        call(ws, "save_snapshot", label="doomed")
    assert err.value.code == "storage_unavailable"
    assert err.value.kind == "down"
    monkeypatch.undo()
    assert ws.bucket.list("snapshots/") == []


def test_a_label_cannot_escape_the_snapshots_prefix(ws):
    """Not a spec ID: labels are slugged into the key, never used as a path."""
    snap = call(ws, "save_snapshot", label="../../other-firm/evil name")
    keys = ws.bucket.list("")
    assert keys and all(k.startswith("snapshots/") for k in keys)
    assert "/" not in snap["snapshot_id"] and ".." not in snap["snapshot_id"]
