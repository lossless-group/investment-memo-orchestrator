"""
Discovery module — Auto-detects firms, deals, versions, and output states.

Used by the interactive CLI to present contextual options without
requiring users to know file paths or directory structures.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime


def discover_firms(base_dir: Path = Path("io")) -> List[Dict]:
    """Discover all firms with deal directories."""
    firms = []
    if not base_dir.exists():
        return firms

    for d in sorted(base_dir.iterdir()):
        if not d.is_dir():
            continue
        deals_dir = d / "deals"
        if deals_dir.exists():
            deal_count = sum(1 for dd in deals_dir.iterdir()
                           if dd.is_dir() and list(dd.glob("*.json")))
            config_path = d / "configs" / f"brand-{d.name}-config.yaml"
            firms.append({
                "name": d.name,
                "path": str(d),
                "deal_count": deal_count,
                "has_brand_config": config_path.exists(),
            })

    return firms


def discover_deals(firm: str, base_dir: Path = Path("io")) -> List[Dict]:
    """Discover all deals for a firm."""
    deals = []
    deals_dir = base_dir / firm / "deals"
    if not deals_dir.exists():
        return deals

    for d in sorted(deals_dir.iterdir()):
        if not d.is_dir():
            continue
        config_files = list(d.glob("*.json"))
        if not config_files:
            continue

        # Load deal config
        config = {}
        for cf in config_files:
            if cf.stem == d.name:  # Match {DealName}.json
                try:
                    config = json.loads(cf.read_text())
                except json.JSONDecodeError:
                    pass
                break

        # Find versions
        outputs_dir = d / "outputs"
        versions = []
        latest_version = None
        latest_date = None
        if outputs_dir.exists():
            for v in sorted(outputs_dir.iterdir()):
                if v.is_dir() and "-v" in v.name:
                    version_str = v.name.split("-v")[-1]
                    state_file = v / "state.json"
                    mod_time = datetime.fromtimestamp(v.stat().st_mtime)
                    versions.append({
                        "version": f"v{version_str}",
                        "path": str(v),
                        "date": mod_time.strftime("%Y-%m-%d"),
                        "has_state": state_file.exists(),
                        "has_final_draft": bool(list(v.glob("7-*.md")) or list(v.glob("4-final-draft.md"))),
                        "has_one_pager": bool(list(v.glob("8-one-pager.*"))),
                    })
                    if latest_date is None or mod_time > latest_date:
                        latest_date = mod_time
                        latest_version = f"v{version_str}"

        # Check for curation files
        curations = {
            "sources": (d / f"{d.name}_source-curation.json").exists(),
            "competitive": (d / f"{d.name}_competitive-curation.json").exists(),
            "tables": (d / f"{d.name}_table-curation.json").exists(),
            "syndicate": (d / f"{d.name}_syndicate-curation.json").exists(),
        }

        deals.append({
            "name": d.name,
            "path": str(d),
            "config": config,
            "type": config.get("type", "direct"),
            "mode": config.get("mode", "consider"),
            "stage": config.get("stage", "Unknown"),
            "versions": versions,
            "latest_version": latest_version,
            "latest_date": latest_date.strftime("%Y-%m-%d") if latest_date else None,
            "version_count": len(versions),
            "has_deck": bool(config.get("deck")),
            "has_dataroom": bool(config.get("dataroom")),
            "curations": curations,
        })

    return deals


def get_latest_output_dir(deal_path: str) -> Optional[Path]:
    """Get the latest version output directory for a deal."""
    outputs_dir = Path(deal_path) / "outputs"
    if not outputs_dir.exists():
        return None
    versions = sorted(outputs_dir.iterdir(), key=lambda p: p.stat().st_mtime)
    return versions[-1] if versions else None


def load_state(output_dir: Path) -> Dict:
    """Load state.json from an output directory."""
    state_path = output_dir / "state.json"
    if state_path.exists():
        try:
            return json.loads(state_path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}
