"""A firm's history: one jj repository per firm workspace.

Every saved artifact calls :meth:`History.record` once, after its files are on
disk, with a message naming the step, deal, and section. :class:`JjHistory`
turns that into exactly one jj change holding those paths; content that didn't
change records nothing. The partner never sees jj.

How jj is run (spec §Storage; decision *jj Versions Text, and a Save Snapshots
to the Bucket*):

- **One repository per firm**, ``jj git init --no-colocate`` in the firm root,
  made on the first write. Every command passes ``-R <firm root>``, so a
  repository above the firms (there should be none) is never used.
- **A fixed environment.** jj runs as a subprocess with ``JJ_CONFIG`` pointing at
  a file this module writes, the author fixed to ``MemoPop <noreply@didi.sh>``,
  and every inherited ``JJ_*`` and ``GIT_*`` variable dropped, so the server
  user's jj config, identity, and git environment never leak in.
- **Text only.** ``snapshot.auto-track`` admits text extensions alone, and the
  firm's ``.gitignore`` excludes the binary kinds as well, so decks, datarooms,
  PDFs, and images (which live in the firm's bucket) never enter the working
  copy, not even when an operator runs jj by hand.
- **One change per save.** ``record`` asks jj for the diff of just those paths
  and commits just those paths (``jj commit <paths>``); anything else in the
  working copy stays in the working-copy change. An empty diff commits nothing.
- **Serialized per firm** by a thread lock and an ``flock`` on
  ``.locks/history.lock``, because jj snapshots the working copy on every
  mutating command. Reads use ``--ignore-working-copy`` and need no lock.

Recording is best-effort *after* the durable write: the artifact is already
saved when ``record`` runs, so a jj failure is logged, not raised (raising
would tell the client ``down`` / nothing saved, which would be false). The
unrecorded diff stays in the working copy and the next record of the same path
sweeps it in.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

log = logging.getLogger("memopop.connector.history")

AUTHOR_NAME = "MemoPop"
AUTHOR_EMAIL = "noreply@didi.sh"

#: Extensions jj may track. Everything else stays out of the working copy.
TEXT_EXTENSIONS = (
    "md",
    "markdown",
    "txt",
    "json",
    "yaml",
    "yml",
    "toml",
    "csv",
    "tsv",
    "html",
    "css",
    "bib",
)

#: Written to the firm root when its repository is made.
GITIGNORE = """\
# MemoPop: jj versions text only. Originals of materials, compiled PDFs, and
# snapshots live in the firm's bucket, never in this working copy.
.locks/
*.tmp
*.part
*.pdf
*.png
*.jpg
*.jpeg
*.gif
*.webp
*.heic
*.tif
*.tiff
*.bmp
*.svg
*.ico
*.ppt
*.pptx
*.key
*.doc
*.docx
*.xls
*.xlsx
*.numbers
*.pages
*.zip
*.gz
*.tgz
*.tar
*.7z
*.rar
*.mp3
*.mp4
*.m4a
*.mov
*.wav
*.webm
*.sqlite
*.db
"""

_AUTO_TRACK = " | ".join(f"glob:**/*.{ext}" for ext in TEXT_EXTENSIONS)

_CONFIG = f"""\
# Written by MemoPop (src/connector/history.py). The only jj config the server
# uses; the server user's own config is never read.
[user]
name = "{AUTHOR_NAME}"
email = "{AUTHOR_EMAIL}"

[operation]
hostname = "memopop"
username = "memopop"

[ui]
paginate = "never"
color = "never"
editor = "false"

[git]
colocate = false

[snapshot]
auto-track = "{_AUTO_TRACK}"
max-new-file-size = "32MiB"

[signing]
behavior = "drop"
"""

_config_lock = threading.Lock()
_config_path: Path | None = None

_thread_locks: dict[str, threading.RLock] = {}
_thread_locks_guard = threading.Lock()


class History(Protocol):
    def record(self, message: str, paths: list[Path]) -> None:
        """Record one change covering ``paths`` (already written)."""

    def read(self, path: Path, version: int) -> str | None:
        """Return ``path``'s text at artifact ``version``, or None if not kept."""

    def quiesced(self) -> contextlib.AbstractContextManager[None]:
        """Hold off history writes while a snapshot archives the workspace."""

    def head(self) -> str | None:
        """The latest recorded change's id, or None."""


class NullHistory:
    """Keeps nothing (no jj on this machine). Earlier versions are not readable."""

    def record(self, message: str, paths: list[Path]) -> None:
        return None

    def read(self, path: Path, version: int) -> str | None:
        return None

    @contextlib.contextmanager
    def quiesced(self) -> Iterator[None]:
        yield

    def head(self) -> str | None:
        return None


class HistoryError(RuntimeError):
    """jj failed. Logged by ``record``; never shown to a client."""


def config_file() -> Path:
    """The JJ_CONFIG file, written once per process (content-addressed)."""
    global _config_path
    with _config_lock:
        if _config_path is None or not _config_path.is_file():
            digest = hashlib.sha256(_CONFIG.encode()).hexdigest()[:12]
            path = Path(tempfile.gettempdir()) / f"memopop-jj-{digest}.toml"
            try:
                if not path.is_file() or path.read_text() != _CONFIG:
                    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
                    tmp.write_text(_CONFIG)
                    os.replace(tmp, path)
            except OSError:  # someone else's file at that name: use a private one
                fd, name = tempfile.mkstemp(prefix="memopop-jj-", suffix=".toml")
                with os.fdopen(fd, "w") as fh:
                    fh.write(_CONFIG)
                path = Path(name)
            _config_path = path
        return _config_path


def _thread_lock(key: str) -> threading.RLock:
    with _thread_locks_guard:
        return _thread_locks.setdefault(key, threading.RLock())


def _fileset(rel: str) -> str:
    """A jj fileset naming exactly one path relative to the repository root."""
    return "root-file:" + json.dumps(rel)


class JjHistory:
    """One firm's history, kept in a jj repository at the firm root."""

    def __init__(self, root: Path, jj_bin: str, timeout: float = 60.0):
        self.root = Path(root)
        self.jj_bin = jj_bin
        self.timeout = timeout

    # ------------------------------------------------------------ plumbing

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.startswith(("JJ_", "GIT_"))}
        env["JJ_CONFIG"] = str(config_file())
        env["JJ_USER"] = AUTHOR_NAME
        env["JJ_EMAIL"] = AUTHOR_EMAIL
        env["JJ_EDITOR"] = "false"
        return env

    def _run(self, *args: str, snapshot: bool = True, repo: bool = True) -> str:
        cmd = [self.jj_bin, "-R", str(self.root)] if repo else [self.jj_bin]
        if not snapshot:
            cmd.append("--ignore-working-copy")
        try:
            result = subprocess.run(
                [*cmd, *args],
                cwd=self.root,
                env=self._env(),
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise HistoryError(f"jj {args[0]}: {exc}") from exc
        if result.returncode != 0:
            raise HistoryError(f"jj {' '.join(args[:2])}: {result.stderr.strip()[:2000]}")
        return result.stdout

    @property
    def has_repo(self) -> bool:
        return (self.root / ".jj").is_dir()

    @contextlib.contextmanager
    def _lock(self) -> Iterator[None]:
        with _thread_lock(os.path.realpath(self.root)):
            locks = self.root / ".locks"
            locks.mkdir(exist_ok=True)
            with open(locks / "history.lock", "a+") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)

    def _rel(self, path: Path) -> str | None:
        """``path`` relative to the firm root, or None if it lies outside it."""
        try:
            resolved = Path(os.path.realpath(self.root / path))
            rel = resolved.relative_to(os.path.realpath(self.root))
        except (ValueError, OSError):
            return None
        if not rel.parts or rel.parts[0] in (".jj", ".locks"):
            return None
        return rel.as_posix()

    def ensure_repo(self) -> None:
        """Make the firm's repository on first write (the caller holds the lock)."""
        if self.has_repo:
            return
        gitignore = self.root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(GITIGNORE)
        self._run("git", "init", "--no-colocate", str(self.root), repo=False)

    # ------------------------------------------------------------ History

    def record(self, message: str, paths: list[Path]) -> None:
        rels = sorted({rel for rel in (self._rel(p) for p in paths) if rel})
        if not rels:
            return
        try:
            with self._lock():
                self.ensure_repo()
                filesets = [_fileset(rel) for rel in rels]
                if not self._run("diff", "--name-only", *filesets).strip():
                    return
                self._run("commit", "--message", message, *filesets)
        except (HistoryError, OSError):
            log.exception("history: could not record %r in %s", message, self.root)

    def read(self, path: Path, version: int) -> str | None:
        """The artifact at ``path`` as it was saved at ``version``.

        Walks the changes that touched ``path``, oldest first, and returns the
        file from the first one whose ``deal.json`` (committed in the same
        change) records that path at that version.
        """
        rel = self._rel(path)
        if rel is None or not self.has_repo:
            return None
        parts = rel.split("/")
        if len(parts) < 3 or parts[0] != "deals":
            return None
        deal_json = f"deals/{parts[1]}/deal.json"
        in_deal = "/".join(parts[2:])
        try:
            commits = self._run(
                "log",
                "--no-graph",
                "--reversed",
                "-r",
                f"::@- & files({_fileset(rel)})",
                "-T",
                'commit_id ++ "\\n"',
                snapshot=False,
            ).split()
            for commit in commits:
                try:
                    state = json.loads(
                        self._run("file", "show", "-r", commit, _fileset(deal_json), snapshot=False)
                    )
                except (HistoryError, json.JSONDecodeError):
                    continue
                for record in (state.get("artifacts") or {}).values():
                    if record.get("path") == in_deal and record.get("version") == version:
                        return self._run(
                            "file", "show", "-r", commit, _fileset(rel), snapshot=False
                        )
        except HistoryError:
            log.exception("history: could not read %s v%s in %s", rel, version, self.root)
        return None

    @contextlib.contextmanager
    def quiesced(self) -> Iterator[None]:
        with self._lock():
            yield

    def head(self) -> str | None:
        if not self.has_repo:
            return None
        try:
            out = self._run("log", "--no-graph", "-r", "@-", "-T", "commit_id", snapshot=False)
        except HistoryError:
            return None
        out = out.strip()
        return out if out and set(out) != {"0"} else None


_warned: set[str] = set()


def history_for(workspace_root: Path, jj_bin: str = "jj") -> History:
    """The firm's history: jj when the binary is on this machine, else nothing.

    A missing jj is logged once per process; the server still saves artifacts
    but keeps no earlier versions until jj is installed.
    """
    resolved = shutil.which(jj_bin)
    if resolved is None:
        if jj_bin not in _warned:
            _warned.add(jj_bin)
            log.warning("history: %r not found; artifact history is not being kept", jj_bin)
        return NullHistory()
    return JjHistory(Path(workspace_root), resolved)
