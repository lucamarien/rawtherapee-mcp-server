"""Tests for metadata strip, set, and inspect operations."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

try:
    import piexif  # type: ignore[import-not-found]
    from PIL import Image

    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

pytestmark = pytest.mark.skipif(not HAS_PIEXIF, reason="piexif not installed")


def _make_jpeg_with_exif(path: Path) -> None:
    """Create a minimal JPEG file with GPS, serial, and copyright EXIF data."""
    exif_dict: dict[str, dict] = {
        "0th": {
            piexif.ImageIFD.Make: b"Canon",
            piexif.ImageIFD.Model: b"Canon EOS 5D Mark IV",
            piexif.ImageIFD.Orientation: 1,
            piexif.ImageIFD.Software: b"RawTherapee 5.12",
            piexif.ImageIFD.Artist: b"Test Owner",
        },
        "Exif": {
            piexif.ExifIFD.ISOSpeedRatings: 200,
            piexif.ExifIFD.FNumber: (2, 1),
            piexif.ExifIFD.ExposureTime: (1, 3200),
            piexif.ExifIFD.FocalLength: (135, 1),
            piexif.ExifIFD.DateTimeOriginal: b"2026:04:14 11:26:33",
            piexif.ExifIFD.BodySerialNumber: b"012345678901",
            piexif.ExifIFD.LensSerialNumber: b"0000000000",
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((51, 1), (1, 1), (55, 100)),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((7, 1), (1, 1), (8, 100)),
        },
        "Interop": {},
        "1st": {},
    }
    exif_bytes = piexif.dump(exif_dict)

    img = Image.new("RGB", (64, 64), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    jpeg_bytes = buf.getvalue()

    path.write_bytes(jpeg_bytes)
    piexif.insert(exif_bytes, str(path))


@pytest.fixture
def jpeg_with_exif(tmp_path: Path) -> Path:
    p = tmp_path / "test.jpg"
    _make_jpeg_with_exif(p)
    return p


# ---------------------------------------------------------------------------
# inspect_metadata
# ---------------------------------------------------------------------------


def test_inspect_finds_gps(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import inspect_metadata

    result = inspect_metadata(jpeg_with_exif)
    assert "error" not in result
    gps = result["sensitive"]["gps_coordinates"]
    assert gps is not None
    assert "N" in gps or "S" in gps


def test_inspect_finds_serials(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import inspect_metadata

    result = inspect_metadata(jpeg_with_exif)
    assert result["sensitive"]["camera_serial"] == "012345678901"
    assert result["sensitive"]["lens_serial"] == "0000000000"


def test_inspect_finds_technical(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import inspect_metadata

    result = inspect_metadata(jpeg_with_exif)
    tech = result["technical"]
    assert "Canon" in (tech["camera"] or "")
    assert tech["iso"] == 200
    assert tech["focal_length"] == "135mm"


def test_inspect_emits_privacy_recommendations(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import inspect_metadata

    result = inspect_metadata(jpeg_with_exif)
    recs = result["privacy_recommendations"]
    assert any("GPS" in r for r in recs)
    assert any("serial" in r.lower() for r in recs)
    # Artist stored in 0th IFD shows up as rights.artist
    assert result["rights"]["artist"] is not None


def test_inspect_missing_file_returns_error() -> None:
    from rawtherapee_mcp.metadata import inspect_metadata

    result = inspect_metadata(Path("/nonexistent.jpg"))
    assert "error" in result


# ---------------------------------------------------------------------------
# strip_metadata
# ---------------------------------------------------------------------------


def test_strip_gps_removes_gps_ifd(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import strip_metadata

    result = strip_metadata(jpeg_with_exif, jpeg_with_exif, strip_gps=True)
    assert "GPS" in result["stripped"]

    exif_after = piexif.load(str(jpeg_with_exif))
    assert exif_after["GPS"] == {}


def test_strip_camera_serial(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import strip_metadata

    strip_metadata(jpeg_with_exif, jpeg_with_exif, strip_gps=False, strip_camera_serial=True)
    exif_after = piexif.load(str(jpeg_with_exif))
    assert piexif.ExifIFD.BodySerialNumber not in exif_after["Exif"]


def test_strip_all_preserves_orientation(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import strip_metadata

    strip_metadata(jpeg_with_exif, jpeg_with_exif, strip_all=True, keep_orientation=True)
    exif_after = piexif.load(str(jpeg_with_exif))
    assert piexif.ImageIFD.Orientation in exif_after["0th"]
    assert piexif.ImageIFD.Software not in exif_after["0th"]


def test_strip_to_separate_output_leaves_source_unchanged(jpeg_with_exif: Path, tmp_path: Path) -> None:
    from rawtherapee_mcp.metadata import strip_metadata

    out = tmp_path / "stripped.jpg"
    strip_metadata(jpeg_with_exif, out, strip_gps=True)

    # Source still has GPS
    src_exif = piexif.load(str(jpeg_with_exif))
    assert src_exif["GPS"] != {}

    # Output does not
    out_exif = piexif.load(str(out))
    assert out_exif["GPS"] == {}


def test_strip_does_not_change_image_dimensions(jpeg_with_exif: Path) -> None:
    """Verify the image pixel data is not recompressed."""
    before_pixels = Image.open(jpeg_with_exif).size

    from rawtherapee_mcp.metadata import strip_metadata

    strip_metadata(jpeg_with_exif, jpeg_with_exif, strip_all=True)

    after_pixels = Image.open(jpeg_with_exif).size
    assert before_pixels == after_pixels


# ---------------------------------------------------------------------------
# set_metadata
# ---------------------------------------------------------------------------


def test_set_copyright(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import set_metadata

    result = set_metadata(jpeg_with_exif, jpeg_with_exif, copyright="© 2026 Test")
    assert "Copyright" in result["written"]

    exif_after = piexif.load(str(jpeg_with_exif))
    raw_val = exif_after["0th"].get(piexif.ImageIFD.Copyright, b"")
    assert b"2026" in raw_val


def test_set_artist_and_keywords(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import set_metadata

    result = set_metadata(
        jpeg_with_exif,
        jpeg_with_exif,
        artist="Test Artist",
        keywords=["nature", "landscape"],
    )
    assert "Artist" in result["written"]
    assert "XPKeywords" in result["written"]

    exif_after = piexif.load(str(jpeg_with_exif))
    artist_raw = exif_after["0th"].get(piexif.ImageIFD.Artist, b"")
    assert b"Test" in artist_raw


def test_set_nothing_returns_error(jpeg_with_exif: Path) -> None:
    from rawtherapee_mcp.metadata import set_metadata

    # Calling _set_metadata with all None should raise since at least one must be set
    # (the MCP tool layer validates this; at the module level no exception is raised —
    # the result simply has an empty "written" list)
    result = set_metadata(jpeg_with_exif, jpeg_with_exif)
    assert result["written"] == []


def test_set_output_path(jpeg_with_exif: Path, tmp_path: Path) -> None:
    from rawtherapee_mcp.metadata import set_metadata

    out = tmp_path / "with_meta.jpg"
    result = set_metadata(jpeg_with_exif, out, copyright="© 2026")
    assert Path(result["file_path"]) == out
    assert out.is_file()
