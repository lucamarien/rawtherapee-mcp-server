"""EXIF metadata read, strip, and write operations for exported images.

Uses piexif for lossless EXIF manipulation (no JPEG recompression).
Reads are delegated to the existing exif_reader module where possible.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import piexif  # type: ignore[import-not-found]
import piexif.helper  # type: ignore[import-not-found]

logger = logging.getLogger("rawtherapee_mcp")

# piexif IFD tag constants
_GPS = piexif.GPSIFD
_IMG = piexif.ImageIFD
_EXIF = piexif.ExifIFD


def _load_exif(file_path: Path) -> dict[str, Any]:
    """Load piexif EXIF dict from a JPEG file."""
    try:
        return dict(piexif.load(str(file_path)))
    except Exception as exc:
        msg = f"Cannot load EXIF from {file_path}: {exc}"
        raise ValueError(msg) from exc


def _sanitize_exif_for_dump(exif_dict: dict[str, Any]) -> dict[str, Any]:
    """Remove tags that piexif cannot serialize.

    piexif.load() reads all tags (including unknown ones), but piexif.dump()
    only handles tags in its internal TAGS dict. Unsupported tags must be
    removed before dumping to avoid KeyError.
    """
    # Tags piexif.dump cannot handle (not in its TAGS table).
    # Determined empirically from piexif source / known-unsupported list.
    _UNSUPPORTED_EXIF_TAGS = frozenset(
        {
            piexif.ExifIFD.CameraOwnerName,  # 0xA430
        }
    )

    sanitized = dict(exif_dict)
    exif_ifd = sanitized.get("Exif")
    if isinstance(exif_ifd, dict):
        cleaned_exif = {k: v for k, v in exif_ifd.items() if k not in _UNSUPPORTED_EXIF_TAGS}
        sanitized["Exif"] = cleaned_exif
    return sanitized


def _save_exif(file_path: Path, output_path: Path, exif_dict: dict[str, Any]) -> None:
    """Dump and insert EXIF bytes into a JPEG, optionally writing to output_path."""
    clean = _sanitize_exif_for_dump(exif_dict)
    exif_bytes = piexif.dump(clean)
    target = str(output_path)
    if output_path == file_path:
        piexif.insert(exif_bytes, str(file_path))
    else:
        import shutil

        shutil.copy2(str(file_path), target)
        piexif.insert(exif_bytes, target)


def strip_metadata(
    file_path: Path,
    output_path: Path,
    *,
    strip_gps: bool = True,
    strip_camera_serial: bool = True,
    strip_lens_serial: bool = True,
    strip_software: bool = False,
    strip_owner: bool = False,
    strip_all: bool = False,
    keep_copyright: bool = True,
    keep_orientation: bool = True,
) -> dict[str, Any]:
    """Strip selected EXIF metadata from a JPEG file.

    Uses piexif.insert() to rewrite only the APP1 EXIF segment,
    leaving JPEG image data (DCT) completely untouched.

    Args:
        file_path: Source JPEG file.
        output_path: Destination file (same as file_path for in-place editing).
        strip_gps: Remove GPS IFD.
        strip_camera_serial: Remove BodySerialNumber tag.
        strip_lens_serial: Remove LensSerialNumber tag.
        strip_software: Remove Software tag.
        strip_owner: Remove CameraOwnerName tag.
        strip_all: Remove everything except orientation and optionally copyright.
        keep_copyright: Preserve Copyright tag even when strip_all=True.
        keep_orientation: Preserve Orientation tag (important for display).

    Returns:
        Dict with stripped/preserved tag lists and file sizes.
    """
    size_before = file_path.stat().st_size

    exif_dict = _load_exif(file_path)

    stripped: list[str] = []
    preserved: list[str] = []

    if strip_all:
        orientation = exif_dict.get("0th", {}).get(_IMG.Orientation, 1)
        copyright_val = exif_dict.get("0th", {}).get(_IMG.Copyright, b"") if keep_copyright else b""

        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}}
        stripped.extend(["GPS", "CameraSerialNumber", "LensSerialNumber", "Software", "CameraOwnerName"])

        if keep_orientation:
            exif_dict["0th"][_IMG.Orientation] = orientation
            preserved.append("Orientation")
        if keep_copyright and copyright_val:
            exif_dict["0th"][_IMG.Copyright] = copyright_val
            preserved.append("Copyright")
    else:
        if strip_gps:
            if exif_dict.get("GPS"):
                exif_dict["GPS"] = {}
                stripped.append("GPS")
            else:
                preserved.append("GPS (absent)")
        if strip_camera_serial:
            if exif_dict.get("Exif", {}).get(_EXIF.BodySerialNumber) is not None:
                del exif_dict["Exif"][_EXIF.BodySerialNumber]
                stripped.append("CameraSerialNumber")
        if strip_lens_serial:
            if exif_dict.get("Exif", {}).get(_EXIF.LensSerialNumber) is not None:
                del exif_dict["Exif"][_EXIF.LensSerialNumber]
                stripped.append("LensSerialNumber")
        if strip_software:
            if exif_dict.get("0th", {}).get(_IMG.Software) is not None:
                del exif_dict["0th"][_IMG.Software]
                stripped.append("Software")
        if strip_owner:
            if exif_dict.get("Exif", {}).get(_EXIF.CameraOwnerName) is not None:
                del exif_dict["Exif"][_EXIF.CameraOwnerName]
                stripped.append("CameraOwnerName")

    _save_exif(file_path, output_path, exif_dict)
    size_after = output_path.stat().st_size

    return {
        "file_path": str(output_path),
        "stripped": stripped,
        "preserved": preserved,
        "file_size_before": size_before,
        "file_size_after": size_after,
    }


def set_metadata(
    file_path: Path,
    output_path: Path,
    *,
    copyright: str | None = None,
    artist: str | None = None,
    description: str | None = None,
    keywords: list[str] | None = None,
) -> dict[str, Any]:
    """Write copyright, artist, description and keywords to a JPEG file.

    Args:
        file_path: Source JPEG file.
        output_path: Destination file (same as file_path for in-place editing).
        copyright: Copyright string e.g. "© 2026 Luca Marien".
        artist: Artist/photographer name.
        description: Image description / caption.
        keywords: List of keyword strings (written as XPKeywords UTF-16LE).

    Returns:
        Dict with the fields that were written.
    """
    exif_dict = _load_exif(file_path)

    written: list[str] = []

    if copyright is not None:
        exif_dict["0th"][_IMG.Copyright] = copyright.encode("utf-8")
        written.append("Copyright")
    if artist is not None:
        exif_dict["0th"][_IMG.Artist] = artist.encode("utf-8")
        written.append("Artist")
    if description is not None:
        exif_dict["0th"][_IMG.ImageDescription] = description.encode("utf-8")
        written.append("ImageDescription")
    if keywords is not None:
        # XPKeywords: UTF-16LE encoded, semicolon-separated, null-terminated
        kw_str = ";".join(keywords)
        exif_dict["0th"][_IMG.XPKeywords] = (kw_str + "\x00").encode("utf-16-le")
        written.append("XPKeywords")

    _save_exif(file_path, output_path, exif_dict)

    return {
        "file_path": str(output_path),
        "written": written,
    }


def _decode_bytes(value: object) -> str | None:
    """Decode a bytes EXIF value to a string, stripping null bytes."""
    if isinstance(value, bytes):
        for enc in ("utf-8", "latin-1"):
            try:
                return value.rstrip(b"\x00").decode(enc)
            except UnicodeDecodeError:
                continue
    if isinstance(value, str):
        return value
    return None


def _decode_rational(value: object) -> float | None:
    """Decode a (numerator, denominator) rational tuple to a float."""
    if isinstance(value, tuple) and len(value) == 2 and value[1] != 0:
        num, den = value[0], value[1]
        if isinstance(num, (int, float)) and isinstance(den, (int, float)):
            return float(num) / float(den)
    return None


def _gps_dms_to_decimal(dms: tuple[Any, ...], ref: bytes) -> float | None:
    """Convert GPS DMS rational tuple to signed decimal degrees."""
    try:
        deg = _decode_rational(dms[0])
        mnt = _decode_rational(dms[1])
        sec = _decode_rational(dms[2])
        if deg is None or mnt is None or sec is None:
            return None
        decimal = deg + mnt / 60.0 + sec / 3600.0
        if ref in (b"S", b"W", "S", "W"):
            decimal = -decimal
        return decimal
    except (IndexError, TypeError):
        return None


def inspect_metadata(file_path: Path) -> dict[str, Any]:
    """Inspect all EXIF metadata in a JPEG file and classify by sensitivity.

    Args:
        file_path: Path to the JPEG (or TIFF) file to inspect.

    Returns:
        Dict with sensitive, technical, processing, rights, and
        privacy_recommendations sections.
    """
    try:
        exif_dict = _load_exif(file_path)
    except ValueError as exc:
        return {"error": str(exc)}

    ifd0 = exif_dict.get("0th", {})
    exif_ifd = exif_dict.get("Exif", {})
    gps_ifd = exif_dict.get("GPS", {})

    # GPS coordinates
    gps_lat_dms = gps_ifd.get(_GPS.GPSLatitude)
    gps_lat_ref = gps_ifd.get(_GPS.GPSLatitudeRef, b"")
    gps_lon_dms = gps_ifd.get(_GPS.GPSLongitude)
    gps_lon_ref = gps_ifd.get(_GPS.GPSLongitudeRef, b"")
    gps_alt_r = gps_ifd.get(_GPS.GPSAltitude)

    gps_lat = _gps_dms_to_decimal(gps_lat_dms, gps_lat_ref) if gps_lat_dms else None
    gps_lon = _gps_dms_to_decimal(gps_lon_dms, gps_lon_ref) if gps_lon_dms else None
    gps_alt = _decode_rational(gps_alt_r) if gps_alt_r else None

    gps_str: str | None = None
    if gps_lat is not None and gps_lon is not None:
        lat_dir = "N" if gps_lat >= 0 else "S"
        lon_dir = "E" if gps_lon >= 0 else "W"
        gps_str = f"{abs(gps_lat):.4f}°{lat_dir}, {abs(gps_lon):.4f}°{lon_dir}"

    # Serial numbers
    body_serial = _decode_bytes(exif_ifd.get(_EXIF.BodySerialNumber))
    lens_serial = _decode_bytes(exif_ifd.get(_EXIF.LensSerialNumber))
    owner = _decode_bytes(exif_ifd.get(_EXIF.CameraOwnerName))

    # Technical
    make = _decode_bytes(ifd0.get(_IMG.Make))
    model = _decode_bytes(ifd0.get(_IMG.Model))
    camera = f"{make} {model}".strip() if (make or model) else None

    lens_make = _decode_bytes(exif_ifd.get(_EXIF.LensMake))
    lens_model_str = _decode_bytes(exif_ifd.get(_EXIF.LensModel))
    lens = f"{lens_make} {lens_model_str}".strip() if (lens_make or lens_model_str) else lens_model_str

    iso_val = exif_ifd.get(_EXIF.ISOSpeedRatings)
    iso = int(iso_val) if iso_val is not None else None

    aperture_r = exif_ifd.get(_EXIF.FNumber)
    aperture_f = _decode_rational(aperture_r)
    aperture = f"f/{aperture_f:.1f}" if aperture_f else None

    shutter_r = exif_ifd.get(_EXIF.ExposureTime)
    shutter_f = _decode_rational(shutter_r)
    if shutter_f and shutter_f < 1:
        shutter = f"1/{round(1 / shutter_f)}"
    elif shutter_f:
        shutter = f"{shutter_f:.1f}s"
    else:
        shutter = None

    fl_r = exif_ifd.get(_EXIF.FocalLength)
    fl_f = _decode_rational(fl_r)
    focal_length = f"{fl_f:.0f}mm" if fl_f else None

    datetime_orig = _decode_bytes(exif_ifd.get(_EXIF.DateTimeOriginal))
    datetime_img = _decode_bytes(ifd0.get(_IMG.DateTime))

    # Processing
    software = _decode_bytes(ifd0.get(_IMG.Software))
    datetime_digitized = _decode_bytes(exif_ifd.get(_EXIF.DateTimeDigitized))

    # Rights
    copyright_val = _decode_bytes(ifd0.get(_IMG.Copyright))
    artist_val = _decode_bytes(ifd0.get(_IMG.Artist))

    # Privacy recommendations
    recommendations: list[str] = []
    if gps_str:
        recommendations.append("GPS coordinates present — consider stripping for public sharing.")
    if body_serial:
        recommendations.append("Camera serial number present — can be used for device tracking.")
    if lens_serial:
        recommendations.append("Lens serial number present.")
    if owner:
        recommendations.append("Camera owner name present in EXIF.")
    if not recommendations:
        recommendations.append("No sensitive metadata detected.")

    return {
        "file_path": str(file_path),
        "sensitive": {
            "gps_coordinates": gps_str,
            "gps_altitude": f"{gps_alt:.1f}m" if gps_alt is not None else None,
            "camera_serial": body_serial,
            "lens_serial": lens_serial,
            "owner_name": owner,
        },
        "technical": {
            "camera": camera,
            "lens": lens,
            "iso": iso,
            "aperture": aperture,
            "shutter": shutter,
            "focal_length": focal_length,
            "datetime": datetime_orig or datetime_img,
        },
        "processing": {
            "software": software,
            "processing_date": datetime_digitized,
        },
        "rights": {
            "copyright": copyright_val,
            "artist": artist_val,
        },
        "privacy_recommendations": recommendations,
    }
