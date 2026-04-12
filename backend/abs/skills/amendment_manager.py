"""
Amendment Manager — Track document versions, apply amendments,
snapshot originals, and maintain version chains.

Ported from PayGen pipeline.skills.amendment_manager → backend.abs.skills
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class AmendmentRecord:
    """Single amendment entry."""
    amendment_id: str
    deal_id: str
    version: int
    description: str
    affected_sections: list[str] = field(default_factory=list)
    changes: dict[str, Any] = field(default_factory=dict)
    applied_at: str = ""
    applied_by: str = ""
    source_document: str = ""

    def to_dict(self) -> dict:
        return {
            "amendment_id": self.amendment_id,
            "deal_id": self.deal_id,
            "version": self.version,
            "description": self.description,
            "affected_sections": self.affected_sections,
            "changes": self.changes,
            "applied_at": self.applied_at,
            "applied_by": self.applied_by,
            "source_document": self.source_document,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AmendmentRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class VersionChain:
    """Ordered chain of amendments for a deal."""
    deal_id: str
    current_version: int = 0
    amendments: list[AmendmentRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "deal_id": self.deal_id,
            "current_version": self.current_version,
            "amendments": [a.to_dict() for a in self.amendments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "VersionChain":
        chain = cls(
            deal_id=d["deal_id"],
            current_version=d.get("current_version", 0),
        )
        chain.amendments = [
            AmendmentRecord.from_dict(a) for a in d.get("amendments", [])
        ]
        return chain


def snapshot_original(
    deal_path: Path,
    extractions: dict[str, list[dict]],
    deal_id: str = "",
) -> Path:
    """
    Save a snapshot of original extractions before any amendments.

    Args:
        deal_path: Deal directory path
        extractions: Original extraction data
        deal_id: Deal identifier

    Returns:
        Path to snapshot file
    """
    versions_dir = Path(deal_path) / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = versions_dir / "v0_original.json"
    snapshot_data = {
        "deal_id": deal_id,
        "version": 0,
        "label": "original",
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "extractions": extractions,
    }

    snapshot_path.write_text(
        json.dumps(snapshot_data, indent=2, default=str),
        encoding="utf-8",
    )

    # Initialize version chain
    chain = VersionChain(deal_id=deal_id, current_version=0)
    _save_version_chain(chain, deal_path)

    return snapshot_path


def apply_amendment(
    deal_path: Path,
    amendment_description: str,
    changes: dict[str, Any],
    affected_sections: list[str],
    source_document: str = "",
    applied_by: str = "system",
) -> AmendmentRecord:
    """
    Apply an amendment to the deal, creating a new version.

    Args:
        deal_path: Deal directory path
        amendment_description: Description of the amendment
        changes: Dict of changes to apply (section → updated items)
        affected_sections: List of affected section names
        source_document: Source document for the amendment
        applied_by: Agent/user who applied it

    Returns:
        AmendmentRecord for the applied amendment
    """
    deal_path = Path(deal_path)
    chain = _load_version_chain(deal_path)

    new_version = chain.current_version + 1
    deal_id = chain.deal_id

    # Create amendment record
    record = AmendmentRecord(
        amendment_id=f"AMD-{deal_id}-{new_version:03d}",
        deal_id=deal_id,
        version=new_version,
        description=amendment_description,
        affected_sections=affected_sections,
        changes=changes,
        applied_at=datetime.now(timezone.utc).isoformat(),
        applied_by=applied_by,
        source_document=source_document,
    )

    # Load current version's extractions
    current_extractions = get_active_version(deal_path)

    # Apply changes to create new version
    new_extractions = _merge_changes(current_extractions, changes)

    # Save new version snapshot
    versions_dir = deal_path / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = versions_dir / f"v{new_version}_{_slugify(amendment_description)}.json"
    snapshot_data = {
        "deal_id": deal_id,
        "version": new_version,
        "label": amendment_description,
        "snapshot_at": record.applied_at,
        "parent_version": chain.current_version,
        "amendment": record.to_dict(),
        "extractions": new_extractions,
    }

    snapshot_path.write_text(
        json.dumps(snapshot_data, indent=2, default=str),
        encoding="utf-8",
    )

    # Update chain
    chain.amendments.append(record)
    chain.current_version = new_version
    _save_version_chain(chain, deal_path)

    return record


def get_active_version(deal_path: Path) -> dict[str, list[dict]]:
    """
    Get the extractions from the current active version.

    Args:
        deal_path: Deal directory path

    Returns:
        Current version's extractions dict
    """
    deal_path = Path(deal_path)
    chain = _load_version_chain(deal_path)

    versions_dir = deal_path / "versions"

    # Find the snapshot for current version
    for f in sorted(versions_dir.glob(f"v{chain.current_version}_*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("extractions", {})

    # Fallback: try v0
    v0_path = versions_dir / "v0_original.json"
    if v0_path.exists():
        data = json.loads(v0_path.read_text(encoding="utf-8"))
        return data.get("extractions", {})

    return {}


def get_version_chain(deal_path: Path) -> VersionChain:
    """Get the full version chain for a deal."""
    return _load_version_chain(deal_path)


def get_version_snapshot(deal_path: Path, version: int) -> dict:
    """Get snapshot data for a specific version."""
    versions_dir = Path(deal_path) / "versions"

    for f in sorted(versions_dir.glob(f"v{version}_*.json")):
        return json.loads(f.read_text(encoding="utf-8"))

    raise FileNotFoundError(f"Version {version} not found in {deal_path}")


def diff_versions(
    deal_path: Path,
    version_a: int,
    version_b: int,
) -> dict[str, Any]:
    """
    Compare two versions of a deal's extractions.

    Args:
        deal_path: Deal directory path
        version_a: First version number
        version_b: Second version number

    Returns:
        Dict with added, removed, modified items per section
    """
    snap_a = get_version_snapshot(deal_path, version_a)
    snap_b = get_version_snapshot(deal_path, version_b)

    ext_a = snap_a.get("extractions", {})
    ext_b = snap_b.get("extractions", {})

    diff: dict[str, Any] = {
        "version_a": version_a,
        "version_b": version_b,
        "sections": {},
    }

    all_sections = set(ext_a.keys()) | set(ext_b.keys())

    for section in sorted(all_sections):
        items_a = {
            _item_key(i): i for i in ext_a.get(section, [])
        }
        items_b = {
            _item_key(i): i for i in ext_b.get(section, [])
        }

        added = [k for k in items_b if k not in items_a]
        removed = [k for k in items_a if k not in items_b]
        modified = [
            k for k in items_a
            if k in items_b and items_a[k] != items_b[k]
        ]

        if added or removed or modified:
            diff["sections"][section] = {
                "added": added,
                "removed": removed,
                "modified": modified,
            }

    return diff


# ── Internal Helpers ──────────────────────────────────────────

def _load_version_chain(deal_path: Path) -> VersionChain:
    """Load version chain from disk."""
    chain_path = Path(deal_path) / "versions" / "version_chain.json"
    if not chain_path.exists():
        return VersionChain(deal_id=deal_path.name)
    data = json.loads(chain_path.read_text(encoding="utf-8"))
    return VersionChain.from_dict(data)


def _save_version_chain(chain: VersionChain, deal_path: Path) -> None:
    """Save version chain to disk."""
    chain_path = Path(deal_path) / "versions" / "version_chain.json"
    chain_path.parent.mkdir(parents=True, exist_ok=True)
    chain_path.write_text(
        json.dumps(chain.to_dict(), indent=2),
        encoding="utf-8",
    )


def _merge_changes(
    current: dict[str, list[dict]],
    changes: dict[str, Any],
) -> dict[str, list[dict]]:
    """Merge amendment changes into current extractions."""
    result = copy.deepcopy(current)

    for section, section_changes in changes.items():
        if isinstance(section_changes, list):
            # Replace entire section
            result[section] = section_changes
        elif isinstance(section_changes, dict):
            # Merge at item level
            action = section_changes.get("action", "replace")
            items = section_changes.get("items", [])

            if action == "replace":
                result[section] = items
            elif action == "add":
                existing = result.get(section, [])
                existing.extend(items)
                result[section] = existing
            elif action == "remove":
                remove_ids = {i.get("id", "") for i in items}
                existing = result.get(section, [])
                result[section] = [
                    i for i in existing
                    if i.get("id", "") not in remove_ids
                ]
            elif action == "update":
                existing_map = {
                    _item_key(i): i for i in result.get(section, [])
                }
                for item in items:
                    key = _item_key(item)
                    if key in existing_map:
                        existing_map[key].update(item)
                    else:
                        existing_map[key] = item
                result[section] = list(existing_map.values())

    return result


def _item_key(item: dict) -> str:
    """Get a stable key for an extraction item."""
    return item.get("id", item.get("name", item.get("term", str(hash(json.dumps(item, sort_keys=True, default=str))))))


def _slugify(text: str) -> str:
    """Simple slugify for filenames."""
    import re
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[\s_]+', '_', slug)
    return slug[:50].strip('_')
