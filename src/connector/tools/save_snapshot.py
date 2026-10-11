"""save_snapshot: back up the firm's whole workspace to its bucket.

A snapshot is a ``.tar.gz`` of the firm's workspace, jj's repository (``.jj/``)
included, written to the firm's own bucket (spec §Defaults: a compressed
archive; Kopia can replace it later behind the same tool)::

    snapshots/<snapshot_id>.tar.gz          the archive; members are <firm>/<path>
    snapshots/<snapshot_id>.manifest.json   the small manifest kept beside it

``snapshot_id`` is ``<UTC timestamp>-<label slug>`` (``20261010T153012Z-before-ic``),
or the timestamp alone without a label. The manifest records a sha256 for every
workspace file (jj's internals and the lock files aside), so the next snapshot
counts files added, changed, and removed against it.

Symlinks are never archived or followed, so a link planted in one firm's
workspace can't pull another firm's files into its snapshot (CONN-HIST-04).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tarfile
from datetime import UTC, datetime

from pydantic import Field

from ..registry.types import ANY, Example, InputDoc, ReturnDoc, ToolDef, ToolInput
from ..workspace import Workspace

PREFIX = "snapshots/"
MANIFEST_SUFFIX = ".manifest.json"
ARCHIVE_SUFFIX = ".tar.gz"
#: Top-level workspace entries never archived (per-process lock files).
NOT_ARCHIVED = {".locks"}
#: Top-level entries archived but not counted as the partner's files.
NOT_COUNTED = {".jj"}
_TIMESTAMP = re.compile(r"^\d{8}T\d{6}Z")


class Input(ToolInput):
    label: str | None = Field(default=None, max_length=120)


def slug(label: str | None) -> str:
    """A label as a key-safe slug: lowercase letters, digits, and dashes."""
    text = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return text[:60].rstrip("-")


def _archive(ws: Workspace) -> tuple[bytes, dict[str, str]]:
    """Tar and gzip the workspace; return the bytes and the counted files' hashes."""
    buf = io.BytesIO()
    hashes: dict[str, str] = {}
    root = str(ws.root)
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
        tar.addfile(_dir_info(ws.firm))
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            rel_dir = os.path.relpath(dirpath, root)
            top = None if rel_dir == "." else rel_dir.split(os.sep)[0]
            dirnames[:] = sorted(
                d
                for d in dirnames
                if not os.path.islink(os.path.join(dirpath, d))
                and not (top is None and d in NOT_ARCHIVED)
            )
            for d in dirnames:
                tar.addfile(_dir_info(_arcname(ws.firm, rel_dir, d)))
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                if top != ".jj" and name.endswith((".tmp", ".part")):
                    continue  # a write in flight elsewhere; its target is archived
                with open(full, "rb") as fh:
                    data = fh.read()
                info = tarfile.TarInfo(_arcname(ws.firm, rel_dir, name))
                info.size = len(data)
                info.mtime = int(os.stat(full).st_mtime)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
                rel = _rel(rel_dir, name)
                if (top or rel) not in NOT_COUNTED:
                    hashes[rel] = hashlib.sha256(data).hexdigest()
    return buf.getvalue(), hashes


def _rel(rel_dir: str, name: str) -> str:
    return name if rel_dir == "." else f"{rel_dir.replace(os.sep, '/')}/{name}"


def _arcname(firm: str, rel_dir: str, name: str) -> str:
    return f"{firm}/{_rel(rel_dir, name)}"


def _dir_info(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    info.mode = 0o755
    return info


def _previous(ws: Workspace) -> dict | None:
    """The latest snapshot's manifest, or None before the first."""
    keys = [
        k
        for k in ws.bucket.list(PREFIX)
        if k.endswith(MANIFEST_SUFFIX) and _TIMESTAMP.match(k[len(PREFIX) :])
    ]
    if not keys:
        return None
    newest = max(k[len(PREFIX) : len(PREFIX) + 16] for k in keys)
    candidates = []
    for key in keys:
        if key[len(PREFIX) :].startswith(newest):
            try:
                candidates.append(json.loads(ws.bucket.get(key)))
            except (ValueError, TypeError):
                continue
    return max(candidates, key=lambda m: m.get("sequence", 0), default=None)


def _counts(before: dict[str, str], after: dict[str, str]) -> tuple[int, int, int]:
    added = sum(1 for p in after if p not in before)
    changed = sum(1 for p in after if p in before and before[p] != after[p])
    removed = sum(1 for p in before if p not in after)
    return added, changed, removed


def handle(ws: Workspace, params: Input) -> dict:
    label = (params.label or "").strip() or None
    with ws.lock("_snapshot"):
        with ws.history.quiesced():
            data, hashes = _archive(ws)
            head = ws.history.head()
        previous = _previous(ws)
        added, changed, removed = _counts((previous or {}).get("files", {}), hashes)

        now = datetime.now(UTC).replace(microsecond=0)
        base = now.strftime("%Y%m%dT%H%M%SZ") + (f"-{slug(label)}" if slug(label) else "")
        snapshot_id, n = base, 1
        while ws.bucket.exists(f"{PREFIX}{snapshot_id}{ARCHIVE_SUFFIX}"):
            n += 1
            snapshot_id = f"{base}-{n}"
        created_at = now.isoformat().replace("+00:00", "Z")
        archive_key = f"{PREFIX}{snapshot_id}{ARCHIVE_SUFFIX}"
        manifest = {
            "snapshot_id": snapshot_id,
            "label": label,
            "created_at": created_at,
            "sequence": (previous or {}).get("sequence", 0) + 1,
            "previous_snapshot_id": (previous or {}).get("snapshot_id"),
            "archive_key": archive_key,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "jj_change": head,
            "files_added": added,
            "files_changed": changed,
            "files_removed": removed,
            "files": hashes,
        }
        # The archive first: a manifest never names an archive that isn't there.
        ws.bucket.put(archive_key, data, "application/gzip")
        ws.bucket.put(
            f"{PREFIX}{snapshot_id}{MANIFEST_SUFFIX}",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            "application/json",
        )
    return {
        "snapshot_id": snapshot_id,
        "label": label,
        "created_at": created_at,
        "bytes": len(data),
        "files_added": added,
        "files_changed": changed,
        "files_removed": removed,
        "previous_snapshot_id": manifest["previous_snapshot_id"],
    }


TOOL = ToolDef(
    name="save_snapshot",
    summary="Save a backup of this firm's whole MemoPop workspace to the firm's private bucket.",
    when_to_use=(
        "the partner asks to back up, checkpoint, or save a copy of their work, for example "
        "before a big revision or at the end of a deal."
    ),
    when_not_to_use=(
        "to save a step's work: submit_artifact already keeps every version. A snapshot is a "
        "whole-workspace backup."
    ),
    inputs=[InputDoc("label", "string", "A short name for the snapshot.", "before IC meeting")],
    returns=[
        ReturnDoc(
            "snapshot_id",
            "The snapshot's id: its UTC time, then the label as a slug "
            "(20261010T153012Z-before-ic-meeting).",
        ),
        ReturnDoc("label", "The label given, if any."),
        ReturnDoc("created_at", "When it was taken (UTC, ISO 8601)."),
        ReturnDoc("bytes", "The archive's size."),
        ReturnDoc(
            "files_added", "Files new since the previous snapshot (all of them, the first time)."
        ),
        ReturnDoc("files_changed", "Files changed since the previous snapshot."),
        ReturnDoc("files_removed", "Files gone since the previous snapshot."),
        ReturnDoc(
            "previous_snapshot_id", "The snapshot the counts compare against; null the first time."
        ),
    ],
    changes=(
        "writes one archive of the whole workspace, its history included, and a small manifest "
        "to the firm's bucket under snapshots/; changes nothing in the workspace. Snapshots are "
        "kept until a retention policy is decided."
    ),
    duration="a few seconds; up to a minute for a large workspace.",
    errors=[],
    error_next_overrides={
        "storage_unavailable": "The backup could not be written; nothing was lost, since every "
        "submitted artifact is already kept. Tell the partner and try again later.",
    },
    next="tell the partner the snapshot's label and time, then carry on.",
    examples=[
        Example(
            title="A labelled snapshot of a new firm",
            request={"label": "before IC meeting"},
            response={
                "ok": True,
                "snapshot_id": ANY,
                "label": "before IC meeting",
                "created_at": ANY,
                "bytes": ANY,
                "files_added": 1,
                "files_changed": 0,
                "files_removed": 0,
                "previous_snapshot_id": None,
                "api_version": "1",
            },
        ),
        Example(
            title="A second snapshot counts what changed since the first",
            setup=[
                ("create_new_deal", {"company": "Acme Robotics", "url": "https://acme.ai"}),
                ("save_snapshot", {"label": "deal created"}),
                ("next_step", {"deal": "acme-ai"}),
            ],
            request={},
            response={
                "ok": True,
                "snapshot_id": ANY,
                "label": None,
                "files_added": 0,
                "files_changed": 1,
                "files_removed": 0,
                "previous_snapshot_id": ANY,
                "api_version": "1",
            },
        ),
    ],
    input_model=Input,
    handler=handle,
    read_only=False,
    destructive=False,
    rest_method="POST",
    rest_path="/v1/snapshots",
)
