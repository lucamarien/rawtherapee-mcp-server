"""Tests for configuration management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rawtherapee_mcp.config import ConfigError, find_rt_cli, load_config


class TestFindRtCli:
    """Tests for RT CLI auto-detection."""

    def test_found_via_which(self):
        with patch("rawtherapee_mcp.config.shutil.which", return_value="/usr/bin/rawtherapee-cli"):
            with patch.object(Path, "is_file", return_value=True):
                result = find_rt_cli()
                assert result == Path("/usr/bin/rawtherapee-cli")

    def test_not_found(self):
        with patch("rawtherapee_mcp.config.shutil.which", return_value=None):
            with patch.object(Path, "is_file", return_value=False):
                result = find_rt_cli()
                assert result is None

    def test_which_returns_none_fallback_path_exists(self):
        with patch("rawtherapee_mcp.config.shutil.which", return_value=None):
            with patch("rawtherapee_mcp.config.platform.system", return_value="Linux"):
                # Mock Path.is_file to return True for /usr/bin/rawtherapee-cli
                original_is_file = Path.is_file

                def mock_is_file(self):
                    if str(self) == "/usr/bin/rawtherapee-cli":
                        return True
                    return original_is_file(self)

                with patch.object(Path, "is_file", mock_is_file):
                    result = find_rt_cli()
                    assert result == Path("/usr/bin/rawtherapee-cli")


class TestLoadConfig:
    """Tests for configuration loading."""

    def test_loads_from_env_vars(self, env_vars, tmp_dirs):
        with patch.object(Path, "is_file", return_value=True):
            config = load_config()
            assert config.rt_cli_path == Path("/usr/bin/rawtherapee-cli")
            assert config.preview_max_width == 800
            assert config.default_jpeg_quality == 90

    def test_defaults_without_env_vars(self, tmp_dirs):
        with patch.dict("os.environ", {}, clear=True):
            with patch("rawtherapee_mcp.config.find_rt_cli", return_value=None):
                config = load_config()
                assert config.rt_cli_path is None
                assert config.preview_max_width == 1200
                assert config.default_jpeg_quality == 95

    def test_invalid_jpeg_quality(self, env_vars):
        with patch.dict("os.environ", {"RT_JPEG_QUALITY": "200"}):
            with pytest.raises(ConfigError, match="RT_JPEG_QUALITY must be between"):
                load_config()

    def test_invalid_preview_width_not_int(self, env_vars):
        with patch.dict("os.environ", {"RT_PREVIEW_MAX_WIDTH": "abc"}):
            with pytest.raises(ConfigError, match="RT_PREVIEW_MAX_WIDTH must be an integer"):
                load_config()

    def test_rt_cli_path_not_exists(self, tmp_dirs):
        with patch.dict("os.environ", {"RT_CLI_PATH": "/nonexistent/rawtherapee-cli"}, clear=True):
            config = load_config()
            assert config.rt_cli_path is None


class TestRTConfig:
    """Tests for the RTConfig dataclass."""

    def test_frozen(self, mock_config):
        with pytest.raises(AttributeError):
            mock_config.preview_max_width = 800  # type: ignore[misc]

    def test_rt_cli_path_optional(self, mock_config_no_rt):
        assert mock_config_no_rt.rt_cli_path is None
