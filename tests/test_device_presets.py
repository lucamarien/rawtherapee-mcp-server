"""Tests for device presets module."""

from __future__ import annotations

from rawtherapee_mcp.device_presets import (
    BUILT_IN_PRESETS,
    add_custom_preset,
    delete_custom_preset,
    get_all_presets,
    get_preset,
    is_builtin_preset,
    load_custom_presets,
)


class TestBuiltInPresets:
    """Tests for built-in preset data."""

    def test_has_mobile_category(self):
        assert "mobile" in BUILT_IN_PRESETS

    def test_has_desktop_category(self):
        assert "desktop" in BUILT_IN_PRESETS

    def test_has_photo_formats(self):
        assert "photo_formats" in BUILT_IN_PRESETS

    def test_s26_ultra_dimensions(self):
        preset = BUILT_IN_PRESETS["mobile"]["s26_ultra"]
        assert preset["width"] == 1440
        assert preset["height"] == 3120

    def test_4k_uhd_dimensions(self):
        preset = BUILT_IN_PRESETS["desktop"]["4k_uhd"]
        assert preset["width"] == 3840
        assert preset["height"] == 2160


class TestGetPreset:
    """Tests for preset lookup."""

    def test_find_builtin(self, tmp_path):
        result = get_preset("s26_ultra", tmp_path)
        assert result is not None
        assert result["name"] == "Samsung Galaxy S26 Ultra"

    def test_find_custom(self, tmp_path):
        add_custom_preset("my_preset", "My Preset", 1000, 2000, "custom", tmp_path)
        result = get_preset("my_preset", tmp_path)
        assert result is not None
        assert result["width"] == 1000

    def test_not_found(self, tmp_path):
        result = get_preset("nonexistent", tmp_path)
        assert result is None

    def test_custom_overrides_builtin_namespace(self, tmp_path):
        # Custom preset with same ID as builtin should be found first
        add_custom_preset("s26_ultra", "Custom S26", 999, 999, "custom", tmp_path)
        result = get_preset("s26_ultra", tmp_path)
        assert result is not None
        assert result["width"] == 999


class TestCustomPresets:
    """Tests for custom preset CRUD."""

    def test_add_and_load(self, tmp_path):
        add_custom_preset("test_preset", "Test", 800, 600, "custom", tmp_path)
        presets = load_custom_presets(tmp_path)
        assert "test_preset" in presets
        assert presets["test_preset"]["width"] == 800

    def test_delete(self, tmp_path):
        add_custom_preset("test_preset", "Test", 800, 600, "custom", tmp_path)
        assert delete_custom_preset("test_preset", tmp_path)
        presets = load_custom_presets(tmp_path)
        assert "test_preset" not in presets

    def test_delete_nonexistent(self, tmp_path):
        assert not delete_custom_preset("nonexistent", tmp_path)

    def test_load_empty_dir(self, tmp_path):
        presets = load_custom_presets(tmp_path)
        assert presets == {}


class TestGetAllPresets:
    """Tests for listing all presets."""

    def test_includes_builtin(self, tmp_path):
        all_presets = get_all_presets(tmp_path)
        assert "mobile" in all_presets
        assert "desktop" in all_presets
        assert "photo_formats" in all_presets

    def test_includes_custom(self, tmp_path):
        add_custom_preset("my_preset", "My", 100, 200, "custom", tmp_path)
        all_presets = get_all_presets(tmp_path)
        assert "custom" in all_presets
        assert "my_preset" in all_presets["custom"]


class TestIsBuiltinPreset:
    """Tests for built-in preset detection."""

    def test_builtin(self):
        assert is_builtin_preset("s26_ultra")
        assert is_builtin_preset("4k_uhd")
        assert is_builtin_preset("photo_3_2")

    def test_not_builtin(self):
        assert not is_builtin_preset("my_custom_preset")
        assert not is_builtin_preset("nonexistent")
