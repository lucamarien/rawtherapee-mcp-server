"""Profile variant system: parent/child PP3 relationships with JSON-backed storage.

Variants are stored as:
  <custom_templates_dir>/profile_hierarchy.json  — index of parent→[variant] relationships
  <custom_templates_dir>/_generated/<name>.pp3   — merged (parent + overrides) PP3 file

The generated PP3 files are standalone and fully compatible with process_raw and
batch_process — no special handling needed in the RT CLI wrapper.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rawtherapee_mcp.pp3_parser import PP3Profile

logger = logging.getLogger("rawtherapee_mcp")

_HIERARCHY_FILENAME = "profile_hierarchy.json"
_GENERATED_DIRNAME = "_generated"


def _hierarchy_path(custom_templates_dir: Path) -> Path:
    return custom_templates_dir / _HIERARCHY_FILENAME


def _generated_dir(custom_templates_dir: Path) -> Path:
    d = custom_templates_dir / _GENERATED_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_hierarchy(custom_templates_dir: Path) -> dict[str, Any]:
    """Load the profile hierarchy index from disk.

    Returns an empty dict if the file does not exist yet.
    """
    path = _hierarchy_path(custom_templates_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read profile hierarchy: %s", exc)
        return {}


def save_hierarchy(custom_templates_dir: Path, hierarchy: dict[str, Any]) -> None:
    """Persist the hierarchy index to disk."""
    path = _hierarchy_path(custom_templates_dir)
    path.write_text(json.dumps(hierarchy, indent=2, ensure_ascii=False), encoding="utf-8")


def _apply_raw_overrides(profile: PP3Profile, overrides: dict[str, dict[str, str]]) -> None:
    """Apply section→{key: value} overrides directly onto a PP3Profile."""
    for section, keys in overrides.items():
        for key, value in keys.items():
            profile.set(section, key, str(value))


def _variant_pp3_path(custom_templates_dir: Path, variant_name: str) -> Path:
    return _generated_dir(custom_templates_dir) / f"{variant_name}.pp3"


def create_variant(
    custom_templates_dir: Path,
    parent_pp3_path: Path,
    variant_name: str,
    overrides: dict[str, dict[str, str]],
    description: str | None = None,
) -> dict[str, Any]:
    """Create a new profile variant by merging parent PP3 with overrides.

    Args:
        custom_templates_dir: Root directory for templates and hierarchy state.
        parent_pp3_path: Absolute path to the parent PP3 file.
        variant_name: Name for the new variant (used as filename stem).
        overrides: Raw PP3 section→{key: value} pairs to override in parent.
        description: Optional human-readable description.

    Returns:
        Dict describing the created variant.
    """
    parent = PP3Profile()
    parent.load(parent_pp3_path)

    variant = parent.copy()
    _apply_raw_overrides(variant, overrides)

    out_path = _variant_pp3_path(custom_templates_dir, variant_name)
    variant.save(out_path)

    hierarchy = load_hierarchy(custom_templates_dir)
    parent_name = parent_pp3_path.stem

    if parent_name not in hierarchy:
        hierarchy[parent_name] = {
            "pp3_path": str(parent_pp3_path),
            "variants": {},
        }

    hierarchy[parent_name]["variants"][variant_name] = {
        "pp3_path": str(out_path),
        "overrides": overrides,
        "description": description,
    }
    save_hierarchy(custom_templates_dir, hierarchy)

    return {
        "variant_name": variant_name,
        "parent": parent_name,
        "parent_pp3_path": str(parent_pp3_path),
        "effective_profile_path": str(out_path),
        "overrides": overrides,
        "description": description,
    }


def list_variants(
    custom_templates_dir: Path,
    parent_profile: str | None = None,
) -> dict[str, Any]:
    """List all profile variants, optionally filtered by parent name.

    Args:
        custom_templates_dir: Root directory for templates and hierarchy state.
        parent_profile: Optional parent name filter.

    Returns:
        Dict mapping parent names to their variant info lists.
    """
    hierarchy = load_hierarchy(custom_templates_dir)

    if parent_profile is not None:
        if parent_profile not in hierarchy:
            return {"parent": parent_profile, "variants": [], "total": 0}
        entry = hierarchy[parent_profile]
        variants = [
            {
                "variant_name": vname,
                "effective_profile_path": vdata.get("pp3_path"),
                "overrides": vdata.get("overrides", {}),
                "description": vdata.get("description"),
            }
            for vname, vdata in entry.get("variants", {}).items()
        ]
        return {"parent": parent_profile, "variants": variants, "total": len(variants)}

    result: dict[str, Any] = {}
    total = 0
    for pname, entry in hierarchy.items():
        variants = [
            {
                "variant_name": vname,
                "effective_profile_path": vdata.get("pp3_path"),
                "overrides": vdata.get("overrides", {}),
                "description": vdata.get("description"),
            }
            for vname, vdata in entry.get("variants", {}).items()
        ]
        result[pname] = {"variants": variants, "count": len(variants)}
        total += len(variants)

    return {"profiles": result, "total_variants": total}


def propagate_to_variants(
    custom_templates_dir: Path,
    parent_name: str,
    updated_parent_path: Path,
) -> list[dict[str, Any]]:
    """Regenerate all variants of a parent after the parent PP3 has been updated.

    Args:
        custom_templates_dir: Root directory for templates and hierarchy state.
        parent_name: The name (stem) of the parent profile.
        updated_parent_path: Path to the updated parent PP3.

    Returns:
        List of dicts describing each regenerated variant (or errors).
    """
    hierarchy = load_hierarchy(custom_templates_dir)
    entry = hierarchy.get(parent_name, {})
    variants_map: dict[str, Any] = entry.get("variants", {})

    results: list[dict[str, Any]] = []
    parent = PP3Profile()
    parent.load(updated_parent_path)

    for vname, vdata in variants_map.items():
        overrides: dict[str, dict[str, str]] = vdata.get("overrides", {})
        try:
            variant = parent.copy()
            _apply_raw_overrides(variant, overrides)
            out_path = _variant_pp3_path(custom_templates_dir, vname)
            variant.save(out_path)
            results.append({"variant_name": vname, "status": "regenerated", "path": str(out_path)})
        except Exception as exc:
            results.append({"variant_name": vname, "status": "error", "error": str(exc)})

    return results
