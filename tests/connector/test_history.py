"""Layer 7, history: every saved artifact is one jj change in the firm's own
repository, identical content is none, binaries never enter it, and two firms
can't reach each other's history (CONN-HIST-01, -02, -04, -05).

The jj-backed tests need the ``jj`` binary. Without it they skip locally with a
reason; in CI (``CI`` set) a missing ``jj`` fails them, so they always run there.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from src.connector.errors import ConnectorError
from src.connector.workspace import open_workspace

from .conftest import SECTIONS, call, new_deal
from .fixtures import canned

AUTHOR_NAME = "MemoPop"
AUTHOR_EMAIL = "noreply@didi.sh"


@pytest.fixture
def jj(tmp_path) -> "Jj":
    binary = shutil.which("jj")
    if binary is None:
        if os.environ.get("CI"):
            pytest.fail("jj is not installed, and CI must run the history tests")
        pytest.skip("jj is not installed; the history tests need it (CI installs it)")
    neutral = tmp_path / "neutral-jj-config.toml"
    neutral.write_text('[ui]\npaginate = "never"\ncolor = "never"\n')
    return Jj(binary, neutral)


class Jj:
    """Reads a firm's repository from outside, the way an operator would.

    Every read passes ``--ignore-working-copy``, so it sees what the server
    recorded and never snapshots anything itself.
    """

    def __init__(self, binary: str, config: Path):
        self.binary = binary
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("JJ_", "GIT_"))}
        self.env["JJ_CONFIG"] = str(config)

    def run(self, root: Path, *args: str, snapshot: bool = False) -> str:
        cmd = [self.binary, "-R", str(root)]
        if not snapshot:
            cmd.append("--ignore-working-copy")
        result = subprocess.run(
            [*cmd, *args],
            cwd=root,
            env=self.env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def changes(self, root: Path) -> list[dict]:
        """Recorded changes, oldest first (the working-copy change excluded)."""
        if not (root / ".jj").is_dir():
            return []
        sep = "\x1f"
        out = self.run(
            root,
            "log",
            "--no-graph",
            "--reversed",
            "-r",
            "::@- ~ root()",
            "-T",
            f'commit_id ++ "{sep}" ++ author.name() ++ "{sep}" ++ author.email() '
            f'++ "{sep}" ++ description.first_line() ++ "\\n"',
        )
        rows = []
        for line in out.splitlines():
            commit, name, email, first = line.split(sep)
            rows.append({"commit": commit, "name": name, "email": email, "description": first})
        return rows

    def files(self, root: Path, rev: str) -> list[str]:
        return self.run(root, "file", "list", "-r", rev).splitlines()

    def files_changed(self, root: Path, rev: str) -> list[str]:
        return self.run(root, "diff", "--name-only", "-r", rev).splitlines()


def submit(ws, deal: str, step: dict, content: str | None = None, **kw) -> dict:
    section = step.get("section")
    if content is None:
        content = canned.research(section)
    return call(
        ws,
        "submit_artifact",
        deal=deal,
        step_id=step["step_id"],
        section=section,
        content=content,
        **kw,
    )


# ---------------------------------------------------------------- CONN-HIST-01


@pytest.mark.spec("CONN-HIST-01")
def test_each_saved_artifact_is_one_change_naming_step_deal_and_section(ws, jj, monkeypatch):
    # The server user's own jj identity and config must never leak in.
    leaky = ws.root.parent / "leaky-user-config.toml"
    leaky.write_text('[user]\nname = "Leaky Operator"\nemail = "leak@example.com"\n')
    monkeypatch.setenv("JJ_CONFIG", str(leaky))
    monkeypatch.setenv("JJ_USER", "Leaky Env")
    monkeypatch.setenv("JJ_EMAIL", "env-leak@example.com")

    deal = new_deal(ws)
    before = jj.changes(ws.root)

    step = call(ws, "next_step", deal=deal)
    saved = submit(ws, deal, step, partner_approved=True)
    after = jj.changes(ws.root)

    assert len(after) == len(before) + 1, "one saved artifact must be exactly one change"
    change = after[-1]
    for part in ("research.section", deal, SECTIONS[0]):
        assert part in change["description"], f"{part!r} missing from {change['description']!r}"
    assert (change["name"], change["email"]) == (AUTHOR_NAME, AUTHOR_EMAIL)
    assert all((c["name"], c["email"]) == (AUTHOR_NAME, AUTHOR_EMAIL) for c in after)

    # The change carries the artifact itself.
    changed = jj.files_changed(ws.root, change["commit"])
    assert f"deals/{deal}/research/{SECTIONS[0]}.md" in changed
    assert saved["version"] == 1

    # A second section is a second change, and only one.
    step = call(ws, "next_step", deal=deal)
    submit(ws, deal, step, partner_approved=True)
    again = jj.changes(ws.root)
    assert len(again) == len(after) + 1
    assert SECTIONS[1] in again[-1]["description"]


@pytest.mark.spec("CONN-HIST-01")
def test_earlier_versions_are_readable_from_history(ws, jj):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    first = canned.research(SECTIONS[0])
    second = first.replace("modestly", "steadily")
    assert first != second
    assert submit(ws, deal, step, content=first)["version"] == 1
    assert submit(ws, deal, step, content=second)["version"] == 2

    artifact_id = f"research.section:{SECTIONS[0]}"
    latest = call(ws, "get_artifact", deal=deal, artifact_id=artifact_id)
    assert (latest["version"], latest["text"]) == (2, second)

    old = call(ws, "get_artifact", deal=deal, artifact_id=artifact_id, version=1)
    assert (old["version"], old["text"]) == (1, first)

    same = call(ws, "get_artifact", deal=deal, artifact_id=artifact_id, version=2)
    assert same["text"] == second

    with pytest.raises(ConnectorError) as err:
        call(ws, "get_artifact", deal=deal, artifact_id=artifact_id, version=3)
    assert err.value.code == "artifact_not_found"


# ---------------------------------------------------------------- CONN-HIST-02


@pytest.mark.spec("CONN-HIST-02")
def test_identical_content_records_no_change(ws, jj):
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    first = submit(ws, deal, step, partner_approved=True)
    before = jj.changes(ws.root)
    op_before = jj.run(ws.root, "op", "log", "--no-graph", "-n", "1", "-T", "id")

    again = submit(ws, deal, step, partner_approved=True)
    assert again["version"] == first["version"]
    assert jj.changes(ws.root) == before, "identical content must record nothing"
    op_after = jj.run(ws.root, "op", "log", "--no-graph", "-n", "1", "-T", "id")
    assert op_after == op_before, "identical content must not even touch the repository"

    # A recorded change is never empty, even if a writer hands history a path
    # whose content did not change.
    path = ws.root / "deals" / deal / "research" / f"{SECTIONS[0]}.md"
    ws.history.record("research.section: no-op probe", [path])
    assert jj.changes(ws.root) == before


# ---------------------------------------------------------------- CONN-HIST-04


@pytest.mark.spec("CONN-HIST-04")
def test_two_firms_have_separate_unreachable_histories_and_buckets(settings, jj):
    a = open_workspace(settings, "test-firm")
    b = open_workspace(settings, "other-firm")
    deal_a = new_deal(a, company="Alpha Fixture", url="https://alpha-fixture.co")
    deal_b = new_deal(b, company="Beta Fixture", url="https://beta-fixture.co")
    for ws, deal in ((a, deal_a), (b, deal_b)):
        submit(ws, deal, call(ws, "next_step", deal=deal), partner_approved=True)

    # One repository per firm, rooted at the firm, and none above them.
    root_a = Path(jj.run(a.root, "root").strip()).resolve()
    root_b = Path(jj.run(b.root, "root").strip()).resolve()
    assert root_a == a.root.resolve()
    assert root_b == b.root.resolve()
    assert root_a != root_b
    assert not (settings.io_root / ".jj").exists()

    # Neither repository has ever recorded a path of the other firm.
    for ws, other_deal in ((a, deal_b), (b, deal_a)):
        recorded = set()
        for change in jj.changes(ws.root):
            recorded.update(jj.files(ws.root, change["commit"]))
        assert recorded, "each firm must have recorded something"
        assert not any(other_deal in p for p in recorded)
        assert all(not p.startswith(("..", "/")) for p in recorded)

    # History reads stay inside the firm: the other firm's file, by absolute
    # path or by traversal, is not readable through this firm's history.
    b_file = b.root / "deals" / deal_b / "research" / f"{SECTIONS[0]}.md"
    assert b_file.is_file()
    assert a.history.read(b_file, 1) is None
    assert a.history.read(a.root / ".." / "other-firm" / b_file.relative_to(b.root), 1) is None
    with pytest.raises(ConnectorError) as err:
        call(a, "get_artifact", deal=deal_b, artifact_id=f"research.section:{SECTIONS[0]}")
    assert err.value.code == "deal_not_found"

    # A link planted in A's workspace that points into B is not followed into
    # A's snapshot.
    (a.root / "deals" / deal_a / "planted.md").symlink_to(b_file)

    snap_a = call(a, "save_snapshot", label="alpha")
    snap_b = call(b, "save_snapshot", label="beta")

    # Separate bucket locations: each snapshot is in its own firm's bucket only.
    keys_a = a.bucket.list("snapshots/")
    keys_b = b.bucket.list("snapshots/")
    assert any(snap_a["snapshot_id"] in k for k in keys_a)
    assert any(snap_b["snapshot_id"] in k for k in keys_b)
    assert not any(snap_a["snapshot_id"] in k for k in keys_b)
    assert not any(snap_b["snapshot_id"] in k for k in keys_a)
    assert a.bucket.root.resolve() != b.bucket.root.resolve()
    assert not a.bucket.root.resolve().is_relative_to(b.bucket.root.resolve())
    assert not b.bucket.root.resolve().is_relative_to(a.bucket.root.resolve())

    # And A's archive holds nothing of B's, not even through the planted link.
    archive_key = next(k for k in keys_a if k.endswith(".tar.gz"))
    with tarfile.open(fileobj=io.BytesIO(a.bucket.get(archive_key)), mode="r:gz") as tar:
        names = tar.getnames()
        assert names and all(n == "test-firm" or n.startswith("test-firm/") for n in names)
        assert not any(deal_b in n for n in names)
        assert not any(n.endswith("planted.md") for n in names)
        for member in tar.getmembers():
            assert not member.issym() and not member.islnk()
            if member.isfile() and "/.jj/" not in member.name:
                assert b"Beta Fixture" not in tar.extractfile(member).read()


# ---------------------------------------------------------------- CONN-HIST-05

BINARY = b"%PDF-1.7\n\x00\x01\x02binary\xff\xfe" + bytes(range(256))


@pytest.mark.spec("CONN-HIST-05")
def test_binary_materials_never_enter_the_jj_working_copy(ws, jj):
    deal = new_deal(ws)
    materials = ws.root / "deals" / deal / "materials"
    materials.mkdir(parents=True, exist_ok=True)
    binaries = {
        f"deals/{deal}/materials/mat-deck01/deck.pdf": BINARY,
        f"deals/{deal}/materials/mat-logo01/logo.png": b"\x89PNG\r\n\x1a\n" + BINARY,
        f"deals/{deal}/materials/mat-model1/model.xlsx": b"PK\x03\x04" + BINARY,
        f"deals/{deal}/materials/mat-raw001/upload": BINARY,
    }
    for rel, data in binaries.items():
        path = ws.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    text_material = f"deals/{deal}/materials/mat-deck01.md"
    (ws.root / text_material).write_text("# Deck, extracted\n\nFixture Co sells software.\n")

    # A saved artifact makes the server snapshot the working copy and record.
    submit(ws, deal, call(ws, "next_step", deal=deal), partner_approved=True)

    tracked_now = set(jj.files(ws.root, "@"))
    recorded = set()
    for change in jj.changes(ws.root):
        recorded.update(jj.files(ws.root, change["commit"]))
    for rel in binaries:
        assert rel not in tracked_now, f"{rel} is in the jj working copy"
        assert rel not in recorded, f"{rel} was recorded in history"
    assert text_material in tracked_now, "extracted text is still versioned"

    # Every file jj holds is text.
    for rel in tracked_now:
        data = (ws.root / rel).read_bytes()
        assert b"\x00" not in data, f"{rel} looks binary"

    # Belt and braces: the workspace's .gitignore keeps the binary kinds out even
    # for someone running jj by hand with default settings.
    tracked_by_hand = set(jj.run(ws.root, "file", "list", "-r", "@", snapshot=True).splitlines())
    for rel in binaries:
        if not rel.endswith("upload"):
            assert rel not in tracked_by_hand, f"{rel} is not ignored by .gitignore"


# ---------------------------------------------------------------- degraded paths


def test_without_jj_artifacts_still_save_and_old_versions_are_not_found(settings):
    """Not a spec ID: a machine without jj keeps working, without history."""
    from src.connector.history import NullHistory

    settings.jj_bin = "memopop-no-such-jj-binary"
    ws = open_workspace(settings, "test-firm")
    assert isinstance(ws.history, NullHistory)
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    first = canned.research(SECTIONS[0])
    submit(ws, deal, step, content=first)
    assert submit(ws, deal, step, content=first.replace("modestly", "steadily"))["version"] == 2
    assert not (ws.root / ".jj").exists()
    with pytest.raises(ConnectorError) as err:
        call(
            ws, "get_artifact", deal=deal, artifact_id=f"research.section:{SECTIONS[0]}", version=1
        )
    assert err.value.code == "artifact_not_found"


def test_a_failing_jj_is_logged_and_the_save_still_stands(settings, caplog):
    """Not a spec ID: recording runs after the durable write, so a jj failure
    must not turn a saved artifact into a `down` the client would retry."""
    false = shutil.which("false")
    if false is None:
        pytest.skip("no `false` binary")
    settings.jj_bin = false
    ws = open_workspace(settings, "test-firm")
    deal = new_deal(ws)
    step = call(ws, "next_step", deal=deal)
    saved = submit(ws, deal, step, partner_approved=True)
    assert saved["version"] == 1
    path = ws.root / "deals" / deal / "research" / f"{SECTIONS[0]}.md"
    assert path.read_text() == canned.research(SECTIONS[0])
    assert any("could not record" in r.getMessage() for r in caplog.records)
