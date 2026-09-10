#!/usr/bin/env python3
"""
Decode a Decile Hub `download_file` tool result onto disk.

The MCP tool returns {filename, content_type, byte_size, data_base64}. A 6MB PDF
is 8.5M characters of base64, so the transport spills it to a file rather than
returning it inline. This turns that spill file into the actual document without
the bytes ever passing through an agent's context.

    python tools/decile_fetch.py <tool-result.txt> <destination-dir> [--name NAME]

Verifies the decoded length against the envelope's byte_size, because a
truncated spill file decodes happily into a corrupt PDF.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tool_result")
    ap.add_argument("destination")
    ap.add_argument("--name", help="Override the filename from the envelope.")
    args = ap.parse_args()

    raw = Path(args.tool_result).read_text()
    envelope = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])

    blob = base64.b64decode(envelope["data_base64"])
    expected = envelope.get("byte_size")
    if expected and len(blob) != expected:
        print(f"✗ size mismatch: decoded {len(blob)}, envelope says {expected} "
              f"— the spill file is probably truncated", file=sys.stderr)
        return 1

    dest_dir = Path(args.destination)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (args.name or envelope["filename"])
    if not dest.suffix and envelope.get("content_type") == "application/pdf":
        dest = dest.with_suffix(".pdf")
    dest.write_bytes(blob)

    print(f"✓ {dest}")
    print(f"  {len(blob) / 1048576:.2f} MB  {envelope.get('content_type', '?')}  "
          f"sha256={hashlib.sha256(blob).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
