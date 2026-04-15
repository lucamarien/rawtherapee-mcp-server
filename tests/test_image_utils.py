"""Tests for image_utils thumbnail generation."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from rawtherapee_mcp.image_utils import generate_thumbnail


def _create_test_image(path: Path, width: int, height: int, mode: str = "RGB") -> None:
    """Create a test image file."""
    img = Image.new(mode, (width, height), color="red")
    ext = path.suffix.lower()
    fmt = {"jpg": "JPEG", ".jpg": "JPEG", ".png": "PNG", ".tif": "TIFF"}.get(ext, "JPEG")
    img.save(path, format=fmt)


class TestGenerateThumbnail:
    """Tests for generate_thumbnail function."""

    def test_jpeg_thumbnail(self, tmp_path: Path) -> None:
        """Generate thumbnail from a JPEG file."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 1920, 1080)

        result = generate_thumbnail(img_path, max_width=600)

        assert isinstance(result, bytes)
        assert len(result) > 0
        # Verify it's valid JPEG
        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.format == "JPEG"
        assert thumb.width <= 600
        assert thumb.height <= 600

    def test_png_thumbnail(self, tmp_path: Path) -> None:
        """Generate thumbnail from a PNG file."""
        img_path = tmp_path / "test.png"
        _create_test_image(img_path, 2000, 1500, mode="RGBA")

        result = generate_thumbnail(img_path, max_width=400)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.format == "JPEG"
        assert thumb.width <= 400
        assert thumb.height <= 400

    def test_tiff_thumbnail(self, tmp_path: Path) -> None:
        """Generate thumbnail from a TIFF file."""
        img_path = tmp_path / "test.tif"
        _create_test_image(img_path, 3000, 2000)

        result = generate_thumbnail(img_path, max_width=600)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.format == "JPEG"
        assert thumb.width <= 600

    def test_preserves_aspect_ratio_landscape(self, tmp_path: Path) -> None:
        """Landscape image should scale width to max_width."""
        img_path = tmp_path / "landscape.jpg"
        _create_test_image(img_path, 2000, 1000)

        result = generate_thumbnail(img_path, max_width=600)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.width == 600
        assert thumb.height == 300

    def test_preserves_aspect_ratio_portrait(self, tmp_path: Path) -> None:
        """Portrait image should scale height to max_width."""
        img_path = tmp_path / "portrait.jpg"
        _create_test_image(img_path, 1000, 2000)

        result = generate_thumbnail(img_path, max_width=600)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.width == 300
        assert thumb.height == 600

    def test_no_upscale(self, tmp_path: Path) -> None:
        """Small images should not be upscaled."""
        img_path = tmp_path / "small.jpg"
        _create_test_image(img_path, 200, 150)

        result = generate_thumbnail(img_path, max_width=600)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.width == 200
        assert thumb.height == 150

    def test_square_image(self, tmp_path: Path) -> None:
        """Square images should scale both dimensions equally."""
        img_path = tmp_path / "square.jpg"
        _create_test_image(img_path, 1000, 1000)

        result = generate_thumbnail(img_path, max_width=500)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.width == 500
        assert thumb.height == 500

    def test_rgba_to_rgb_conversion(self, tmp_path: Path) -> None:
        """RGBA images should be converted to RGB for JPEG output."""
        img_path = tmp_path / "rgba.png"
        _create_test_image(img_path, 800, 600, mode="RGBA")

        result = generate_thumbnail(img_path, max_width=400)

        thumb = Image.open(__import__("io").BytesIO(result))
        assert thumb.mode in ("RGB", "L")

    def test_file_not_found(self) -> None:
        """Missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            generate_thumbnail(Path("/nonexistent/image.jpg"))

    def test_quality_parameter(self, tmp_path: Path) -> None:
        """Higher quality should produce larger file."""
        img_path = tmp_path / "quality.jpg"
        _create_test_image(img_path, 1000, 1000)

        low_q = generate_thumbnail(img_path, max_width=500, quality=20)
        high_q = generate_thumbnail(img_path, max_width=500, quality=95)

        assert len(high_q) > len(low_q)
