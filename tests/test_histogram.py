"""Tests for histogram computation and SVG rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from rawtherapee_mcp.histogram import compute_histogram, render_histogram_svg


def _create_test_image(path: Path, width: int, height: int, color: str = "red") -> None:
    """Create a test image file."""
    img = Image.new("RGB", (width, height), color=color)
    img.save(path, format="JPEG")


class TestComputeHistogram:
    """Tests for compute_histogram function."""

    def test_basic_histogram(self, tmp_path: Path) -> None:
        """Compute histogram from a JPEG file."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 100, 100, color="red")

        result = compute_histogram(img_path)

        assert "channels" in result
        assert "statistics" in result
        assert "clipping" in result
        assert "total_pixels" in result
        assert result["total_pixels"] == 10000

    def test_channel_lengths(self, tmp_path: Path) -> None:
        """Each channel should have 256 bins."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 50, 50)

        result = compute_histogram(img_path)

        assert len(result["channels"]["red"]) == 256
        assert len(result["channels"]["green"]) == 256
        assert len(result["channels"]["blue"]) == 256

    def test_statistics_keys(self, tmp_path: Path) -> None:
        """Each channel should have mean, median, std_dev, min, max."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 50, 50)

        stats = compute_histogram(img_path)["statistics"]

        for channel in ("red", "green", "blue"):
            assert "mean" in stats[channel]
            assert "median" in stats[channel]
            assert "std_dev" in stats[channel]
            assert "min" in stats[channel]
            assert "max" in stats[channel]

    def test_clipping_keys(self, tmp_path: Path) -> None:
        """Clipping data should have shadows_pct and highlights_pct."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 50, 50)

        clipping = compute_histogram(img_path)["clipping"]

        for channel in ("red", "green", "blue"):
            assert "shadows_pct" in clipping[channel]
            assert "highlights_pct" in clipping[channel]

    def test_red_image(self, tmp_path: Path) -> None:
        """A pure red image should have high red mean and low green/blue."""
        img_path = tmp_path / "red.jpg"
        _create_test_image(img_path, 100, 100, color="red")

        stats = compute_histogram(img_path)["statistics"]

        # Pure red: R=255 (after JPEG compression, close to 255)
        assert stats["red"]["mean"] > 200
        assert stats["green"]["mean"] < 50
        assert stats["blue"]["mean"] < 50

    def test_white_image(self, tmp_path: Path) -> None:
        """A white image should have highlight clipping in all channels."""
        img_path = tmp_path / "white.jpg"
        _create_test_image(img_path, 100, 100, color="white")

        clipping = compute_histogram(img_path)["clipping"]

        for channel in ("red", "green", "blue"):
            assert clipping[channel]["highlights_pct"] > 50

    def test_rgba_conversion(self, tmp_path: Path) -> None:
        """RGBA images should be converted to RGB."""
        img_path = tmp_path / "rgba.png"
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        img.save(img_path, format="PNG")

        result = compute_histogram(img_path)

        assert result["total_pixels"] == 10000
        assert len(result["channels"]["red"]) == 256

    def test_file_not_found(self) -> None:
        """Missing file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            compute_histogram(Path("/nonexistent/image.jpg"))

    def test_png_image(self, tmp_path: Path) -> None:
        """PNG images should work."""
        img_path = tmp_path / "test.png"
        img = Image.new("RGB", (100, 100), color="blue")
        img.save(img_path, format="PNG")

        result = compute_histogram(img_path)

        assert result["total_pixels"] == 10000
        assert result["statistics"]["blue"]["mean"] > 200


class TestRenderHistogramSvg:
    """Tests for render_histogram_svg function."""

    def test_returns_svg_string(self, tmp_path: Path) -> None:
        """Should return a valid SVG string."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 100, 100)

        data = compute_histogram(img_path)
        svg = render_histogram_svg(data)

        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")

    def test_svg_dimensions(self, tmp_path: Path) -> None:
        """SVG should use specified dimensions."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 100, 100)

        data = compute_histogram(img_path)
        svg = render_histogram_svg(data, width=800, height=300)

        assert 'width="800"' in svg
        assert 'height="300"' in svg

    def test_svg_contains_channels(self, tmp_path: Path) -> None:
        """SVG should contain color elements for each channel."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 100, 100)

        data = compute_histogram(img_path)
        svg = render_histogram_svg(data)

        assert "#ff4444" in svg  # red channel
        assert "#44ff44" in svg  # green channel
        assert "#4444ff" in svg  # blue channel

    def test_svg_background(self, tmp_path: Path) -> None:
        """SVG should have a dark background."""
        img_path = tmp_path / "test.jpg"
        _create_test_image(img_path, 100, 100)

        data = compute_histogram(img_path)
        svg = render_histogram_svg(data)

        assert "#1a1a1a" in svg
