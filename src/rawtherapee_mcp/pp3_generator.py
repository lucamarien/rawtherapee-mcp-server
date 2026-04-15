"""PP3 profile generation from parameter dictionaries.

Maps user-friendly parameter names to RawTherapee PP3 section/key pairs
and generates complete profiles from templates or neutral defaults.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rawtherapee_mcp.pp3_parser import PP3Profile

logger = logging.getLogger("rawtherapee_mcp")

# Mapping of friendly parameter paths to PP3 [Section] Key pairs
_PARAMETER_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "exposure": {
        "compensation": ("Exposure", "Compensation"),
        "brightness": ("Exposure", "Brightness"),
        "contrast": ("Exposure", "Contrast"),
        "saturation": ("Exposure", "Saturation"),
        "black": ("Exposure", "Black"),
        "highlight_compression": ("Exposure", "HighlightCompr"),
        "highlightcompression": ("Exposure", "HighlightCompr"),
        "auto": ("Exposure", "Auto"),
    },
    "white_balance": {
        "method": ("White Balance", "Setting"),
        "temperature": ("White Balance", "Temperature"),
        "green": ("White Balance", "Green"),
    },
    "whitebalance": {
        "method": ("White Balance", "Setting"),
        "temperature": ("White Balance", "Temperature"),
        "green": ("White Balance", "Green"),
    },
    "crop": {
        "enabled": ("Crop", "Enabled"),
        "x": ("Crop", "X"),
        "y": ("Crop", "Y"),
        "w": ("Crop", "W"),
        "width": ("Crop", "W"),
        "h": ("Crop", "H"),
        "height": ("Crop", "H"),
        "fixed_ratio": ("Crop", "FixedRatio"),
        "fixedratio": ("Crop", "FixedRatio"),
        "ratio": ("Crop", "Ratio"),
        "guide": ("Crop", "Guide"),
        "orientation": ("Crop", "Orientation"),
    },
    "resize": {
        "enabled": ("Resize", "Enabled"),
        "method": ("Resize", "Method"),
        "width": ("Resize", "Width"),
        "height": ("Resize", "Height"),
        "apply_to": ("Resize", "AppliesTo"),
        "appliesto": ("Resize", "AppliesTo"),
        "scale": ("Resize", "Scale"),
        "dataspecified": ("Resize", "DataSpecified"),
        "allowupscaling": ("Resize", "AllowUpscaling"),
    },
    "sharpening": {
        "enabled": ("Sharpening", "Enabled"),
        "method": ("Sharpening", "Method"),
        "radius": ("Sharpening", "Radius"),
        "amount": ("Sharpening", "Amount"),
        "threshold": ("Sharpening", "Threshold"),
    },
    "noise_reduction": {
        "enabled": ("Directional Pyramid Denoising", "Enabled"),
        "luminance": ("Directional Pyramid Denoising", "Luma"),
        "chrominance": ("Directional Pyramid Denoising", "Chroma"),
    },
    "noisereduction": {
        "enabled": ("Directional Pyramid Denoising", "Enabled"),
        "luminance": ("Directional Pyramid Denoising", "Luma"),
        "chrominance": ("Directional Pyramid Denoising", "Chroma"),
    },
    "color": {
        "vibrance": ("Vibrance", "Pastels"),
        "hue_shift": ("ColorToning", "HLHue"),
    },
    "lens_correction": {
        "auto": ("LensProfile", "UseDistortion"),
    },
    "lenscorrection": {
        "auto": ("LensProfile", "UseDistortion"),
    },
}


def create_neutral_profile() -> PP3Profile:
    """Create a minimal neutral PP3 profile.

    Returns:
        A PP3Profile with version header and neutral defaults.
    """
    profile = PP3Profile()

    # Required version header
    profile.set("Version", "AppVersion", "5.11")
    profile.set("Version", "Version", "351")

    # General
    profile.set("General", "ColorLabel", "0")
    profile.set("General", "InTrash", "false")

    # Neutral exposure
    profile.set("Exposure", "Auto", "false")
    profile.set("Exposure", "Compensation", "0")
    profile.set("Exposure", "Brightness", "0")
    profile.set("Exposure", "Contrast", "0")
    profile.set("Exposure", "Saturation", "0")
    profile.set("Exposure", "Black", "0")
    profile.set("Exposure", "HighlightCompr", "0")
    profile.set("Exposure", "ShadowCompr", "50")

    # Camera white balance
    profile.set("White Balance", "Setting", "Camera")
    profile.set("White Balance", "Temperature", "5500")
    profile.set("White Balance", "Green", "1.0")

    # No crop
    profile.set("Crop", "Enabled", "false")

    # No resize
    profile.set("Resize", "Enabled", "false")

    # Basic sharpening
    profile.set("Sharpening", "Enabled", "true")
    profile.set("Sharpening", "Method", "usm")
    profile.set("Sharpening", "Radius", "0.50")
    profile.set("Sharpening", "Amount", "150")
    profile.set("Sharpening", "Threshold", "20;80;2000;1200;")

    # Color management
    profile.set("Color Management", "InputProfile", "(camera)")
    profile.set("Color Management", "WorkingProfile", "ProPhoto")
    profile.set("Color Management", "OutputProfile", "RT_sRGB")

    # No noise reduction
    profile.set("Directional Pyramid Denoising", "Enabled", "false")

    return profile


def apply_parameters(
    profile: PP3Profile,
    parameters: dict[str, Any],
    *,
    raw_fallback: bool = False,
) -> None:
    """Apply user-friendly parameters to a PP3 profile.

    Maps friendly nested dicts to PP3 section/key pairs. Parameter names are
    matched case-insensitively (e.g. "fixedRatio" matches "fixedratio").

    When raw_fallback is True, unrecognized groups are treated as raw PP3
    section names and their key-value pairs are set directly. This is useful
    for adjust_profile where users may pass raw PP3 section/key pairs.

    Args:
        profile: The profile to modify in-place.
        parameters: Nested dict of parameter groups and values.
        raw_fallback: If True, set unrecognized groups as raw PP3 values.
    """
    for group_name, group_values in parameters.items():
        if not isinstance(group_values, dict):
            logger.warning("Skipping non-dict parameter group: %s", group_name)
            continue

        group_map = _PARAMETER_MAP.get(group_name.lower())
        if group_map is None:
            if raw_fallback:
                # Treat as raw PP3 section name with raw key-value pairs
                for key, value in group_values.items():
                    if isinstance(value, bool):
                        profile.set(group_name, key, str(value).lower())
                    else:
                        profile.set(group_name, key, str(value))
            else:
                logger.warning("Unknown parameter group: %s", group_name)
            continue

        for param_name, param_value in group_values.items():
            mapping = group_map.get(param_name.lower())
            if mapping is None:
                if raw_fallback:
                    # Fall back to raw PP3 key within the mapped section
                    # Use the first section name from this group's mappings
                    first_section = next(iter(group_map.values()))[0]
                    if isinstance(param_value, bool):
                        profile.set(first_section, param_name, str(param_value).lower())
                    else:
                        profile.set(first_section, param_name, str(param_value))
                else:
                    logger.warning("Unknown parameter %s.%s", group_name, param_name)
                continue

            section, key = mapping
            # Convert booleans to lowercase strings for PP3
            if isinstance(param_value, bool):
                profile.set(section, key, str(param_value).lower())
            else:
                profile.set(section, key, str(param_value))


def apply_device_preset(profile: PP3Profile, preset: dict[str, Any]) -> None:
    """Apply a device preset's resize settings to a profile (resize only, no crop).

    Use this when the source image dimensions are not known (e.g. profile generation).
    For correct aspect-ratio cropping, use apply_device_crop() at processing time.

    Args:
        profile: The profile to modify in-place.
        preset: Preset dict with 'width' and 'height' keys.
    """
    width = preset.get("width")
    height = preset.get("height")

    if width is None or height is None:
        logger.warning("Preset missing width/height, skipping")
        return

    # Only resize — crop requires source image dimensions
    profile.set("Resize", "Enabled", "true")
    profile.set("Resize", "Scale", "1")
    profile.set("Resize", "AppliesTo", "Full Image")
    profile.set("Resize", "Method", "Lanczos")
    profile.set("Resize", "DataSpecified", "3")
    profile.set("Resize", "Width", str(width))
    profile.set("Resize", "Height", str(height))
    profile.set("Resize", "AllowUpscaling", "false")


def apply_device_crop(
    profile: PP3Profile,
    preset: dict[str, Any],
    source_width: int,
    source_height: int,
) -> None:
    """Apply a device preset with correct aspect-ratio crop (no resize).

    Calculates the maximum crop area in the target aspect ratio that fits
    within the source image, centered. Outputs at cropped resolution —
    the device scales natively.

    NOTE: RT 5.12 ignores Crop when Resize is also enabled in the same PP3.
    This function explicitly disables Resize to avoid that bug.

    RawTherapee applies crop AFTER orientation correction, so source_width
    and source_height should be the effective (post-rotation) dimensions.

    Args:
        profile: The profile to modify in-place.
        preset: Preset dict with 'width' and 'height' keys.
        source_width: Effective source image width (after orientation).
        source_height: Effective source image height (after orientation).
    """
    target_w = preset.get("width")
    target_h = preset.get("height")

    if target_w is None or target_h is None:
        logger.warning("Preset missing width/height, skipping")
        return

    if source_width <= 0 or source_height <= 0:
        logger.warning(
            "Invalid source dimensions %dx%d, falling back to resize-only",
            source_width,
            source_height,
        )
        apply_device_preset(profile, preset)
        return

    target_ratio = target_w / target_h
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        # Source is wider than target — use full height, crop width
        crop_h = source_height
        crop_w = int(source_height * target_ratio)
    else:
        # Source is taller than target — use full width, crop height
        crop_w = source_width
        crop_h = int(source_width / target_ratio)

    # Center the crop
    crop_x = (source_width - crop_w) // 2
    crop_y = (source_height - crop_h) // 2

    # Set crop with all required fields for RT
    profile.set("Crop", "Enabled", "true")
    profile.set("Crop", "X", str(crop_x))
    profile.set("Crop", "Y", str(crop_y))
    profile.set("Crop", "W", str(crop_w))
    profile.set("Crop", "H", str(crop_h))
    profile.set("Crop", "FixedRatio", "true")
    profile.set("Crop", "Ratio", f"{target_w}:{target_h}")
    profile.set("Crop", "Orientation", "As Image")
    profile.set("Crop", "Guide", "Frame")

    # RT 5.12 bug: Crop is ignored when Resize is also enabled.
    # Disable Resize so Crop takes effect. The output will be at cropped
    # resolution (e.g. 3108x6732) and the device scales natively.
    profile.set("Resize", "Enabled", "false")

    logger.info(
        "Device crop: %dx%d source -> crop %dx%d at (%d,%d), target ratio %d:%d",
        source_width,
        source_height,
        crop_w,
        crop_h,
        crop_x,
        crop_y,
        target_w,
        target_h,
    )


def generate_profile(
    name: str,
    base_template: str | None,
    parameters: dict[str, Any] | None,
    device_preset: dict[str, Any] | None,
    templates_dir: Path,
    custom_templates_dir: Path,
) -> tuple[PP3Profile, Path]:
    """Generate a PP3 profile from parameters and/or template.

    Args:
        name: Name for the profile (used as filename).
        base_template: Name of built-in or custom template to use as base.
        parameters: Processing parameters to set/override.
        device_preset: Device preset dict with width/height.
        templates_dir: Path to built-in templates.
        custom_templates_dir: Path to custom templates directory.

    Returns:
        Tuple of (profile, output_path).

    Raises:
        FileNotFoundError: If the specified template does not exist.
    """
    # Load base template or create neutral
    if base_template:
        profile = _load_template(base_template, templates_dir, custom_templates_dir)
    else:
        profile = create_neutral_profile()

    # Apply parameters
    if parameters:
        apply_parameters(profile, parameters)

    # Apply device preset
    if device_preset:
        apply_device_preset(profile, device_preset)

    # Save to custom templates directory
    output_path = custom_templates_dir / f"{name}.pp3"
    profile.save(output_path)

    return profile, output_path


def _load_template(
    template_name: str,
    templates_dir: Path,
    custom_templates_dir: Path,
) -> PP3Profile:
    """Load a template by name, checking custom then built-in directories.

    Args:
        template_name: Template name (without .pp3 extension).
        templates_dir: Path to built-in templates.
        custom_templates_dir: Path to custom templates.

    Returns:
        Loaded PP3Profile.

    Raises:
        FileNotFoundError: If template not found in either location.
    """
    # Check custom templates first
    custom_path = custom_templates_dir / f"{template_name}.pp3"
    if custom_path.is_file():
        profile = PP3Profile()
        profile.load(custom_path)
        return profile

    # Check built-in templates
    builtin_path = templates_dir / f"{template_name}.pp3"
    if builtin_path.is_file():
        profile = PP3Profile()
        profile.load(builtin_path)
        return profile

    msg = f"Template '{template_name}' not found in {custom_templates_dir} or {templates_dir}"
    raise FileNotFoundError(msg)
