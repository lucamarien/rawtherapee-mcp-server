"""Image utility functions for thumbnail generation.

Uses Pillow to create in-memory JPEG thumbnails from processed images.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageOps

logger = logging.getLogger("rawtherapee_mcp")

# Default thumbnail settings
DEFAULT_THUMBNAIL_MAX_WIDTH = 600
DEFAULT_THUMBNAIL_QUALITY = 80


def generate_thumbnail(
    image_path: Path,
    max_width: int = DEFAULT_THUMBNAIL_MAX_WIDTH,
    quality: int = DEFAULT_THUMBNAIL_QUALITY,
) -> bytes:
    """Generate a JPEG thumbnail from an image file.

    Resizes the image so the longest side is at most max_width pixels,
    preserving aspect ratio. Returns JPEG bytes in memory (no disk I/O).

    Args:
        image_path: Path to the source image (JPEG, TIFF, or PNG).
        max_width: Maximum width/height in pixels.
        quality: JPEG compression quality (1-100).

    Returns:
        JPEG image bytes.

    Raises:
        FileNotFoundError: If image_path does not exist.
        OSError: If the file cannot be read or is not a valid image.
    """
    resolved = image_path.resolve()
    if not resolved.is_file():
        msg = f"Image file not found: {resolved}"
        raise FileNotFoundError(msg)

    with Image.open(resolved) as file_img:
        # Preserve orientation from EXIF
        img: Image.Image = ImageOps.exif_transpose(file_img) or file_img

        # Calculate new size preserving aspect ratio
        width, height = img.size
        if width <= max_width and height <= max_width:
            scale = 1.0
        elif width >= height:
            scale = max_width / width
        else:
            scale = max_width / height

        new_width = int(width * scale)
        new_height = int(height * scale)

        if scale < 1.0:
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (TIFF can be RGBA/16-bit, etc.)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()
