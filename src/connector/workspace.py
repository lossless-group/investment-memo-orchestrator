"""A firm's workspace: deal folders under ``MEMO_IO_ROOT``, ``deal.json``, and
artifact files, written atomically and serialized per deal.

Layout (spec §Storage)::

    <io_root>/<firm>/              # one workspace (and, from phase 6, one jj repo) per firm
      firm.json                    # {"default_template": ..., "entity_id": ...}; optional
      templates/outlines/*.yaml    # the firm's own outlines; optional
      deals/<deal>/
        deal.json                  # template, sections, artifacts, step log, skips
        materials/<id>.md
        research/<section>.md
        sections/<section>.md
        enhancements/<step>/...
        compiled/<version>/

Every write goes through :meth:`Workspace.transaction`: files are staged to temp
files and swapped in by :meth:`Workspace._replace`. If any swap fails, every file
the transaction touched is restored and every directory it created is removed,
so a failing disk yields ``down`` / ``storage_unavailable`` with nothing saved
(CONN-ERR-03). ``_replace`` is the single seam tests use to inject that failure.

Nothing here hardcodes ``Path("io")``; the root always comes from settings.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .bucket import Bucket, bucket_for
from .config import ConnectorSettings
from .errors import ConnectorError
from .history import History, history_for

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")

_thread_locks: dict[str, threading.RLock] = {}
_thread_locks_guard = threading.Lock()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_slug(value: str) -> bool:
    return bool(SLUG_RE.match(value or ""))


def _thread_lock(key: str) -> threading.RLock:
    with _thread_locks_guard:
        return _thread_locks.setdefault(key, threading.RLock())


class Transaction:
    """Stage writes, then swap them all in, or none of them."""

    def __init__(self, ws: Workspace):
        self.ws = ws
        self._staged: list[tuple[Path, bytes]] = []

    def write_text(self, rel: str | Path, text: str) -> Path:
        dest = self.ws.root / rel
        self._staged.append((dest, text.encode("utf-8")))
        return dest

    def write_json(self, rel: str | Path, obj: Any) -> Path:
        return self.write_text(rel, json.dumps(obj, indent=2, sort_keys=False) + "\n")

    @property
    def paths(self) -> list[Path]:
        return [dest for dest, _ in self._staged]

    def commit(self) -> None:
        backups: list[tuple[Path, bytes | None]] = []
        created_dirs: list[Path] = []
        temps: list[Path] = []
        try:
            for dest, data in self._staged:
                missing = []
                parent = dest.parent
                while not parent.exists():
                    missing.append(parent)
                    parent = parent.parent
                for d in reversed(missing):
                    d.mkdir()
                    created_dirs.append(d)
                backups.append((dest, dest.read_bytes() if dest.exists() else None))
                tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.tmp")
                temps.append(tmp)
                with open(tmp, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                self.ws._replace(tmp, dest)
        except OSError as exc:
            self._rollback(backups, created_dirs, temps)
            raise ConnectorError("storage_unavailable", details={"reason": str(exc)}) from exc

    @staticmethod
    def _rollback(backups, created_dirs, temps) -> None:
        for tmp in temps:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        for dest, original in reversed(backups):
            try:
                if original is None:
                    dest.unlink(missing_ok=True)
                else:
                    dest.write_bytes(original)
            except OSError:
                pass
        for d in reversed(created_dirs):
            try:
                for child in sorted(d.rglob("*"), reverse=True):
                    child.rmdir() if child.is_dir() else child.unlink()
                d.rmdir()
            except OSError:
                pass


class Workspace:
    """One firm's workspace. Tools take one of these and nothing else."""

    def __init__(
        self,
        settings: ConnectorSettings,
        firm: str,
        root: Path,
        bucket: Bucket,
        history: History,
    ):
        self.settings = settings
        self.firm = firm
        self.root = root
        self.bucket = bucket
        self.history = history

    # ------------------------------------------------------------ files

    def _replace(self, tmp: Path, dest: Path) -> None:
        """Atomically move a staged temp file into place (the failure seam)."""
        os.replace(tmp, dest)

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        tx = Transaction(self)
        yield tx
        tx.commit()

    def read_text(self, rel: str | Path) -> str:
        try:
            return (self.root / rel).read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ConnectorError("artifact_not_found") from None
        except OSError as exc:
            raise ConnectorError("storage_unavailable") from exc

    def firm_config(self) -> dict:
        path = self.root / "firm.json"
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectorError("storage_unavailable", details={"file": "firm.json"}) from exc
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------ deals

    def deal_rel(self, deal: str) -> Path:
        return Path("deals") / deal

    def deal_exists(self, deal: str) -> bool:
        return is_slug(deal) and (self.root / "deals" / deal / "deal.json").is_file()

    def deal_slugs(self) -> list[str]:
        deals = self.root / "deals"
        if not deals.is_dir():
            return []
        return sorted(p.name for p in deals.iterdir() if (p / "deal.json").is_file())

    def read_deal(self, deal: str) -> dict:
        if not self.deal_exists(deal):
            raise ConnectorError(
                "deal_not_found",
                (
                    f"No deal called '{deal}' in this workspace."
                    if is_slug(deal)
                    else "No deal by that name in this workspace."
                ),
            )
        try:
            return json.loads((self.root / "deals" / deal / "deal.json").read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConnectorError("storage_unavailable") from exc

    @contextmanager
    def lock(self, name: str) -> Iterator[None]:
        """Serialize writers of one deal (or one firm-level operation).

        A thread lock for this process plus an flock for other processes, so the
        unlocked read-modify-write of the old ``versions.json`` is not repeated.
        """
        key = f"{self.root}:{name}"
        with _thread_lock(key):
            locks = self.root / ".locks"
            try:
                locks.mkdir(exist_ok=True)
                fh = open(locks / f"{name}.lock", "a+")
            except OSError as exc:
                raise ConnectorError("storage_unavailable") from exc
            try:
                fcntl.flock(fh, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
                fh.close()

    def update_deal(self, deal: str, mutate: Callable[[dict], Any]) -> dict:
        """Read, mutate, and write ``deal.json`` under the deal's lock."""
        with self.lock(deal):
            state = self.read_deal(deal)
            mutate(state)
            state["updated_at"] = now_iso()
            with self.transaction() as tx:
                tx.write_json(self.deal_rel(deal) / "deal.json", state)
            return state


def provision_firm(
    io_root: Path,
    firm: str,
    *,
    default_template: str | None = None,
    entity_id: str | None = None,
) -> Path:
    """Create a firm's workspace (an operator act, never a tool)."""
    if not is_slug(firm):
        raise ValueError(f"Bad firm slug {firm!r}")
    root = Path(io_root) / firm
    (root / "deals").mkdir(parents=True, exist_ok=True)
    config: dict[str, Any] = {}
    if default_template:
        config["default_template"] = default_template
    if entity_id:
        config["entity_id"] = entity_id
    (root / "firm.json").write_text(json.dumps(config, indent=2) + "\n")
    return root


def open_workspace(settings: ConnectorSettings, firm: str) -> Workspace:
    """The firm's workspace, or ``forbidden_firm`` if it has none.

    The message never says whether the firm exists, so the answer for a firm
    that is merely someone else's is the same as for one that is nobody's.
    """
    root = Path(settings.io_root) / firm
    if not is_slug(firm) or not root.is_dir():
        raise ConnectorError("forbidden_firm")
    return Workspace(settings, firm, root, bucket_for(settings, firm), history_for(root))
