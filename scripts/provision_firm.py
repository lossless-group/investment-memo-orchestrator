#!/usr/bin/env python3
"""Provision a firm's workspace on the volume (an operator act; see docs/operator/deploy.md).

Run it where the volume is mounted. On Railway:

    railway ssh -- python scripts/provision_firm.py test-firm --health-check --new-key
    railway ssh -- python scripts/provision_firm.py acme-capital \\
        --entity-id ent_123 --default-template direct-early-stage-12Ps

Re-running is safe: deals are kept and firm.json is merged. ``--new-key`` prints
a fresh static key and the ``MEMOPOP_STATIC_KEYS`` entry to add; the key is
never written to disk. The firm's bucket is not created here (see the guide).
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.connector.provision import HEALTH_CHECK_TEMPLATE, provision_firm  # noqa: E402


def _match_owner(root: Path, io_root: Path) -> None:
    """Run as root (``railway ssh``), hand what was made to the server's user."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    owner = io_root.stat()
    if owner.st_uid == 0:
        return
    for path in [root, *root.rglob("*")]:
        os.chown(path, owner.st_uid, owner.st_gid, follow_symlinks=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("firm", help="the firm's slug, which must equal its didi.sh entity slug")
    parser.add_argument("--io-root", default=os.environ.get("MEMO_IO_ROOT", "/data/firms"))
    parser.add_argument("--entity-id", help="the didi.sh entity id (tokens may carry only the id)")
    parser.add_argument("--default-template", help="the firm's default outline")
    parser.add_argument(
        "--health-check",
        action="store_true",
        help=f"install the one-section '{HEALTH_CHECK_TEMPLATE}' outline (test-firm only)",
    )
    parser.add_argument("--new-key", action="store_true", help="print a fresh static key")
    args = parser.parse_args(argv)

    try:
        root = provision_firm(
            Path(args.io_root),
            args.firm,
            default_template=args.default_template,
            entity_id=args.entity_id,
            health_check=args.health_check,
        )
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    _match_owner(root, Path(args.io_root))
    print(f"provisioned {root}")
    print(f"firm.json: {(root / 'firm.json').read_text().strip()}")
    if args.health_check:
        print(f"outline: {root / 'templates' / 'outlines' / (HEALTH_CHECK_TEMPLATE + '.yaml')}")
    if args.new_key:
        key = f"sk-{args.firm}-{secrets.token_urlsafe(24)}"
        print("\nStatic key (shown once; store it in the password manager):")
        print(f"  {key}")
        print("Append to MEMOPOP_STATIC_KEYS (comma-separated firm=key pairs):")
        print(f"  {args.firm}={key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
