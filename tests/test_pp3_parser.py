"""Tests for PP3 profile parser."""

from __future__ import annotations

import pytest

from rawtherapee_mcp.pp3_parser import PP3Profile


class TestPP3Load:
    """Tests for loading PP3 files."""

    def test_load_sample(self, sample_pp3_path):
        profile = PP3Profile()
        profile.load(sample_pp3_path)
        assert profile.has_section("Version")
        assert profile.get("Version", "AppVersion") == "5.11"

    def test_load_exposure(self, sample_pp3_path):
        profile = PP3Profile()
        profile.load(sample_pp3_path)
        assert profile.get("Exposure", "Compensation") == "0.0"
        assert profile.get("Exposure", "Brightness") == "0"

    def test_load_preserves_semicolons(self, sample_pp3_path):
        profile = PP3Profile()
        profile.load(sample_pp3_path)
        threshold = profile.get("Sharpening", "Threshold")
        assert threshold == "20;80;2000;1200;"

    def test_load_white_balance_section(self, sample_pp3_path):
        profile = PP3Profile()
        profile.load(sample_pp3_path)
        assert profile.has_section("White Balance")
        assert profile.get("White Balance", "Setting") == "Camera"
        assert profile.get("White Balance", "Temperature") == "5500"

    def test_load_nonexistent_raises(self, tmp_path):
        profile = PP3Profile()
        nonexistent = tmp_path / "nope.pp3"
        with pytest.raises(FileNotFoundError):
            profile.load(nonexistent)


class TestPP3LoadFromString:
    """Tests for loading PP3 from string."""

    def test_loads_simple(self):
        profile = PP3Profile()
        profile.loads("[Version]\nAppVersion=5.11\nVersion=351\n")
        assert profile.get("Version", "AppVersion") == "5.11"

    def test_loads_ignores_comments(self):
        profile = PP3Profile()
        profile.loads("# comment\n[Section]\nKey=Value\n")
        assert profile.get("Section", "Key") == "Value"

    def test_loads_ignores_empty_lines(self):
        profile = PP3Profile()
        profile.loads("\n\n[Section]\n\nKey=Value\n\n")
        assert profile.get("Section", "Key") == "Value"


class TestPP3Save:
    """Tests for saving PP3 files."""

    def test_roundtrip(self, sample_pp3_path, tmp_path):
        profile = PP3Profile()
        profile.load(sample_pp3_path)

        output_path = tmp_path / "output.pp3"
        profile.save(output_path)

        reloaded = PP3Profile()
        reloaded.load(output_path)

        assert reloaded.to_dict() == profile.to_dict()

    def test_roundtrip_preserves_semicolons(self, tmp_path):
        profile = PP3Profile()
        profile.set("Sharpening", "Threshold", "20;80;2000;1200;")
        path = tmp_path / "test.pp3"
        profile.save(path)

        reloaded = PP3Profile()
        reloaded.load(path)
        assert reloaded.get("Sharpening", "Threshold") == "20;80;2000;1200;"


class TestPP3GetSet:
    """Tests for get/set operations."""

    def test_set_creates_section(self):
        profile = PP3Profile()
        profile.set("NewSection", "Key", "Value")
        assert profile.has_section("NewSection")
        assert profile.get("NewSection", "Key") == "Value"

    def test_get_default(self):
        profile = PP3Profile()
        assert profile.get("Missing", "Key") == ""
        assert profile.get("Missing", "Key", "default") == "default"

    def test_has_key(self):
        profile = PP3Profile()
        profile.set("Section", "Key", "Value")
        assert profile.has_key("Section", "Key")
        assert not profile.has_key("Section", "Other")
        assert not profile.has_key("Missing", "Key")

    def test_set_coerces_none_to_empty(self):
        """set() with None value should store empty string, not None."""
        profile = PP3Profile()
        profile.set("Section", "Key", None)  # type: ignore[arg-type]
        assert profile.get("Section", "Key") == ""
        # Must not crash on strip
        assert profile.get("Section", "Key").strip() == ""

    def test_set_coerces_numeric_to_string(self):
        """set() with numeric values should store string representations."""
        profile = PP3Profile()
        profile.set("Section", "IntKey", 42)  # type: ignore[arg-type]
        profile.set("Section", "FloatKey", 3.14)  # type: ignore[arg-type]
        assert profile.get("Section", "IntKey") == "42"
        assert profile.get("Section", "FloatKey") == "3.14"

    def test_get_never_returns_none(self):
        """get() should never return None even with None stored or as default."""
        profile = PP3Profile()
        # Force None into _sections to simulate corruption
        profile._sections["Section"] = {"Key": None}  # type: ignore[dict-item]
        assert profile.get("Section", "Key") is not None
        assert profile.get("Section", "Key") == ""
        # Also test None default for missing key
        assert profile.get("Missing", "Key", None) is not None  # type: ignore[arg-type]


class TestPP3Merge:
    """Tests for profile merging."""

    def test_merge_adds_new_sections(self):
        a = PP3Profile()
        a.set("SectionA", "Key", "A")

        b = PP3Profile()
        b.set("SectionB", "Key", "B")

        a.merge(b)
        assert a.get("SectionA", "Key") == "A"
        assert a.get("SectionB", "Key") == "B"

    def test_merge_overrides_values(self):
        a = PP3Profile()
        a.set("Section", "Key", "Original")

        b = PP3Profile()
        b.set("Section", "Key", "Override")

        a.merge(b)
        assert a.get("Section", "Key") == "Override"


class TestPP3Diff:
    """Tests for profile diffing."""

    def test_diff_identical(self):
        a = PP3Profile()
        a.set("Section", "Key", "Value")

        b = PP3Profile()
        b.set("Section", "Key", "Value")

        result = a.diff(b)
        assert result["only_a"] == {}
        assert result["only_b"] == {}
        assert result["different"] == {}

    def test_diff_only_a(self):
        a = PP3Profile()
        a.set("Section", "Key", "Value")

        b = PP3Profile()

        result = a.diff(b)
        assert "Section" in result["only_a"]
        assert result["only_a"]["Section"]["Key"] == "Value"

    def test_diff_different_values(self):
        a = PP3Profile()
        a.set("Section", "Key", "A")

        b = PP3Profile()
        b.set("Section", "Key", "B")

        result = a.diff(b)
        assert result["different"]["Section"]["Key"]["a"] == "A"
        assert result["different"]["Section"]["Key"]["b"] == "B"


class TestPP3Sections:
    """Tests for section and key listing."""

    def test_sections(self):
        profile = PP3Profile()
        profile.set("A", "K", "V")
        profile.set("B", "K", "V")
        assert sorted(profile.sections()) == ["A", "B"]

    def test_keys(self):
        profile = PP3Profile()
        profile.set("Section", "A", "1")
        profile.set("Section", "B", "2")
        assert sorted(profile.keys("Section")) == ["A", "B"]
        assert profile.keys("Missing") == []


class TestPP3Copy:
    """Tests for profile deep copy."""

    def test_copy_preserves_data(self):
        profile = PP3Profile()
        profile.set("Exposure", "Compensation", "1.5")
        profile.set("Crop", "Enabled", "true")

        clone = profile.copy()
        assert clone.get("Exposure", "Compensation") == "1.5"
        assert clone.get("Crop", "Enabled") == "true"

    def test_copy_is_independent(self):
        """Modifying the copy should not affect the original."""
        profile = PP3Profile()
        profile.set("Exposure", "Compensation", "1.5")

        clone = profile.copy()
        clone.set("Exposure", "Compensation", "3.0")

        assert profile.get("Exposure", "Compensation") == "1.5"
        assert clone.get("Exposure", "Compensation") == "3.0"

    def test_copy_empty_profile(self):
        profile = PP3Profile()
        clone = profile.copy()
        assert clone.sections() == []


class TestPP3Interpolate:
    """Tests for profile interpolation."""

    def test_numeric_midpoint(self):
        a = PP3Profile()
        a.set("Exposure", "Compensation", "0")
        b = PP3Profile()
        b.set("Exposure", "Compensation", "2")

        result = PP3Profile.interpolate(a, b, 0.5)
        assert result.get("Exposure", "Compensation") == "1"

    def test_factor_zero_returns_a(self):
        a = PP3Profile()
        a.set("Exposure", "Compensation", "1.5")
        b = PP3Profile()
        b.set("Exposure", "Compensation", "3.0")

        result = PP3Profile.interpolate(a, b, 0.0)
        assert result.get("Exposure", "Compensation") == "1.5"

    def test_factor_one_returns_b(self):
        a = PP3Profile()
        a.set("Exposure", "Compensation", "1.5")
        b = PP3Profile()
        b.set("Exposure", "Compensation", "3.0")

        result = PP3Profile.interpolate(a, b, 1.0)
        assert result.get("Exposure", "Compensation") == "3"

    def test_non_numeric_takes_nearer(self):
        a = PP3Profile()
        a.set("White Balance", "Setting", "Daylight")
        b = PP3Profile()
        b.set("White Balance", "Setting", "Cloudy")

        result_low = PP3Profile.interpolate(a, b, 0.3)
        assert result_low.get("White Balance", "Setting") == "Daylight"

        result_high = PP3Profile.interpolate(a, b, 0.7)
        assert result_high.get("White Balance", "Setting") == "Cloudy"

    def test_semicolon_values_take_nearer(self):
        a = PP3Profile()
        a.set("Sharpening", "Threshold", "20;80;2000;1200;")
        b = PP3Profile()
        b.set("Sharpening", "Threshold", "30;90;3000;1500;")

        result = PP3Profile.interpolate(a, b, 0.3)
        assert result.get("Sharpening", "Threshold") == "20;80;2000;1200;"

    def test_key_only_in_a(self):
        a = PP3Profile()
        a.set("Exposure", "Compensation", "1.5")
        b = PP3Profile()

        result = PP3Profile.interpolate(a, b, 0.5)
        assert result.get("Exposure", "Compensation") == "1.5"

    def test_key_only_in_b(self):
        a = PP3Profile()
        b = PP3Profile()
        b.set("Exposure", "Compensation", "2.0")

        result = PP3Profile.interpolate(a, b, 0.5)
        assert result.get("Exposure", "Compensation") == "2.0"

    def test_integer_formatting_preserved(self):
        """When both values are integers, result should be integer string."""
        a = PP3Profile()
        a.set("Sharpening", "Amount", "50")
        b = PP3Profile()
        b.set("Sharpening", "Amount", "100")

        result = PP3Profile.interpolate(a, b, 0.5)
        assert result.get("Sharpening", "Amount") == "75"
        assert "." not in result.get("Sharpening", "Amount")

    def test_float_formatting_preserved(self):
        """When values have decimals, result should be float."""
        a = PP3Profile()
        a.set("Exposure", "Compensation", "0.0")
        b = PP3Profile()
        b.set("Exposure", "Compensation", "2.0")

        result = PP3Profile.interpolate(a, b, 0.5)
        assert float(result.get("Exposure", "Compensation")) == pytest.approx(1.0)

    def test_factor_clamped(self):
        """Factor outside [0, 1] should be clamped."""
        a = PP3Profile()
        a.set("Exposure", "Compensation", "0")
        b = PP3Profile()
        b.set("Exposure", "Compensation", "10")

        result_neg = PP3Profile.interpolate(a, b, -0.5)
        assert result_neg.get("Exposure", "Compensation") == "0"

        result_over = PP3Profile.interpolate(a, b, 1.5)
        assert result_over.get("Exposure", "Compensation") == "10"

    def test_multi_section(self):
        """Interpolation across multiple sections."""
        a = PP3Profile()
        a.set("Exposure", "Compensation", "0")
        a.set("Sharpening", "Amount", "50")
        b = PP3Profile()
        b.set("Exposure", "Compensation", "2")
        b.set("Sharpening", "Amount", "150")

        result = PP3Profile.interpolate(a, b, 0.5)
        assert result.get("Exposure", "Compensation") == "1"
        assert result.get("Sharpening", "Amount") == "100"

    def test_empty_profiles(self):
        a = PP3Profile()
        b = PP3Profile()
        result = PP3Profile.interpolate(a, b, 0.5)
        assert result.sections() == []
