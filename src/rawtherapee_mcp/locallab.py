"""Locallab (local adjustments) support for RawTherapee PP3 profiles.

Provides luminance-based local adjustments via RT's Locallab system (RT 5.9+).
Each "spot" targets a luminance range (shadows, midtones, highlights, or custom)
and applies processing adjustments only to pixels within that range.

The PP3 Locallab format uses indexed keys (e.g. Expcomp_0, Expcomp_1) for each
spot. This module handles the mapping between high-level parameters and the
~120 PP3 keys per spot.
"""

from __future__ import annotations

import logging
from typing import Any

from rawtherapee_mcp.pp3_parser import PP3Profile

logger = logging.getLogger("rawtherapee_mcp")

# ---------------------------------------------------------------------------
# Predefined luminance ranges
# ---------------------------------------------------------------------------

_LUMINANCE_RANGES: dict[str, dict[str, int]] = {
    "shadows": {"lower": 0, "upper": 30, "lower_transition": 0, "upper_transition": 20},
    "midtones": {"lower": 25, "upper": 75, "lower_transition": 15, "upper_transition": 15},
    "highlights": {"lower": 70, "upper": 100, "lower_transition": 20, "upper_transition": 0},
}

# ---------------------------------------------------------------------------
# Luminance mask curve generation
# ---------------------------------------------------------------------------


def luminance_range_to_curve(
    lower: int,
    upper: int,
    lower_transition: int = 15,
    upper_transition: int = 15,
) -> str:
    """Convert a luminance range to an RT Locallab mask curve string.

    The curve defines a trapezoid shape where the mask is fully active
    between ``lower`` and ``upper``, with smooth transitions at the edges.

    Args:
        lower: Lower luminance bound (0-100).
        upper: Upper luminance bound (0-100).
        lower_transition: Transition width below lower (0-100).
        upper_transition: Transition width above upper (0-100).

    Returns:
        RT curve string in the format ``1;N;x1;y1;s1;x2;y2;s2;...;``
    """
    lo = max(0.0, lower / 100.0)
    hi = min(1.0, upper / 100.0)
    lt = lower_transition / 100.0
    ut = upper_transition / 100.0

    points: list[tuple[float, float]] = []

    # Start: no effect
    lo_start = max(0.0, lo - lt)
    hi_end = min(1.0, hi + ut)

    if lo_start > 0.0:
        points.append((0.0, 0.0))

    # Transition start (zero)
    if lt > 0.0 and lo_start > 0.0:
        points.append((lo_start, 0.0))

    # Full effect start
    points.append((lo, 1.0))

    # Full effect end
    if hi > lo:
        points.append((hi, 1.0))

    # Transition end (zero)
    if ut > 0.0 and hi_end < 1.0:
        points.append((hi_end, 0.0))

    if hi_end < 1.0:
        points.append((1.0, 0.0))

    # RT curve format: type;count;x1;y1;slope1;x2;y2;slope2;...;
    parts: list[str] = ["1", str(len(points))]
    for x, y in points:
        parts.extend([f"{x:.4f}", f"{y:.4f}", "0.3500"])

    return ";".join(parts) + ";"


# ---------------------------------------------------------------------------
# Flat curve (no mask — full effect everywhere)
# ---------------------------------------------------------------------------

_FLAT_CURVE_FULL = "1;1;0.0000;1.0000;0.3500;"


# ---------------------------------------------------------------------------
# Default PP3 keys for a Locallab spot
# ---------------------------------------------------------------------------


def _spot_defaults(index: int) -> dict[str, str]:
    """Return the full set of default PP3 keys for a Locallab spot.

    These defaults create a spot covering the full image with no processing
    adjustments. Only the luminance mask curve and processing parameters
    need to be overridden.

    Args:
        index: Spot index (0-based).

    Returns:
        Dict of PP3 key -> value for the [Locallab] section.
    """
    i = str(index)
    return {
        # -- Spot shape: full image ellipse --
        f"Shape_{i}": "ELI",
        f"SpotX_{i}": "0",
        f"SpotY_{i}": "0",
        f"Sensi_{i}": "60",
        f"Sizeshape_{i}": "0",
        f"FeatherShape_{i}": "0",
        f"Struc_{i}": "0",
        f"Shapemethod_{i}": "IND",
        f"Loc_{i}": "2000;2000;2000;2000;",
        f"CenterX_{i}": "0",
        f"CenterY_{i}": "0",
        f"Circrad_{i}": "18",
        f"QualityMethod_{i}": "enh",
        f"ComplexMethod_{i}": "mod",
        f"Transit_{i}": "60",
        f"Feather_{i}": "25",
        f"Thresh_{i}": "2",
        f"Iter_{i}": "2",
        f"Balan_{i}": "1",
        f"Balanh_{i}": "1",
        f"Colorde_{i}": "5",
        f"Colorscope_{i}": "30",
        f"Avoidrad_{i}": "0",
        f"Transitweak_{i}": "1",
        f"Transitgrad_{i}": "0",
        f"Hishow_{i}": "false",
        f"Activ_{i}": "true",
        f"Avoid_{i}": "false",
        f"Blwh_{i}": "false",
        f"Recurs_{i}": "false",
        f"Laplac_{i}": "true",
        f"Deltae_{i}": "false",
        f"Shortc_{i}": "false",
        f"Savrest_{i}": "false",
        f"Scopemask_{i}": "60",
        f"Lumask_{i}": "10",
        f"Name_{i}": f"Spot {index}",
        # -- Exposure --
        f"Expexpose_{i}": "false",
        f"Expcomp_{i}": "0",
        f"Hlcompr_{i}": "0",
        f"Hlcomprthresh_{i}": "0",
        f"Shadex_{i}": "0",
        f"Shcompr_{i}": "50",
        f"Expchroma_{i}": "5",
        f"Sensiex_{i}": "60",
        f"Structexp_{i}": "0",
        f"Blurexpde_{i}": "5",
        f"Gamex_{i}": "1.0",
        f"Strexp_{i}": "0.0",
        f"Angexp_{i}": "0.0",
        f"Softradiusexp_{i}": "0.0",
        f"Laplacexp_{i}": "0.0",
        f"Balanexp_{i}": "1.2",
        f"Linearexp_{i}": "0.05",
        f"CCmaskexpena_{i}": "false",
        f"LLmaskexpena_{i}": "true",
        f"HHmaskexpena_{i}": "false",
        f"Exnoisemethod_{i}": "none",
        f"LLmaskexpcurve_{i}": _FLAT_CURVE_FULL,
        f"CCmaskexpcurve_{i}": _FLAT_CURVE_FULL,
        f"HHmaskexpcurve_{i}": _FLAT_CURVE_FULL,
        f"Blendmaskexp_{i}": "0",
        f"Radmaskexp_{i}": "0",
        f"Chromaskexp_{i}": "0",
        f"Gammaskexp_{i}": "1",
        f"Slomaskexp_{i}": "0",
        f"Strmaskexp_{i}": "0",
        f"Angmaskexp_{i}": "0",
        f"Lmaskexpcurve_{i}": "0;",
        # -- Contrast / brightness --
        f"Expcontrast_{i}": "false",
        f"Contrast_{i}": "0",
        f"Sensicn_{i}": "60",
        f"Lcurve_{i}": "0;",
        # -- Color / saturation --
        f"Expcolor_{i}": "false",
        f"Curvactiv_{i}": "false",
        f"Lightness_{i}": "0",
        f"Reparcol_{i}": "100",
        f"Gamc_{i}": "1",
        f"Qualitycurvemethod_{i}": "none",
        f"Gridmethod_{i}": "one",
        f"Mermethod_{i}": "mone",
        f"Tonemethod_{i}": "one",
        f"Mergecolmethod_{i}": "one",
        f"Sensihs_{i}": "60",
        f"Structcol_{i}": "0",
        f"Strcol_{i}": "0.0",
        f"Strcolab_{i}": "0.0",
        f"Strcolh_{i}": "0.0",
        f"Angcol_{i}": "0.0",
        f"Blurcol_{i}": "0.2",
        f"Blendmaskcol_{i}": "0",
        f"Radmaskcol_{i}": "0",
        f"Chromaskcol_{i}": "0",
        f"Gammaskcol_{i}": "1",
        f"Slomaskcol_{i}": "0",
        f"CCmaskcol_{i}": "1",
        f"LLmaskcol_{i}": "1",
        f"HHmaskcol_{i}": "1",
        f"Strumaskcol_{i}": "0",
        f"Toolcol_{i}": "0",
        f"FLmaskcol_{i}": "0",
        f"Contmaskcol_{i}": "0",
        f"Softradiuscol_{i}": "0.0",
        f"Opacol_{i}": "100",
        f"CCmaskcolena_{i}": "false",
        f"LLmaskcolena_{i}": "false",
        f"HHmaskcolena_{i}": "false",
        f"LLmaskcolcurve_{i}": _FLAT_CURVE_FULL,
        f"CCmaskcolcurve_{i}": _FLAT_CURVE_FULL,
        f"HHmaskcolcurve_{i}": _FLAT_CURVE_FULL,
        f"Lmaskcolcurve_{i}": "0;",
        f"LcurveL_{i}": "0;",
        # -- Sharpening (local) --
        f"Expsharp_{i}": "false",
        f"Sharcontrast_{i}": "20",
        f"Sharradius_{i}": "0.42",
        f"Sharamount_{i}": "100",
        f"Shardamping_{i}": "0",
        f"Shariter_{i}": "30",
        f"Sharblur_{i}": "0.2",
        f"Sensisha_{i}": "40",
        f"Inverssha_{i}": "false",
        # -- Noise (local) --
        f"Expdenoi_{i}": "false",
        f"Noiselumf0_{i}": "0",
        f"Noiselumf_{i}": "0",
        f"Noiselumf2_{i}": "0",
        f"Noiselumc_{i}": "0",
        f"Noiselumdetail_{i}": "0",
        f"Noiselequal_{i}": "7",
        f"Noisechrof_{i}": "0",
        f"Noisechroc_{i}": "0",
        f"Noisechrodetail_{i}": "0",
        f"Adjblur_{i}": "0",
        f"Bilateral_{i}": "0",
        f"Sensiden_{i}": "60",
        f"Detailthr_{i}": "0",
        f"Locwavcurveden_{i}": "0;",
        # -- Tone mapping (local) --
        f"Exptonemap_{i}": "false",
        f"Stren_{i}": "0.5",
        f"Gamma_{i}": "1.0",
        f"Estop_{i}": "1.4",
        f"Scaltm_{i}": "3",
        f"Rewei_{i}": "0",
        f"Sensitm_{i}": "60",
        f"Softradiustm_{i}": "0.0",
        f"Amount_{i}": "80",
        f"Equiltm_{i}": "true",
        # -- Vibrance (local) --
        f"Expvibrance_{i}": "false",
        f"Saturated_{i}": "0",
        f"Pastels_{i}": "0",
        f"Warm_{i}": "0",
        f"Psthreshold_{i}": "0;75;",
        f"Protectskins_{i}": "false",
        f"Avoidcolorshift_{i}": "true",
        f"Pastsattog_{i}": "true",
        f"Sensiv_{i}": "60",
        f"Skintonescurve_{i}": "0;",
        # -- Soft light / retinex --
        f"Expsoftlight_{i}": "false",
        f"Streng_{i}": "0",
        f"Sensisf_{i}": "60",
        f"Laplace_{i}": "25",
        f"Softmethod_{i}": "soft",
    }


# ---------------------------------------------------------------------------
# Parameter mapping: high-level -> PP3 keys
# ---------------------------------------------------------------------------

# Maps high-level parameter names to (PP3 key template, enable key, default)
# Key template uses {i} for the spot index placeholder.
_PARAM_MAP: dict[str, tuple[str, str, str]] = {
    # (pp3_key_template, pp3_enable_key_template, section_type)
    "exposure": ("Expcomp_{i}", "Expexpose_{i}", "exposure"),
    "contrast": ("Contrast_{i}", "Expcontrast_{i}", "contrast"),
    "saturation": ("Saturated_{i}", "Expvibrance_{i}", "vibrance"),
    "brightness": ("Lightness_{i}", "Expcolor_{i}", "color"),
    "black": ("Shadex_{i}", "Expexpose_{i}", "exposure"),
    "highlight_compression": ("Hlcompr_{i}", "Expexpose_{i}", "exposure"),
    "sharpening": ("Sharamount_{i}", "Expsharp_{i}", "sharpening"),
    "denoise_luma": ("Noiselumf_{i}", "Expdenoi_{i}", "denoise"),
    "denoise_chroma": ("Noisechrof_{i}", "Expdenoi_{i}", "denoise"),
    "white_balance_shift": ("Warm_{i}", "Expvibrance_{i}", "vibrance"),
}


def _apply_parameters_to_spot(
    defaults: dict[str, str],
    index: int,
    parameters: dict[str, Any],
    strength: int = 100,
) -> None:
    """Apply high-level parameters to a spot's PP3 key dict.

    Modifies ``defaults`` in place by mapping parameter names to PP3 keys
    and enabling the corresponding processing modules.

    Args:
        defaults: Mutable dict of PP3 keys for this spot.
        index: Spot index.
        parameters: High-level parameter dict (e.g. {"exposure": 0.3}).
        strength: Overall strength 0-100 (scales numeric values).
    """
    i = str(index)
    # Track which modules to enable
    enabled_modules: set[str] = set()

    for param_name, value in parameters.items():
        mapping = _PARAM_MAP.get(param_name)
        if mapping is None:
            logger.warning("Unknown local adjustment parameter: %s", param_name)
            continue

        key_template, enable_template, module = mapping
        pp3_key = key_template.replace("{i}", i)
        enable_key = enable_template.replace("{i}", i)

        # Scale by strength
        if isinstance(value, (int, float)) and strength != 100:
            value = value * strength / 100

        defaults[pp3_key] = str(value)
        enabled_modules.add(module)

        # Enable the module if not already
        defaults[enable_key] = "true"

    # Set sensitivity to 100 for enabled modules so the effect is fully applied
    _sensitivity_keys: dict[str, str] = {
        "exposure": f"Sensiex_{i}",
        "contrast": f"Sensicn_{i}",
        "color": f"Sensihs_{i}",
        "vibrance": f"Sensiv_{i}",
        "sharpening": f"Sensisha_{i}",
        "denoise": f"Sensiden_{i}",
    }
    for module in enabled_modules:
        sens_key = _sensitivity_keys.get(module)
        if sens_key:
            defaults[sens_key] = "100"


# ---------------------------------------------------------------------------
# Spot read/write operations on PP3Profile
# ---------------------------------------------------------------------------


def get_spot_count(profile: PP3Profile) -> int:
    """Return the number of Locallab spots in a profile.

    Args:
        profile: The PP3 profile to inspect.

    Returns:
        Number of spots (0 if no Locallab section).
    """
    raw = profile.get("Locallab", "Spots", "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def add_spot(
    profile: PP3Profile,
    adjustment_type: str,
    parameters: dict[str, Any],
    luminance_range: dict[str, int] | None = None,
    transition: int = 30,
    strength: int = 100,
    spot_name: str | None = None,
) -> int:
    """Add a Locallab spot with luminance mask to a PP3 profile.

    Args:
        profile: The PP3 profile to modify in-place.
        adjustment_type: One of "shadows", "midtones", "highlights", "custom".
        parameters: Processing parameters (e.g. {"exposure": 0.3}).
        luminance_range: Custom range dict (required when type is "custom").
        transition: Transition softness (0-100), used for predefined types.
        strength: Overall strength 0-100.
        spot_name: Optional name for the spot.

    Returns:
        The index of the newly added spot.

    Raises:
        ValueError: If adjustment_type is invalid or custom range is missing.
    """
    # Resolve luminance range
    if adjustment_type == "custom":
        if luminance_range is None:
            msg = "luminance_range is required when adjustment_type is 'custom'"
            raise ValueError(msg)
        lum_lower = luminance_range.get("lower", 0)
        lum_upper = luminance_range.get("upper", 100)
        lower_trans = luminance_range.get("lower_transition", 15)
        upper_trans = luminance_range.get("upper_transition", 15)
    elif adjustment_type in _LUMINANCE_RANGES:
        preset = _LUMINANCE_RANGES[adjustment_type]
        lum_lower = preset["lower"]
        lum_upper = preset["upper"]
        # Use custom transition if provided, else use preset defaults
        lower_trans = preset["lower_transition"] if transition == 30 else transition
        upper_trans = preset["upper_transition"] if transition == 30 else transition
        # For shadows lower_transition is always 0, for highlights upper is 0
        if adjustment_type == "shadows":
            lower_trans = 0
        elif adjustment_type == "highlights":
            upper_trans = 0
    else:
        msg = f"Invalid adjustment_type: {adjustment_type!r}. Use 'shadows', 'midtones', 'highlights', or 'custom'."
        raise ValueError(msg)

    # Determine new spot index
    count = get_spot_count(profile)
    new_index = count

    # Build spot defaults
    defaults = _spot_defaults(new_index)

    # Set name
    name = spot_name or f"{adjustment_type.title()} adjustment"
    defaults[f"Name_{new_index}"] = name

    # Set luminance mask curve
    curve = luminance_range_to_curve(lum_lower, lum_upper, lower_trans, upper_trans)
    defaults[f"LLmaskexpcurve_{new_index}"] = curve
    defaults[f"LLmaskexpena_{new_index}"] = "true"

    # Apply processing parameters
    _apply_parameters_to_spot(defaults, new_index, parameters, strength)

    # Write all keys to the profile
    for key, value in defaults.items():
        profile.set("Locallab", key, value)

    # Update Locallab header
    profile.set("Locallab", "Spots", str(count + 1))
    profile.set("Locallab", "Selspot", str(new_index))

    return new_index


def read_spot(profile: PP3Profile, index: int) -> dict[str, Any] | None:
    """Read a Locallab spot's high-level parameters from a PP3 profile.

    Args:
        profile: The PP3 profile to read from.
        index: Spot index (0-based).

    Returns:
        Dict with spot info, or None if the spot does not exist.
    """
    count = get_spot_count(profile)
    if index < 0 or index >= count:
        return None

    i = str(index)
    name = profile.get("Locallab", f"Name_{i}", f"Spot {index}")
    enabled = profile.get("Locallab", f"Activ_{i}", "true") == "true"

    # Read parameters
    params: dict[str, Any] = {}
    for param_name, (key_template, _enable_template, _module) in _PARAM_MAP.items():
        pp3_key = key_template.replace("{i}", i)
        raw = profile.get("Locallab", pp3_key, "")
        if raw:
            try:
                val = float(raw)
                # Use int if it's a whole number
                params[param_name] = int(val) if val == int(val) else val
            except ValueError:
                params[param_name] = raw

    # Filter out zeroes — only include non-default parameters
    active_params = {k: v for k, v in params.items() if v != 0 and v != 0.0}

    # Determine adjustment type from luminance mask curve
    adj_type = _detect_adjustment_type(profile, index)
    lum_range = _read_luminance_range(profile, index)

    return {
        "index": index,
        "name": name,
        "type": adj_type,
        "luminance_range": lum_range,
        "parameters": active_params,
        "enabled": enabled,
    }


def _detect_adjustment_type(profile: PP3Profile, index: int) -> str:
    """Detect the adjustment type based on the luminance mask curve.

    Args:
        profile: The PP3 profile.
        index: Spot index.

    Returns:
        One of "shadows", "midtones", "highlights", or "custom".
    """
    lum_range = _read_luminance_range(profile, index)
    if lum_range is None:
        return "custom"

    lo = lum_range.get("lower", 0)
    hi = lum_range.get("upper", 100)

    # Match against predefined ranges (with tolerance)
    for name, preset in _LUMINANCE_RANGES.items():
        if abs(lo - preset["lower"]) <= 5 and abs(hi - preset["upper"]) <= 5:
            return name

    return "custom"


def _read_luminance_range(profile: PP3Profile, index: int) -> dict[str, int] | None:
    """Parse the luminance range from a spot's mask curve.

    Extracts the lower/upper bounds from the trapezoid curve.

    Args:
        profile: The PP3 profile.
        index: Spot index.

    Returns:
        Dict with lower/upper, or None if unparseable.
    """
    i = str(index)
    curve_str = profile.get("Locallab", f"LLmaskexpcurve_{i}", "")
    if not curve_str:
        return None

    return parse_curve_to_range(curve_str)


def parse_curve_to_range(curve_str: str) -> dict[str, int] | None:
    """Parse an RT Locallab mask curve string back to a luminance range.

    Extracts the first and last points where the curve reaches 1.0 to
    determine the active luminance range.

    Args:
        curve_str: The RT curve string.

    Returns:
        Dict with lower/upper keys (0-100 scale), or None if unparseable.
    """
    parts = curve_str.rstrip(";").split(";")
    if len(parts) < 5:
        return None

    try:
        curve_type = int(parts[0])
        if curve_type != 1:
            return None
        num_points = int(parts[1])
        if num_points < 2:
            return None
    except ValueError:
        return None

    # Parse control points (x, y, slope) triplets
    points: list[tuple[float, float]] = []
    for p in range(num_points):
        base = 2 + p * 3
        if base + 1 >= len(parts):
            break
        try:
            x = float(parts[base])
            y = float(parts[base + 1])
            points.append((x, y))
        except ValueError:
            continue

    if not points:
        return None

    # Find the range where y >= 0.5 (active region)
    active_x = [x for x, y in points if y >= 0.5]
    if not active_x:
        return {"lower": 0, "upper": 100}

    lower = int(round(min(active_x) * 100))
    upper = int(round(max(active_x) * 100))

    return {"lower": lower, "upper": upper}


def remove_spot(profile: PP3Profile, index: int) -> bool:
    """Remove a Locallab spot from a PP3 profile and re-index remaining spots.

    Args:
        profile: The PP3 profile to modify in-place.
        index: Spot index to remove (0-based).

    Returns:
        True if the spot was removed, False if index is invalid.
    """
    count = get_spot_count(profile)
    if index < 0 or index >= count:
        return False

    # If this is the only spot, just remove the Locallab section
    if count == 1:
        # Clear all Locallab keys
        all_keys = profile.keys("Locallab")
        for key in all_keys:
            profile.set("Locallab", key, "")
        profile.set("Locallab", "Spots", "0")
        return True

    # Collect all spot key templates (we need to know which keys belong to spots)
    # Strategy: for each spot after the removed one, shift its keys down by 1
    sample_keys = _spot_defaults(0)
    key_suffixes = [k.rsplit("_", 1)[0] + "_" for k in sample_keys]
    # Deduplicate
    key_suffixes = sorted(set(key_suffixes))

    # Shift spots after the removed index
    for src_idx in range(index + 1, count):
        dst_idx = src_idx - 1
        for suffix in key_suffixes:
            src_key = f"{suffix}{src_idx}"
            dst_key = f"{suffix}{dst_idx}"
            val = profile.get("Locallab", src_key, "")
            if val:
                profile.set("Locallab", dst_key, val)

    # Clear the last spot's keys (now orphaned)
    last_idx = count - 1
    for suffix in key_suffixes:
        key = f"{suffix}{last_idx}"
        # We can't truly delete keys from PP3Profile, set to empty
        profile.set("Locallab", key, "")

    profile.set("Locallab", "Spots", str(count - 1))
    sel = int(profile.get("Locallab", "Selspot", "0"))
    if sel >= count - 1:
        profile.set("Locallab", "Selspot", str(max(0, count - 2)))

    return True


def update_spot(
    profile: PP3Profile,
    index: int,
    parameters: dict[str, Any] | None = None,
    luminance_range: dict[str, int] | None = None,
    strength: int | None = None,
    enabled: bool | None = None,
) -> bool:
    """Update an existing Locallab spot's parameters.

    Args:
        profile: The PP3 profile to modify in-place.
        index: Spot index to update (0-based).
        parameters: New processing parameters (merged with existing).
        luminance_range: New luminance range.
        strength: New overall strength (not stored directly, scales params).
        enabled: Enable/disable the spot.

    Returns:
        True if the spot was updated, False if index is invalid.
    """
    count = get_spot_count(profile)
    if index < 0 or index >= count:
        return False

    i = str(index)

    if enabled is not None:
        profile.set("Locallab", f"Activ_{i}", "true" if enabled else "false")

    if luminance_range is not None:
        lum_lower = luminance_range.get("lower", 0)
        lum_upper = luminance_range.get("upper", 100)
        lower_trans = luminance_range.get("lower_transition", 15)
        upper_trans = luminance_range.get("upper_transition", 15)
        curve = luminance_range_to_curve(lum_lower, lum_upper, lower_trans, upper_trans)
        profile.set("Locallab", f"LLmaskexpcurve_{i}", curve)
        profile.set("Locallab", f"LLmaskexpena_{i}", "true")

    if parameters is not None:
        effective_strength = strength if strength is not None else 100
        # Build a temporary defaults dict, apply params, write to profile
        spot_keys: dict[str, str] = {}
        _apply_parameters_to_spot(spot_keys, index, parameters, effective_strength)
        for key, value in spot_keys.items():
            profile.set("Locallab", key, value)

    return True


# ---------------------------------------------------------------------------
# Preset definitions
# ---------------------------------------------------------------------------

_PRESETS: dict[str, dict[str, Any]] = {
    "shadow_recovery": {
        "description": "Lift shadows with gentle noise reduction",
        "spots": [
            {
                "type": "shadows",
                "name": "Shadow recovery",
                "parameters": {"exposure": 0.5, "contrast": 10, "denoise_luma": 5},
            },
        ],
    },
    "highlight_protection": {
        "description": "Compress highlights and reduce saturation to prevent blow-outs",
        "spots": [
            {
                "type": "highlights",
                "name": "Highlight protection",
                "parameters": {"exposure": -0.3, "saturation": -10, "highlight_compression": 40},
            },
        ],
    },
    "split_tone_warm_cool": {
        "description": "Warm shadows and cool highlights for cinematic look",
        "spots": [
            {
                "type": "shadows",
                "name": "Warm shadows",
                "parameters": {"white_balance_shift": 300},
            },
            {
                "type": "highlights",
                "name": "Cool highlights",
                "parameters": {"white_balance_shift": -200},
            },
        ],
    },
    "midtone_contrast": {
        "description": "Add contrast and clarity to midtones",
        "spots": [
            {
                "type": "midtones",
                "name": "Midtone contrast",
                "parameters": {"contrast": 25, "sharpening": 15},
            },
        ],
    },
    "shadow_desaturation": {
        "description": "Desaturate shadows to reduce color noise in dark areas",
        "spots": [
            {
                "type": "shadows",
                "name": "Shadow desaturation",
                "parameters": {"saturation": -30},
            },
        ],
    },
    "amoled_optimize": {
        "description": "Deep blacks and vibrant midtones for AMOLED displays",
        "spots": [
            {
                "type": "shadows",
                "name": "Deep blacks",
                "parameters": {"black": 100, "contrast": 10},
            },
            {
                "type": "midtones",
                "name": "Vibrant midtones",
                "parameters": {"saturation": 10, "contrast": 5},
            },
        ],
    },
    "hdr_natural": {
        "description": "Natural HDR look: lift shadows, boost midtones, compress highlights",
        "spots": [
            {
                "type": "shadows",
                "name": "HDR shadow lift",
                "parameters": {"exposure": 0.5, "denoise_luma": 5},
            },
            {
                "type": "midtones",
                "name": "HDR midtone boost",
                "parameters": {"contrast": 15, "saturation": 5},
            },
            {
                "type": "highlights",
                "name": "HDR highlight compress",
                "parameters": {"exposure": -0.3, "highlight_compression": 30},
            },
        ],
    },
}


def get_preset(name: str) -> dict[str, Any] | None:
    """Get a local adjustment preset by name.

    Args:
        name: Preset name.

    Returns:
        Preset dict with 'description' and 'spots', or None.
    """
    return _PRESETS.get(name)


def list_presets() -> dict[str, str]:
    """List all available local adjustment presets.

    Returns:
        Dict of preset_name -> description.
    """
    return {name: info["description"] for name, info in _PRESETS.items()}


def apply_preset(
    profile: PP3Profile,
    preset_name: str,
    intensity: int = 50,
) -> list[int]:
    """Apply a local adjustment preset to a PP3 profile.

    Args:
        profile: The PP3 profile to modify in-place.
        preset_name: Name of the preset.
        intensity: Intensity 0-100 (50 = default values, 100 = double).

    Returns:
        List of spot indices that were added.

    Raises:
        ValueError: If the preset name is unknown.
    """
    preset = _PRESETS.get(preset_name)
    if preset is None:
        msg = f"Unknown preset: {preset_name!r}. Available: {', '.join(_PRESETS)}"
        raise ValueError(msg)

    # Scale: intensity 50 = 1x, 100 = 2x, 25 = 0.5x
    scale = intensity / 50.0

    indices: list[int] = []
    for spot_def in preset["spots"]:
        # Scale numeric parameters, preserving int type for whole numbers
        # (RT CLI requires integer strings for certain keys like Contrast,
        # Noiselumf, Hlcompr — "15.0" causes a crash, "15" works)
        scaled_params: dict[str, Any] = {}
        for k, v in spot_def["parameters"].items():
            if isinstance(v, (int, float)):
                scaled = v * scale
                # Preserve int when result is a whole number
                scaled_params[k] = int(scaled) if scaled == int(scaled) else scaled
            else:
                scaled_params[k] = v

        idx = add_spot(
            profile,
            adjustment_type=spot_def["type"],
            parameters=scaled_params,
            spot_name=spot_def.get("name"),
        )
        indices.append(idx)

    return indices
