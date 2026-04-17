"""Lensfun database parser for lens correction support queries.

Reads the Lensfun XML database to determine whether a camera/lens combination
has calibration data available for distortion, vignetting, and TCA correction.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

logger = logging.getLogger("rawtherapee_mcp")


def _normalize(text: str) -> str:
    return text.strip().lower()


def _load_database(lensfun_dir: Path) -> list[ET.Element]:
    """Load all XML files in the Lensfun database directory.

    Returns a flat list of root elements from each XML file found.
    """
    roots: list[ET.Element] = []
    for xml_file in sorted(lensfun_dir.rglob("*.xml")):
        try:
            tree = ET.parse(xml_file)  # noqa: S314
            roots.append(tree.getroot())
        except ET.ParseError:
            logger.debug("Skipping malformed Lensfun XML: %s", xml_file)
    return roots


def _find_camera(
    roots: list[ET.Element],
    make: str,
    model: str,
) -> ET.Element | None:
    """Find a <camera> element matching the given make and model."""
    make_n = _normalize(make)
    model_n = _normalize(model)

    for root in roots:
        for camera in root.iter("camera"):
            cam_make = camera.findtext("maker", "")
            cam_model = camera.findtext("model", "")
            if _normalize(cam_make) == make_n and _normalize(cam_model) == model_n:
                return camera

    return None


def _find_lenses(
    roots: list[ET.Element],
    lens_model: str,
) -> list[ET.Element]:
    """Find <lens> elements whose name contains the search string (case-insensitive)."""
    lens_n = _normalize(lens_model)
    matches: list[ET.Element] = []

    for root in roots:
        for lens in root.iter("lens"):
            name = lens.findtext("model", "")
            if lens_n in _normalize(name):
                matches.append(lens)

    return matches


def _calibrations_available(lens: ET.Element) -> dict[str, bool]:
    """Report which calibration types are present in a <lens> element."""
    calib = lens.find("calibration")
    if calib is None:
        return {"distortion": False, "vignetting": False, "tca": False}
    return {
        "distortion": calib.find("distortion") is not None,
        "vignetting": calib.find("vignetting") is not None,
        "tca": calib.find("tca") is not None,
    }


def check_lens_support(
    lensfun_dir: Path,
    camera_make: str | None = None,
    camera_model: str | None = None,
    lens_model: str | None = None,
) -> dict[str, Any]:
    """Query the Lensfun database for lens and camera support.

    Args:
        lensfun_dir: Path to the directory containing Lensfun XML files.
        camera_make: Camera manufacturer (e.g. "Canon"). Optional.
        camera_model: Camera model (e.g. "Canon EOS 5D Mark IV"). Optional.
        lens_model: Lens model string to search for (e.g. "EF135mm"). Optional.

    Returns:
        Dict with keys: camera_found, lens_found, corrections_available,
        matched_lens_name, recommendation.
    """
    if not lensfun_dir.is_dir():
        return {
            "error": f"Lensfun database directory not found: {lensfun_dir}",
            "suggestion": "Set RT_LENSFUN_DIR to the directory containing Lensfun XML files.",
        }

    roots = _load_database(lensfun_dir)
    if not roots:
        return {
            "error": f"No Lensfun XML files found in {lensfun_dir}",
            "suggestion": "Verify the Lensfun database is installed.",
        }

    result: dict[str, Any] = {
        "lensfun_dir": str(lensfun_dir),
        "camera_found": False,
        "lens_found": False,
        "matched_lens_name": None,
        "corrections_available": {"distortion": False, "vignetting": False, "tca": False},
        "recommendation": None,
    }

    # Camera lookup
    if camera_make and camera_model:
        cam = _find_camera(roots, camera_make, camera_model)
        result["camera_found"] = cam is not None

    # Lens lookup
    if lens_model:
        lenses = _find_lenses(roots, lens_model)
        if lenses:
            result["lens_found"] = True
            best = lenses[0]
            result["matched_lens_name"] = best.findtext("model", "")
            result["corrections_available"] = _calibrations_available(best)

    # Build recommendation
    if result["lens_found"] and result["corrections_available"].get("distortion"):
        result["recommendation"] = "Use mode='auto' for automatic Lensfun correction."
    elif result["lens_found"]:
        result["recommendation"] = "Lens found but limited calibration data. Check the Lensfun database for updates."
    elif lens_model:
        result["recommendation"] = "Lens not found in Lensfun database. Consider using an Adobe LCP profile instead."
    else:
        result["recommendation"] = "Provide camera_make, camera_model, or lens_model to check support."

    return result
