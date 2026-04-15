"""RawTherapee MCP Server — FastMCP entrypoint.

Registers all tool modules and starts the STDIO server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import time
from collections.abc import AsyncIterator
from importlib.resources import files
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import lifespan
from fastmcp.tools import ToolResult
from fastmcp.utilities.types import Image as MCPImage
from mcp.types import ImageContent, TextContent

from rawtherapee_mcp import __version__
from rawtherapee_mcp.config import RTConfig, load_config
from rawtherapee_mcp.device_presets import (
    add_custom_preset,
    delete_custom_preset,
    get_all_presets,
    get_preset,
    is_builtin_preset,
)
from rawtherapee_mcp.exif_reader import (
    generate_recommendations,
    get_effective_dimensions,
    read_exif_data,
)
from rawtherapee_mcp.exif_reader import get_image_info as _get_image_info
from rawtherapee_mcp.histogram import compute_histogram, render_histogram_svg
from rawtherapee_mcp.image_utils import generate_thumbnail
from rawtherapee_mcp.locallab import (
    add_spot,
    apply_preset,
    get_spot_count,
    read_spot,
    remove_spot,
    update_spot,
)
from rawtherapee_mcp.locallab import (
    get_preset as get_local_preset,
)
from rawtherapee_mcp.locallab import (
    list_presets as list_local_presets,
)
from rawtherapee_mcp.pp3_generator import apply_device_crop, apply_parameters
from rawtherapee_mcp.pp3_generator import generate_profile as _generate_profile
from rawtherapee_mcp.pp3_parser import PP3Profile
from rawtherapee_mcp.rt_cli import get_rt_version, run_rt_cli

logger = logging.getLogger("rawtherapee_mcp")

# Supported RAW file extensions (case-insensitive)
RAW_EXTENSIONS = frozenset(
    {
        ".cr2",
        ".cr3",
        ".nef",
        ".nrw",
        ".arw",
        ".srf",
        ".sr2",
        ".raf",
        ".orf",
        ".rw2",
        ".rwl",
        ".dng",
        ".pef",
        ".ptx",
        ".3fr",
        ".fff",
        ".iiq",
        ".mrw",
        ".mef",
        ".mos",
        ".kdc",
        ".dcr",
        ".raw",
        ".srw",
        ".x3f",
        ".erf",
    }
)


def _get_templates_dir() -> Path:
    """Get the path to built-in PP3 templates."""
    return Path(str(files("rawtherapee_mcp.templates")))


@lifespan
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Initialize configuration on server startup."""
    config = load_config()
    try:
        yield {"config": config}
    finally:
        pass


mcp = FastMCP("rawtherapee", version=__version__, lifespan=app_lifespan)


def get_config(ctx: Context) -> RTConfig:
    """Extract the RTConfig from the MCP context.

    Args:
        ctx: The FastMCP context object.

    Returns:
        The RTConfig instance.

    Raises:
        RuntimeError: If the config is not initialized.
    """
    cfg: Any = ctx.lifespan_context.get("config")
    if not isinstance(cfg, RTConfig):
        msg = "RTConfig not initialized"
        raise RuntimeError(msg)
    return cfg


def _require_rt(config: RTConfig) -> dict[str, Any] | Path:
    """Check that RT CLI is available, returning error dict if not.

    Returns:
        The RT CLI path, or an error dict.
    """
    if config.rt_cli_path is None:
        return {
            "error": "RawTherapee CLI not found",
            "suggestion": "Install RawTherapee and set RT_CLI_PATH, or run check_rt_status for details",
        }
    return config.rt_cli_path


async def _preview_to_image_content(
    preview_path: str,
    max_width: int,
) -> ImageContent:
    """Convert a preview file to a thumbnailed ImageContent.

    Generates a thumbnail from the preview JPEG so it stays within MCP's
    1MB response limit, even when the preview is full-resolution (e.g.
    crop-only profiles where RT can't resize).
    """
    thumb_bytes = await asyncio.to_thread(generate_thumbnail, Path(preview_path), max_width)
    return MCPImage(data=thumb_bytes, format="jpeg").to_image_content()


def _check_crop_resize_conflict(profile: PP3Profile) -> str | None:
    """Return warning string if profile has both Crop and Resize enabled.

    RT 5.12 silently ignores Crop when Resize is also active.
    """
    if profile.get("Crop", "Enabled") == "true" and profile.get("Resize", "Enabled") == "true":
        return (
            "RT 5.12 bug: Crop is ignored when Resize is also enabled. "
            "Disable Resize to preserve the crop, or use preview_raw "
            "which handles this automatically."
        )
    return None


def _check_crop_resize_conflict_text(pp3_text: str) -> str | None:
    """Text-based crop/resize conflict check — no PP3Profile parsing needed."""
    crop_enabled = False
    resize_enabled = False
    current_section = ""
    for line in pp3_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            continue
        if current_section == "Crop" and stripped == "Enabled=true":
            crop_enabled = True
        elif current_section == "Resize" and stripped == "Enabled=true":
            resize_enabled = True
    if crop_enabled and resize_enabled:
        return (
            "RT 5.12 bug: Crop is ignored when Resize is also enabled. "
            "Disable Resize to preserve the crop, or use preview_raw "
            "which handles this automatically."
        )
    return None


def _pp3_text_has_crop(pp3_text: str) -> bool:
    """Check if raw PP3 text has Crop enabled, without full parsing."""
    current_section = ""
    for line in pp3_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            continue
        if current_section == "Crop" and stripped == "Enabled=true":
            return True
    return False


def _pp3_text_set_resize(pp3_text: str, resize_settings: dict[str, str]) -> str:
    """Replace or append [Resize] section in raw PP3 text.

    Overwrites any existing [Resize] section with the given key-value pairs.
    If no [Resize] section exists, appends one at the end.
    """
    lines = pp3_text.splitlines()
    out: list[str] = []
    in_resize = False
    resize_written = False

    for line in lines:
        stripped = line.strip()
        if stripped == "[Resize]":
            in_resize = True
            # Write our replacement section
            out.append("[Resize]")
            for key, value in resize_settings.items():
                out.append(f"{key}={value}")
            resize_written = True
            continue
        if in_resize:
            # Skip old resize lines until the next section header
            if stripped.startswith("[") and stripped.endswith("]"):
                in_resize = False
                out.append(line)
            continue
        out.append(line)

    if not resize_written:
        out.append("")
        out.append("[Resize]")
        for key, value in resize_settings.items():
            out.append(f"{key}={value}")

    return "\n".join(out)


async def _maybe_attach_thumbnail(
    result: dict[str, Any],
    output_path_key: str = "output_path",
    max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Attach an inline thumbnail to a successful processing result.

    On success, returns ToolResult with TextContent + ImageContent.
    On failure or if the output file is not available, returns the original dict.
    """
    if not result.get("success"):
        return result

    output_path = result.get(output_path_key)
    if not output_path:
        return result

    try:
        thumb_bytes = await asyncio.to_thread(generate_thumbnail, Path(str(output_path)), max_width)
        return ToolResult(
            content=[
                TextContent(type="text", text=json.dumps(result, indent=2)),
                MCPImage(data=thumb_bytes, format="jpeg").to_image_content(),
            ],
            structured_content=result,
        )
    except Exception:  # noqa: BLE001
        logger.debug("Thumbnail generation failed for %s", output_path, exc_info=True)
        return result


async def _render_preview(
    config: RTConfig,
    raw_path: Path,
    profile: PP3Profile | Path,
    max_width: int = 600,
    jpeg_quality: int = 85,
    label: str = "preview",
) -> dict[str, Any]:
    """Render a RAW file with a PP3 profile to a preview JPEG.

    Handles Crop/Resize conflict (RT 5.12 bug), temp PP3 creation, RT CLI
    invocation, and temp file cleanup.

    When ``profile`` is a Path, the PP3 is read as raw text and the Resize
    section is manipulated without full parsing.  This avoids the parser
    crash on profiles with complex Locallab sections.  When ``profile`` is a
    PP3Profile (for in-memory profiles without Locallab), the legacy
    copy-modify-save path is used.

    Args:
        config: Server configuration.
        raw_path: Path to the RAW file.
        profile: PP3 profile to apply — either a PP3Profile object or a
            Path to a ``.pp3`` file on disk.
        max_width: Maximum preview dimension in pixels.
        jpeg_quality: JPEG compression quality (1-100).
        label: Label for temp file naming.

    Returns:
        Dict with ``success``, ``preview_path`` on success, or ``error`` key.
    """
    if config.rt_cli_path is None:
        return {"error": "RawTherapee CLI not found"}

    timestamp = int(time.time() * 1000)
    combined_pp3_path = config.preview_dir / f"_{label}_{timestamp}.pp3"

    if isinstance(profile, Path):
        # --- Raw-text path: bypass PP3Profile parser entirely ---
        pp3_text = profile.read_text(encoding="utf-8")
        has_crop = _pp3_text_has_crop(pp3_text)

        if has_crop:
            resize_settings = {"Enabled": "false"}
        else:
            resize_settings = {
                "Enabled": "true",
                "Scale": "1",
                "AppliesTo": "Full Image",
                "Method": "Lanczos",
                "DataSpecified": "1",
                "Width": str(max_width),
                "Height": str(max_width),
                "AllowUpscaling": "false",
            }

        combined_text = _pp3_text_set_resize(pp3_text, resize_settings)
        combined_pp3_path.write_text(combined_text, encoding="utf-8")
    else:
        # --- PP3Profile path: for in-memory profiles (no Locallab) ---
        combined = profile.copy()

        has_crop = combined.get("Crop", "Enabled") == "true"
        if has_crop:
            combined.set("Resize", "Enabled", "false")
        else:
            combined.set("Resize", "Enabled", "true")
            combined.set("Resize", "Scale", "1")
            combined.set("Resize", "AppliesTo", "Full Image")
            combined.set("Resize", "Method", "Lanczos")
            combined.set("Resize", "DataSpecified", "1")
            combined.set("Resize", "Width", str(max_width))
            combined.set("Resize", "Height", str(max_width))
            combined.set("Resize", "AllowUpscaling", "false")

        combined.save(combined_pp3_path)

    preview_name = f"{label}_{raw_path.stem}_{timestamp}.jpg"
    preview_path = config.preview_dir / preview_name

    result = await run_rt_cli(
        rt_path=config.rt_cli_path,
        input_path=raw_path,
        output_path=preview_path,
        profiles=[combined_pp3_path],
        output_format="jpeg",
        jpeg_quality=jpeg_quality,
    )

    # Include PP3 content in error responses for debugging
    if not result.get("success"):
        try:
            result["preview_pp3_content"] = combined_pp3_path.read_text(encoding="utf-8")
        except OSError:
            pass

    # Clean up temporary profile
    try:
        combined_pp3_path.unlink(missing_ok=True)
    except OSError:
        pass

    if result.get("success"):
        result["preview_path"] = str(preview_path)
        result["max_width"] = max_width

    return result


# ---------------------------------------------------------------------------
# Phase 1 Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def check_rt_status(ctx: Context) -> dict[str, Any]:
    """Check RawTherapee installation status and server configuration.

    Use this to verify RT is installed, check its version, and view the
    configured output directories. Call this first when troubleshooting.
    Returns: dict with installed, cli_path, version, platform, and directory paths.
    """
    config = get_config(ctx)

    result: dict[str, Any] = {
        "installed": config.rt_cli_path is not None,
        "cli_path": str(config.rt_cli_path) if config.rt_cli_path else None,
        "version": None,
        "detection_method": "not_found",
        "platform": platform.system(),
        "output_dir": str(config.output_dir),
        "preview_dir": str(config.preview_dir),
        "custom_templates_dir": str(config.custom_templates_dir),
        "preview_max_width": config.preview_max_width,
        "default_jpeg_quality": config.default_jpeg_quality,
        "mcp_version": __version__,
    }

    if config.rt_cli_path:
        import os

        if os.environ.get("RT_CLI_PATH"):
            result["detection_method"] = "env_var"
        else:
            result["detection_method"] = "auto_detected"

        version = await get_rt_version(config.rt_cli_path)
        result["version"] = version

    return result


@mcp.tool()
async def list_raw_files(
    ctx: Context,
    directory: str,
    recursive: bool = False,
) -> dict[str, Any]:
    """Scan a directory for supported RAW image files.

    Use this to discover which RAW files are available for processing.
    Returns: dict with files list (path, size, extension) and count.
    Params: directory, recursive (default: false)
    """
    dir_path = Path(directory)

    if not dir_path.is_dir():
        return {"error": f"Directory not found: {directory}"}

    found_files: list[dict[str, Any]] = []
    pattern = "**/*" if recursive else "*"

    for file_path in sorted(dir_path.glob(pattern)):
        if file_path.is_file() and file_path.suffix.lower() in RAW_EXTENSIONS:
            found_files.append(
                {
                    "path": str(file_path),
                    "filename": file_path.name,
                    "size": file_path.stat().st_size,
                    "extension": file_path.suffix.lower(),
                }
            )

    return {"files": found_files, "count": len(found_files), "directory": str(dir_path)}


@mcp.tool()
async def read_exif(ctx: Context, file_path: str) -> dict[str, Any]:
    """Read EXIF metadata from a RAW image file.

    Returns camera settings (ISO, aperture, shutter speed, focal length, etc.)
    used when the photo was taken. Use this to make better decisions about
    processing parameters like noise reduction, lens correction, and white balance.
    Params: file_path
    """
    path = Path(file_path)

    if not path.is_file():
        return {"error": f"File not found: {file_path}"}

    exif = read_exif_data(path)
    result: dict[str, Any] = {**exif, "file_path": str(path)}
    result["recommendations"] = generate_recommendations(exif)
    return result


@mcp.tool()
async def generate_pp3_profile(
    ctx: Context,
    name: str,
    base_template: str | None = None,
    parameters: dict[str, Any] | None = None,
    device_preset: str | None = None,
    file_path: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a PP3 processing profile from parameters.

    Use this to generate a new processing profile for RAW development.
    Start with a base_template (e.g. "neutral", "warm_portrait") and
    override specific parameters, or build from scratch with parameters only.

    When device_preset is specified with file_path, the profile uses
    aspect-ratio-based cropping (correct behavior). Without file_path,
    it falls back to resize-only which may produce different results.
    Params: name, base_template, parameters, device_preset, file_path, description
    """
    config = get_config(ctx)
    templates_dir = _get_templates_dir()

    # Resolve device preset if specified
    preset_dict: dict[str, Any] | None = None
    if device_preset:
        preset_dict = get_preset(device_preset, config.custom_templates_dir)
        if preset_dict is None:
            return {"error": f"Device preset '{device_preset}' not found"}

    try:
        profile, output_path = _generate_profile(
            name=name,
            base_template=base_template,
            parameters=parameters,
            device_preset=preset_dict,
            templates_dir=templates_dir,
            custom_templates_dir=config.custom_templates_dir,
        )
    except FileNotFoundError as exc:
        return {"error": str(exc)}

    # Override resize-only device preset with proper crop when source image is available
    if preset_dict and file_path:
        raw_path = Path(file_path)
        if raw_path.is_file():
            eff_w, eff_h = get_effective_dimensions(raw_path)
            if eff_w > 0 and eff_h > 0:
                apply_device_crop(profile, preset_dict, eff_w, eff_h)
                profile.save(output_path)

    summary = profile.to_dict()
    return {
        "profile_path": str(output_path),
        "name": name,
        "base_template": base_template,
        "device_preset": device_preset,
        "file_path": file_path,
        "description": description,
        "summary": summary,
    }


@mcp.tool()
async def process_raw(
    ctx: Context,
    file_path: str,
    profile_path: str,
    output_format: str = "jpeg",
    output_path: str | None = None,
    jpeg_quality: int | None = None,
    bit_depth: int = 16,
    include_preview: bool = True,
    preview_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Process a RAW file with a PP3 processing profile.

    Use this to convert a RAW file to JPEG, TIFF, or PNG using a PP3 profile.
    The profile controls all processing parameters (exposure, white balance,
    sharpening, etc.). Returns an inline thumbnail when include_preview is True.
    Params: file_path, profile_path, output_format, output_path, jpeg_quality, bit_depth,
    include_preview, preview_max_width
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    pp3_path = Path(profile_path)

    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    # Check for Crop+Resize conflict (RT 5.12 bug) — text-based to avoid
    # parser crash on Locallab profiles
    pp3_text = pp3_path.read_text(encoding="utf-8")
    crop_resize_warning = _check_crop_resize_conflict_text(pp3_text)

    # Determine output path
    quality = jpeg_quality if jpeg_quality is not None else config.default_jpeg_quality
    ext_map = {"jpeg": ".jpg", "tiff": ".tif", "png": ".png"}
    ext = ext_map.get(output_format.lower(), ".jpg")

    if output_path:
        out = Path(output_path)
    else:
        out = config.output_dir / f"{raw_path.stem}{ext}"

    # Ensure output directory exists
    out.parent.mkdir(parents=True, exist_ok=True)

    result = await run_rt_cli(
        rt_path=rt_check,
        input_path=raw_path,
        output_path=out,
        profiles=[pp3_path],
        output_format=output_format,
        jpeg_quality=quality,
        bit_depth=bit_depth,
    )

    if crop_resize_warning:
        result["warning"] = crop_resize_warning

    if include_preview:
        return await _maybe_attach_thumbnail(result, "output_path", preview_max_width)
    return result


@mcp.tool()
async def preview_raw(
    ctx: Context,
    file_path: str,
    profile_path: str | None = None,
    max_width: int | None = None,
    return_image: bool = True,
) -> dict[str, Any] | ToolResult:
    """Generate a small preview JPEG for visual analysis.

    Use this to create a quick preview of how a RAW file will look with
    specific processing settings. The preview is a small JPEG suitable for
    visual inspection of composition, exposure, and color. When return_image
    is True, the preview image is returned inline for the LLM to see.
    Params: file_path, profile_path, max_width, return_image
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    width = max_width if max_width is not None else config.preview_max_width

    # When a profile path is given, pass the Path directly to avoid parsing
    # (prevents crash on Locallab profiles).  Without a path, use empty profile.
    profile: PP3Profile | Path
    if profile_path:
        pp3_path = Path(profile_path)
        if not pp3_path.is_file():
            return {"error": f"Profile not found: {profile_path}"}
        profile = pp3_path
    else:
        profile = PP3Profile()

    result = await _render_preview(config, raw_path, profile, max_width=width)

    if result.get("success") and return_image:
        preview_path = result.get("preview_path", "")
        try:
            img_content = await _preview_to_image_content(preview_path, width)
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(result, indent=2)),
                    img_content,
                ],
                structured_content=result,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Image return failed for %s", preview_path, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Phase 2 Tools — Templates & Presets
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_templates(ctx: Context) -> dict[str, Any]:
    """List all available PP3 processing templates (built-in and custom).

    Use this to discover which templates are available for apply_template
    or as a base_template for generate_pp3_profile.
    Returns: dict with built_in and custom template lists.
    """
    config = get_config(ctx)
    templates_dir = _get_templates_dir()

    built_in: list[dict[str, str]] = []
    for pp3_file in sorted(templates_dir.glob("*.pp3")):
        built_in.append({"name": pp3_file.stem, "source": "built_in", "path": str(pp3_file)})

    custom: list[dict[str, str]] = []
    for pp3_file in sorted(config.custom_templates_dir.glob("*.pp3")):
        custom.append({"name": pp3_file.stem, "source": "custom", "path": str(pp3_file)})

    return {"built_in": built_in, "custom": custom, "total": len(built_in) + len(custom)}


@mcp.tool()
async def apply_template(
    ctx: Context,
    file_path: str,
    template_name: str,
    output_format: str = "jpeg",
    output_dir: str | None = None,
    device_preset: str | None = None,
    include_preview: bool = True,
    preview_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Apply a built-in or custom PP3 template to a RAW file and process it.

    Use this for quick processing with a predefined style. Optionally apply
    a device preset for crop/resize on top of the template. Returns an inline
    thumbnail when include_preview is True.
    Params: file_path, template_name, output_format, output_dir, device_preset,
    include_preview, preview_max_width
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    templates_dir = _get_templates_dir()

    # Load template
    template_path = config.custom_templates_dir / f"{template_name}.pp3"
    if not template_path.is_file():
        template_path = templates_dir / f"{template_name}.pp3"
    if not template_path.is_file():
        return {"error": f"Template '{template_name}' not found"}

    # Build a SINGLE combined PP3 (RT 5.12 can crash merging multiple PP3s)
    combined = PP3Profile()
    combined.load(template_path)

    combined_path: Path | None = None
    eff_w, eff_h = 0, 0
    if device_preset:
        preset_dict = get_preset(device_preset, config.custom_templates_dir)
        if preset_dict is None:
            return {"error": f"Device preset '{device_preset}' not found"}

        # Read source image dimensions for correct crop calculation
        eff_w, eff_h = get_effective_dimensions(raw_path)

        if eff_w > 0 and eff_h > 0:
            # Calculate correct aspect-ratio crop using source dimensions
            apply_device_crop(combined, preset_dict, eff_w, eff_h)
        else:
            # Fallback: resize only (no crop possible without dimensions)
            from rawtherapee_mcp.pp3_generator import apply_device_preset

            apply_device_preset(combined, preset_dict)
            logger.warning(
                "Could not read source dimensions for %s (got %dx%d), using resize-only",
                raw_path.name,
                eff_w,
                eff_h,
            )

    # Save combined PP3 to a temp file
    timestamp = int(time.time() * 1000)
    combined_path = config.preview_dir / f"_combined_{template_name}_{timestamp}.pp3"
    combined.save(combined_path)

    # Determine output path
    out_dir = Path(output_dir) if output_dir else config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    ext_map = {"jpeg": ".jpg", "tiff": ".tif", "png": ".png"}
    ext = ext_map.get(output_format.lower(), ".jpg")
    output_path = out_dir / f"{raw_path.stem}_{template_name}{ext}"

    result = await run_rt_cli(
        rt_path=rt_check,
        input_path=raw_path,
        output_path=output_path,
        profiles=[combined_path],
        output_format=output_format,
        jpeg_quality=config.default_jpeg_quality,
    )

    # Add diagnostic info for device preset results
    if device_preset:
        result["effective_dimensions"] = [eff_w, eff_h]
        result["device_crop_applied"] = eff_w > 0 and eff_h > 0
        if not result.get("success"):
            result["combined_pp3_content"] = combined.dumps()

    # Clean up temporary combined PP3
    if combined_path:
        try:
            combined_path.unlink(missing_ok=True)
        except OSError:
            pass

    if include_preview:
        return await _maybe_attach_thumbnail(result, "output_path", preview_max_width)
    return result


@mcp.tool()
async def list_device_presets(ctx: Context) -> dict[str, Any]:
    """List all device/format crop and resize presets.

    Use this to discover available presets for mobile wallpapers, desktop
    wallpapers, and photo aspect ratios. Presets can be applied when
    generating profiles or processing images.
    Returns: dict with presets grouped by category (mobile, desktop, photo_formats, custom).
    """
    config = get_config(ctx)
    presets = get_all_presets(config.custom_templates_dir)
    return {"presets": presets}


@mcp.tool()
async def adjust_profile(
    ctx: Context,
    profile_path: str,
    adjustments: dict[str, Any],
    save_as: str | None = None,
) -> dict[str, Any]:
    """Modify specific parameters in an existing PP3 profile.

    Use this to tweak individual settings without recreating the entire profile.
    Only the specified parameters are changed; all other settings are preserved.

    Accepts both friendly parameter names (e.g. {"crop": {"width": 3108}}) and
    raw PP3 section/key pairs (e.g. {"Crop": {"W": "3108", "H": "6732"}}).
    Unrecognized group names are treated as raw PP3 section names.
    Params: profile_path, adjustments, save_as
    """
    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(pp3_path)

    apply_parameters(profile, adjustments, raw_fallback=True)

    if save_as:
        output_path = pp3_path.parent / save_as
        if not output_path.suffix:
            output_path = output_path.with_suffix(".pp3")
    else:
        output_path = pp3_path

    profile.save(output_path)

    return {
        "profile_path": str(output_path),
        "adjustments_applied": adjustments,
        "summary": profile.to_dict(),
    }


@mcp.tool()
async def read_profile(ctx: Context, profile_path: str) -> dict[str, Any]:
    """Display contents of a PP3 profile in human-readable format.

    Use this to inspect what settings a profile contains before applying it.
    Returns all active sections and their key-value pairs.
    Params: profile_path
    """
    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(pp3_path)

    return {
        "profile_path": str(pp3_path),
        "sections": profile.to_dict(),
        "section_count": len(profile.sections()),
    }


@mcp.tool()
async def compare_profiles(
    ctx: Context,
    profile_a: str,
    profile_b: str,
    file_path: str | None = None,
    include_preview: bool = False,
    preview_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Compare two PP3 profiles and show the differences.

    Use this to understand how two profiles differ before choosing between them,
    or to see what changed after adjustments. When file_path and include_preview
    are provided, renders both profiles as inline images for visual comparison.
    Params: profile_a, profile_b, file_path, include_preview, preview_max_width
    """
    path_a = Path(profile_a)
    path_b = Path(profile_b)

    if not path_a.is_file():
        return {"error": f"Profile A not found: {profile_a}"}
    if not path_b.is_file():
        return {"error": f"Profile B not found: {profile_b}"}

    prof_a = PP3Profile()
    prof_a.load(path_a)

    prof_b = PP3Profile()
    prof_b.load(path_b)

    diff = prof_a.diff(prof_b)

    result: dict[str, Any] = {
        "profile_a": str(path_a),
        "profile_b": str(path_b),
        **diff,
    }

    if file_path and include_preview:
        config = get_config(ctx)
        rt_check = _require_rt(config)
        raw_path = Path(file_path)

        if not isinstance(rt_check, dict) and raw_path.is_file():
            # Pass Paths to avoid parser crash on Locallab profiles
            preview_a = await _render_preview(config, raw_path, path_a, max_width=preview_max_width, label="cmp_a")
            preview_b = await _render_preview(config, raw_path, path_b, max_width=preview_max_width, label="cmp_b")
            result["preview_a"] = preview_a
            result["preview_b"] = preview_b

            if preview_a.get("success") and preview_b.get("success"):
                try:
                    img_a = await _preview_to_image_content(preview_a["preview_path"], preview_max_width)
                    img_b = await _preview_to_image_content(preview_b["preview_path"], preview_max_width)
                    return ToolResult(
                        content=[
                            TextContent(type="text", text=json.dumps(result, indent=2)),
                            img_a,
                            img_b,
                        ],
                        structured_content=result,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("Image return failed for compare preview", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Phase 3 Tools — CRUD & Batch
# ---------------------------------------------------------------------------


@mcp.tool()
async def save_template(
    ctx: Context,
    profile_path: str,
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Save an existing PP3 profile as a reusable custom template.

    Use this to save a tuned profile so it can be reused later with
    apply_template or as a base_template for generate_pp3_profile.
    Params: profile_path, name, description
    """
    config = get_config(ctx)
    pp3_path = Path(profile_path)

    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    import shutil

    dest = config.custom_templates_dir / f"{name}.pp3"
    shutil.copy2(str(pp3_path), str(dest))

    return {
        "template_name": name,
        "template_path": str(dest),
        "description": description,
        "source_path": str(pp3_path),
    }


@mcp.tool()
async def create_template_from_description(
    ctx: Context,
    name: str,
    description: str,
    reference_image_path: str | None = None,
) -> dict[str, Any]:
    """Create a new PP3 template from a natural language style description.

    Use this to create a template when the user describes a look in words
    (e.g. "warm golden hour tones, film-like grain"). You (Claude) interpret
    the description and call generate_pp3_profile with appropriate parameters.
    This tool creates a neutral base template with the given name and description.
    Params: name, description, reference_image_path
    """
    config = get_config(ctx)
    templates_dir = _get_templates_dir()

    profile, output_path = _generate_profile(
        name=name,
        base_template=None,
        parameters=None,
        device_preset=None,
        templates_dir=templates_dir,
        custom_templates_dir=config.custom_templates_dir,
    )

    result: dict[str, Any] = {
        "template_name": name,
        "template_path": str(output_path),
        "description": description,
        "reference_image_path": reference_image_path,
        "note": "Template created with neutral settings. Use adjust_profile to refine parameters.",
        "recommended_workflow": [
            "1. Use adjust_profile() to set processing parameters based on the description",
            "2. Use preview_raw() to verify the result visually",
            "3. Use save_template() to save the finalized profile",
        ],
        "summary": profile.to_dict(),
    }

    # If a reference image is provided, include EXIF-based recommendations
    if reference_image_path:
        ref_path = Path(reference_image_path)
        if ref_path.is_file():
            exif = read_exif_data(ref_path)
            if "error" not in exif:
                recs = generate_recommendations(exif)
                result["exif_recommendations"] = recs

    return result


@mcp.tool()
async def delete_template(ctx: Context, template_name: str) -> dict[str, Any]:
    """Delete a custom PP3 template.

    Use this to remove a custom template that is no longer needed.
    Built-in templates cannot be deleted.
    Params: template_name
    """
    config = get_config(ctx)
    templates_dir = _get_templates_dir()

    # Check if it's a built-in template
    builtin_path = templates_dir / f"{template_name}.pp3"
    if builtin_path.is_file():
        return {"error": f"Cannot delete built-in template '{template_name}'"}

    custom_path = config.custom_templates_dir / f"{template_name}.pp3"
    if not custom_path.is_file():
        return {"error": f"Custom template '{template_name}' not found"}

    custom_path.unlink()
    return {"deleted": template_name, "path": str(custom_path)}


@mcp.tool()
async def add_device_preset_tool(
    ctx: Context,
    preset_id: str,
    name: str,
    width: int,
    height: int,
    category: str = "custom",
) -> dict[str, Any]:
    """Create and persist a custom device/format preset for cropping and resizing.

    Use this to add a preset for a device or format not in the built-in list.
    Custom presets are saved to disk and available in future sessions.
    Params: preset_id, name, width, height, category
    """
    config = get_config(ctx)
    add_custom_preset(preset_id, name, width, height, category, config.custom_templates_dir)
    return {
        "preset_id": preset_id,
        "name": name,
        "width": width,
        "height": height,
        "category": category,
    }


@mcp.tool()
async def delete_device_preset(ctx: Context, preset_id: str) -> dict[str, Any]:
    """Delete a custom device preset.

    Use this to remove a custom device preset. Built-in presets cannot be deleted.
    Params: preset_id
    """
    if is_builtin_preset(preset_id):
        return {"error": f"Cannot delete built-in preset '{preset_id}'"}

    config = get_config(ctx)
    deleted = delete_custom_preset(preset_id, config.custom_templates_dir)
    if not deleted:
        return {"error": f"Custom preset '{preset_id}' not found"}

    return {"deleted": preset_id}


@mcp.tool()
async def batch_process(
    ctx: Context,
    file_paths: list[str],
    profile_path: str,
    output_format: str = "jpeg",
    output_dir: str | None = None,
    device_preset: str | None = None,
) -> dict[str, Any]:
    """Process multiple RAW files with the same PP3 profile.

    Use this for bulk processing of a set of RAW files with identical settings.
    Params: file_paths, profile_path, output_format, output_dir, device_preset
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    # Check for Crop+Resize conflict (RT 5.12 bug)
    base_check = PP3Profile()
    base_check.load(pp3_path)
    crop_resize_warning = _check_crop_resize_conflict(base_check)

    out_dir = Path(output_dir) if output_dir else config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Resolve device preset if specified
    preset_dict: dict[str, Any] | None = None
    if device_preset:
        preset_dict = get_preset(device_preset, config.custom_templates_dir)
        if preset_dict is None:
            return {"error": f"Device preset '{device_preset}' not found"}

    ext_map = {"jpeg": ".jpg", "tiff": ".tif", "png": ".png"}
    ext = ext_map.get(output_format.lower(), ".jpg")

    # Load the base profile once
    base_profile = PP3Profile()
    base_profile.load(pp3_path)

    results: list[dict[str, Any]] = []
    temp_paths: list[Path] = []

    for fp in file_paths:
        raw_path = Path(fp)
        if not raw_path.is_file():
            results.append({"file": fp, "error": f"File not found: {fp}"})
            continue

        # Build a SINGLE combined PP3 per file (RT 5.12 can't merge multiple PP3s)
        combined = PP3Profile()
        combined.load(pp3_path)

        if preset_dict:
            # Calculate per-file crop from source dimensions
            eff_w, eff_h = get_effective_dimensions(raw_path)

            if eff_w > 0 and eff_h > 0:
                apply_device_crop(combined, preset_dict, eff_w, eff_h)
            else:
                from rawtherapee_mcp.pp3_generator import apply_device_preset as _apply_preset

                _apply_preset(combined, preset_dict)

        ts = int(time.time() * 1000)
        combined_path = config.preview_dir / f"_batch_{raw_path.stem}_{ts}.pp3"
        combined.save(combined_path)
        temp_paths.append(combined_path)

        output_path = out_dir / f"{raw_path.stem}{ext}"
        result = await run_rt_cli(
            rt_path=rt_check,
            input_path=raw_path,
            output_path=output_path,
            profiles=[combined_path],
            output_format=output_format,
            jpeg_quality=config.default_jpeg_quality,
        )
        result["file"] = fp
        results.append(result)

    # Clean up per-file temp PP3s
    for tp in temp_paths:
        try:
            tp.unlink(missing_ok=True)
        except OSError:
            pass

    succeeded = sum(1 for r in results if r.get("success"))
    failed = len(results) - succeeded

    batch_result: dict[str, Any] = {
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
    }
    if crop_resize_warning:
        batch_result["warning"] = crop_resize_warning
    return batch_result


@mcp.tool()
async def list_output_files(
    ctx: Context,
    directory: str | None = None,
    format_filter: str | None = None,
) -> dict[str, Any]:
    """List processed output files in the output directory.

    Use this to see what images have been processed and are available.
    Params: directory, format_filter (jpeg, tiff, png)
    """
    config = get_config(ctx)
    dir_path = Path(directory) if directory else config.output_dir

    if not dir_path.is_dir():
        return {"error": f"Directory not found: {dir_path}"}

    ext_filter: set[str] | None = None
    if format_filter:
        filter_map: dict[str, set[str]] = {
            "jpeg": {".jpg", ".jpeg"},
            "tiff": {".tif", ".tiff"},
            "png": {".png"},
        }
        ext_filter = filter_map.get(format_filter.lower())
        if ext_filter is None:
            return {"error": f"Unknown format filter: {format_filter}. Use 'jpeg', 'tiff', or 'png'."}

    files: list[dict[str, Any]] = []
    image_exts = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}

    for file_path in sorted(dir_path.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in image_exts:
            continue
        if ext_filter and file_path.suffix.lower() not in ext_filter:
            continue

        stat = file_path.stat()
        files.append(
            {
                "path": str(file_path),
                "filename": file_path.name,
                "size": stat.st_size,
                "format": file_path.suffix.lower().lstrip("."),
                "modified": stat.st_mtime,
            }
        )

    return {"files": files, "count": len(files), "directory": str(dir_path)}


@mcp.tool()
async def get_image_info(
    ctx: Context,
    file_path: str,
    include_thumbnail: bool = True,
    thumbnail_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Get technical information about a processed image file.

    Use this to check dimensions, format, file size, and bit depth of
    JPEG, TIFF, or PNG output files. When include_thumbnail is True,
    returns an inline thumbnail for visual verification.
    Params: file_path, include_thumbnail, thumbnail_max_width
    """
    path = Path(file_path)
    # Brief delay to allow file handle release after recent processing
    await asyncio.sleep(0.5)
    try:
        info = await asyncio.wait_for(
            asyncio.to_thread(_get_image_info, path),
            timeout=10.0,
        )
    except TimeoutError:
        return {"error": f"Timeout reading {file_path} — file may be locked by another process"}

    if include_thumbnail and "error" not in info:
        try:
            thumb_bytes = await asyncio.to_thread(generate_thumbnail, path, thumbnail_max_width)
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(info, indent=2)),
                    MCPImage(data=thumb_bytes, format="jpeg").to_image_content(),
                ],
                structured_content=info,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Thumbnail generation failed for %s", file_path, exc_info=True)

    return info


# ---------------------------------------------------------------------------
# Phase 5 Tools — Visual Analysis & Advanced Processing
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_histogram(
    ctx: Context,
    file_path: str,
    include_svg: bool = True,
) -> dict[str, Any]:
    """Compute RGB histogram and image statistics for a processed image.

    Analyzes the tonal distribution of a JPEG, TIFF, or PNG image. Returns
    per-channel histograms (256 bins), statistics (mean, median, std_dev,
    min, max), and clipping percentages. Optionally includes an SVG
    visualization.
    Params: file_path, include_svg
    """
    path = Path(file_path)
    if not path.is_file():
        return {"error": f"Image not found: {file_path}"}

    try:
        data = await asyncio.to_thread(compute_histogram, path)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Histogram computation failed: {exc}"}

    result: dict[str, Any] = {
        "file_path": str(path),
        "statistics": data["statistics"],
        "clipping": data["clipping"],
        "total_pixels": data["total_pixels"],
    }

    if include_svg:
        result["svg"] = render_histogram_svg(data)

    return result


@mcp.tool()
async def preview_before_after(
    ctx: Context,
    file_path: str,
    profile_path: str,
    max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Generate before/after preview images to compare processing effects.

    Renders a RAW file twice: once with default (neutral) settings and once
    with the specified profile. Returns both images inline for the LLM to
    visually compare the difference.
    Params: file_path, profile_path, max_width
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    # Render "before" (neutral profile — no Locallab, safe to use PP3Profile)
    before_profile = PP3Profile()
    before_result = await _render_preview(config, raw_path, before_profile, max_width=max_width, label="before")

    # Render "after" — pass Path to avoid parser crash on Locallab profiles
    after_result = await _render_preview(config, raw_path, pp3_path, max_width=max_width, label="after")

    metadata: dict[str, Any] = {
        "file_path": str(raw_path),
        "profile_path": str(pp3_path),
        "before": before_result,
        "after": after_result,
    }

    # Return with inline images if both succeeded
    if before_result.get("success") and after_result.get("success"):
        try:
            img_before = await _preview_to_image_content(before_result["preview_path"], max_width)
            img_after = await _preview_to_image_content(after_result["preview_path"], max_width)
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(metadata, indent=2)),
                    img_before,
                    img_after,
                ],
                structured_content=metadata,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Image return failed for before/after preview", exc_info=True)

    return metadata


@mcp.tool()
async def adjust_crop_position(
    ctx: Context,
    profile_path: str,
    file_path: str,
    horizontal: str = "center",
    vertical: str = "center",
    include_preview: bool = True,
    preview_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Reposition an existing crop within the source image bounds.

    Moves the crop area defined in a PP3 profile to a new position. Accepts
    named positions ('left', 'center', 'right' for horizontal; 'top',
    'center', 'bottom' for vertical) or pixel offsets as strings.
    The profile is updated in-place.
    Params: profile_path, file_path, horizontal, vertical, include_preview,
    preview_max_width
    """
    config = get_config(ctx)

    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    profile = PP3Profile()
    profile.load(pp3_path)

    if profile.get("Crop", "Enabled") != "true":
        return {"error": "No crop is enabled in this profile"}

    try:
        crop_w = int(profile.get("Crop", "W"))
        crop_h = int(profile.get("Crop", "H"))
    except (ValueError, KeyError):
        return {"error": "Could not read crop dimensions from profile"}

    if crop_w <= 0 or crop_h <= 0:
        return {"error": f"Invalid crop dimensions: {crop_w}x{crop_h}"}

    # Get source image dimensions
    src_w, src_h = get_effective_dimensions(raw_path)
    if src_w == 0 or src_h == 0:
        return {"error": f"Could not determine source image dimensions for {file_path}"}

    # Calculate new X position
    max_x = max(0, src_w - crop_w)
    if horizontal == "left":
        new_x = 0
    elif horizontal == "center":
        new_x = max_x // 2
    elif horizontal == "right":
        new_x = max_x
    else:
        try:
            new_x = max(0, min(int(horizontal), max_x))
        except ValueError:
            return {"error": f"Invalid horizontal position: {horizontal}"}

    # Calculate new Y position
    max_y = max(0, src_h - crop_h)
    if vertical == "top":
        new_y = 0
    elif vertical == "center":
        new_y = max_y // 2
    elif vertical == "bottom":
        new_y = max_y
    else:
        try:
            new_y = max(0, min(int(vertical), max_y))
        except ValueError:
            return {"error": f"Invalid vertical position: {vertical}"}

    # Update profile in-place
    profile.set("Crop", "X", str(new_x))
    profile.set("Crop", "Y", str(new_y))
    profile.save(pp3_path)

    result: dict[str, Any] = {
        "profile_path": str(pp3_path),
        "crop_x": new_x,
        "crop_y": new_y,
        "crop_w": crop_w,
        "crop_h": crop_h,
        "source_width": src_w,
        "source_height": src_h,
    }

    if include_preview:
        rt_check = _require_rt(config)
        if isinstance(rt_check, dict):
            return result

        # Profile was just saved to pp3_path — pass Path to avoid parser
        # issues on re-load (e.g. Locallab sections)
        preview_result = await _render_preview(config, raw_path, pp3_path, max_width=preview_max_width, label="crop")
        result["preview"] = preview_result

        if preview_result.get("success"):
            try:
                img = await _preview_to_image_content(preview_result["preview_path"], preview_max_width)
                return ToolResult(
                    content=[
                        TextContent(type="text", text=json.dumps(result, indent=2)),
                        img,
                    ],
                    structured_content=result,
                )
            except Exception:  # noqa: BLE001
                logger.debug("Image return failed for crop preview", exc_info=True)

    return result


@mcp.tool()
async def preview_exposure_bracket(
    ctx: Context,
    file_path: str,
    profile_path: str | None = None,
    stops: list[float] | None = None,
    max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Simulate exposure bracketing by rendering multiple EV previews.

    Generates preview images at different exposure compensation values.
    Useful for determining the optimal exposure before committing to a
    full-resolution render.
    Params: file_path, profile_path, stops, max_width
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    if stops is None:
        stops = [-1.0, 0.0, 1.0]

    # Load base profile
    base_profile = PP3Profile()
    if profile_path:
        pp3_path = Path(profile_path)
        if not pp3_path.is_file():
            return {"error": f"Profile not found: {profile_path}"}
        base_profile.load(pp3_path)

    # Get current exposure compensation
    base_comp_str = base_profile.get("Exposure", "Compensation")
    try:
        base_comp = float(base_comp_str) if base_comp_str else 0.0
    except ValueError:
        base_comp = 0.0

    previews: list[dict[str, Any]] = []
    image_contents: list[Any] = []

    for stop in stops:
        variant = base_profile.copy()
        variant.set("Exposure", "Compensation", str(base_comp + stop))

        label = f"ev{stop:+.1f}".replace(".", "_").replace("+", "p").replace("-", "m")
        result = await _render_preview(config, raw_path, variant, max_width=max_width, label=label)
        result["ev_offset"] = stop
        result["total_compensation"] = base_comp + stop
        previews.append(result)

        if result.get("success"):
            try:
                image_contents.append(await _preview_to_image_content(result["preview_path"], max_width))
            except Exception:  # noqa: BLE001
                logger.debug("Image return failed for EV %+.1f", stop, exc_info=True)

    metadata: dict[str, Any] = {
        "file_path": str(raw_path),
        "base_compensation": base_comp,
        "stops": stops,
        "previews": previews,
    }

    if image_contents:
        try:
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(metadata, indent=2)),
                    *image_contents,
                ],
                structured_content=metadata,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ToolResult creation failed for exposure bracket", exc_info=True)

    return metadata


_WB_TEMPERATURES: dict[str, int] = {
    "Daylight": 5500,
    "Cloudy": 6500,
    "Shade": 7500,
    "Tungsten": 3200,
    "Fluorescent": 4000,
    "Flash": 5500,
    "Camera": 0,
    "Auto": 0,
    "Custom": 0,
}


@mcp.tool()
async def preview_white_balance(
    ctx: Context,
    file_path: str,
    profile_path: str | None = None,
    presets: list[str] | None = None,
    max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Preview different white balance presets on a RAW file.

    Renders the same image with multiple white balance settings so the LLM
    can compare and recommend the best one. Each preview includes an
    approximate Kelvin temperature for reference.
    Params: file_path, profile_path, presets, max_width
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    if presets is None:
        presets = ["Daylight", "Cloudy", "Shade", "Tungsten", "Fluorescent"]

    base_profile = PP3Profile()
    if profile_path:
        pp3_path = Path(profile_path)
        if not pp3_path.is_file():
            return {"error": f"Profile not found: {profile_path}"}
        base_profile.load(pp3_path)

    previews: list[dict[str, Any]] = []
    image_contents: list[Any] = []

    for preset_name in presets:
        variant = base_profile.copy()
        variant.set("White Balance", "Setting", preset_name)

        label = f"wb_{preset_name.lower()}"
        result = await _render_preview(config, raw_path, variant, max_width=max_width, label=label)
        result["wb_preset"] = preset_name
        result["temperature_k"] = _WB_TEMPERATURES.get(preset_name, 0)
        previews.append(result)

        if result.get("success"):
            try:
                image_contents.append(await _preview_to_image_content(result["preview_path"], max_width))
            except Exception:  # noqa: BLE001
                logger.debug("Image return failed for WB %s", preset_name, exc_info=True)

    metadata: dict[str, Any] = {
        "file_path": str(raw_path),
        "presets": presets,
        "previews": previews,
    }

    if image_contents:
        try:
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(metadata, indent=2)),
                    *image_contents,
                ],
                structured_content=metadata,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ToolResult creation failed for WB preview", exc_info=True)

    return metadata


@mcp.tool()
async def export_multi_device(
    ctx: Context,
    file_path: str,
    profile_path: str,
    device_presets: list[str],
    output_format: str = "jpeg",
    output_dir: str | None = None,
    include_previews: bool = False,
    preview_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Export a RAW file optimized for multiple devices in one call.

    Processes the same RAW file with device-specific crop/resize for each
    target device. Output filenames include the device name. Set
    include_previews=True to return inline thumbnails per export.
    Params: file_path, profile_path, device_presets, output_format, output_dir,
    include_previews, preview_max_width
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"RAW file not found: {file_path}"}

    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    out_dir = Path(output_dir) if output_dir else config.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    ext_map = {"jpeg": ".jpg", "tiff": ".tif", "png": ".png"}
    ext = ext_map.get(output_format.lower(), ".jpg")

    base_profile = PP3Profile()
    base_profile.load(pp3_path)

    # Get source dimensions once
    src_w, src_h = get_effective_dimensions(raw_path)

    results: list[dict[str, Any]] = []
    temp_paths: list[Path] = []
    image_contents: list[Any] = []

    for preset_name in device_presets:
        preset_dict = get_preset(preset_name, config.custom_templates_dir)
        if preset_dict is None:
            results.append({"device": preset_name, "error": f"Device preset '{preset_name}' not found"})
            continue

        combined = base_profile.copy()

        if src_w > 0 and src_h > 0:
            apply_device_crop(combined, preset_dict, src_w, src_h)
        else:
            from rawtherapee_mcp.pp3_generator import apply_device_preset as _apply_preset

            _apply_preset(combined, preset_dict)

        ts = int(time.time() * 1000)
        combined_path = config.preview_dir / f"_multi_{preset_name}_{ts}.pp3"
        combined.save(combined_path)
        temp_paths.append(combined_path)

        safe_name = preset_name.replace(" ", "_").lower()
        output_path = out_dir / f"{raw_path.stem}_{safe_name}{ext}"

        result = await run_rt_cli(
            rt_path=rt_check,
            input_path=raw_path,
            output_path=output_path,
            profiles=[combined_path],
            output_format=output_format,
            jpeg_quality=config.default_jpeg_quality,
        )
        result["device"] = preset_name
        results.append(result)

        if include_previews and result.get("success") and result.get("output_path"):
            try:
                image_contents.append(await _preview_to_image_content(result["output_path"], preview_max_width))
            except Exception:  # noqa: BLE001
                logger.debug("Thumbnail failed for %s export", preset_name, exc_info=True)

    # Clean up temp PP3s
    for tp in temp_paths:
        try:
            tp.unlink(missing_ok=True)
        except OSError:
            pass

    succeeded = sum(1 for r in results if r.get("success"))
    metadata: dict[str, Any] = {
        "file_path": str(raw_path),
        "results": results,
        "total": len(results),
        "succeeded": succeeded,
        "failed": len(results) - succeeded,
    }

    if image_contents:
        try:
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(metadata, indent=2)),
                    *image_contents,
                ],
                structured_content=metadata,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ToolResult creation failed for export_multi_device", exc_info=True)

    return metadata


@mcp.tool()
async def batch_preview(
    ctx: Context,
    file_paths: list[str],
    profile_path: str | None = None,
    max_width: int = 300,
    max_images: int = 12,
    include_exif: bool = False,
) -> dict[str, Any] | ToolResult:
    """Generate small preview thumbnails for multiple RAW files.

    Creates a batch of preview images for quick visual scanning. Useful for
    selecting images from a series or verifying batch settings before
    full-resolution processing. Set include_exif=True to attach a short EXIF
    summary (ISO, aperture, shutter speed, focal length) per image.
    Params: file_paths, profile_path, max_width, max_images, include_exif
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    # When a profile path is given, pass Path to avoid parser crash on
    # Locallab profiles.  Without a path, use empty PP3Profile.
    base_profile: PP3Profile | Path
    if profile_path:
        pp3_path = Path(profile_path)
        if not pp3_path.is_file():
            return {"error": f"Profile not found: {profile_path}"}
        base_profile = pp3_path
    else:
        base_profile = PP3Profile()

    capped = file_paths[:max_images]
    previews: list[dict[str, Any]] = []
    image_contents: list[Any] = []

    for fp in capped:
        raw_path = Path(fp)
        if not raw_path.is_file():
            previews.append({"file": fp, "error": f"File not found: {fp}"})
            continue

        result = await _render_preview(config, raw_path, base_profile, max_width=max_width, label="batch")
        result["file"] = fp

        if include_exif:
            exif = read_exif_data(raw_path)
            if "error" not in exif:
                result["exif_summary"] = {
                    "iso": exif.get("iso", ""),
                    "aperture": exif.get("aperture", ""),
                    "shutter_speed": exif.get("shutter_speed", ""),
                    "focal_length": exif.get("focal_length", ""),
                }

        previews.append(result)

        if result.get("success"):
            try:
                image_contents.append(await _preview_to_image_content(result["preview_path"], max_width))
            except Exception:  # noqa: BLE001
                logger.debug("Image return failed for batch preview %s", fp, exc_info=True)

    metadata: dict[str, Any] = {
        "previews": previews,
        "total": len(capped),
        "succeeded": sum(1 for p in previews if p.get("success")),
        "capped": len(file_paths) > max_images,
    }

    if image_contents:
        try:
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(metadata, indent=2)),
                    *image_contents,
                ],
                structured_content=metadata,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ToolResult creation failed for batch preview", exc_info=True)

    return metadata


@mcp.tool()
async def analyze_image(
    ctx: Context,
    file_path: str,
    include_histogram: bool = True,
    include_thumbnail: bool = True,
    thumbnail_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Comprehensive single-call analysis of a RAW or processed image.

    Combines EXIF metadata, structured processing recommendations, histogram
    statistics, and an inline thumbnail into one response. Use this for the
    initial assessment of an image before deciding on processing settings.
    Params: file_path, include_histogram, include_thumbnail, thumbnail_max_width
    """
    path = Path(file_path)
    if not path.is_file():
        return {"error": f"Image not found: {file_path}"}

    result: dict[str, Any] = {"file_path": str(path)}

    # EXIF data + recommendations
    exif = read_exif_data(path)
    result["exif"] = exif
    if "error" not in exif:
        result["recommendations"] = generate_recommendations(exif)

    # Histogram
    if include_histogram:
        try:
            hist_data = await asyncio.to_thread(compute_histogram, path)
            result["histogram"] = {
                "statistics": hist_data["statistics"],
                "clipping": hist_data["clipping"],
                "total_pixels": hist_data["total_pixels"],
                "svg": render_histogram_svg(hist_data),
            }
        except Exception:  # noqa: BLE001
            logger.debug("Histogram failed for %s", path, exc_info=True)

    # Thumbnail
    if include_thumbnail:
        try:
            thumb_bytes = await asyncio.to_thread(generate_thumbnail, path, thumbnail_max_width)
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(result, indent=2)),
                    MCPImage(data=thumb_bytes, format="jpeg").to_image_content(),
                ],
                structured_content=result,
            )
        except Exception:  # noqa: BLE001
            logger.debug("Thumbnail failed for %s", path, exc_info=True)

    return result


@mcp.tool()
async def interpolate_profiles(
    ctx: Context,
    profile_a: str,
    profile_b: str,
    factor: float = 0.5,
    output_name: str = "interpolated",
    file_path: str | None = None,
    include_preview: bool = False,
    preview_max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Blend two PP3 profiles by linear interpolation.

    Numeric values are interpolated (factor=0.0 gives profile A, factor=1.0
    gives profile B). Non-numeric values are taken from the nearer profile.
    Useful for creating intermediate looks between two processing styles.
    Params: profile_a, profile_b, factor, output_name, file_path,
    include_preview, preview_max_width
    """
    config = get_config(ctx)

    path_a = Path(profile_a)
    path_b = Path(profile_b)

    if not path_a.is_file():
        return {"error": f"Profile A not found: {profile_a}"}
    if not path_b.is_file():
        return {"error": f"Profile B not found: {profile_b}"}

    prof_a = PP3Profile()
    prof_a.load(path_a)
    prof_b = PP3Profile()
    prof_b.load(path_b)

    interpolated = PP3Profile.interpolate(prof_a, prof_b, factor)

    output_path = config.output_dir / f"{output_name}.pp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    interpolated.save(output_path)

    result: dict[str, Any] = {
        "profile_a": str(path_a),
        "profile_b": str(path_b),
        "factor": factor,
        "output_path": str(output_path),
        "summary": interpolated.to_dict(),
    }

    if include_preview and file_path:
        rt_check = _require_rt(config)
        if not isinstance(rt_check, dict):
            raw_path = Path(file_path)
            if raw_path.is_file():
                width = preview_max_width
                preview_result = await _render_preview(config, raw_path, interpolated, max_width=width, label="interp")
                result["preview"] = preview_result
                if preview_result.get("success"):
                    try:
                        img_content = await _preview_to_image_content(preview_result["preview_path"], width)
                        return ToolResult(
                            content=[
                                TextContent(type="text", text=json.dumps(result, indent=2)),
                                img_content,
                            ],
                            structured_content=result,
                        )
                    except Exception:  # noqa: BLE001
                        logger.debug("Preview failed for interpolated profile", exc_info=True)

    return result


@mcp.tool()
async def batch_analyze(
    ctx: Context,
    file_paths: list[str],
    max_images: int = 20,
    include_thumbnails: bool = True,
    thumbnail_max_width: int = 200,
) -> dict[str, Any] | ToolResult:
    """Batch analysis of multiple images with EXIF, recommendations, and stats.

    A lightweight alternative to calling analyze_image N times. Returns per-image
    EXIF data, processing recommendations, and summary histogram statistics
    (mean, clipping) without full 256-bin channel data or SVG. Optionally
    includes small thumbnails.
    Params: file_paths, max_images, include_thumbnails, thumbnail_max_width
    """
    capped = file_paths[:max_images]
    analyses: list[dict[str, Any]] = []
    image_contents: list[Any] = []

    for fp in capped:
        path = Path(fp)
        entry: dict[str, Any] = {"file_path": fp}

        if not path.is_file():
            entry["error"] = f"File not found: {fp}"
            analyses.append(entry)
            continue

        # EXIF + recommendations
        exif = read_exif_data(path)
        entry["exif"] = exif
        if "error" not in exif:
            entry["recommendations"] = generate_recommendations(exif)

        # Lightweight histogram stats (no full channel data, no SVG)
        try:
            hist_data = await asyncio.to_thread(compute_histogram, path)
            entry["histogram_summary"] = {
                "statistics": hist_data["statistics"],
                "clipping": hist_data["clipping"],
                "total_pixels": hist_data["total_pixels"],
            }
        except Exception:  # noqa: BLE001
            logger.debug("Histogram failed for %s", fp, exc_info=True)

        analyses.append(entry)

        # Optional small thumbnail
        if include_thumbnails:
            try:
                thumb_bytes = await asyncio.to_thread(generate_thumbnail, path, thumbnail_max_width)
                image_contents.append(MCPImage(data=thumb_bytes, format="jpeg").to_image_content())
            except Exception:  # noqa: BLE001
                logger.debug("Thumbnail failed for %s", fp, exc_info=True)

    metadata: dict[str, Any] = {
        "analyses": analyses,
        "total": len(capped),
        "capped": len(file_paths) > max_images,
    }

    if image_contents:
        try:
            return ToolResult(
                content=[
                    TextContent(type="text", text=json.dumps(metadata, indent=2)),
                    *image_contents,
                ],
                structured_content=metadata,
            )
        except Exception:  # noqa: BLE001
            logger.debug("ToolResult creation failed for batch_analyze", exc_info=True)

    return metadata


# ---------------------------------------------------------------------------
# Locallab — Luminance-based Local Adjustments
# ---------------------------------------------------------------------------


@mcp.tool()
async def add_luminance_adjustment(
    ctx: Context,
    profile_path: str,
    adjustment_type: str,
    parameters: dict[str, Any],
    luminance_range: dict[str, int] | None = None,
    transition: int = 30,
    strength: int = 100,
    spot_name: str | None = None,
    save_as: str | None = None,
) -> dict[str, Any]:
    """Add a luminance-based local adjustment to a PP3 profile.

    Creates a Locallab spot that targets a specific luminance range (shadows,
    midtones, highlights, or custom). The adjustment only affects pixels
    within the specified brightness range, enabling selective edits like
    shadow recovery or highlight compression without affecting the rest.

    adjustment_type: "shadows" (0-30%), "midtones" (25-75%),
    "highlights" (70-100%), or "custom" (requires luminance_range).

    parameters: Processing adjustments to apply in the selected range.
    Keys: exposure (-2 to +2 EV), contrast (-100 to +100),
    saturation (-100 to +100), brightness (-100 to +100), black (0-500),
    highlight_compression (0-500), sharpening (0-100), denoise_luma (0-100),
    denoise_chroma (0-100), white_balance_shift (Kelvin, -500 to +500).

    luminance_range (custom only): {"lower": 0-100, "upper": 0-100,
    "lower_transition": 0-100, "upper_transition": 0-100}.

    Params: profile_path, adjustment_type, parameters, luminance_range,
    transition, strength, spot_name, save_as
    """
    path = Path(profile_path)
    if not path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(path)

    try:
        idx = add_spot(
            profile,
            adjustment_type=adjustment_type,
            parameters=parameters,
            luminance_range=luminance_range,
            transition=transition,
            strength=strength,
            spot_name=spot_name,
        )
    except ValueError as exc:
        return {"error": str(exc)}

    out_path = Path(save_as) if save_as else path
    profile.save(out_path)

    spot_info = read_spot(profile, idx)
    return {
        "profile_path": str(out_path),
        "spot_index": idx,
        "spot_name": spot_info["name"] if spot_info else spot_name,
        "adjustment_type": adjustment_type,
        "luminance_range": spot_info.get("luminance_range") if spot_info else None,
        "parameters_applied": parameters,
        "total_spots": get_spot_count(profile),
    }


@mcp.tool()
async def preview_luminance_mask(
    ctx: Context,
    file_path: str,
    profile_path: str,
    spot_index: int = 0,
    max_width: int = 600,
) -> dict[str, Any] | ToolResult:
    """Preview a luminance mask showing which image areas are affected by a local adjustment.

    Generates a grayscale mask image: white = full effect, black = no effect,
    gray = transition zone. Use this to verify the luminance range targets
    the correct tonal areas before processing.

    Params: file_path, profile_path, spot_index, max_width
    """
    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"Image file not found: {file_path}"}

    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(pp3_path)

    spot = read_spot(profile, spot_index)
    if spot is None:
        return {"error": f"Spot index {spot_index} not found (total: {get_spot_count(profile)})"}

    lum_range = spot.get("luminance_range")
    if lum_range is None:
        return {"error": "Could not determine luminance range for this spot"}

    # Generate mask preview using Pillow
    try:
        mask_bytes = await asyncio.to_thread(_generate_mask_preview, raw_path, lum_range, max_width)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Mask preview generation failed", exc_info=True)
        return {"error": f"Failed to generate mask preview: {exc}"}

    metadata: dict[str, Any] = {
        "spot_index": spot_index,
        "spot_name": spot["name"],
        "luminance_range": lum_range,
        "adjustment_type": spot["type"],
    }

    try:
        return ToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata, indent=2)),
                MCPImage(data=mask_bytes, format="jpeg").to_image_content(),
            ],
            structured_content=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.debug("ToolResult creation failed for mask preview", exc_info=True)
        return metadata


def _generate_mask_preview(
    image_path: Path,
    lum_range: dict[str, int],
    max_width: int,
) -> bytes:
    """Generate a grayscale luminance mask preview image.

    Args:
        image_path: Path to the source image.
        lum_range: Dict with lower/upper keys (0-100 scale).
        max_width: Maximum output dimension.

    Returns:
        JPEG bytes of the mask image.
    """
    import io

    from PIL import Image, ImageOps

    lower = lum_range.get("lower", 0) / 100.0 * 255.0
    upper = lum_range.get("upper", 100) / 100.0 * 255.0

    with Image.open(image_path) as file_img:
        img: Image.Image = ImageOps.exif_transpose(file_img) or file_img

        # Resize first for performance
        w, h = img.size
        if max(w, h) > max_width:
            scale = max_width / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)

        # Convert to grayscale (luminance)
        gray = img.convert("L")

        # Build mask: pixels in range -> white, outside -> black
        pixels = list(gray.getdata())
        mask_data = []
        for p in pixels:
            if lower <= p <= upper:
                mask_data.append(255)
            elif p < lower:
                # Transition zone below
                dist = lower - p
                if dist < 30:  # ~12% transition
                    mask_data.append(int(255 * (1.0 - dist / 30.0)))
                else:
                    mask_data.append(0)
            else:
                # Transition zone above
                dist = p - upper
                if dist < 30:
                    mask_data.append(int(255 * (1.0 - dist / 30.0)))
                else:
                    mask_data.append(0)

        mask_img = Image.new("L", gray.size)
        mask_img.putdata(mask_data)

        buf = io.BytesIO()
        mask_img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()


@mcp.tool()
async def list_local_adjustments(
    ctx: Context,
    profile_path: str,
) -> dict[str, Any]:
    """List all Locallab (local adjustment) spots in a PP3 profile.

    Shows each spot's name, type, luminance range, active parameters,
    and enabled state. Use this to inspect the local adjustments before
    previewing or modifying them.

    Params: profile_path
    """
    path = Path(profile_path)
    if not path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(path)

    count = get_spot_count(profile)
    spots: list[dict[str, Any]] = []
    for i in range(count):
        spot = read_spot(profile, i)
        if spot is not None:
            spots.append(spot)

    return {
        "profile_path": profile_path,
        "total_spots": count,
        "spots": spots,
    }


@mcp.tool()
async def adjust_local_spot(
    ctx: Context,
    profile_path: str,
    spot_index: int,
    parameters: dict[str, Any] | None = None,
    luminance_range: dict[str, int] | None = None,
    strength: int | None = None,
    enabled: bool | None = None,
    save_as: str | None = None,
) -> dict[str, Any]:
    """Modify parameters of an existing Locallab spot in a PP3 profile.

    Change processing parameters, luminance range, strength, or
    enable/disable a spot without removing and re-adding it.

    Params: profile_path, spot_index, parameters, luminance_range,
    strength, enabled, save_as
    """
    path = Path(profile_path)
    if not path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(path)

    if not update_spot(profile, spot_index, parameters, luminance_range, strength, enabled):
        return {"error": f"Spot index {spot_index} not found (total: {get_spot_count(profile)})"}

    out_path = Path(save_as) if save_as else path
    profile.save(out_path)

    spot = read_spot(profile, spot_index)
    return {
        "profile_path": str(out_path),
        "spot_index": spot_index,
        "updated": spot if spot else {},
        "total_spots": get_spot_count(profile),
    }


@mcp.tool()
async def remove_local_adjustment(
    ctx: Context,
    profile_path: str,
    spot_index: int,
    save_as: str | None = None,
) -> dict[str, Any]:
    """Remove a Locallab spot from a PP3 profile.

    Deletes the spot at the given index and re-indexes remaining spots.

    Params: profile_path, spot_index, save_as
    """
    path = Path(profile_path)
    if not path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(path)

    old_count = get_spot_count(profile)
    if not remove_spot(profile, spot_index):
        return {"error": f"Spot index {spot_index} not found (total: {old_count})"}

    out_path = Path(save_as) if save_as else path
    profile.save(out_path)

    return {
        "profile_path": str(out_path),
        "removed_index": spot_index,
        "total_spots": get_spot_count(profile),
    }


@mcp.tool()
async def preview_with_adjustments(
    ctx: Context,
    file_path: str,
    profile_path: str,
    max_width: int = 600,
    include_histogram: bool = False,
) -> dict[str, Any] | ToolResult:
    """Preview a RAW file with all active local adjustments applied.

    Renders a preview JPEG using RT CLI with the full profile including
    Locallab spots. Optionally includes histogram statistics for the
    processed result. Use this after add_luminance_adjustment or
    apply_local_preset to verify the effect visually.

    Params: file_path, profile_path, max_width, include_histogram
    """
    config = get_config(ctx)
    rt_check = _require_rt(config)
    if isinstance(rt_check, dict):
        return rt_check

    raw_path = Path(file_path)
    if not raw_path.is_file():
        return {"error": f"Image file not found: {file_path}"}

    pp3_path = Path(profile_path)
    if not pp3_path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    # Pass Path to _render_preview to avoid parser crash on Locallab profiles.
    # Load PP3Profile separately only for spot metadata reading.
    profile = PP3Profile()
    profile.load(pp3_path)
    spot_count = get_spot_count(profile)

    preview_result = await _render_preview(config, raw_path, pp3_path, max_width=max_width, label="localadj")

    if not preview_result.get("success"):
        return preview_result

    preview_path = preview_result["preview_path"]

    # Build metadata
    spots_summary: list[dict[str, Any]] = []
    for i in range(spot_count):
        spot = read_spot(profile, i)
        if spot:
            spots_summary.append(
                {
                    "index": spot["index"],
                    "name": spot["name"],
                    "type": spot["type"],
                    "enabled": spot["enabled"],
                }
            )

    metadata: dict[str, Any] = {
        "success": True,
        "preview_path": preview_path,
        "active_spots": spot_count,
        "spots": spots_summary,
    }

    # Optional histogram
    if include_histogram:
        try:
            hist_data = await asyncio.to_thread(compute_histogram, Path(preview_path))
            metadata["histogram"] = {
                "statistics": hist_data["statistics"],
                "clipping": hist_data["clipping"],
            }
        except Exception:  # noqa: BLE001
            logger.debug("Histogram failed for preview", exc_info=True)

    # Thumbnail for inline display
    try:
        thumb = await _preview_to_image_content(preview_path, max_width)
        return ToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata, indent=2)),
                thumb,
            ],
            structured_content=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.debug("Thumbnail creation failed for preview_with_adjustments", exc_info=True)
        return metadata


@mcp.tool()
async def apply_local_preset(
    ctx: Context,
    profile_path: str,
    preset: str,
    intensity: int = 50,
    save_as: str | None = None,
) -> dict[str, Any]:
    """Apply a predefined local adjustment preset to a PP3 profile.

    Available presets: shadow_recovery, highlight_protection,
    split_tone_warm_cool, midtone_contrast, shadow_desaturation,
    amoled_optimize, hdr_natural.

    intensity scales all parameters: 50 = default, 25 = half, 100 = double.

    Params: profile_path, preset, intensity, save_as
    """
    path = Path(profile_path)
    if not path.is_file():
        return {"error": f"Profile not found: {profile_path}"}

    profile = PP3Profile()
    profile.load(path)

    preset_info = get_local_preset(preset)
    if preset_info is None:
        available = list_local_presets()
        return {
            "error": f"Unknown preset: {preset!r}",
            "available_presets": available,
        }

    try:
        indices = apply_preset(profile, preset, intensity)
    except ValueError as exc:
        return {"error": str(exc)}

    out_path = Path(save_as) if save_as else path
    profile.save(out_path)

    # Read back the spots we just added
    spots: list[dict[str, Any]] = []
    for idx in indices:
        spot = read_spot(profile, idx)
        if spot:
            spots.append(spot)

    return {
        "profile_path": str(out_path),
        "preset": preset,
        "description": preset_info["description"],
        "intensity": intensity,
        "spots_added": spots,
        "total_spots": get_spot_count(profile),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the RawTherapee MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
