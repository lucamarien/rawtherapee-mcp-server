"""Histogram computation and SVG rendering for processed images.

Uses Pillow to compute RGB histograms and image statistics without
requiring matplotlib or any additional visualization library.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat


def compute_histogram(image_path: Path) -> dict[str, Any]:
    """Compute RGB histogram and statistics from an image file.

    Args:
        image_path: Path to a JPEG, PNG, or TIFF image.

    Returns:
        Dict with ``channels``, ``statistics``, and ``clipping`` keys.

    Raises:
        FileNotFoundError: If the image file does not exist.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with Image.open(image_path) as img:
        # Convert to RGB if needed (handles RGBA, L, CMYK, etc.)
        if img.mode != "RGB":
            img = img.convert("RGB")

        histogram = img.histogram()
        stat = ImageStat.Stat(img)

    # Pillow histogram() returns a flat list: [R0..R255, G0..G255, B0..B255]
    red = histogram[0:256]
    green = histogram[256:512]
    blue = histogram[512:768]

    total_pixels = stat.count[0]

    channels: dict[str, list[int]] = {
        "red": red,
        "green": green,
        "blue": blue,
    }

    # Per-channel statistics
    channel_names = ["red", "green", "blue"]
    statistics: dict[str, dict[str, float]] = {}
    for i, name in enumerate(channel_names):
        statistics[name] = {
            "mean": round(stat.mean[i], 2),
            "median": round(stat.median[i], 2),
            "std_dev": round(stat.stddev[i], 2),
            "min": float(stat.extrema[i][0]),
            "max": float(stat.extrema[i][1]),
        }

    # Clipping analysis (pixels at 0 or 255)
    clipping: dict[str, dict[str, float]] = {}
    for i, name in enumerate(channel_names):
        ch = [red, green, blue][i]
        shadow_pct = round((ch[0] / total_pixels) * 100, 2) if total_pixels > 0 else 0.0
        highlight_pct = round((ch[255] / total_pixels) * 100, 2) if total_pixels > 0 else 0.0
        clipping[name] = {
            "shadows_pct": shadow_pct,
            "highlights_pct": highlight_pct,
        }

    return {
        "channels": channels,
        "statistics": statistics,
        "clipping": clipping,
        "total_pixels": total_pixels,
    }


def render_histogram_svg(
    histogram_data: dict[str, Any],
    width: int = 600,
    height: int = 200,
) -> str:
    """Render histogram data as an inline SVG string.

    Args:
        histogram_data: Output from ``compute_histogram()``.
        width: SVG width in pixels.
        height: SVG height in pixels.

    Returns:
        SVG markup string.
    """
    channels = histogram_data["channels"]
    red: list[int] = channels["red"]
    green: list[int] = channels["green"]
    blue: list[int] = channels["blue"]

    # Find max value across all channels for normalization
    max_val = max(max(red), max(green), max(blue), 1)
    # Use log scale for better visibility of lower values
    log_max = math.log1p(max_val)

    bar_width = width / 256.0

    def _make_path(data: list[int], color: str, opacity: str = "0.6") -> str:
        points = []
        for i, count in enumerate(data):
            x = i * bar_width
            h = (math.log1p(count) / log_max) * height if log_max > 0 else 0
            y = height - h
            points.append(f"{x:.1f},{y:.1f}")

        # Close the path at the baseline
        points.append(f"{width:.1f},{height}")
        points.append(f"0,{height}")

        return f'<polygon points="{" ".join(points)}" fill="{color}" opacity="{opacity}" />'

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#1a1a1a" />',
        _make_path(red, "#ff4444"),
        _make_path(green, "#44ff44"),
        _make_path(blue, "#4444ff"),
        "</svg>",
    ]

    return "\n".join(svg_parts)
