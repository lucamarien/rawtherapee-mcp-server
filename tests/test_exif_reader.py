"""Tests for EXIF metadata extraction."""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

from rawtherapee_mcp.exif_reader import (
    _get_raw_dimensions_from_tiff_ifds,
    get_effective_dimensions,
    get_image_info,
    read_exif_data,
)


class TestReadExifData:
    """Tests for EXIF reading."""

    def test_returns_structured_data(self, tmp_path):
        """Test that read_exif_data returns a properly structured dict."""
        mock_tags = {
            "Image Make": MagicMock(__str__=lambda self: "Canon"),
            "Image Model": MagicMock(__str__=lambda self: "EOS R5"),
            "EXIF ISOSpeedRatings": MagicMock(__str__=lambda self: "400"),
            "EXIF FNumber": MagicMock(__str__=lambda self: "2.8"),
            "EXIF ExposureTime": MagicMock(__str__=lambda self: "1/250"),
            "EXIF FocalLength": MagicMock(__str__=lambda self: "85"),
        }

        test_file = tmp_path / "test.cr2"
        test_file.write_bytes(b"fake raw data")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            result = read_exif_data(test_file)

            assert result["camera_make"] == "Canon"
            assert result["camera_model"] == "EOS R5"
            assert result["iso"] == "400"
            assert result["aperture"] == "2.8"
            assert result["shutter_speed"] == "1/250"

    def test_missing_tags_return_empty_string(self, tmp_path):
        """Test that missing EXIF tags return empty strings."""
        test_file = tmp_path / "test.cr2"
        test_file.write_bytes(b"fake raw data")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value={}):
            result = read_exif_data(test_file)

            assert result["camera_make"] == ""
            assert result["lens_model"] == ""
            assert result["gps_latitude"] == ""

    def test_file_not_found(self, tmp_path):
        """Test error handling for missing files."""
        result = read_exif_data(tmp_path / "nonexistent.cr2")
        assert "error" in result


class TestGetEffectiveDimensions:
    """Tests for orientation-aware dimension extraction."""

    def test_normal_orientation(self, tmp_path):
        mock_tags = {
            "EXIF ExifImageWidth": MagicMock(__str__=lambda self: "6720"),
            "EXIF ExifImageLength": MagicMock(__str__=lambda self: "4480"),
            "Image Orientation": MagicMock(__str__=lambda self: "Horizontal (normal)"),
        }
        test_file = tmp_path / "test.cr2"
        test_file.write_bytes(b"fake")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            assert w == 6720
            assert h == 4480

    def test_90_ccw_rotation_swaps_dimensions(self, tmp_path):
        mock_tags = {
            "EXIF ExifImageWidth": MagicMock(__str__=lambda self: "6720"),
            "EXIF ExifImageLength": MagicMock(__str__=lambda self: "4480"),
            "Image Orientation": MagicMock(__str__=lambda self: "Rotated 90 CCW"),
        }
        test_file = tmp_path / "test.cr2"
        test_file.write_bytes(b"fake")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            assert w == 4480
            assert h == 6720

    def test_90_cw_rotation_swaps_dimensions(self, tmp_path):
        mock_tags = {
            "EXIF ExifImageWidth": MagicMock(__str__=lambda self: "6720"),
            "EXIF ExifImageLength": MagicMock(__str__=lambda self: "4480"),
            "Image Orientation": MagicMock(__str__=lambda self: "Rotated 90 CW"),
        }
        test_file = tmp_path / "test.cr2"
        test_file.write_bytes(b"fake")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            assert w == 4480
            assert h == 6720

    def test_missing_file_returns_zero(self, tmp_path):
        w, h = get_effective_dimensions(tmp_path / "nonexistent.cr2")
        assert w == 0
        assert h == 0

    def test_fallback_to_image_tags(self, tmp_path):
        """Test that Image-level dimension tags are used as fallback."""
        mock_tags = {
            "Image ImageWidth": MagicMock(__str__=lambda self: "6720"),
            "Image ImageLength": MagicMock(__str__=lambda self: "4480"),
            "Image Orientation": MagicMock(__str__=lambda self: "Horizontal (normal)"),
        }
        test_file = tmp_path / "test.cr2"
        test_file.write_bytes(b"fake")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            assert w == 6720
            assert h == 4480

    def test_handles_empty_dimensions_with_no_tiff(self, tmp_path):
        """Test that empty dimension tags return (0, 0) for non-TIFF files."""
        mock_tags = {
            "Image Orientation": MagicMock(__str__=lambda self: "Horizontal (normal)"),
        }
        test_file = tmp_path / "test.cr2"
        # Write non-TIFF data so TIFF fallback also fails
        test_file.write_bytes(b"not a tiff file")

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            assert w == 0
            assert h == 0

    def test_tiff_ifd_fallback_when_exif_has_no_dimensions(self, tmp_path):
        """Test that TIFF IFD parsing provides dimensions when EXIF lacks them."""
        # EXIF returns no dimension tags
        mock_tags = {
            "Image Orientation": MagicMock(__str__=lambda self: "Horizontal (normal)"),
        }
        test_file = tmp_path / "test.cr2"

        # Write a minimal TIFF file with IFD containing dimensions
        tiff_data = _build_tiff_with_dimensions(6720, 4480)
        test_file.write_bytes(tiff_data)

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            assert w == 6720
            assert h == 4480

    def test_tiff_ifd_fallback_with_rotation(self, tmp_path):
        """Test that TIFF fallback dimensions are swapped for rotated images."""
        mock_tags = {
            "Image Orientation": MagicMock(__str__=lambda self: "Rotated 90 CW"),
        }
        test_file = tmp_path / "test.cr2"
        tiff_data = _build_tiff_with_dimensions(6720, 4480)
        test_file.write_bytes(tiff_data)

        with patch("rawtherapee_mcp.exif_reader.exifread.process_file", return_value=mock_tags):
            w, h = get_effective_dimensions(test_file)
            # Should be swapped due to 90° rotation
            assert w == 4480
            assert h == 6720


class TestGetRawDimensionsFromTiffIfds:
    """Tests for TIFF IFD dimension extraction."""

    def test_single_ifd(self, tmp_path):
        """Test reading dimensions from a single TIFF IFD."""
        tiff_file = tmp_path / "test.tif"
        tiff_file.write_bytes(_build_tiff_with_dimensions(1920, 1080))

        w, h = _get_raw_dimensions_from_tiff_ifds(tiff_file)
        assert w == 1920
        assert h == 1080

    def test_multi_ifd_returns_largest(self, tmp_path):
        """Test that the largest dimensions from multiple IFDs are returned."""
        tiff_file = tmp_path / "test.cr2"
        tiff_file.write_bytes(_build_tiff_multi_ifd([(160, 120), (6720, 4480)]))

        w, h = _get_raw_dimensions_from_tiff_ifds(tiff_file)
        assert w == 6720
        assert h == 4480

    def test_invalid_file(self, tmp_path):
        """Test that non-TIFF files return (0, 0)."""
        bad_file = tmp_path / "not_tiff.bin"
        bad_file.write_bytes(b"this is not a tiff file")

        w, h = _get_raw_dimensions_from_tiff_ifds(bad_file)
        assert w == 0
        assert h == 0

    def test_missing_file(self, tmp_path):
        """Test that missing files return (0, 0)."""
        w, h = _get_raw_dimensions_from_tiff_ifds(tmp_path / "nonexistent.cr2")
        assert w == 0
        assert h == 0


def _build_tiff_with_dimensions(width: int, height: int) -> bytes:
    """Build a minimal TIFF file with a single IFD containing ImageWidth/ImageLength."""
    # Little-endian TIFF header
    header = b"II"  # byte order
    header += struct.pack("<H", 42)  # magic
    header += struct.pack("<I", 8)  # offset to first IFD (right after header)

    # IFD with 2 entries (ImageWidth=256, ImageLength=257)
    num_entries = 2
    ifd = struct.pack("<H", num_entries)
    # Tag 256 (ImageWidth), type LONG (4), count 1, value
    ifd += struct.pack("<HHI", 256, 4, 1) + struct.pack("<I", width)
    # Tag 257 (ImageLength), type LONG (4), count 1, value
    ifd += struct.pack("<HHI", 257, 4, 1) + struct.pack("<I", height)
    # Next IFD offset (0 = no more)
    ifd += struct.pack("<I", 0)

    return header + ifd


def _build_tiff_multi_ifd(dimensions: list[tuple[int, int]]) -> bytes:
    """Build a TIFF file with multiple IFDs (e.g. thumbnail + full image)."""
    header = b"II"
    header += struct.pack("<H", 42)
    # First IFD starts at offset 8
    header += struct.pack("<I", 8)

    data = header
    current_offset = 8

    for i, (width, height) in enumerate(dimensions):
        num_entries = 2
        # Each IFD: 2 bytes (count) + 12*entries + 4 bytes (next offset)
        ifd_size = 2 + 12 * num_entries + 4
        next_offset = current_offset + ifd_size if i < len(dimensions) - 1 else 0

        ifd = struct.pack("<H", num_entries)
        ifd += struct.pack("<HHI", 256, 4, 1) + struct.pack("<I", width)
        ifd += struct.pack("<HHI", 257, 4, 1) + struct.pack("<I", height)
        ifd += struct.pack("<I", next_offset)

        data += ifd
        current_offset += ifd_size

    return data


class TestGetImageInfo:
    """Tests for image header parsing."""

    def test_jpeg_dimensions(self, tmp_path):
        """Test JPEG SOF marker parsing."""
        # Construct a minimal JPEG with SOF0 marker
        # SOI + SOF0 marker
        sof_data = (
            b"\xff\xd8"  # SOI
            b"\xff\xc0"  # SOF0
            b"\x00\x0b"  # Length (11)
            b"\x08"  # Precision (8-bit)
            b"\x02\x00"  # Height (512)
            b"\x03\x00"  # Width (768)
            b"\x03"  # Components
            b"\x01\x11\x00"  # Component data
        )
        jpeg_file = tmp_path / "test.jpg"
        jpeg_file.write_bytes(sof_data)

        result = get_image_info(jpeg_file)
        assert result["format"] == "jpeg"
        assert result["width"] == 768
        assert result["height"] == 512

    def test_png_dimensions(self, tmp_path):
        """Test PNG IHDR chunk parsing."""
        import struct

        png_data = (
            b"\x89PNG\r\n\x1a\n"  # PNG signature
            + struct.pack(">I", 13)  # Chunk length
            + b"IHDR"  # Chunk type
            + struct.pack(">II", 1920, 1080)  # Width, Height
            + b"\x08"  # Bit depth
            + b"\x02"  # Color type (RGB)
            + b"\x00\x00\x00"  # Compression, filter, interlace
            + b"\x00\x00\x00\x00"  # CRC (fake)
        )
        png_file = tmp_path / "test.png"
        png_file.write_bytes(png_data)

        result = get_image_info(png_file)
        assert result["format"] == "png"
        assert result["width"] == 1920
        assert result["height"] == 1080
        assert result["bit_depth"] == 8

    def test_unsupported_format(self, tmp_path):
        """Test unsupported file format."""
        bmp_file = tmp_path / "test.bmp"
        bmp_file.write_bytes(b"BM fake bmp data")

        result = get_image_info(bmp_file)
        assert "error" in result

    def test_file_not_found(self, tmp_path):
        """Test missing file."""
        result = get_image_info(tmp_path / "nonexistent.jpg")
        assert "error" in result
