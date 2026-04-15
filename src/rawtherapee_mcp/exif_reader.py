"""EXIF metadata extraction from RAW image files.

Uses the exifread library to parse EXIF data without loading the full image.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

import exifread

logger = logging.getLogger("rawtherapee_mcp")


def read_exif_data(file_path: Path) -> dict[str, str]:
    """Read EXIF metadata from a RAW or image file.

    Args:
        file_path: Path to the image file.

    Returns:
        Dict with extracted EXIF fields, or error dict on failure.
    """
    try:
        with file_path.open("rb") as f:
            tags = exifread.process_file(f, details=False)
    except OSError as exc:
        return {"error": f"Failed to read file: {exc}"}

    # Some cameras use Image-level tags instead of EXIF-level for dimensions
    width_val = tags.get("EXIF ExifImageWidth") or tags.get("Image ImageWidth", "")
    height_val = tags.get("EXIF ExifImageLength") or tags.get("Image ImageLength", "")

    return {
        "camera_make": str(tags.get("Image Make", "")),
        "camera_model": str(tags.get("Image Model", "")),
        "lens_model": str(tags.get("EXIF LensModel", "")),
        "iso": str(tags.get("EXIF ISOSpeedRatings", "")),
        "aperture": str(tags.get("EXIF FNumber", "")),
        "shutter_speed": str(tags.get("EXIF ExposureTime", "")),
        "focal_length": str(tags.get("EXIF FocalLength", "")),
        "white_balance": str(tags.get("EXIF WhiteBalance", "")),
        "datetime": str(tags.get("EXIF DateTimeOriginal", "")),
        "width": str(width_val),
        "height": str(height_val),
        "gps_latitude": str(tags.get("GPS GPSLatitude", "")),
        "gps_longitude": str(tags.get("GPS GPSLongitude", "")),
        "orientation": str(tags.get("Image Orientation", "")),
    }


def _get_raw_dimensions_from_tiff_ifds(path: Path) -> tuple[int, int]:
    """Read ALL TIFF IFDs and return the largest width/height found.

    Most RAW formats (CR2, NEF, ARW, DNG, etc.) are TIFF-based. The first
    IFD often contains thumbnail dimensions; the actual RAW sensor dimensions
    are usually in a later IFD. This scans all IFDs and picks the largest.

    Args:
        path: Path to the RAW/TIFF file.

    Returns:
        Tuple of (width, height) from the largest IFD, or (0, 0) on failure.
    """
    try:
        with path.open("rb") as f:
            byte_order = f.read(2)
            if byte_order == b"II":
                endian = "<"
            elif byte_order == b"MM":
                endian = ">"
            else:
                return (0, 0)

            magic = struct.unpack(f"{endian}H", f.read(2))[0]
            if magic != 42:
                return (0, 0)

            max_width = 0
            max_height = 0

            ifd_offset = struct.unpack(f"{endian}I", f.read(4))[0]

            # Prevent infinite loops from malformed files
            visited: set[int] = set()
            while ifd_offset != 0 and ifd_offset not in visited:
                visited.add(ifd_offset)
                f.seek(ifd_offset)

                raw = f.read(2)
                if len(raw) < 2:
                    break
                num_entries = struct.unpack(f"{endian}H", raw)[0]

                ifd_width = 0
                ifd_height = 0

                for _ in range(num_entries):
                    entry = f.read(12)
                    if len(entry) < 12:
                        break

                    tag = struct.unpack(f"{endian}H", entry[0:2])[0]
                    value_type = struct.unpack(f"{endian}H", entry[2:4])[0]

                    if value_type == 3:  # SHORT
                        value = struct.unpack(f"{endian}H", entry[8:10])[0]
                    elif value_type == 4:  # LONG
                        value = struct.unpack(f"{endian}I", entry[8:12])[0]
                    else:
                        continue

                    if tag == 256:  # ImageWidth
                        ifd_width = value
                    elif tag == 257:  # ImageLength
                        ifd_height = value

                if ifd_width > max_width or ifd_height > max_height:
                    max_width = max(max_width, ifd_width)
                    max_height = max(max_height, ifd_height)

                # Read next IFD offset (immediately after directory entries)
                raw = f.read(4)
                if len(raw) < 4:
                    break
                ifd_offset = struct.unpack(f"{endian}I", raw)[0]

            return (max_width, max_height)

    except (OSError, struct.error) as exc:
        logger.debug("TIFF IFD parsing failed for %s: %s", path, exc)
        return (0, 0)


def get_effective_dimensions(file_path: Path) -> tuple[int, int]:
    """Get the effective (post-orientation) image dimensions.

    Reads EXIF data and applies the orientation tag to return the display
    dimensions. RawTherapee applies crop after orientation, so these are
    the dimensions to use for crop calculations.

    Falls back to TIFF IFD parsing when EXIF dimension tags are missing
    (common for Canon CR2 and other TIFF-based RAW formats).

    Args:
        file_path: Path to the image file.

    Returns:
        Tuple of (width, height) in display orientation. Returns (0, 0) on failure.
    """
    resolved = file_path.resolve()
    exif = read_exif_data(resolved)
    if "error" in exif:
        logger.warning("EXIF read failed for %s: %s", resolved, exif.get("error"))
        return (0, 0)

    try:
        # Handle both int and float string representations (e.g. "6720" or "6720.0")
        width = int(float(exif["width"])) if exif["width"] else 0
        height = int(float(exif["height"])) if exif["height"] else 0
    except (ValueError, KeyError):
        logger.warning(
            "Could not parse dimensions from EXIF: width=%r, height=%r",
            exif.get("width"),
            exif.get("height"),
        )
        width, height = 0, 0

    # Fallback: parse TIFF IFDs for RAW files when EXIF dimensions are missing
    if width == 0 or height == 0:
        tiff_w, tiff_h = _get_raw_dimensions_from_tiff_ifds(resolved)
        if tiff_w > 0 and tiff_h > 0:
            logger.debug(
                "Using TIFF IFD dimensions for %s: %dx%d",
                resolved.name,
                tiff_w,
                tiff_h,
            )
            width, height = tiff_w, tiff_h

    if width == 0 or height == 0:
        logger.warning(
            "Could not determine dimensions for %s (EXIF and TIFF IFD both failed)",
            resolved,
        )
        return (0, 0)

    # EXIF orientations that swap width/height (90° and 270° rotations)
    orientation = exif.get("orientation", "")
    swap_orientations = {"Rotated 90 CW", "Rotated 90 CCW", "Transposed", "Transverse"}
    if orientation in swap_orientations:
        logger.debug(
            "Swapping dimensions for %s orientation: %dx%d -> %dx%d",
            orientation,
            width,
            height,
            height,
            width,
        )
        return (height, width)

    return (width, height)


def _parse_fraction_or_float(value: str) -> float:
    """Parse a string as a fraction (e.g. '14/10') or float.

    Raises:
        ValueError: If the string cannot be parsed.
        ZeroDivisionError: If the denominator is zero.
    """
    if "/" in value:
        num, den = value.split("/")
        return float(num) / float(den)
    return float(value)


def generate_recommendations(exif_data: dict[str, str]) -> dict[str, Any]:
    """Generate structured processing recommendations based on EXIF metadata.

    Analyzes camera settings (ISO, aperture, shutter speed, focal length)
    and returns actionable suggestions with both human-readable text and
    machine-readable parameter suggestions for RawTherapee.

    Args:
        exif_data: Dict from read_exif_data().

    Returns:
        Dict with ``text`` (list of readable strings),
        ``suggested_parameters`` (dict of raw PP3 section/key pairs, e.g.
        ``{"Directional Pyramid Denoising": {"Luma": "50"}}``),
        and ``warnings`` (list of short warning strings).
    """
    text: list[str] = []
    suggested_parameters: dict[str, Any] = {}
    warnings: list[str] = []

    # ISO-based noise reduction advice (PP3: Directional Pyramid Denoising)
    iso_str = exif_data.get("iso", "")
    if iso_str:
        try:
            iso = int(iso_str)
            if iso > 6400:
                text.append(
                    f"High ISO ({iso}): Use aggressive noise reduction (luminance NR 60-80, chrominance NR 40-60)"
                )
                suggested_parameters["Directional Pyramid Denoising"] = {
                    "Enabled": "true",
                    "Luma": "50",
                    "Chroma": "60",
                    "Ldetail": "40",
                }
            elif iso > 1600:
                text.append(
                    f"Moderate ISO ({iso}): Apply moderate noise reduction (luminance NR 30-50, chrominance NR 20-40)"
                )
                suggested_parameters["Directional Pyramid Denoising"] = {
                    "Enabled": "true",
                    "Luma": "30",
                    "Chroma": "40",
                    "Ldetail": "45",
                }
            elif iso > 400:
                text.append(f"ISO {iso}: Light noise reduction may help (luminance NR 10-20)")
                suggested_parameters["Directional Pyramid Denoising"] = {
                    "Enabled": "true",
                    "Luma": "15",
                    "Chroma": "25",
                    "Ldetail": "50",
                }
            else:
                text.append(f"Low ISO ({iso}): Minimal noise expected — noise reduction likely unnecessary")
                suggested_parameters["Directional Pyramid Denoising"] = {
                    "Enabled": "true",
                    "Luma": "5",
                    "Chroma": "10",
                    "Ldetail": "50",
                }
        except ValueError:
            pass

    # Aperture-based sharpening/lens correction (PP3: Sharpening, LensProfile)
    aperture_str = exif_data.get("aperture", "")
    if aperture_str:
        try:
            aperture = _parse_fraction_or_float(aperture_str)
            if aperture <= 2.0:
                text.append(f"Wide aperture (f/{aperture:.1f}): Consider lens correction for vignetting and CA")
                suggested_parameters["LensProfile"] = {"UseDistortion": "true"}
                suggested_parameters["Sharpening"] = {
                    "Enabled": "true",
                    "Amount": "100",
                    "Radius": "0.7",
                    "Threshold": "15",
                }
            elif aperture <= 5.6:
                suggested_parameters["Sharpening"] = {
                    "Enabled": "true",
                    "Amount": "130",
                    "Radius": "0.5",
                    "Threshold": "20",
                }
            elif aperture >= 11.0:
                text.append(
                    f"Narrow aperture (f/{aperture:.1f}): Watch for diffraction softening — apply capture sharpening"
                )
                suggested_parameters["Sharpening"] = {
                    "Enabled": "true",
                    "Amount": "80",
                    "Radius": "0.8",
                    "Threshold": "25",
                }
                warnings.append("Diffraction softening likely")
        except (ValueError, ZeroDivisionError):
            pass

    # Shutter speed / motion blur
    shutter_str = exif_data.get("shutter_speed", "")
    if shutter_str:
        try:
            shutter_seconds = _parse_fraction_or_float(shutter_str)
            if shutter_seconds >= 1.0:
                text.append(f"Long exposure ({shutter_str}s): Check for motion blur — may benefit from sharpening")
                warnings.append("Long exposure — check for motion blur")
            elif shutter_seconds >= 0.5:
                text.append(f"Slow shutter ({shutter_str}s): Possible camera shake — check sharpness at 100%")
                warnings.append("Possible camera shake")
        except (ValueError, ZeroDivisionError):
            pass

    # White balance
    wb_str = exif_data.get("white_balance", "")
    if wb_str:
        try:
            wb_val = int(wb_str)
            if wb_val == 0:
                text.append("Auto white balance used in-camera — consider setting WB manually for accuracy")
                warnings.append("Auto white balance — consider manual WB")
        except ValueError:
            pass

    # Focal length + lens model
    focal_str = exif_data.get("focal_length", "")
    lens_str = exif_data.get("lens_model", "")
    if focal_str:
        try:
            focal = _parse_fraction_or_float(focal_str)
            if focal <= 24:
                text.append(f"Wide-angle ({focal:.0f}mm): Enable distortion and vignetting correction")
                suggested_parameters.setdefault("LensProfile", {})["UseDistortion"] = "true"
                warnings.append("Wide-angle distortion likely")
        except (ValueError, ZeroDivisionError):
            pass

    if lens_str:
        text.append(f"Lens: {lens_str} — check if RawTherapee has a matching lens profile for automatic correction")

    if not text:
        text.append("No specific recommendations — EXIF data is limited")

    return {
        "text": text,
        "suggested_parameters": suggested_parameters,
        "warnings": warnings,
    }


def get_image_info(file_path: Path) -> dict[str, Any]:
    """Get technical information about a processed image file.

    Parses image headers directly (no Pillow dependency) to extract
    dimensions, format, and other metadata.

    Args:
        file_path: Path to a JPEG, TIFF, or PNG file.

    Returns:
        Dict with width, height, format, file_size, and bit_depth.
    """
    if not file_path.is_file():
        return {"error": f"File not found: {file_path}"}

    ext = file_path.suffix.lower()
    file_size = file_path.stat().st_size

    try:
        if ext in (".jpg", ".jpeg"):
            info = _parse_jpeg_header(file_path)
        elif ext in (".tif", ".tiff"):
            info = _parse_tiff_header(file_path)
        elif ext == ".png":
            info = _parse_png_header(file_path)
        else:
            return {
                "file_path": str(file_path),
                "file_size": file_size,
                "format": ext.lstrip("."),
                "error": "Unsupported format for dimension extraction",
            }
    except (OSError, struct.error) as exc:
        return {
            "file_path": str(file_path),
            "file_size": file_size,
            "format": ext.lstrip("."),
            "error": f"Failed to parse header: {exc}",
        }

    info["file_path"] = str(file_path)
    info["file_size"] = file_size
    return info


def _parse_jpeg_header(path: Path) -> dict[str, Any]:
    """Extract dimensions from JPEG SOF marker."""
    # Limit scan to first 1MB to avoid hanging on large files
    max_scan_bytes = 1024 * 1024

    with path.open("rb") as f:
        # Verify JPEG signature
        if f.read(2) != b"\xff\xd8":
            return {"format": "jpeg", "error": "Invalid JPEG signature"}

        while f.tell() < max_scan_bytes:
            marker = f.read(2)
            if len(marker) < 2:
                break

            if marker[0] != 0xFF:
                break

            marker_type = marker[1]

            # SOF markers (Start of Frame) contain image dimensions
            if marker_type in (0xC0, 0xC1, 0xC2, 0xC3):
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    break
                # Skip precision byte
                data = f.read(5)
                if len(data) < 5:
                    break
                precision = data[0]
                height = struct.unpack(">H", data[1:3])[0]
                width = struct.unpack(">H", data[3:5])[0]
                return {
                    "format": "jpeg",
                    "width": width,
                    "height": height,
                    "bit_depth": precision,
                }

            # Skip other markers
            if marker_type == 0xD9:  # EOI
                break
            if marker_type in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0x01):
                continue

            length_bytes = f.read(2)
            if len(length_bytes) < 2:
                break
            length = struct.unpack(">H", length_bytes)[0]
            f.seek(length - 2, 1)

    return {"format": "jpeg", "error": "Could not find SOF marker"}


def _parse_png_header(path: Path) -> dict[str, Any]:
    """Extract dimensions from PNG IHDR chunk."""
    with path.open("rb") as f:
        signature = f.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            return {"format": "png", "error": "Invalid PNG signature"}

        # Read IHDR chunk (must be first)
        _chunk_length = f.read(4)
        chunk_type = f.read(4)
        if chunk_type != b"IHDR":
            return {"format": "png", "error": "Missing IHDR chunk"}

        ihdr_data = f.read(13)
        if len(ihdr_data) < 13:
            return {"format": "png", "error": "Truncated IHDR chunk"}

        width = struct.unpack(">I", ihdr_data[0:4])[0]
        height = struct.unpack(">I", ihdr_data[4:8])[0]
        bit_depth = ihdr_data[8]
        color_type = ihdr_data[9]

        color_types = {0: "grayscale", 2: "rgb", 3: "indexed", 4: "grayscale+alpha", 6: "rgba"}

        return {
            "format": "png",
            "width": width,
            "height": height,
            "bit_depth": bit_depth,
            "color_type": color_types.get(color_type, f"unknown({color_type})"),
        }


def _parse_tiff_header(path: Path) -> dict[str, Any]:
    """Extract dimensions from TIFF header."""
    with path.open("rb") as f:
        # Read byte order
        byte_order = f.read(2)
        if byte_order == b"II":
            endian = "<"
        elif byte_order == b"MM":
            endian = ">"
        else:
            return {"format": "tiff", "error": "Invalid TIFF byte order"}

        # Verify magic number
        magic = struct.unpack(f"{endian}H", f.read(2))[0]
        if magic != 42:
            return {"format": "tiff", "error": "Invalid TIFF magic number"}

        # Read first IFD offset
        ifd_offset = struct.unpack(f"{endian}I", f.read(4))[0]
        f.seek(ifd_offset)

        # Read number of directory entries
        num_entries = struct.unpack(f"{endian}H", f.read(2))[0]

        width = 0
        height = 0
        bits_per_sample = 0

        for _ in range(num_entries):
            entry = f.read(12)
            if len(entry) < 12:
                break

            tag = struct.unpack(f"{endian}H", entry[0:2])[0]
            value_type = struct.unpack(f"{endian}H", entry[2:4])[0]
            # For SHORT (3) and LONG (4) types, value is in bytes 8-12
            if value_type == 3:  # SHORT
                value = struct.unpack(f"{endian}H", entry[8:10])[0]
            elif value_type == 4:  # LONG
                value = struct.unpack(f"{endian}I", entry[8:12])[0]
            else:
                value = 0

            if tag == 256:  # ImageWidth
                width = value
            elif tag == 257:  # ImageLength
                height = value
            elif tag == 258:  # BitsPerSample
                bits_per_sample = value

        return {
            "format": "tiff",
            "width": width,
            "height": height,
            "bit_depth": bits_per_sample,
        }
