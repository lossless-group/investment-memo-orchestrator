"""
Validation utilities for citation source URLs.

Modules:
  - url_recovery: attempts to find a working URL for citations whose
    original URL has drifted (e.g., publisher re-slugged the article).
    See `gated_publishers.yaml` for the recovery query's domain seeds.
"""
