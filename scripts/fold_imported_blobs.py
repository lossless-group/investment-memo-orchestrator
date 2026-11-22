#!/usr/bin/env python3
"""Fold the bucket's old ``imported/…`` keys into content-addressed ``blobs/<sha256>``.

Spec: ``context-v/specs/Upload-Deal-Folders-With-a-Binaries-Manifest.md``, "The 901
keys already imported". Runs once per firm, on the server, as the service user, so
no byte crosses the network twice::

    railway ssh --service connector -- sh -c 'cd /app && runuser -u memopop -- \\
      env HOME=/home/memopop /opt/venv/bin/python - <firm> [--dry-run]' \\
      < scripts/fold_imported_blobs.py > known-blobs.txt

For every object under ``imported/`` it reads the bytes and hashes them. Each
distinct hash is copied to ``blobs/<sha256>`` once, unless that key is already
there. It prints the hash list on stdout, one sha256 per line, and its progress
on stderr. ``scripts/upload_firm.py --known-blobs known-blobs.txt`` then treats
those hashes as already uploaded.

It never deletes or changes an ``imported/`` key: that is a separate step, with
its own go-ahead, once the uploaded deals check out (``scripts/check_upload.py``).
``--dry-run`` hashes and counts but copies nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import dataclass, field

PREFIX = "imported/"


@dataclass
class FoldResult:
    hashes: list[str] = field(default_factory=list)  # every distinct hash, sorted
    objects: int = 0  # imported objects read
    copied: int = 0  # blobs/<hash> keys written by this run
    bytes_read: int = 0


def fold(bucket, *, prefix: str = PREFIX, dry_run: bool = False, log=None) -> FoldResult:
    """Hash every object under ``prefix``; copy each new hash to ``blobs/<hash>`` once."""
    log = log or (lambda message: None)
    result = FoldResult()
    seen: set[str] = set()
    keys = sorted(bucket.list(prefix))
    log(f"{len(keys)} objects under {prefix}")
    for n, key in enumerate(keys, 1):
        data = bucket.get(key)
        digest = hashlib.sha256(data).hexdigest()
        result.objects += 1
        result.bytes_read += len(data)
        if digest not in seen:
            seen.add(digest)
            blob = f"blobs/{digest}"
            if not dry_run and not bucket.exists(blob):
                bucket.put(blob, data)
                result.copied += 1
        if n % 50 == 0:
            log(f"  {n}/{len(keys)} read, {len(seen)} distinct")
    result.hashes = sorted(seen)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fold imported/ keys into blobs/<sha256>.")
    parser.add_argument("firm", help="the firm's slug on the server")
    parser.add_argument("--dry-run", action="store_true", help="hash and count; copy nothing")
    args = parser.parse_args(argv)

    sys.path.insert(0, "/app")
    from src.connector.bucket import bucket_for
    from src.connector.config import ConnectorSettings

    bucket = bucket_for(ConnectorSettings.from_env(), args.firm)

    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    result = fold(bucket, dry_run=args.dry_run, log=log)
    for digest in result.hashes:
        print(digest)
    log(
        f"{result.objects} imported objects, {result.bytes_read / 1e6:,.0f} MB read, "
        f"{len(result.hashes)} distinct; "
        + ("dry run, nothing copied" if args.dry_run else f"{result.copied} copied to blobs/")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
