"""RawTherapee CLI wrapper with cross-platform subprocess handling.

All CLI calls use subprocess argument lists (never shell=True) and are
wrapped with asyncio.to_thread() to avoid blocking the async event loop.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("rawtherapee_mcp")

_IS_WINDOWS = platform.system() == "Windows"


class RTProcessingError(Exception):
    """Raised when RawTherapee CLI processing fails."""


def _run_subprocess(
    cmd: list[str],
    *,
    capture_output: bool = True,
    text: bool = True,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with platform-specific settings."""
    return subprocess.run(  # noqa: S603
        cmd, capture_output=capture_output, text=text, timeout=timeout
    )


async def get_rt_version(rt_path: Path) -> str | None:
    """Get the RawTherapee version string.

    Args:
        rt_path: Path to the rawtherapee-cli binary.

    Returns:
        Version string (e.g. "5.11"), or None if detection fails.
    """
    try:
        result = await asyncio.to_thread(
            functools.partial(_run_subprocess, [str(rt_path), "--version"], timeout=10),
        )
        # RT outputs version info to stdout or stderr depending on version
        output = result.stdout.strip() or result.stderr.strip()
        if output:
            # Try to extract version number from output
            for line in output.splitlines():
                line = line.strip()
                if line:
                    return line
        return None
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("Failed to get RT version: %s", exc)
        return None


async def run_rt_cli(
    rt_path: Path,
    input_path: Path,
    output_path: Path,
    profiles: list[Path],
    output_format: str = "jpeg",
    jpeg_quality: int = 95,
    bit_depth: int = 16,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Run rawtherapee-cli to process a RAW file.

    Args:
        rt_path: Path to the rawtherapee-cli binary.
        input_path: Path to the input RAW file.
        output_path: Path for the output file.
        profiles: List of PP3 profile paths to apply (stacked in order).
        output_format: Output format - "jpeg", "tiff", or "png".
        jpeg_quality: JPEG quality 1-100 (only for JPEG output).
        bit_depth: Bit depth for TIFF/PNG output (8 or 16).
        overwrite: Whether to overwrite existing output.

    Returns:
        Dict with success status, output path, processing time, and file size.
    """
    # Resolve all paths to avoid 8.3 short name issues on Windows
    rt_resolved = rt_path.resolve()
    input_resolved = input_path.resolve()
    output_resolved = output_path.resolve()

    cmd: list[str] = [str(rt_resolved)]

    # Apply profiles in order (resolve each profile path)
    for profile in profiles:
        cmd.extend(["-p", str(profile.resolve())])

    # Output path (use -o for file path)
    cmd.extend(["-o", str(output_resolved)])

    # Format-specific flags
    match output_format.lower():
        case "jpeg":
            cmd.append(f"-j{jpeg_quality}")
            cmd.append("-js3")  # Best quality chroma subsampling
        case "tiff":
            cmd.append("-tz")  # Compressed TIFF
            cmd.append(f"-b{bit_depth}")
        case "png":
            cmd.append("-n")
            cmd.append(f"-b{bit_depth}")
        case _:
            return {
                "error": f"Unsupported output format: {output_format}",
                "suggestion": "Use 'jpeg', 'tiff', or 'png'",
            }

    if overwrite:
        cmd.append("-Y")

    cmd.append("-q")  # Quiet mode (no text output)

    # Input file must be last with -c flag
    cmd.extend(["-c", str(input_resolved)])

    cmd_str = " ".join(cmd)
    logger.info("Running RT CLI: %s", cmd_str)

    start = time.monotonic()
    try:
        result = await asyncio.to_thread(
            functools.partial(_run_subprocess, cmd, timeout=300),
        )
    except subprocess.TimeoutExpired:
        return {
            "error": "Processing timed out after 300 seconds",
            "suggestion": "Try a smaller file or simpler profile",
            "command": cmd_str,
        }
    except OSError as exc:
        return {
            "error": f"Failed to run rawtherapee-cli: {exc}",
            "suggestion": "Check that RT_CLI_PATH is correct and RawTherapee is installed",
            "command": cmd_str,
        }

    elapsed = time.monotonic() - start

    if result.returncode != 0:
        return {
            "error": f"rawtherapee-cli failed (exit code {result.returncode})",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "command": cmd_str,
            "suggestion": "Check the PP3 profile syntax and input file format",
            "processing_time": round(elapsed, 2),
        }

    file_size = output_resolved.stat().st_size if output_resolved.exists() else 0

    return {
        "success": True,
        "output_path": str(output_resolved),
        "processing_time": round(elapsed, 2),
        "file_size": file_size,
    }
