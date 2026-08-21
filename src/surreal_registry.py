"""
Register sources in the shared SurrealDB registry.

WHAT THIS IS
------------
`augment-it` owns a SurrealDB instance that is the system of record for
information sources with URLs. memopop writes into the SAME instance rather than
standing up its own, so a URL cited in a memo and a URL captured for a client
corpus are the same row.

Two tables, and the split is load-bearing:

    sources         canonical, client-AGNOSTIC identity. UNIQUE on
                    normalized_url. One row per URL in the world. It carries NO
                    client field — a source is a fact, shared by everyone who
                    cites it.

    source_usages   the edge: (client_slug, domain_type, domain_slug,
                    source_uuid) + status/tags. This is where client scoping
                    lives, via singular `client_slug` — NOT the `client_access`
                    array used on persons/organizations/events.

The SurrealQL below mirrors `augment-it/services/record-surrealdb-resolver/
src/domains.ts` (`upsertSource` / `addSource`). Adoption is copy-from, not a
shared package: three bindings across a Python orchestrator, a Node service and
a Tauri app is a release cadence nobody wants.

WHAT GETS REGISTERED
--------------------
ONLY explicitly-approved sources. The registry is a system of record; a broad
search drags in whatever it drags in, and junk written here is visible to every
other client and deal, permanently. `sources_md.is_explicitly_approved` is the
gate, and it is deliberately stricter than the citation membership check.

Status mirrors the two-tier fetch, using augment-it's existing vocabulary:

    metadata-only   registered, full content not pulled
    fetched         full content pulled and stored

FAILURE POSTURE
---------------
Registration must never gate whether a memo can be written. Every entry point
returns a result object and swallows connection errors — an unreachable database
means `source_uuid` backfills later, not that the run dies.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_DOMAIN_TYPE = "deal"


@dataclass
class RegistryResult:
    registered: int = 0
    reused: int = 0
    skipped_unapproved: int = 0
    failed: int = 0
    uuids: Dict[str, str] = field(default_factory=dict)   # url -> source_uuid
    error: Optional[str] = None

    def summary(self) -> str:
        if self.error:
            return f"registry unavailable ({self.error}) — source_uuid backfills later"
        return (f"{self.registered} newly registered, {self.reused} already known, "
                f"{self.skipped_unapproved} not approved, {self.failed} failed")


def _config() -> Optional[Dict[str, str]]:
    cfg = {k: os.environ.get(f"SURREAL_{k.upper()}", "")
           for k in ("url", "ns", "db", "user", "pass")}
    return cfg if all(cfg.values()) else None


def _connect():
    """Open a signed-in connection, or None if unconfigured/unreachable."""
    cfg = _config()
    if not cfg:
        return None, "SURREAL_* not configured"
    try:
        from surrealdb import Surreal
    except ImportError:
        return None, "surrealdb driver not installed"
    try:
        db = Surreal(cfg["url"])
        db.signin({"username": cfg["user"], "password": cfg["pass"]})
        db.use(cfg["ns"], cfg["db"])
        return db, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:120]


def _rows(result: Any) -> List[Dict[str, Any]]:
    """Normalize the driver's query return into a list of dicts."""
    if result is None:
        return []
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        if result and isinstance(result[0], dict) and "result" in result[0]:
            out: List[Dict[str, Any]] = []
            for block in result:
                r = block.get("result")
                if isinstance(r, list):
                    out.extend(x for x in r if isinstance(x, dict))
                elif isinstance(r, dict):
                    out.append(r)
            return out
        return [x for x in result if isinstance(x, dict)]
    return []


def upsert_source(db, url: str, normalized_url: str) -> Optional[str]:
    """Return the source_uuid for this URL, creating the row if new.

    Mirrors augment-it's `upsertSource`: look up by normalized_url first, and
    only CREATE when absent. The UNIQUE index makes a blind CREATE fail, so the
    read is not an optimization — it is the contract.
    """
    found = _rows(db.query(
        "SELECT source_uuid FROM sources WHERE normalized_url = $n LIMIT 1;",
        {"n": normalized_url},
    ))
    if found and found[0].get("source_uuid"):
        return str(found[0]["source_uuid"]), False

    created = _rows(db.query(
        """CREATE sources SET
               id = rand::uuid::v7(),
               source_uuid = type::string(rand::uuid::v7()),
               normalized_url = $n, url = $url,
               title = '', authors = [], publisher = '', published_date = '',
               content_type = '', first_seen_at = time::now()
           RETURN source_uuid;""",
        {"n": normalized_url, "url": url},
    ))
    if created and created[0].get("source_uuid"):
        return str(created[0]["source_uuid"]), True
    return None, False


def ensure_usage(db, source_uuid: str, *, client_slug: str,
                 domain_type: str, domain_slug: str, status: str) -> None:
    """Create the (client, domain, source) edge if it does not already exist."""
    dupe = _rows(db.query(
        """SELECT source_uuid FROM source_usages
           WHERE source_uuid = $u AND client_slug = $c
             AND domain_type = $t AND domain_slug = $s LIMIT 1;""",
        {"u": source_uuid, "c": client_slug, "t": domain_type, "s": domain_slug},
    ))
    if dupe:
        return
    db.query(
        """CREATE source_usages SET
               id = rand::uuid::v7(), source_uuid = $u, client_slug = $c,
               domain_type = $t, domain_slug = $s,
               corpus_path = NONE, status = $st, tags = [], created_at = time::now();""",
        {"u": source_uuid, "c": client_slug, "t": domain_type,
         "s": domain_slug, "st": status},
    )


def register_deal_sources(
    deal_inputs_dir,
    *,
    client_slug: str,
    domain_slug: str,
    domain_type: str = DEFAULT_DOMAIN_TYPE,
    dry_run: bool = False,
) -> RegistryResult:
    """Register every EXPLICITLY-APPROVED source of a deal, writing back uuids.

    Writes `source_uuid` into each per-source file's frontmatter so the local
    file and the registry agree without a second lookup.
    """
    from pathlib import Path

    from .curation import load_sources_md
    from .curation.best_sources import canonical_url
    from .curation.extracts import split_body
    from .curation.source_file import read_source_file, sources_dir, write_source_file
    from .curation.sources_md import is_explicitly_approved

    inputs = Path(deal_inputs_dir)
    res = RegistryResult()
    sm = load_sources_md(inputs)
    if not sm or not sm.sources:
        res.error = "no Sources.md"
        return res

    approved, res.skipped_unapproved = [], 0
    for e in sm.sources:
        (approved.append(e) if is_explicitly_approved(e)
         else res.__setattr__("skipped_unapproved", res.skipped_unapproved + 1))

    if dry_run:
        print(f"  [dry run] would register {len(approved)} approved source(s) "
              f"as {client_slug}/{domain_type}/{domain_slug}; "
              f"{res.skipped_unapproved} not approved")
        return res

    db, err = _connect()
    if db is None:
        res.error = err
        print(f"  ⚠️  SurrealDB: {err} — continuing without registration")
        return res

    # Index local files by normalized URL so uuids land in the right file.
    files: Dict[str, Any] = {}
    sdir = sources_dir(inputs)
    if sdir.exists():
        for p in sdir.glob("*.md"):
            sf = read_source_file(p)
            if sf and sf.url:
                files[canonical_url(sf.url)] = sf

    try:
        for e in approved:
            norm = canonical_url(e.url)
            try:
                uuid, created = upsert_source(db, e.url, norm)
            except Exception as exc:  # noqa: BLE001
                res.failed += 1
                print(f"     ⚠️  {e.url[:56]}: {str(exc)[:70]}")
                continue
            if not uuid:
                res.failed += 1
                continue

            sf = files.get(norm)
            content = split_body(sf.body or "")[0] if sf else ""
            status = "fetched" if content.strip() else "metadata-only"
            try:
                ensure_usage(db, uuid, client_slug=client_slug,
                             domain_type=domain_type, domain_slug=domain_slug,
                             status=status)
            except Exception as exc:  # noqa: BLE001
                print(f"     ⚠️  usage edge for {e.url[:46]}: {str(exc)[:60]}")

            res.uuids[e.url] = uuid
            res.registered += 1 if created else 0
            res.reused += 0 if created else 1

            if sf is not None and getattr(sf, "extra_metadata", None) is not None:
                if sf.extra_metadata.get("source_uuid") != uuid:
                    sf.extra_metadata = {**sf.extra_metadata, "source_uuid": uuid}
                    try:
                        write_source_file(inputs, sf)
                    except Exception:  # noqa: BLE001
                        pass
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            pass

    print(f"  🗄️  SurrealDB registry: {res.summary()}")
    return res
