"""Shared test fixtures — mock RawTherapee configuration and context."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rawtherapee_mcp.config import RTConfig


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create temporary directories for testing."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    preview_dir = tmp_path / "preview"
    preview_dir.mkdir()
    custom_templates_dir = tmp_path / "custom_templates"
    custom_templates_dir.mkdir()
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    return {
        "output": output_dir,
        "preview": preview_dir,
        "custom_templates": custom_templates_dir,
        "templates": templates_dir,
    }


@pytest.fixture
def mock_config(tmp_dirs: dict[str, Path]) -> RTConfig:
    """Create a test configuration with RT CLI available."""
    return RTConfig(
        rt_cli_path=Path("/usr/bin/rawtherapee-cli"),
        output_dir=tmp_dirs["output"],
        preview_dir=tmp_dirs["preview"],
        custom_templates_dir=tmp_dirs["custom_templates"],
        preview_max_width=1200,
        default_jpeg_quality=95,
    )


@pytest.fixture
def mock_config_no_rt(tmp_dirs: dict[str, Path]) -> RTConfig:
    """Create a test configuration without RT CLI."""
    return RTConfig(
        rt_cli_path=None,
        output_dir=tmp_dirs["output"],
        preview_dir=tmp_dirs["preview"],
        custom_templates_dir=tmp_dirs["custom_templates"],
        preview_max_width=1200,
        default_jpeg_quality=95,
    )


@pytest.fixture
def mock_ctx(mock_config: RTConfig) -> MagicMock:
    """Create a mock FastMCP Context with config in lifespan_context."""
    ctx = MagicMock()
    ctx.lifespan_context = {"config": mock_config}
    return ctx


@pytest.fixture
def mock_ctx_no_rt(mock_config_no_rt: RTConfig) -> MagicMock:
    """Create a mock FastMCP Context without RT CLI."""
    ctx = MagicMock()
    ctx.lifespan_context = {"config": mock_config_no_rt}
    return ctx


@pytest.fixture
def sample_pp3_path() -> Path:
    """Path to the sample PP3 fixture file."""
    return Path(__file__).parent / "fixtures" / "sample.pp3"


@pytest.fixture
def env_vars(tmp_dirs: dict[str, Path]) -> Generator[dict[str, str]]:
    """Set test environment variables."""
    test_env = {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": str(tmp_dirs["output"]),
        "RT_PREVIEW_DIR": str(tmp_dirs["preview"]),
        "RT_CUSTOM_TEMPLATES_DIR": str(tmp_dirs["custom_templates"]),
        "RT_PREVIEW_MAX_WIDTH": "800",
        "RT_JPEG_QUALITY": "90",
        "RT_LOG_LEVEL": "WARNING",
    }
    with patch.dict("os.environ", test_env, clear=False):
        yield test_env
