"""Tests for the Locallab (local adjustments) module."""

from __future__ import annotations

import pytest

from rawtherapee_mcp.locallab import (
    add_spot,
    apply_preset,
    get_spot_count,
    list_presets,
    luminance_range_to_curve,
    parse_curve_to_range,
    read_spot,
    remove_spot,
    update_spot,
)
from rawtherapee_mcp.pp3_parser import PP3Profile

# ---------------------------------------------------------------------------
# Curve generation
# ---------------------------------------------------------------------------


class TestLuminanceRangeToCurve:
    """Tests for luminance range to RT curve conversion."""

    def test_shadows_curve(self):
        curve = luminance_range_to_curve(0, 30, 0, 20)
        assert curve.startswith("1;")
        assert curve.endswith(";")
        # Should contain control points
        parts = curve.rstrip(";").split(";")
        assert int(parts[1]) >= 2  # At least 2 control points

    def test_highlights_curve(self):
        curve = luminance_range_to_curve(70, 100, 20, 0)
        parts = curve.rstrip(";").split(";")
        assert int(parts[0]) == 1  # Type = 1 (custom curve)

    def test_full_range_curve(self):
        """Full range (0-100) should produce active curve everywhere."""
        curve = luminance_range_to_curve(0, 100, 0, 0)
        # Should have points at 0.0 and 1.0 with y=1.0
        assert "1.0000" in curve

    def test_narrow_range(self):
        """Narrow range with transitions."""
        curve = luminance_range_to_curve(40, 60, 10, 10)
        parts = curve.rstrip(";").split(";")
        num_points = int(parts[1])
        assert num_points >= 4  # Start, lower, upper, end transitions

    def test_zero_transitions(self):
        """Zero transitions should produce sharp edges."""
        curve = luminance_range_to_curve(30, 70, 0, 0)
        assert "0.3000" in curve
        assert "0.7000" in curve


class TestParseCurveToRange:
    """Tests for parsing RT curves back to luminance ranges."""

    def test_roundtrip_shadows(self):
        curve = luminance_range_to_curve(0, 30, 0, 20)
        result = parse_curve_to_range(curve)
        assert result is not None
        assert result["lower"] <= 5  # ~0
        assert 25 <= result["upper"] <= 35  # ~30

    def test_roundtrip_highlights(self):
        curve = luminance_range_to_curve(70, 100, 20, 0)
        result = parse_curve_to_range(curve)
        assert result is not None
        assert 65 <= result["lower"] <= 75
        assert result["upper"] >= 95

    def test_roundtrip_midtones(self):
        curve = luminance_range_to_curve(25, 75, 15, 15)
        result = parse_curve_to_range(curve)
        assert result is not None
        assert 20 <= result["lower"] <= 30
        assert 70 <= result["upper"] <= 80

    def test_invalid_curve(self):
        assert parse_curve_to_range("") is None
        assert parse_curve_to_range("garbage") is None
        assert parse_curve_to_range("0;") is None

    def test_non_type1_curve(self):
        assert parse_curve_to_range("2;3;0;0;0;0.5;1;0;1;0;0;") is None


# ---------------------------------------------------------------------------
# Spot management
# ---------------------------------------------------------------------------


class TestAddSpot:
    """Tests for adding Locallab spots."""

    def test_add_shadow_spot(self):
        profile = PP3Profile()
        idx = add_spot(profile, "shadows", {"exposure": 0.5})
        assert idx == 0
        assert get_spot_count(profile) == 1
        assert profile.get("Locallab", "Spots") == "1"
        assert profile.get("Locallab", "Expcomp_0") == "0.5"
        assert profile.get("Locallab", "Expexpose_0") == "true"

    def test_add_highlight_spot(self):
        profile = PP3Profile()
        idx = add_spot(profile, "highlights", {"exposure": -0.3, "saturation": -10})
        assert idx == 0
        assert profile.get("Locallab", "Expcomp_0") == "-0.3"
        assert profile.get("Locallab", "Saturated_0") == "-10"

    def test_add_midtone_spot(self):
        profile = PP3Profile()
        idx = add_spot(profile, "midtones", {"contrast": 25})
        assert idx == 0
        assert profile.get("Locallab", "Contrast_0") == "25"
        assert profile.get("Locallab", "Expcontrast_0") == "true"

    def test_add_custom_spot(self):
        profile = PP3Profile()
        idx = add_spot(
            profile,
            "custom",
            {"exposure": 0.2},
            luminance_range={"lower": 40, "upper": 80, "lower_transition": 10, "upper_transition": 10},
        )
        assert idx == 0
        curve = profile.get("Locallab", "LLmaskexpcurve_0")
        assert curve  # Non-empty curve
        assert "0.4000" in curve  # Lower bound
        assert "0.8000" in curve  # Upper bound

    def test_custom_requires_range(self):
        profile = PP3Profile()
        with pytest.raises(ValueError, match="luminance_range is required"):
            add_spot(profile, "custom", {"exposure": 0.5})

    def test_invalid_type(self):
        profile = PP3Profile()
        with pytest.raises(ValueError, match="Invalid adjustment_type"):
            add_spot(profile, "invalid", {"exposure": 0.5})

    def test_multiple_spots(self):
        profile = PP3Profile()
        idx0 = add_spot(profile, "shadows", {"exposure": 0.5})
        idx1 = add_spot(profile, "highlights", {"exposure": -0.3})
        idx2 = add_spot(profile, "midtones", {"contrast": 20})
        assert idx0 == 0
        assert idx1 == 1
        assert idx2 == 2
        assert get_spot_count(profile) == 3
        assert profile.get("Locallab", "Expcomp_0") == "0.5"
        assert profile.get("Locallab", "Expcomp_1") == "-0.3"
        assert profile.get("Locallab", "Contrast_2") == "20"

    def test_spot_name(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5}, spot_name="My shadow lift")
        assert profile.get("Locallab", "Name_0") == "My shadow lift"

    def test_default_spot_name(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert profile.get("Locallab", "Name_0") == "Shadows adjustment"

    def test_strength_scaling(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 1.0}, strength=50)
        # strength=50 scales to 50% of the value
        assert profile.get("Locallab", "Expcomp_0") == "0.5"

    def test_luminance_mask_enabled(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert profile.get("Locallab", "LLmaskexpena_0") == "true"

    def test_full_image_shape(self):
        """Spot should cover full image."""
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert profile.get("Locallab", "Shape_0") == "ELI"

    def test_denoise_parameter(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"denoise_luma": 20})
        assert profile.get("Locallab", "Noiselumf_0") == "20"
        assert profile.get("Locallab", "Expdenoi_0") == "true"

    def test_sharpening_parameter(self):
        profile = PP3Profile()
        add_spot(profile, "midtones", {"sharpening": 50})
        assert profile.get("Locallab", "Sharamount_0") == "50"
        assert profile.get("Locallab", "Expsharp_0") == "true"

    def test_white_balance_shift(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"white_balance_shift": 300})
        assert profile.get("Locallab", "Warm_0") == "300"
        assert profile.get("Locallab", "Expvibrance_0") == "true"


class TestReadSpot:
    """Tests for reading Locallab spots."""

    def test_read_added_spot(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5, "contrast": 10}, spot_name="Test spot")
        spot = read_spot(profile, 0)
        assert spot is not None
        assert spot["name"] == "Test spot"
        assert spot["parameters"]["exposure"] == 0.5
        assert spot["parameters"]["contrast"] == 10
        assert spot["enabled"] is True

    def test_read_type_detection(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        spot = read_spot(profile, 0)
        assert spot is not None
        assert spot["type"] == "shadows"

    def test_read_nonexistent(self):
        profile = PP3Profile()
        assert read_spot(profile, 0) is None
        assert read_spot(profile, -1) is None

    def test_read_filters_zeroes(self):
        """Zero-valued parameters should not appear in active_params."""
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        spot = read_spot(profile, 0)
        assert spot is not None
        # Only non-zero params
        assert "contrast" not in spot["parameters"]

    def test_read_multiple_spots(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.3})
        add_spot(profile, "highlights", {"exposure": -0.2})
        spot0 = read_spot(profile, 0)
        spot1 = read_spot(profile, 1)
        assert spot0 is not None
        assert spot1 is not None
        assert spot0["parameters"]["exposure"] == 0.3
        assert spot1["parameters"]["exposure"] == -0.2


class TestRemoveSpot:
    """Tests for removing Locallab spots."""

    def test_remove_only_spot(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert remove_spot(profile, 0) is True
        assert get_spot_count(profile) == 0

    def test_remove_first_of_two(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5}, spot_name="Shadow")
        add_spot(profile, "highlights", {"exposure": -0.3}, spot_name="Highlight")
        assert remove_spot(profile, 0) is True
        assert get_spot_count(profile) == 1
        # The highlight spot should now be at index 0
        spot = read_spot(profile, 0)
        assert spot is not None
        assert spot["name"] == "Highlight"

    def test_remove_last_of_two(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5}, spot_name="Shadow")
        add_spot(profile, "highlights", {"exposure": -0.3}, spot_name="Highlight")
        assert remove_spot(profile, 1) is True
        assert get_spot_count(profile) == 1
        spot = read_spot(profile, 0)
        assert spot is not None
        assert spot["name"] == "Shadow"

    def test_remove_invalid_index(self):
        profile = PP3Profile()
        assert remove_spot(profile, 0) is False
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert remove_spot(profile, 1) is False
        assert remove_spot(profile, -1) is False


class TestUpdateSpot:
    """Tests for updating Locallab spots."""

    def test_update_parameters(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert update_spot(profile, 0, parameters={"exposure": 0.3})
        assert profile.get("Locallab", "Expcomp_0") == "0.3"

    def test_update_enabled(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert update_spot(profile, 0, enabled=False)
        assert profile.get("Locallab", "Activ_0") == "false"

    def test_update_luminance_range(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        new_range = {"lower": 10, "upper": 50, "lower_transition": 5, "upper_transition": 10}
        assert update_spot(profile, 0, luminance_range=new_range)
        curve = profile.get("Locallab", "LLmaskexpcurve_0")
        assert "0.1000" in curve  # lower = 10%
        assert "0.5000" in curve  # upper = 50%

    def test_update_invalid_index(self):
        profile = PP3Profile()
        assert update_spot(profile, 0, parameters={"exposure": 0.3}) is False

    def test_update_with_strength(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 1.0})
        assert update_spot(profile, 0, parameters={"exposure": 1.0}, strength=50)
        assert profile.get("Locallab", "Expcomp_0") == "0.5"


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


class TestPresets:
    """Tests for local adjustment presets."""

    def test_list_presets(self):
        presets = list_presets()
        assert "shadow_recovery" in presets
        assert "highlight_protection" in presets
        assert "split_tone_warm_cool" in presets
        assert "midtone_contrast" in presets
        assert "shadow_desaturation" in presets
        assert "amoled_optimize" in presets
        assert "hdr_natural" in presets

    def test_apply_shadow_recovery(self):
        profile = PP3Profile()
        indices = apply_preset(profile, "shadow_recovery")
        assert len(indices) == 1
        assert get_spot_count(profile) == 1
        spot = read_spot(profile, 0)
        assert spot is not None
        assert spot["name"] == "Shadow recovery"

    def test_apply_split_tone(self):
        profile = PP3Profile()
        indices = apply_preset(profile, "split_tone_warm_cool")
        assert len(indices) == 2
        assert get_spot_count(profile) == 2

    def test_apply_hdr_natural(self):
        profile = PP3Profile()
        indices = apply_preset(profile, "hdr_natural")
        assert len(indices) == 3
        assert get_spot_count(profile) == 3

    def test_apply_unknown_preset(self):
        profile = PP3Profile()
        with pytest.raises(ValueError, match="Unknown preset"):
            apply_preset(profile, "nonexistent")

    def test_intensity_scaling(self):
        """intensity=100 should double the default values."""
        profile_default = PP3Profile()
        apply_preset(profile_default, "shadow_recovery", intensity=50)
        default_exp = float(profile_default.get("Locallab", "Expcomp_0"))

        profile_double = PP3Profile()
        apply_preset(profile_double, "shadow_recovery", intensity=100)
        double_exp = float(profile_double.get("Locallab", "Expcomp_0"))

        assert abs(double_exp - default_exp * 2) < 0.01

    def test_intensity_half(self):
        """intensity=25 should halve the default values."""
        profile_default = PP3Profile()
        apply_preset(profile_default, "shadow_recovery", intensity=50)
        default_exp = float(profile_default.get("Locallab", "Expcomp_0"))

        profile_half = PP3Profile()
        apply_preset(profile_half, "shadow_recovery", intensity=25)
        half_exp = float(profile_half.get("Locallab", "Expcomp_0"))

        assert abs(half_exp - default_exp * 0.5) < 0.01

    def test_preset_on_existing_profile(self):
        """Preset should add spots to an existing profile with Locallab spots."""
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        assert get_spot_count(profile) == 1

        apply_preset(profile, "highlight_protection")
        assert get_spot_count(profile) == 2

    def test_preset_integer_values_preserved(self):
        """Preset scaling must preserve integer type for whole numbers.

        RT CLI crashes when integer-only keys (Contrast, Noiselumf, Hlcompr)
        contain float strings like "15.0" instead of "15".
        """
        profile = PP3Profile()
        apply_preset(profile, "hdr_natural", intensity=50)  # scale=1.0

        # These keys must be integer strings, not "5.0", "15.0", "30.0"
        assert profile.get("Locallab", "Noiselumf_0") == "5"
        assert profile.get("Locallab", "Contrast_1") == "15"
        assert profile.get("Locallab", "Saturated_1") == "5"
        assert profile.get("Locallab", "Hlcompr_2") == "30"

    def test_preset_non_integer_results_stay_float(self):
        """When scaling produces a non-whole number, keep as float."""
        profile = PP3Profile()
        apply_preset(profile, "hdr_natural", intensity=75)  # scale=1.5

        # 15 * 1.5 = 22.5 → float
        assert profile.get("Locallab", "Contrast_1") == "22.5"
        # 30 * 1.5 = 45 → int
        assert profile.get("Locallab", "Hlcompr_2") == "45"


class TestLocallabRoundtrip:
    """Tests for save/load/copy roundtrip with Locallab profiles.

    Reproduces the crash reported in the Locallab render pipeline:
    profiles with Locallab sections would fail with
    'NoneType' object has no attribute 'strip' when passed to
    render tools (_render_preview, process_raw, etc.).
    """

    def test_single_spot_roundtrip(self, tmp_path):
        """Save a profile with one Locallab spot, load it, copy and save again."""
        profile = PP3Profile()
        profile.set("Version", "AppVersion", "5.11")
        profile.set("Exposure", "Compensation", "0")
        profile.set("Crop", "Enabled", "false")
        profile.set("Resize", "Enabled", "false")
        add_spot(profile, "shadows", {"exposure": 0.5})

        # Save
        path = tmp_path / "locallab_single.pp3"
        profile.save(path)

        # Load into new profile (like preview_raw does)
        loaded = PP3Profile()
        loaded.load(path)

        # Verify Locallab data survived roundtrip
        assert get_spot_count(loaded) == 1
        assert loaded.get("Locallab", "Expcomp_0") == "0.5"
        assert loaded.get("Locallab", "Expexpose_0") == "true"

        # Copy and modify resize (like _render_preview does)
        combined = loaded.copy()
        combined.set("Resize", "Enabled", "true")
        combined.set("Resize", "Width", "600")
        combined.set("Resize", "Height", "600")

        # Save the combined profile (should not crash)
        combined_path = tmp_path / "combined.pp3"
        combined.save(combined_path)

        # Verify the combined file is valid
        reloaded = PP3Profile()
        reloaded.load(combined_path)
        assert get_spot_count(reloaded) == 1
        assert reloaded.get("Resize", "Enabled") == "true"

    def test_multi_spot_roundtrip(self, tmp_path):
        """Save a profile with multiple Locallab spots (hdr_natural preset)."""
        profile = PP3Profile()
        profile.set("Version", "AppVersion", "5.11")
        profile.set("Exposure", "Compensation", "0")
        apply_preset(profile, "hdr_natural", intensity=50)
        assert get_spot_count(profile) == 3

        # Save, load, copy, save
        path = tmp_path / "locallab_multi.pp3"
        profile.save(path)

        loaded = PP3Profile()
        loaded.load(path)
        assert get_spot_count(loaded) == 3

        combined = loaded.copy()
        combined.set("Resize", "Enabled", "true")
        combined.set("Resize", "Width", "600")

        combined_path = tmp_path / "combined_multi.pp3"
        combined.save(combined_path)

        reloaded = PP3Profile()
        reloaded.load(combined_path)
        assert get_spot_count(reloaded) == 3

        # Verify all spots survived
        for i in range(3):
            spot = read_spot(reloaded, i)
            assert spot is not None

    def test_locallab_curve_values_preserved(self, tmp_path):
        """Semicolon-delimited curve values must survive save/load."""
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})

        curve = profile.get("Locallab", "LLmaskexpcurve_0")
        assert ";" in curve  # Must have semicolon-separated values

        path = tmp_path / "curves.pp3"
        profile.save(path)

        loaded = PP3Profile()
        loaded.load(path)

        assert loaded.get("Locallab", "LLmaskexpcurve_0") == curve

    def test_locallab_empty_curve_values_preserved(self, tmp_path):
        """Empty curve values like '0;' must survive save/load."""
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})

        # These are the "0;" values from _spot_defaults
        assert profile.get("Locallab", "Lcurve_0") == "0;"
        assert profile.get("Locallab", "Lmaskexpcurve_0") == "0;"

        path = tmp_path / "empty_curves.pp3"
        profile.save(path)

        loaded = PP3Profile()
        loaded.load(path)
        assert loaded.get("Locallab", "Lcurve_0") == "0;"
        assert loaded.get("Locallab", "Lmaskexpcurve_0") == "0;"

    def test_read_spot_after_roundtrip(self, tmp_path):
        """read_spot must work after save/load with Locallab profiles."""
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5}, spot_name="Shadow lift")

        path = tmp_path / "read_spot_rt.pp3"
        profile.save(path)

        loaded = PP3Profile()
        loaded.load(path)

        spot = read_spot(loaded, 0)
        assert spot is not None
        assert spot["name"] == "Shadow lift"
        assert spot["type"] == "shadows"
        assert spot["parameters"]["exposure"] == 0.5

    def test_dumps_with_locallab_does_not_crash(self):
        """dumps() must handle Locallab section without errors."""
        profile = PP3Profile()
        apply_preset(profile, "hdr_natural", intensity=75)

        # This is the operation that crashed in the bug report
        text = profile.dumps()
        assert "[Locallab]" in text
        assert "Spots=3" in text
        assert "Expcomp_0=" in text


class TestSpotCount:
    """Tests for spot counting."""

    def test_empty_profile(self):
        profile = PP3Profile()
        assert get_spot_count(profile) == 0

    def test_with_spots(self):
        profile = PP3Profile()
        add_spot(profile, "shadows", {"exposure": 0.5})
        add_spot(profile, "highlights", {"exposure": -0.3})
        assert get_spot_count(profile) == 2

    def test_invalid_spots_value(self):
        profile = PP3Profile()
        profile.set("Locallab", "Spots", "abc")
        assert get_spot_count(profile) == 0
