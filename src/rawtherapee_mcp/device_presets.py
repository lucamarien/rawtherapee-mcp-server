"""Device crop/resize presets for mobile, desktop, and photo formats.

Built-in presets cover common devices and aspect ratios. Users can add
custom presets which are persisted to a JSON file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("rawtherapee_mcp")

BUILT_IN_PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "mobile": {
        "s26_ultra": {"name": "Samsung Galaxy S26 Ultra", "width": 1440, "height": 3120, "ratio": "9:19.5"},
        "s25_ultra": {"name": "Samsung Galaxy S25 Ultra", "width": 1440, "height": 3120, "ratio": "9:19.5"},
        "iphone_16_pro_max": {
            "name": "iPhone 16 Pro Max",
            "width": 1320,
            "height": 2868,
            "ratio": "~9:19.5",
        },
        "iphone_16": {"name": "iPhone 16", "width": 1179, "height": 2556, "ratio": "~9:19.5"},
        "pixel_9_pro": {"name": "Google Pixel 9 Pro", "width": 1344, "height": 2992, "ratio": "~9:20"},
        "generic_9_16": {"name": "Generic 9:16", "width": 1440, "height": 2560, "ratio": "9:16"},
        "generic_9_195": {"name": "Generic 9:19.5", "width": 1440, "height": 3120, "ratio": "9:19.5"},
    },
    "desktop": {
        "4k_uhd": {"name": "4K UHD", "width": 3840, "height": 2160, "ratio": "16:9"},
        "wqhd": {"name": "WQHD", "width": 2560, "height": 1440, "ratio": "16:9"},
        "fhd": {"name": "Full HD", "width": 1920, "height": 1080, "ratio": "16:9"},
        "ultrawide_3440": {"name": "Ultrawide", "width": 3440, "height": 1440, "ratio": "21:9"},
        "dual_4k": {"name": "Dual 4K", "width": 7680, "height": 2160, "ratio": "32:9"},
    },
    "photo_formats": {
        "photo_3_2": {"name": "3:2 Classic 35mm", "width": 6000, "height": 4000, "ratio": "3:2"},
        "photo_4_3": {"name": "4:3 Micro Four Thirds", "width": 4000, "height": 3000, "ratio": "4:3"},
        "photo_16_9": {"name": "16:9 Widescreen", "width": 6000, "height": 3375, "ratio": "16:9"},
        "photo_1_1": {"name": "1:1 Square", "width": 4000, "height": 4000, "ratio": "1:1"},
        "photo_5_4": {"name": "5:4 Large Format", "width": 5000, "height": 4000, "ratio": "5:4"},
        "photo_4_5": {"name": "4:5 Instagram Portrait", "width": 4000, "height": 5000, "ratio": "4:5"},
        "photo_2_3": {"name": "2:3 Portrait 35mm", "width": 4000, "height": 6000, "ratio": "2:3"},
    },
}

_CUSTOM_PRESETS_FILE = "device_presets.json"


def _custom_presets_path(custom_templates_dir: Path) -> Path:
    """Get the path to the custom presets JSON file."""
    return custom_templates_dir / _CUSTOM_PRESETS_FILE


def load_custom_presets(custom_templates_dir: Path) -> dict[str, dict[str, Any]]:
    """Load custom presets from JSON file.

    Args:
        custom_templates_dir: Directory containing the custom presets file.

    Returns:
        Dict of preset_id -> preset data.
    """
    path = _custom_presets_path(custom_templates_dir)
    if not path.is_file():
        return {}
    try:
        data: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load custom presets: %s", exc)
        return {}


def save_custom_presets(presets: dict[str, dict[str, Any]], custom_templates_dir: Path) -> None:
    """Save custom presets to JSON file.

    Args:
        presets: Dict of preset_id -> preset data.
        custom_templates_dir: Directory to write the file to.
    """
    path = _custom_presets_path(custom_templates_dir)
    path.write_text(json.dumps(presets, indent=2), encoding="utf-8")


def get_preset(preset_id: str, custom_templates_dir: Path) -> dict[str, Any] | None:
    """Look up a preset by ID, checking custom then built-in.

    Args:
        preset_id: The preset identifier.
        custom_templates_dir: Directory for custom presets.

    Returns:
        Preset dict with name/width/height/ratio, or None if not found.
    """
    # Check custom first
    custom = load_custom_presets(custom_templates_dir)
    if preset_id in custom:
        return custom[preset_id]

    # Check built-in categories
    for _category, presets in BUILT_IN_PRESETS.items():
        if preset_id in presets:
            return presets[preset_id]

    return None


def get_all_presets(custom_templates_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """Get all presets grouped by category.

    Args:
        custom_templates_dir: Directory for custom presets.

    Returns:
        Dict of category -> preset_id -> preset data.
    """
    result: dict[str, dict[str, dict[str, Any]]] = {}

    # Copy built-in presets
    for category, presets in BUILT_IN_PRESETS.items():
        result[category] = dict(presets)

    # Add custom presets
    custom = load_custom_presets(custom_templates_dir)
    if custom:
        result["custom"] = custom

    return result


def add_custom_preset(
    preset_id: str,
    name: str,
    width: int,
    height: int,
    category: str,
    custom_templates_dir: Path,
) -> None:
    """Add a custom device preset.

    Args:
        preset_id: Unique identifier for the preset.
        name: Human-readable display name.
        width: Target width in pixels.
        height: Target height in pixels.
        category: Category grouping (stored but informational).
        custom_templates_dir: Directory for custom presets.
    """
    presets = load_custom_presets(custom_templates_dir)
    presets[preset_id] = {
        "name": name,
        "width": width,
        "height": height,
        "category": category,
    }
    save_custom_presets(presets, custom_templates_dir)


def delete_custom_preset(preset_id: str, custom_templates_dir: Path) -> bool:
    """Delete a custom device preset.

    Args:
        preset_id: Preset ID to delete.
        custom_templates_dir: Directory for custom presets.

    Returns:
        True if deleted, False if not found.
    """
    presets = load_custom_presets(custom_templates_dir)
    if preset_id not in presets:
        return False
    del presets[preset_id]
    save_custom_presets(presets, custom_templates_dir)
    return True


def is_builtin_preset(preset_id: str) -> bool:
    """Check if a preset ID belongs to a built-in preset.

    Args:
        preset_id: The preset identifier.

    Returns:
        True if the preset is built-in.
    """
    for _category, presets in BUILT_IN_PRESETS.items():
        if preset_id in presets:
            return True
    return False
