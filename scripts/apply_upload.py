#!/usr/bin/env python3
"""Apply a staged upload on the server. Shipped inside the staging by upload_firm.py.

Run as the service user from /app, never by hand on a laptop::

    python /tmp/upload/apply_upload.py <firm> /tmp/upload

In order:

0. Refuse, changing nothing, if a blob the staging counts on being in the bucket
   already (``known_blobs``, from ``--known-blobs``) isn't there.
1. Back up the whole firm folder (``.jj`` included) to ``/data/backups/<firm>-<UTC time>``.
2. Put each staged binary into the firm's bucket as ``blobs/<sha256>``, skipping
   any key that already exists, so nothing is stored twice.
3. Replace each uploaded deal's folder with the staged one, under the deal's lock.
4. Copy the firm's staged configs, outlines and scorecards over the server's.
5. Record one change in the firm's history covering all of it.
6. Tell the firm's site about each deal whose compiled version changed
   (``src/connector/site_hook.py``), and wait for those sends before exiting.

Deals on the server that the upload doesn't name are left alone.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")

from src.connector import site_hook  # noqa: E402
from src.connector.config import ConnectorSettings  # noqa: E402
from src.connector.workspace import Workspace, open_workspace  # noqa: E402

#: How long the script waits for site notifications before exiting: every
#: attempt's 5 s timeout plus the backoff between them, with room to spare.
HOOK_WAIT_SECONDS = 90.0


def missing_known(bucket, plan: dict) -> list[str]:
    """The known blobs the staging relies on that the bucket doesn't hold."""
    return [d for d in plan.get("known_blobs") or [] if not bucket.exists(f"blobs/{d}")]


def _compiled(ws: Workspace, deal: str) -> dict | None:
    """The deal's compiled record on the server, or None if it has none (or no deal)."""
    if not ws.deal_exists(deal):
        return None
    return ws.read_deal(deal).get("compiled") or None


def _changed(before: dict | None, after: dict | None) -> bool:
    if not after:
        return False
    if not before:
        return True
    return (before.get("version"), before.get("sha256")) != (
        after.get("version"),
        after.get("sha256"),
    )


def replace_deals(ws: Workspace, staged: Path, deals: list[str]) -> list[str]:
    """Replace each deal's folder with the staged one; notify the site of changed compiles.

    Returns the deals whose compiled version changed. The notifications run in
    the background (``site_hook.wait_for_senders`` waits for them).
    """
    changed: list[str] = []
    for deal in deals:
        with ws.lock(deal):
            before = _compiled(ws, deal)
            dest = ws.root / "deals" / deal
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(staged / "deals" / deal, dest)
            after = _compiled(ws, deal)
        if _changed(before, after):
            changed.append(deal)
    return changed


def notify_site(ws: Workspace, deals: list[str]) -> None:
    """Notify the firm's site for each deal, once the change is recorded."""
    for deal in deals:
        site_hook.notify(ws, deal, _compiled(ws, deal) or {})


def drop_macos_metadata(up: Path) -> int:
    """Delete ``._*`` and ``.DS_Store`` files under the staging; return how many.

    A staging packed on a Mac without COPYFILE_DISABLE carries a ``._`` file
    beside every real one. They are never content, so they never reach the
    workspace, whatever the sender did.
    """
    dropped = 0
    for f in sorted(up.rglob("*")):
        if f.is_file() and (f.name.startswith("._") or f.name == ".DS_Store"):
            f.unlink()
            dropped += 1
    return dropped


def main(firm: str, up: Path) -> int:
    plan = json.loads((up / "plan.json").read_text(encoding="utf-8"))
    if plan["firm"] != firm:
        raise SystemExit(f"staging is for {plan['firm']}, not {firm}")
    ws = open_workspace(ConnectorSettings.from_env(), firm)
    root = ws.root
    dropped = drop_macos_metadata(up)
    if dropped:
        print(f"staging: dropped {dropped} macOS metadata file(s)", flush=True)
    staged = up / "firms" / firm

    missing = missing_known(ws.bucket, plan)
    if missing:
        raise SystemExit(
            f"{len(missing)} known blob(s) are not in the bucket, e.g. blobs/{missing[0]}; "
            "run fold_imported_blobs.py first, or stage without --known-blobs. Nothing changed."
        )

    backup = Path("/data/backups") / f"{firm}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root, backup, symlinks=True)
    print(f"backup: {backup}", flush=True)

    put = 0
    for digest in plan["blobs"]:
        key = f"blobs/{digest}"
        if not ws.bucket.exists(key):
            ws.bucket.put(key, (up / "blobs" / digest).read_bytes())
            put += 1
    print(f"bucket: {put} put, {len(plan['blobs']) - put} already there", flush=True)

    changed = replace_deals(ws, staged, plan["deals"])
    touched: list[Path] = [root / "deals" / deal for deal in plan["deals"]]
    for rel in plan["firm_paths"]:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged / rel, dest)
        touched.append(dest)
    ws.history.record(
        f"upload: {len(plan['deals'])} deals and the firm's files from the local folder", touched
    )
    print(
        f"workspace: {len(plan['deals'])} deals replaced, {len(plan['firm_paths'])} firm files",
        flush=True,
    )
    notify_site(ws, changed)
    left = site_hook.wait_for_senders(HOOK_WAIT_SECONDS)
    print(
        f"site: {len(changed)} deal(s) with a new compiled version; {left} notification(s) unfinished",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
