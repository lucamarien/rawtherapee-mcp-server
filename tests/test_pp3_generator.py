"""Tests for PP3 profile generation."""

from __future__ import annotations

import pytest

from rawtherapee_mcp.pp3_generator import (
    apply_device_crop,
    apply_device_preset,
    apply_parameters,
    create_neutral_profile,
    generate_profile,
)


class TestCreateNeutralProfile:
    """Tests for neutral profile creation."""

    def test_has_version(self):
        profile = create_neutral_profile()
        assert profile.get("Version", "AppVersion") == "5.11"
        assert profile.get("Version", "Version") == "351"

    def test_neutral_exposure(self):
        profile = create_neutral_profile()
        assert profile.get("Exposure", "Compensation") == "0"
        assert profile.get("Exposure", "Brightness") == "0"
        assert profile.get("Exposure", "Contrast") == "0"

    def test_camera_white_balance(self):
        profile = create_neutral_profile()
        assert profile.get("White Balance", "Setting") == "Camera"

    def test_no_crop(self):
        profile = create_neutral_profile()
        assert profile.get("Crop", "Enabled") == "false"

    def test_sharpening_enabled(self):
        profile = create_neutral_profile()
        assert profile.get("Sharpening", "Enabled") == "true"


class TestApplyParameters:
    """Tests for parameter application."""

    def test_exposure_compensation(self):
        profile = create_neutral_profile()
        apply_parameters(profile, {"exposure": {"compensation": 1.5}})
        assert profile.get("Exposure", "Compensation") == "1.5"

    def test_white_balance(self):
        profile = create_neutral_profile()
        apply_parameters(profile, {"white_balance": {"method": "Custom", "temperature": 6500}})
        assert profile.get("White Balance", "Setting") == "Custom"
        assert profile.get("White Balance", "Temperature") == "6500"

    def test_crop_enabled(self):
        profile = create_neutral_profile()
        apply_parameters(profile, {"crop": {"enabled": True, "width": 1440, "height": 3120}})
        assert profile.get("Crop", "Enabled") == "true"
        assert profile.get("Crop", "W") == "1440"
        assert profile.get("Crop", "H") == "3120"

    def test_crop_short_aliases(self):
        """Test that w, h, fixedRatio aliases work for crop parameters."""
        profile = create_neutral_profile()
        apply_parameters(
            profile,
            {"crop": {"enabled": True, "x": 692, "y": 0, "w": 3108, "h": 6732, "fixedRatio": True, "ratio": "9:19.5"}},
        )
        assert profile.get("Crop", "Enabled") == "true"
        assert profile.get("Crop", "X") == "692"
        assert profile.get("Crop", "Y") == "0"
        assert profile.get("Crop", "W") == "3108"
        assert profile.get("Crop", "H") == "6732"
        assert profile.get("Crop", "FixedRatio") == "true"
        assert profile.get("Crop", "Ratio") == "9:19.5"

    def test_case_insensitive_group_names(self):
        """Test that group names are case-insensitive."""
        profile = create_neutral_profile()
        apply_parameters(profile, {"Exposure": {"compensation": 2.0}})
        assert profile.get("Exposure", "Compensation") == "2.0"

    def test_case_insensitive_param_names(self):
        """Test that param names are case-insensitive."""
        profile = create_neutral_profile()
        apply_parameters(profile, {"crop": {"FixedRatio": True, "Width": 1000}})
        assert profile.get("Crop", "FixedRatio") == "true"
        assert profile.get("Crop", "W") == "1000"

    def test_camel_case_group_names(self):
        """Test whiteBalance / noiseReduction aliases."""
        profile = create_neutral_profile()
        apply_parameters(profile, {"whiteBalance": {"temperature": 6000}})
        assert profile.get("White Balance", "Temperature") == "6000"

    def test_noise_reduction(self):
        profile = create_neutral_profile()
        apply_parameters(profile, {"noise_reduction": {"enabled": True, "luminance": 20, "chrominance": 15}})
        assert profile.get("Directional Pyramid Denoising", "Enabled") == "true"
        assert profile.get("Directional Pyramid Denoising", "Luma") == "20"

    def test_multiple_groups(self):
        profile = create_neutral_profile()
        apply_parameters(
            profile,
            {
                "exposure": {"compensation": 0.5, "contrast": 10},
                "sharpening": {"amount": 250},
            },
        )
        assert profile.get("Exposure", "Compensation") == "0.5"
        assert profile.get("Exposure", "Contrast") == "10"
        assert profile.get("Sharpening", "Amount") == "250"

    def test_unknown_group_ignored(self):
        profile = create_neutral_profile()
        apply_parameters(profile, {"unknown_group": {"key": "value"}})
        # Should not crash, just log a warning

    def test_unknown_param_ignored(self):
        profile = create_neutral_profile()
        apply_parameters(profile, {"exposure": {"unknown_param": 42}})
        # Should not crash

    def test_raw_fallback_sets_pp3_values(self):
        """Test raw_fallback mode for unrecognized groups."""
        profile = create_neutral_profile()
        apply_parameters(
            profile,
            {"Crop": {"W": "3108", "H": "6732", "FixedRatio": "true", "Guide": "Frame"}},
            raw_fallback=True,
        )
        assert profile.get("Crop", "W") == "3108"
        assert profile.get("Crop", "H") == "6732"
        assert profile.get("Crop", "FixedRatio") == "true"
        assert profile.get("Crop", "Guide") == "Frame"

    def test_raw_fallback_with_bool_values(self):
        """Test that raw_fallback converts booleans correctly."""
        profile = create_neutral_profile()
        apply_parameters(
            profile,
            {"SomeSection": {"Enabled": True, "Disabled": False}},
            raw_fallback=True,
        )
        assert profile.get("SomeSection", "Enabled") == "true"
        assert profile.get("SomeSection", "Disabled") == "false"

    def test_raw_fallback_mixed_with_friendly(self):
        """Test raw_fallback with a mix of friendly and raw groups."""
        profile = create_neutral_profile()
        apply_parameters(
            profile,
            {
                "exposure": {"compensation": 1.5},
                "Crop": {"W": "3108", "H": "6732"},
            },
            raw_fallback=True,
        )
        assert profile.get("Exposure", "Compensation") == "1.5"
        assert profile.get("Crop", "W") == "3108"
        assert profile.get("Crop", "H") == "6732"


class TestApplyDevicePreset:
    """Tests for device preset application (resize only, no crop)."""

    def test_sets_resize_only(self):
        profile = create_neutral_profile()
        apply_device_preset(profile, {"width": 1440, "height": 3120})
        # Should set resize but NOT crop
        assert profile.get("Resize", "Enabled") == "true"
        assert profile.get("Resize", "Width") == "1440"
        assert profile.get("Resize", "Height") == "3120"
        assert profile.get("Resize", "AppliesTo") == "Full Image"
        assert profile.get("Resize", "Scale") == "1"
        assert profile.get("Resize", "DataSpecified") == "3"
        assert profile.get("Resize", "AllowUpscaling") == "false"
        # Crop should remain disabled (from neutral profile)
        assert profile.get("Crop", "Enabled") == "false"

    def test_missing_dimensions_skipped(self):
        profile = create_neutral_profile()
        apply_device_preset(profile, {"name": "No dims"})
        assert profile.get("Crop", "Enabled") == "false"


class TestApplyDeviceCrop:
    """Tests for aspect-ratio crop calculation with source dimensions."""

    def test_landscape_source_to_portrait_target(self):
        """4480x6720 portrait source -> 1440x3120 S26 Ultra."""
        profile = create_neutral_profile()
        apply_device_crop(profile, {"width": 1440, "height": 3120}, 4480, 6720)

        assert profile.get("Crop", "Enabled") == "true"
        crop_w = int(profile.get("Crop", "W"))
        crop_h = int(profile.get("Crop", "H"))
        crop_x = int(profile.get("Crop", "X"))
        crop_y = int(profile.get("Crop", "Y"))

        # Crop should use full height, reduced width
        assert crop_h == 6720
        # Target ratio: 1440/3120 = 0.4615, so crop_w ≈ 6720 * 0.4615 ≈ 3101
        assert 3090 < crop_w < 3110
        # Crop should be centered
        assert crop_x == (4480 - crop_w) // 2
        assert crop_y == 0

        # Crop should have all required RT fields
        assert profile.get("Crop", "FixedRatio") == "true"
        assert profile.get("Crop", "Ratio") == "1440:3120"
        assert profile.get("Crop", "Orientation") == "As Image"
        assert profile.get("Crop", "Guide") == "Frame"

        # RT 5.12 bug: Resize must be disabled when Crop is enabled
        assert profile.get("Resize", "Enabled") == "false"

    def test_landscape_source_to_landscape_target(self):
        """6720x4480 landscape source -> 3840x2160 4K."""
        profile = create_neutral_profile()
        apply_device_crop(profile, {"width": 3840, "height": 2160}, 6720, 4480)

        crop_w = int(profile.get("Crop", "W"))
        crop_h = int(profile.get("Crop", "H"))

        # Target ratio: 3840/2160 = 1.778, source ratio: 6720/4480 = 1.5
        # Source is narrower than target -> use full width, crop height
        assert crop_w == 6720
        assert 3770 < crop_h < 3790  # 6720/1.778 ≈ 3780

        # Resize must be disabled (RT 5.12 Crop+Resize bug)
        assert profile.get("Resize", "Enabled") == "false"

    def test_same_aspect_ratio(self):
        """Source and target have same aspect ratio."""
        profile = create_neutral_profile()
        apply_device_crop(profile, {"width": 1920, "height": 1080}, 3840, 2160)

        crop_w = int(profile.get("Crop", "W"))
        crop_h = int(profile.get("Crop", "H"))

        # Should use the full image
        assert crop_w == 3840
        assert crop_h == 2160

        # Resize must be disabled
        assert profile.get("Resize", "Enabled") == "false"

    def test_invalid_source_falls_back_to_resize(self):
        """Invalid source dimensions should fall back to resize-only."""
        profile = create_neutral_profile()
        apply_device_crop(profile, {"width": 1440, "height": 3120}, 0, 0)

        # Should set resize but not crop
        assert profile.get("Resize", "Enabled") == "true"
        assert profile.get("Crop", "Enabled") == "false"


class TestGenerateProfile:
    """Tests for the full profile generation workflow."""

    def test_generate_neutral(self, tmp_path):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        profile, output_path = generate_profile(
            name="test_neutral",
            base_template=None,
            parameters=None,
            device_preset=None,
            templates_dir=templates_dir,
            custom_templates_dir=custom_dir,
        )

        assert output_path.exists()
        assert output_path.name == "test_neutral.pp3"
        assert profile.get("Exposure", "Compensation") == "0"

    def test_generate_with_parameters(self, tmp_path):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        profile, output_path = generate_profile(
            name="bright",
            base_template=None,
            parameters={"exposure": {"compensation": 1.0, "brightness": 20}},
            device_preset=None,
            templates_dir=templates_dir,
            custom_templates_dir=custom_dir,
        )

        assert profile.get("Exposure", "Compensation") == "1.0"
        assert profile.get("Exposure", "Brightness") == "20"

    def test_generate_with_base_template(self, tmp_path):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        # Create a template
        template_path = templates_dir / "test_template.pp3"
        template_path.write_text(
            "[Version]\nAppVersion=5.11\nVersion=351\n[Exposure]\nCompensation=0.5\nBrightness=10\n"
        )

        profile, _ = generate_profile(
            name="from_template",
            base_template="test_template",
            parameters={"exposure": {"brightness": 30}},
            device_preset=None,
            templates_dir=templates_dir,
            custom_templates_dir=custom_dir,
        )

        # Template's compensation preserved, brightness overridden
        assert profile.get("Exposure", "Compensation") == "0.5"
        assert profile.get("Exposure", "Brightness") == "30"

    def test_generate_template_not_found(self, tmp_path):
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            generate_profile(
                name="bad",
                base_template="nonexistent",
                parameters=None,
                device_preset=None,
                templates_dir=templates_dir,
                custom_templates_dir=custom_dir,
            )
