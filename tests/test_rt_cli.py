"""Tests for RawTherapee CLI wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rawtherapee_mcp.rt_cli import get_rt_version, run_rt_cli


class TestGetRtVersion:
    """Tests for version detection."""

    async def test_returns_version_string(self):
        mock_result = MagicMock()
        mock_result.stdout = "RawTherapee, version 5.11"
        mock_result.stderr = ""

        with patch("rawtherapee_mcp.rt_cli.asyncio.to_thread", return_value=mock_result):
            version = await get_rt_version(Path("/usr/bin/rawtherapee-cli"))
            assert version == "RawTherapee, version 5.11"

    async def test_returns_none_on_timeout(self):
        import subprocess

        with patch(
            "rawtherapee_mcp.rt_cli.asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired("cmd", 10),
        ):
            version = await get_rt_version(Path("/usr/bin/rawtherapee-cli"))
            assert version is None

    async def test_returns_none_on_os_error(self):
        with patch(
            "rawtherapee_mcp.rt_cli.asyncio.to_thread",
            side_effect=OSError("not found"),
        ):
            version = await get_rt_version(Path("/usr/bin/rawtherapee-cli"))
            assert version is None


class TestRunRtCli:
    """Tests for RT CLI execution."""

    async def test_successful_jpeg_processing(self, tmp_path):
        output_file = tmp_path / "output.jpg"
        output_file.write_bytes(b"fake jpeg data")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("rawtherapee_mcp.rt_cli.asyncio.to_thread", return_value=mock_result):
            result = await run_rt_cli(
                rt_path=Path("/usr/bin/rawtherapee-cli"),
                input_path=tmp_path / "input.cr2",
                output_path=output_file,
                profiles=[tmp_path / "profile.pp3"],
                output_format="jpeg",
                jpeg_quality=95,
            )

            assert result["success"] is True
            assert "processing_time" in result

    async def test_cli_failure(self, tmp_path):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Error: file not found"

        with patch("rawtherapee_mcp.rt_cli.asyncio.to_thread", return_value=mock_result):
            result = await run_rt_cli(
                rt_path=Path("/usr/bin/rawtherapee-cli"),
                input_path=tmp_path / "input.cr2",
                output_path=tmp_path / "output.jpg",
                profiles=[],
            )

            assert "error" in result
            assert "exit code 1" in result["error"]
            assert result["stderr"] == "Error: file not found"
            assert "command" in result

    async def test_timeout(self, tmp_path):
        import subprocess

        with patch(
            "rawtherapee_mcp.rt_cli.asyncio.to_thread",
            side_effect=subprocess.TimeoutExpired("cmd", 300),
        ):
            result = await run_rt_cli(
                rt_path=Path("/usr/bin/rawtherapee-cli"),
                input_path=tmp_path / "input.cr2",
                output_path=tmp_path / "output.jpg",
                profiles=[],
            )

            assert "error" in result
            assert "timed out" in result["error"]
            assert "command" in result

    async def test_unsupported_format(self, tmp_path):
        result = await run_rt_cli(
            rt_path=Path("/usr/bin/rawtherapee-cli"),
            input_path=tmp_path / "input.cr2",
            output_path=tmp_path / "output.bmp",
            profiles=[],
            output_format="bmp",
        )

        assert "error" in result
        assert "Unsupported" in result["error"]

    async def test_command_construction_jpeg(self, tmp_path):
        """Verify the correct CLI flags are constructed for JPEG output."""
        captured_cmd: list[str] | None = None
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        output_file = tmp_path / "output.jpg"
        output_file.write_bytes(b"data")

        def capture_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            return mock_result

        with patch("rawtherapee_mcp.rt_cli._run_subprocess", side_effect=capture_run):
            await run_rt_cli(
                rt_path=Path("/usr/bin/rawtherapee-cli"),
                input_path=tmp_path / "input.cr2",
                output_path=output_file,
                profiles=[tmp_path / "profile.pp3"],
                output_format="jpeg",
                jpeg_quality=92,
            )

        assert captured_cmd is not None
        assert "-j92" in captured_cmd
        assert "-js3" in captured_cmd
        assert "-Y" in captured_cmd
        assert "-q" in captured_cmd
        assert captured_cmd[-2] == "-c"
        # Verify no -w flag (was removed — rawtherapee-cli doesn't support it)
        assert "-w" not in captured_cmd

    async def test_command_construction_tiff(self, tmp_path):
        """Verify the correct CLI flags are constructed for TIFF output."""
        captured_cmd: list[str] | None = None
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        output_file = tmp_path / "output.tif"
        output_file.write_bytes(b"data")

        def capture_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            return mock_result

        with patch("rawtherapee_mcp.rt_cli._run_subprocess", side_effect=capture_run):
            await run_rt_cli(
                rt_path=Path("/usr/bin/rawtherapee-cli"),
                input_path=tmp_path / "input.cr2",
                output_path=output_file,
                profiles=[],
                output_format="tiff",
                bit_depth=16,
            )

        assert captured_cmd is not None
        assert "-tz" in captured_cmd
        assert "-b16" in captured_cmd

    async def test_command_has_no_w_flag(self, tmp_path):
        """Verify -w flag is never added (rawtherapee-cli doesn't support it)."""
        captured_cmd: list[str] | None = None
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        output_file = tmp_path / "output.jpg"
        output_file.write_bytes(b"data")

        def capture_run(cmd, **kwargs):
            nonlocal captured_cmd
            captured_cmd = cmd
            return mock_result

        with patch("rawtherapee_mcp.rt_cli._run_subprocess", side_effect=capture_run):
            await run_rt_cli(
                rt_path=Path("/usr/bin/rawtherapee-cli"),
                input_path=tmp_path / "input.cr2",
                output_path=output_file,
                profiles=[],
            )

        assert captured_cmd is not None
        assert "-w" not in captured_cmd
