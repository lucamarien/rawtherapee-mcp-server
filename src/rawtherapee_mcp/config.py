"""Configuration management via environment variables.

Environment variables:
    RT_CLI_PATH: Path to rawtherapee-cli binary (auto-detected if not set)
    RT_OUTPUT_DIR: Default output directory (default: ~/Pictures/rawtherapee-mcp-output)
    RT_PREVIEW_DIR: Preview image directory (default: OS temp dir)
    RT_CUSTOM_TEMPLATES_DIR: Custom PP3 templates directory (default: ~/.rawtherapee-mcp/custom_templates)
    RT_PREVIEW_MAX_WIDTH: Max preview width in pixels (default: 1200)
    RT_JPEG_QUALITY: Default JPEG quality 1-100 (default: 95)
    RT_LOG_LEVEL: Logging level (default: WARNING)
    RT_HALDCLUT_DIR: Directory containing HaldCLUT PNG/TIFF files for film simulation
    RT_LCP_DIR: Optional directory containing Adobe Lens Correction Profile (.lcp) files
    RT_LENSFUN_DIR: Optional override for Lensfun database directory (auto-detected per platform if not set)
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
    haldclut_dir: Path | None
    lcp_dir: Path | None
    lensfun_dir: Path | None


def find_lensfun_dir(rt_cli_path: Path | None) -> Path | None:
    """Auto-detect the Lensfun database directory.

    Checks platform-specific paths, falling back to a path relative to the
    RT binary on Windows and macOS.

    Returns:
        Path to the directory containing Lensfun XML files, or None if not found.
    """
    system = platform.system()

    candidates: list[Path] = []

    if system == "Linux":
        candidates = [
            Path("/usr/share/lensfun"),
            Path("/usr/share/lensfun/version_1"),
            Path("/usr/local/share/lensfun"),
        ]
    elif system == "Darwin":
        candidates = [
            Path("/usr/local/share/lensfun"),
            Path("/opt/homebrew/share/lensfun"),
        ]
        if rt_cli_path:
            candidates.append(rt_cli_path.parent.parent / "share" / "lensfun")
    else:  # Windows
        if rt_cli_path:
            candidates.append(rt_cli_path.parent / "share" / "lensfun")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates.append(Path(program_files) / "RawTherapee" / "share" / "lensfun")

    for candidate in candidates:
        if candidate.is_dir():
            return candidate

    return None


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

    # HaldCLUT directory for film simulation LUTs
    haldclut_dir: Path | None = None
    haldclut_str = os.environ.get("RT_HALDCLUT_DIR", "").strip()
    if haldclut_str:
        haldclut_candidate = Path(haldclut_str)
        if haldclut_candidate.is_dir():
            haldclut_dir = haldclut_candidate
        else:
            logger.warning("RT_HALDCLUT_DIR set to %s but directory does not exist", haldclut_candidate)

    # Adobe LCP directory (optional)
    lcp_dir: Path | None = None
    lcp_str = os.environ.get("RT_LCP_DIR", "").strip()
    if lcp_str:
        lcp_candidate = Path(lcp_str)
        if lcp_candidate.is_dir():
            lcp_dir = lcp_candidate
        else:
            logger.warning("RT_LCP_DIR set to %s but directory does not exist", lcp_candidate)

    # Lensfun database directory
    lensfun_dir: Path | None = None
    lensfun_str = os.environ.get("RT_LENSFUN_DIR", "").strip()
    if lensfun_str:
        lensfun_candidate = Path(lensfun_str)
        if lensfun_candidate.is_dir():
            lensfun_dir = lensfun_candidate
        else:
            logger.warning("RT_LENSFUN_DIR set to %s but directory does not exist", lensfun_candidate)
    else:
        lensfun_dir = find_lensfun_dir(rt_cli_path)
        if lensfun_dir:
            logger.info("Auto-detected Lensfun database at %s", lensfun_dir)

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
        haldclut_dir=haldclut_dir.resolve() if haldclut_dir else None,
        lcp_dir=lcp_dir.resolve() if lcp_dir else None,
        lensfun_dir=lensfun_dir.resolve() if lensfun_dir else None,
    )
