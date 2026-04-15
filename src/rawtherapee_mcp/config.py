"""Configuration management via environment variables.

Environment variables:
    RT_CLI_PATH: Path to rawtherapee-cli binary (auto-detected if not set)
    RT_OUTPUT_DIR: Default output directory (default: ~/Pictures/rawtherapee-mcp-output)
    RT_PREVIEW_DIR: Preview image directory (default: OS temp dir)
    RT_CUSTOM_TEMPLATES_DIR: Custom PP3 templates directory (default: ~/.rawtherapee-mcp/custom_templates)
    RT_PREVIEW_MAX_WIDTH: Max preview width in pixels (default: 1200)
    RT_JPEG_QUALITY: Default JPEG quality 1-100 (default: 95)
    RT_LOG_LEVEL: Logging level (default: WARNING)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("rawtherapee_mcp")


class ConfigError(Exception):
    """Raised when configuration is invalid."""


@dataclass(frozen=True)
class RTConfig:
    """Immutable configuration loaded from environment variables."""

    rt_cli_path: Path | None
    output_dir: Path
    preview_dir: Path
    custom_templates_dir: Path
    preview_max_width: int
    default_jpeg_quality: int


def find_rt_cli() -> Path | None:
    """Auto-detect rawtherapee-cli binary location.

    Checks platform-specific default paths after trying PATH lookup.

    Returns:
        Path to the rawtherapee-cli binary, or None if not found.
    """
    system = platform.system()

    candidates: list[str | None] = []

    if system == "Windows":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates = [
            shutil.which("rawtherapee-cli"),
            str(Path(program_files) / "RawTherapee" / "5.11" / "rawtherapee-cli.exe"),
            str(Path(program_files) / "RawTherapee" / "rawtherapee-cli.exe"),
        ]
    elif system == "Darwin":
        candidates = [
            shutil.which("rawtherapee-cli"),
            "/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli",
        ]
    else:  # Linux
        candidates = [
            shutil.which("rawtherapee-cli"),
            "/usr/bin/rawtherapee-cli",
            "/usr/local/bin/rawtherapee-cli",
            "/snap/bin/rawtherapee-cli",
        ]

    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)

    return None


def _parse_int(value: str, var_name: str, min_val: int, max_val: int) -> int:
    """Parse and validate an integer environment variable.

    Raises:
        ConfigError: If the value is not a valid integer or out of range.
    """
    try:
        result = int(value)
    except ValueError:
        msg = f"{var_name} must be an integer (got {value!r})"
        raise ConfigError(msg) from None

    if result < min_val or result > max_val:
        msg = f"{var_name} must be between {min_val} and {max_val} (got {result})"
        raise ConfigError(msg)

    return result


def _setup_logging() -> None:
    """Configure logging to stderr only."""
    level_str = os.environ.get("RT_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_str, logging.WARNING)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(name)s %(levelname)s: %(message)s"))
    root_logger = logging.getLogger("rawtherapee_mcp")
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def load_config() -> RTConfig:
    """Load and validate configuration from environment variables.

    The server starts even if RT CLI is not found — tools that require it
    will return error dicts. This enables check_rt_status to diagnose issues.

    Returns:
        Frozen dataclass with validated configuration.

    Raises:
        ConfigError: If environment variable values are invalid.
    """
    _setup_logging()

    # RT CLI path: env var override or auto-detect
    rt_cli_path: Path | None = None
    rt_cli_env = os.environ.get("RT_CLI_PATH", "").strip()
    if rt_cli_env:
        rt_cli_candidate = Path(rt_cli_env)
        if rt_cli_candidate.is_file():
            rt_cli_path = rt_cli_candidate
        else:
            logger.warning("RT_CLI_PATH set to %s but file does not exist", rt_cli_candidate)
    else:
        rt_cli_path = find_rt_cli()
        if rt_cli_path:
            logger.info("Auto-detected rawtherapee-cli at %s", rt_cli_path)
        else:
            logger.warning("rawtherapee-cli not found. Set RT_CLI_PATH or install RawTherapee.")

    # Output directory
    output_dir_str = os.environ.get("RT_OUTPUT_DIR", "").strip()
    if output_dir_str:
        output_dir = Path(output_dir_str)
    else:
        output_dir = Path.home() / "Pictures" / "rawtherapee-mcp-output"

    # Preview directory
    preview_dir_str = os.environ.get("RT_PREVIEW_DIR", "").strip()
    if preview_dir_str:
        preview_dir = Path(preview_dir_str)
    else:
        preview_dir = Path(tempfile.gettempdir())

    # Custom templates directory
    custom_templates_str = os.environ.get("RT_CUSTOM_TEMPLATES_DIR", "").strip()
    if custom_templates_str:
        custom_templates_dir = Path(custom_templates_str)
    else:
        custom_templates_dir = Path.home() / ".rawtherapee-mcp" / "custom_templates"

    # Preview max width
    preview_max_width_str = os.environ.get("RT_PREVIEW_MAX_WIDTH", "1200").strip()
    preview_max_width = _parse_int(preview_max_width_str, "RT_PREVIEW_MAX_WIDTH", 100, 10000)

    # JPEG quality
    jpeg_quality_str = os.environ.get("RT_JPEG_QUALITY", "95").strip()
    default_jpeg_quality = _parse_int(jpeg_quality_str, "RT_JPEG_QUALITY", 1, 100)

    # Ensure output directories exist
    output_dir.mkdir(parents=True, exist_ok=True)
    custom_templates_dir.mkdir(parents=True, exist_ok=True)

    # Resolve all paths to canonical form (avoids 8.3 short names on Windows)
    return RTConfig(
        rt_cli_path=rt_cli_path.resolve() if rt_cli_path else None,
        output_dir=output_dir.resolve(),
        preview_dir=preview_dir.resolve(),
        custom_templates_dir=custom_templates_dir.resolve(),
        preview_max_width=preview_max_width,
        default_jpeg_quality=default_jpeg_quality,
    )
