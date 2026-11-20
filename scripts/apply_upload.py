#!/usr/bin/env python3
"""Apply a staged upload on the server. Shipped inside the staging by upload_firm.py.

Run as the service user from /app, never by hand on a laptop::

    python /tmp/upload/apply_upload.py <firm> /tmp/upload

In order:

1. Back up the whole firm folder (``.jj`` included) to ``/data/backups/<firm>-<UTC time>``.
2. Put each staged binary into the firm's bucket as ``blobs/<sha256>``, skipping
   any key that already exists, so nothing is stored twice.
3. Replace each uploaded deal's folder with the staged one, under the deal's lock.
4. Copy the firm's staged configs, outlines and scorecards over the server's.
5. Record one change in the firm's history covering all of it.

Deals on the server that the upload doesn't name are left alone.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")

from src.connector.config import ConnectorSettings  # noqa: E402
from src.connector.workspace import open_workspace  # noqa: E402


def main(firm: str, up: Path) -> int:
    plan = json.loads((up / "plan.json").read_text(encoding="utf-8"))
    if plan["firm"] != firm:
        raise SystemExit(f"staging is for {plan['firm']}, not {firm}")
    ws = open_workspace(ConnectorSettings.from_env(), firm)
    root = ws.root
    staged = up / "firms" / firm

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

    touched: list[Path] = []
    for deal in plan["deals"]:
        with ws.lock(deal):
            dest = root / "deals" / deal
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(staged / "deals" / deal, dest)
        touched.append(dest)
    for rel in plan["firm_paths"]:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged / rel, dest)
        touched.append(dest)
    ws.history.record(f"upload: {len(plan['deals'])} deals and the firm's files from the local folder", touched)
    print(f"workspace: {len(plan['deals'])} deals replaced, {len(plan['firm_paths'])} firm files", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
