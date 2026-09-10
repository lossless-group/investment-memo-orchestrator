"""
Tests for locating the `claude` binary when PATH does not name it.

A Tauri app launched from Finder gets the macOS GUI default PATH —
/usr/bin:/bin:/usr/sbin:/sbin — not the user's shell PATH. The FastAPI sidecar
is spawned by that app and inherits it, so `shutil.which("claude")` returns None
inside the sidecar on a machine where the CLI is installed and logged in. Every
model call then falls back to the metered API, silently, for every memo
generated from the desktop app.

`bun run dev:native` inherits the terminal's PATH, so the bug is invisible in
development and appears only in the shipped app. That is the kind of thing that
has to be tested rather than noticed.
"""

import os
import stat

import pytest

import src.llm_provider as llm
from src.llm_provider import claude_binary, cli_available, reset_claude_binary_cache


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_claude_binary_cache()
    yield
    reset_claude_binary_cache()


def _make_executable(path):
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_prefers_path_when_it_resolves(monkeypatch, tmp_path):
    fake = _make_executable(tmp_path / "claude")
    monkeypatch.setattr(llm.shutil, "which", lambda name: str(fake) if name == "claude" else None)
    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    assert claude_binary() == str(fake)


def test_falls_back_to_known_install_dirs_when_path_misses(monkeypatch, tmp_path):
    """The sidecar case: PATH does not name it, but it is installed."""
    install_dir = tmp_path / "homebrew" / "bin"
    install_dir.mkdir(parents=True)
    fake = _make_executable(install_dir / "claude")

    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda _name: None)
    monkeypatch.setattr(llm, "_CLAUDE_FALLBACK_DIRS", (str(install_dir),))

    assert claude_binary() == str(fake)
    assert cli_available() is True


def test_returns_none_when_genuinely_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda _name: None)
    monkeypatch.setattr(llm, "_CLAUDE_FALLBACK_DIRS", (str(tmp_path / "nowhere"),))
    assert claude_binary() is None
    assert cli_available() is False


def test_env_override_wins_over_path(monkeypatch, tmp_path):
    on_path = _make_executable(tmp_path / "path-claude")
    override = _make_executable(tmp_path / "override-claude")
    monkeypatch.setattr(llm.shutil, "which", lambda _name: str(on_path))
    monkeypatch.setenv("MEMOPOP_CLAUDE_BIN", str(override))
    assert claude_binary() == str(override)


def test_env_override_pointing_at_nothing_is_not_silently_ignored(monkeypatch, tmp_path):
    """An operator who sets the override and gets it wrong should not be
    quietly handed a different binary — that is how you end up billing an
    account you were trying to avoid."""
    on_path = _make_executable(tmp_path / "path-claude")
    monkeypatch.setattr(llm.shutil, "which", lambda _name: str(on_path))
    monkeypatch.setenv("MEMOPOP_CLAUDE_BIN", str(tmp_path / "does-not-exist"))
    assert claude_binary() is None


def test_non_executable_candidate_is_rejected(monkeypatch, tmp_path):
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    (install_dir / "claude").write_text("not executable")
    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda _name: None)
    monkeypatch.setattr(llm, "_CLAUDE_FALLBACK_DIRS", (str(install_dir),))
    assert claude_binary() is None


def test_resolution_is_cached(monkeypatch, tmp_path):
    """The fallback sweep touches the filesystem; it must not run per call."""
    calls = []
    fake = _make_executable(tmp_path / "claude")

    def counting_which(name):
        calls.append(name)
        return str(fake)

    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", counting_which)
    for _ in range(5):
        claude_binary()
    assert len(calls) == 1


def test_via_cli_invokes_the_resolved_absolute_path(monkeypatch, tmp_path):
    """PATH is exactly what is missing where this matters, so the command must
    not rely on it resolving the bare name."""
    fake = _make_executable(tmp_path / "claude")
    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda _n: None)
    monkeypatch.setattr(llm, "_CLAUDE_FALLBACK_DIRS", (str(tmp_path),))

    seen = {}

    class _Result:
        returncode = 0
        stdout = '{"result": "hi"}'
        stderr = ""

    def fake_run(command, **kwargs):
        seen["argv0"] = command[0]
        return _Result()

    monkeypatch.setattr(llm.subprocess, "run", fake_run)
    llm._via_cli("prompt", None, None, 30)
    assert seen["argv0"] == str(fake), "invoked the bare name instead of the resolved path"


def test_describe_provider_names_the_binary(monkeypatch, tmp_path):
    fake = _make_executable(tmp_path / "claude")
    monkeypatch.delenv("MEMOPOP_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MEMOPOP_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda _n: str(fake))
    assert str(fake) in llm.describe_provider()
