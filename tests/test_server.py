"""Tests for MCP server tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastmcp.tools import ToolResult
from PIL import Image as PILImage

from rawtherapee_mcp.server import (
    add_luminance_adjustment,
    adjust_crop_position,
    adjust_local_spot,
    adjust_profile,
    analyze_image,
    apply_local_preset,
    batch_analyze,
    batch_preview,
    check_rt_status,
    compare_profiles,
    export_multi_device,
    get_config,
    get_histogram,
    interpolate_profiles,
    list_local_adjustments,
    list_raw_files,
    preview_before_after,
    preview_exposure_bracket,
    preview_raw,
    preview_white_balance,
    process_raw,
    read_exif,
    remove_local_adjustment,
)


class TestGetConfig:
    """Tests for context config extraction."""

    def test_extracts_config(self, mock_ctx, mock_config):
        config = get_config(mock_ctx)
        assert config is mock_config

    def test_raises_on_missing(self):
        ctx = MagicMock()
        ctx.lifespan_context = {}
        with pytest.raises(RuntimeError, match="RTConfig not initialized"):
            get_config(ctx)


class TestCheckRtStatus:
    """Tests for check_rt_status tool."""

    async def test_rt_installed(self, mock_ctx):
        with patch("rawtherapee_mcp.server.get_rt_version", return_value="5.11"):
            result = await check_rt_status(mock_ctx)
            assert result["installed"] is True
            assert result["version"] == "5.11"
            assert result["cli_path"] is not None

    async def test_rt_not_installed(self, mock_ctx_no_rt):
        result = await check_rt_status(mock_ctx_no_rt)
        assert result["installed"] is False
        assert result["cli_path"] is None
        assert result["version"] is None


class TestListRawFiles:
    """Tests for list_raw_files tool."""

    async def test_finds_raw_files(self, mock_ctx, tmp_path):
        # Create some test files
        (tmp_path / "photo1.cr2").write_bytes(b"raw1")
        (tmp_path / "photo2.nef").write_bytes(b"raw2")
        (tmp_path / "readme.txt").write_bytes(b"text")

        result = await list_raw_files(mock_ctx, str(tmp_path))
        assert result["count"] == 2
        extensions = [f["extension"] for f in result["files"]]
        assert ".cr2" in extensions
        assert ".nef" in extensions

    async def test_recursive_scan(self, mock_ctx, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "photo1.arw").write_bytes(b"raw1")
        (subdir / "photo2.dng").write_bytes(b"raw2")

        result = await list_raw_files(mock_ctx, str(tmp_path), recursive=True)
        assert result["count"] == 2

    async def test_non_recursive_skips_subdirs(self, mock_ctx, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "photo1.arw").write_bytes(b"raw1")
        (subdir / "photo2.dng").write_bytes(b"raw2")

        result = await list_raw_files(mock_ctx, str(tmp_path), recursive=False)
        assert result["count"] == 1

    async def test_directory_not_found(self, mock_ctx):
        result = await list_raw_files(mock_ctx, "/nonexistent/path")
        assert "error" in result

    async def test_case_insensitive_extensions(self, mock_ctx, tmp_path):
        (tmp_path / "PHOTO.CR2").write_bytes(b"raw")
        (tmp_path / "photo.Nef").write_bytes(b"raw")

        result = await list_raw_files(mock_ctx, str(tmp_path))
        assert result["count"] == 2


class TestReadExif:
    """Tests for read_exif tool."""

    async def test_returns_exif_data(self, mock_ctx, tmp_path):
        test_file = tmp_path / "photo.cr2"
        test_file.write_bytes(b"fake raw")

        mock_data = {
            "camera_make": "Canon",
            "camera_model": "EOS R5",
            "iso": "400",
            "aperture": "2.8",
            "shutter_speed": "1/250",
            "focal_length": "85",
            "white_balance": "",
            "datetime": "",
            "width": "",
            "height": "",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
            "lens_model": "",
        }

        with patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_data):
            result = await read_exif(mock_ctx, str(test_file))
            assert result["camera_make"] == "Canon"
            assert result["file_path"] == str(test_file)

    async def test_file_not_found(self, mock_ctx):
        result = await read_exif(mock_ctx, "/nonexistent/photo.cr2")
        assert "error" in result


class TestProcessRaw:
    """Tests for process_raw tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        result = await process_raw(mock_ctx_no_rt, str(raw_file), str(pp3_file))
        assert "error" in result
        assert "not found" in result["error"]

    async def test_raw_file_not_found(self, mock_ctx):
        result = await process_raw(mock_ctx, "/nonexistent.cr2", "/some.pp3")
        assert "error" in result

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        result = await process_raw(mock_ctx, str(raw_file), "/nonexistent.pp3")
        assert "error" in result

    async def test_calls_rt_cli(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        mock_result = {"success": True, "output_path": "/output/photo.jpg", "processing_time": 1.5, "file_size": 1000}

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await process_raw(mock_ctx, str(raw_file), str(pp3_file), include_preview=False)
            assert result["success"] is True


class TestPreviewRaw:
    """Tests for preview_raw tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        result = await preview_raw(mock_ctx_no_rt, str(raw_file))
        assert "error" in result

    async def test_raw_file_not_found(self, mock_ctx):
        result = await preview_raw(mock_ctx, "/nonexistent.cr2")
        assert "error" in result

    async def test_generates_preview(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "preview.jpg"),
            "processing_time": 0.5,
            "file_size": 500,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await preview_raw(mock_ctx, str(raw_file), return_image=False)
            assert result["success"] is True
            assert "preview_path" in result
            assert result["max_width"] == 1200

    async def test_preview_with_profile_merges_single_pp3(self, mock_ctx, tmp_path):
        """Preview should merge resize into user's profile (single PP3)."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "warm.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\nVersion=351\n[Exposure]\nCompensation=0.5\n")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "preview.jpg"),
            "processing_time": 0.5,
            "file_size": 500,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result) as mock_cli:
            result = await preview_raw(mock_ctx, str(raw_file), profile_path=str(pp3_file), return_image=False)
            assert result["success"] is True
            # Should pass exactly ONE profile (combined) to avoid multi-PP3 merge crashes
            call_args = mock_cli.call_args
            profiles = call_args.kwargs.get("profiles", call_args[1].get("profiles", []))
            assert len(profiles) == 1

    async def test_preview_error_includes_pp3_content(self, mock_ctx, tmp_path):
        """Failed preview should include PP3 content for debugging."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        mock_result = {
            "error": "rawtherapee-cli failed (exit code -1)",
            "stdout": "",
            "stderr": "",
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await preview_raw(mock_ctx, str(raw_file))
            assert "error" in result
            assert "preview_pp3_content" in result

    async def test_preview_skips_resize_when_crop_enabled(self, mock_ctx, tmp_path):
        """Preview should not add Resize when profile has Crop (RT 5.12 bug)."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "cropped.pp3"
        pp3_file.write_text(
            "[Version]\nAppVersion=5.11\nVersion=351\n[Crop]\nEnabled=true\nX=100\nY=0\nW=3000\nH=4000\n"
        )

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "preview.jpg"),
            "processing_time": 0.5,
            "file_size": 500,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result) as mock_cli:
            result = await preview_raw(mock_ctx, str(raw_file), profile_path=str(pp3_file), return_image=False)
            assert result["success"] is True
            # Verify the combined PP3 was saved — read it to check Resize is disabled
            call_args = mock_cli.call_args
            profiles = call_args.kwargs.get("profiles", call_args[1].get("profiles", []))
            assert len(profiles) == 1
            # The temp PP3 was cleaned up, but we can verify from the call that
            # exactly one profile was passed (combined with Crop but no Resize)

    async def test_preview_adds_resize_when_no_crop(self, mock_ctx, tmp_path):
        """Preview should add Resize when profile has no Crop."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "nocrop.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\nVersion=351\n[Exposure]\nCompensation=0.5\n")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "preview.jpg"),
            "processing_time": 0.5,
            "file_size": 500,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await preview_raw(mock_ctx, str(raw_file), profile_path=str(pp3_file), return_image=False)
            assert result["success"] is True
            assert result["max_width"] == 1200


class TestAdjustProfile:
    """Tests for adjust_profile tool."""

    async def test_adjust_with_friendly_names(self, mock_ctx, tmp_path):
        """Test adjust_profile with friendly parameter names."""
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\nVersion=351\n[Exposure]\nCompensation=0\n")

        result = await adjust_profile(
            mock_ctx,
            str(pp3_file),
            {"exposure": {"compensation": 1.5}},
        )
        assert "error" not in result
        assert result["adjustments_applied"]["exposure"]["compensation"] == 1.5

        # Verify the file was actually written
        from rawtherapee_mcp.pp3_parser import PP3Profile

        profile = PP3Profile()
        profile.load(pp3_file)
        assert profile.get("Exposure", "Compensation") == "1.5"

    async def test_adjust_with_raw_pp3_keys(self, mock_ctx, tmp_path):
        """Test adjust_profile with raw PP3 section/key pairs."""
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\nVersion=351\n[Crop]\nEnabled=true\nX=0\nY=0\n")

        result = await adjust_profile(
            mock_ctx,
            str(pp3_file),
            {"Crop": {"W": "3108", "H": "6732", "FixedRatio": "true", "Guide": "Frame"}},
        )
        assert "error" not in result

        # Verify the raw values were written
        from rawtherapee_mcp.pp3_parser import PP3Profile

        profile = PP3Profile()
        profile.load(pp3_file)
        assert profile.get("Crop", "W") == "3108"
        assert profile.get("Crop", "H") == "6732"
        assert profile.get("Crop", "FixedRatio") == "true"
        assert profile.get("Crop", "Guide") == "Frame"

    async def test_adjust_profile_not_found(self, mock_ctx):
        result = await adjust_profile(
            mock_ctx,
            "/nonexistent.pp3",
            {"exposure": {"compensation": 1.0}},
        )
        assert "error" in result


class TestReadExifRecommendations:
    """Tests for EXIF recommendations in read_exif."""

    async def test_includes_recommendations(self, mock_ctx, tmp_path):
        """read_exif should include processing recommendations."""
        test_file = tmp_path / "photo.cr2"
        test_file.write_bytes(b"fake raw")

        mock_data = {
            "camera_make": "Canon",
            "camera_model": "EOS R5",
            "iso": "6400",
            "aperture": "14/10",
            "shutter_speed": "1/250",
            "focal_length": "85",
            "white_balance": "0",
            "datetime": "",
            "width": "",
            "height": "",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
            "lens_model": "RF 85mm F1.2L USM",
        }

        with patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_data):
            result = await read_exif(mock_ctx, str(test_file))
            assert "recommendations" in result
            recs = result["recommendations"]
            assert isinstance(recs, dict)
            assert "text" in recs
            assert "suggested_parameters" in recs
            assert "warnings" in recs
            assert len(recs["text"]) >= 3


class TestPreviewRawToolResult:
    """Tests for preview_raw ToolResult image return."""

    async def test_returns_tool_result_with_image(self, mock_ctx, tmp_path):
        """Successful preview with return_image=True returns ToolResult."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "blue").save(str(out), "JPEG")
            return {
                "success": True,
                "output_path": str(out),
                "processing_time": 0.5,
                "file_size": 500,
            }

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_raw(mock_ctx, str(raw_file), return_image=True)
            assert isinstance(result, ToolResult)
            assert result.content is not None
            assert len(result.content) == 2
            assert result.content[0].type == "text"
            assert result.content[1].type == "image"
            assert result.structured_content is not None
            assert result.structured_content["success"] is True

    async def test_returns_dict_when_return_image_false(self, mock_ctx, tmp_path):
        """return_image=False returns plain dict even on success."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "preview.jpg"),
            "processing_time": 0.5,
            "file_size": 500,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await preview_raw(mock_ctx, str(raw_file), return_image=False)
            assert isinstance(result, dict)
            assert result["success"] is True

    async def test_returns_dict_on_error(self, mock_ctx, tmp_path):
        """Errors always return dict regardless of return_image."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        mock_result = {"error": "RT failed", "stdout": "", "stderr": ""}

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await preview_raw(mock_ctx, str(raw_file), return_image=True)
            assert isinstance(result, dict)
            assert "error" in result


class TestProcessRawToolResult:
    """Tests for process_raw ToolResult thumbnail return."""

    async def test_returns_tool_result_with_preview(self, mock_ctx, tmp_path):
        """Successful processing with include_preview=True returns ToolResult."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        output_file = tmp_path / "output" / "photo.jpg"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        PILImage.new("RGB", (3000, 2000), "green").save(str(output_file), "JPEG")

        mock_result = {
            "success": True,
            "output_path": str(output_file),
            "processing_time": 1.5,
            "file_size": 1000,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await process_raw(mock_ctx, str(raw_file), str(pp3_file), include_preview=True)
            assert isinstance(result, ToolResult)
            assert result.content is not None
            assert len(result.content) == 2
            assert result.content[1].type == "image"

    async def test_returns_dict_when_preview_disabled(self, mock_ctx, tmp_path):
        """include_preview=False returns plain dict."""
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "photo.jpg"),
            "processing_time": 1.5,
            "file_size": 1000,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await process_raw(mock_ctx, str(raw_file), str(pp3_file), include_preview=False)
            assert isinstance(result, dict)
            assert result["success"] is True


# ---------------------------------------------------------------------------
# Feature Request v2 Tests
# ---------------------------------------------------------------------------


class TestGetHistogram:
    """Tests for get_histogram tool."""

    async def test_file_not_found(self, mock_ctx):
        result = await get_histogram(mock_ctx, "/nonexistent/image.jpg")
        assert "error" in result

    async def test_returns_statistics(self, mock_ctx, tmp_path):
        img_path = tmp_path / "test.jpg"
        PILImage.new("RGB", (100, 100), "red").save(str(img_path), "JPEG")

        result = await get_histogram(mock_ctx, str(img_path))
        assert "statistics" in result
        assert "clipping" in result
        assert "total_pixels" in result
        assert result["total_pixels"] == 10000

    async def test_includes_svg(self, mock_ctx, tmp_path):
        img_path = tmp_path / "test.jpg"
        PILImage.new("RGB", (100, 100), "blue").save(str(img_path), "JPEG")

        result = await get_histogram(mock_ctx, str(img_path), include_svg=True)
        assert "svg" in result
        assert result["svg"].startswith("<svg")

    async def test_excludes_svg(self, mock_ctx, tmp_path):
        img_path = tmp_path / "test.jpg"
        PILImage.new("RGB", (100, 100), "blue").save(str(img_path), "JPEG")

        result = await get_histogram(mock_ctx, str(img_path), include_svg=False)
        assert "svg" not in result


class TestPreviewBeforeAfter:
    """Tests for preview_before_after tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        result = await preview_before_after(mock_ctx_no_rt, str(raw_file), str(pp3_file))
        assert "error" in result

    async def test_raw_not_found(self, mock_ctx, tmp_path):
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        result = await preview_before_after(mock_ctx, "/nonexistent.cr2", str(pp3_file))
        assert "error" in result

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        result = await preview_before_after(mock_ctx, str(raw_file), "/nonexistent.pp3")
        assert "error" in result

    async def test_returns_both_previews(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n[Exposure]\nCompensation=1.0\n")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "blue").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_before_after(mock_ctx, str(raw_file), str(pp3_file))
            assert isinstance(result, ToolResult)
            assert result.content is not None
            # TextContent + 2 ImageContent (before + after)
            assert len(result.content) == 3
            assert result.content[0].type == "text"
            assert result.content[1].type == "image"
            assert result.content[2].type == "image"


class TestAdjustCropPosition:
    """Tests for adjust_crop_position tool."""

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        result = await adjust_crop_position(mock_ctx, "/nonexistent.pp3", str(raw_file), include_preview=False)
        assert "error" in result

    async def test_no_crop_enabled(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "nocrop.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n[Exposure]\nCompensation=0\n")

        result = await adjust_crop_position(mock_ctx, str(pp3_file), str(raw_file), include_preview=False)
        assert "error" in result
        assert "crop" in result["error"].lower()

    async def test_moves_crop_center(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "cropped.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n[Crop]\nEnabled=true\nX=0\nY=0\nW=1000\nH=500\n")

        with patch("rawtherapee_mcp.server.get_effective_dimensions", return_value=(4000, 3000)):
            result = await adjust_crop_position(
                mock_ctx,
                str(pp3_file),
                str(raw_file),
                horizontal="center",
                vertical="center",
                include_preview=False,
            )
            assert "error" not in result
            assert result["crop_x"] == 1500  # (4000 - 1000) // 2
            assert result["crop_y"] == 1250  # (3000 - 500) // 2

    async def test_moves_crop_bottom_right(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "cropped.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n[Crop]\nEnabled=true\nX=0\nY=0\nW=1000\nH=500\n")

        with patch("rawtherapee_mcp.server.get_effective_dimensions", return_value=(4000, 3000)):
            result = await adjust_crop_position(
                mock_ctx,
                str(pp3_file),
                str(raw_file),
                horizontal="right",
                vertical="bottom",
                include_preview=False,
            )
            assert result["crop_x"] == 3000  # 4000 - 1000
            assert result["crop_y"] == 2500  # 3000 - 500

    async def test_pixel_offset(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "cropped.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n[Crop]\nEnabled=true\nX=0\nY=0\nW=1000\nH=500\n")

        with patch("rawtherapee_mcp.server.get_effective_dimensions", return_value=(4000, 3000)):
            result = await adjust_crop_position(
                mock_ctx,
                str(pp3_file),
                str(raw_file),
                horizontal="500",
                vertical="200",
                include_preview=False,
            )
            assert result["crop_x"] == 500
            assert result["crop_y"] == 200


class TestPreviewExposureBracket:
    """Tests for preview_exposure_bracket tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        result = await preview_exposure_bracket(mock_ctx_no_rt, str(raw_file))
        assert "error" in result

    async def test_raw_not_found(self, mock_ctx):
        result = await preview_exposure_bracket(mock_ctx, "/nonexistent.cr2")
        assert "error" in result

    async def test_default_stops(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_exposure_bracket(mock_ctx, str(raw_file))
            assert isinstance(result, ToolResult)
            assert result.content is not None
            # TextContent + 3 ImageContent (default: -1, 0, +1)
            assert len(result.content) == 4

    async def test_custom_stops(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_exposure_bracket(mock_ctx, str(raw_file), stops=[-2.0, 0.0, 2.0])
            assert isinstance(result, ToolResult)
            assert result.structured_content is not None
            assert result.structured_content["stops"] == [-2.0, 0.0, 2.0]


class TestPreviewWhiteBalance:
    """Tests for preview_white_balance tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        result = await preview_white_balance(mock_ctx_no_rt, str(raw_file))
        assert "error" in result

    async def test_raw_not_found(self, mock_ctx):
        result = await preview_white_balance(mock_ctx, "/nonexistent.cr2")
        assert "error" in result

    async def test_default_presets(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_white_balance(mock_ctx, str(raw_file))
            assert isinstance(result, ToolResult)
            assert result.content is not None
            # TextContent + 5 ImageContent (default: 5 presets)
            assert len(result.content) == 6
            assert result.structured_content is not None
            assert len(result.structured_content["presets"]) == 5

    async def test_custom_presets(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_white_balance(mock_ctx, str(raw_file), presets=["Daylight", "Tungsten"])
            assert isinstance(result, ToolResult)
            assert result.content is not None
            # TextContent + 2 ImageContent
            assert len(result.content) == 3


class TestCompareProfilesVisual:
    """Tests for compare_profiles with visual preview."""

    async def test_diff_only(self, mock_ctx, tmp_path):
        """Default behavior: diff only, no preview."""
        pp3_a = tmp_path / "a.pp3"
        pp3_a.write_text("[Version]\nAppVersion=5.11\n[Exposure]\nCompensation=0\n")
        pp3_b = tmp_path / "b.pp3"
        pp3_b.write_text("[Version]\nAppVersion=5.11\n[Exposure]\nCompensation=1.5\n")

        result = await compare_profiles(mock_ctx, str(pp3_a), str(pp3_b))
        assert isinstance(result, dict)
        assert "profile_a" in result

    async def test_visual_preview(self, mock_ctx, tmp_path):
        """With file_path + include_preview, returns ToolResult with images."""
        pp3_a = tmp_path / "a.pp3"
        pp3_a.write_text("[Version]\nAppVersion=5.11\n[Exposure]\nCompensation=0\n")
        pp3_b = tmp_path / "b.pp3"
        pp3_b.write_text("[Version]\nAppVersion=5.11\n[Exposure]\nCompensation=1.5\n")
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await compare_profiles(
                mock_ctx,
                str(pp3_a),
                str(pp3_b),
                file_path=str(raw_file),
                include_preview=True,
            )
            assert isinstance(result, ToolResult)
            assert result.content is not None
            # TextContent + 2 ImageContent
            assert len(result.content) == 3


class TestExportMultiDevice:
    """Tests for export_multi_device tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        result = await export_multi_device(mock_ctx_no_rt, str(raw_file), str(pp3_file), ["iphone_15_pro"])
        assert "error" in result

    async def test_raw_not_found(self, mock_ctx):
        result = await export_multi_device(mock_ctx, "/nonexistent.cr2", "/some.pp3", ["iphone_15_pro"])
        assert "error" in result

    async def test_unknown_preset(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        with patch("rawtherapee_mcp.server.get_effective_dimensions", return_value=(4000, 3000)):
            result = await export_multi_device(mock_ctx, str(raw_file), str(pp3_file), ["nonexistent_device"])
            assert result["failed"] == 1
            assert "not found" in result["results"][0]["error"]

    async def test_processes_multiple_presets(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "profile.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "output.jpg"),
            "processing_time": 1.0,
            "file_size": 1000,
        }

        preset_a = {"name": "Device A", "width": 1170, "height": 2532}
        preset_b = {"name": "Device B", "width": 1440, "height": 3200}

        def mock_get_preset(name, _dir):
            return {"device_a": preset_a, "device_b": preset_b}.get(name)

        with (
            patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result),
            patch("rawtherapee_mcp.server.get_effective_dimensions", return_value=(6000, 4000)),
            patch("rawtherapee_mcp.server.get_preset", side_effect=mock_get_preset),
        ):
            result = await export_multi_device(mock_ctx, str(raw_file), str(pp3_file), ["device_a", "device_b"])
            assert result["total"] == 2
            assert result["succeeded"] == 2


class TestBatchPreview:
    """Tests for batch_preview tool."""

    async def test_no_rt_returns_error(self, mock_ctx_no_rt, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        result = await batch_preview(mock_ctx_no_rt, [str(raw_file)])
        assert "error" in result

    async def test_previews_multiple_files(self, mock_ctx, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"photo{i}.cr2"
            f.write_bytes(b"raw")
            files.append(str(f))

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (300, 200), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.3, "file_size": 200}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await batch_preview(mock_ctx, files)
            assert isinstance(result, ToolResult)
            assert result.content is not None
            # TextContent + 3 ImageContent
            assert len(result.content) == 4

    async def test_caps_at_max_images(self, mock_ctx, tmp_path):
        files = []
        for i in range(20):
            f = tmp_path / f"photo{i}.cr2"
            f.write_bytes(b"raw")
            files.append(str(f))

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (300, 200), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.3, "file_size": 200}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await batch_preview(mock_ctx, files, max_images=5)
            assert isinstance(result, ToolResult)
            assert result.structured_content is not None
            assert result.structured_content["total"] == 5
            assert result.structured_content["capped"] is True

    async def test_missing_file_in_batch(self, mock_ctx, tmp_path):
        real_file = tmp_path / "photo.cr2"
        real_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (300, 200), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.3, "file_size": 200}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await batch_preview(mock_ctx, [str(real_file), "/nonexistent.cr2"])
            # Should still return something — one success, one error
            if isinstance(result, ToolResult):
                assert result.structured_content is not None
                previews = result.structured_content["previews"]
            else:
                previews = result["previews"]
            assert len(previews) == 2
            assert any("error" in p for p in previews)


class TestAnalyzeImage:
    """Tests for analyze_image tool."""

    async def test_file_not_found(self, mock_ctx):
        result = await analyze_image(mock_ctx, "/nonexistent/image.jpg")
        assert "error" in result

    async def test_returns_exif_and_histogram(self, mock_ctx, tmp_path):
        img_path = tmp_path / "photo.jpg"
        PILImage.new("RGB", (1000, 800), "green").save(str(img_path), "JPEG")

        mock_exif = {
            "camera_make": "Canon",
            "camera_model": "EOS R5",
            "iso": "400",
            "aperture": "5.6",
            "shutter_speed": "1/250",
            "focal_length": "85",
            "white_balance": "",
            "datetime": "",
            "width": "1000",
            "height": "800",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
            "lens_model": "",
        }

        with patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_exif):
            result = await analyze_image(mock_ctx, str(img_path))
            assert isinstance(result, ToolResult)
            assert result.structured_content is not None
            assert "exif" in result.structured_content
            assert "recommendations" in result.structured_content
            assert "histogram" in result.structured_content

    async def test_no_thumbnail(self, mock_ctx, tmp_path):
        img_path = tmp_path / "photo.jpg"
        PILImage.new("RGB", (100, 100), "red").save(str(img_path), "JPEG")

        mock_exif = {
            "camera_make": "",
            "camera_model": "",
            "iso": "",
            "aperture": "",
            "shutter_speed": "",
            "focal_length": "",
            "white_balance": "",
            "datetime": "",
            "width": "",
            "height": "",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
            "lens_model": "",
        }

        with patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_exif):
            result = await analyze_image(mock_ctx, str(img_path), include_thumbnail=False)
            assert isinstance(result, dict)
            assert "exif" in result


# ---------------------------------------------------------------------------
# Bug 3 — Crop+Resize conflict warning
# ---------------------------------------------------------------------------


class TestCropResizeWarning:
    """Tests for Crop+Resize conflict detection."""

    async def test_process_raw_warns_on_conflict(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "conflict.pp3"
        pp3_file.write_text(
            "[Version]\nAppVersion=5.11\n"
            "[Crop]\nEnabled=true\nX=0\nY=0\nW=1000\nH=500\n"
            "[Resize]\nEnabled=true\nWidth=800\nHeight=600\n"
        )

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "output.jpg"),
            "processing_time": 1.0,
            "file_size": 1000,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await process_raw(mock_ctx, str(raw_file), str(pp3_file), include_preview=False)
            assert "warning" in result
            assert "crop" in result["warning"].lower()

    async def test_process_raw_no_warning_without_conflict(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")
        pp3_file = tmp_path / "ok.pp3"
        pp3_file.write_text("[Version]\nAppVersion=5.11\n[Crop]\nEnabled=true\nX=0\nY=0\nW=1000\nH=500\n")

        mock_result = {
            "success": True,
            "output_path": str(tmp_path / "output.jpg"),
            "processing_time": 1.0,
            "file_size": 1000,
        }

        with patch("rawtherapee_mcp.server.run_rt_cli", return_value=mock_result):
            result = await process_raw(mock_ctx, str(raw_file), str(pp3_file), include_preview=False)
            assert "warning" not in result


# ---------------------------------------------------------------------------
# V2 — batch_preview EXIF summary
# ---------------------------------------------------------------------------


class TestBatchPreviewExif:
    """Tests for batch_preview include_exif parameter."""

    async def test_include_exif(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        mock_exif = {
            "iso": "400",
            "aperture": "2.8",
            "shutter_speed": "1/250",
            "focal_length": "85",
            "camera_make": "Canon",
            "camera_model": "EOS R5",
            "lens_model": "",
            "white_balance": "",
            "datetime": "",
            "width": "",
            "height": "",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
        }

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (300, 200), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.3, "file_size": 200}

        with (
            patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview),
            patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_exif),
        ):
            result = await batch_preview(mock_ctx, [str(raw_file)], include_exif=True)
            if isinstance(result, ToolResult):
                previews = result.structured_content["previews"]
            else:
                previews = result["previews"]
            assert "exif_summary" in previews[0]
            assert previews[0]["exif_summary"]["iso"] == "400"


# ---------------------------------------------------------------------------
# V4 — White balance Kelvin temperatures
# ---------------------------------------------------------------------------


class TestWhiteBalanceTemperature:
    """Tests for WB Kelvin temperature annotations."""

    async def test_temperature_included(self, mock_ctx, tmp_path):
        raw_file = tmp_path / "photo.cr2"
        raw_file.write_bytes(b"raw")

        async def create_preview(**kwargs):
            out = kwargs["output_path"]
            PILImage.new("RGB", (600, 400), "gray").save(str(out), "JPEG")
            return {"success": True, "output_path": str(out), "processing_time": 0.5, "file_size": 500}

        with patch("rawtherapee_mcp.server.run_rt_cli", side_effect=create_preview):
            result = await preview_white_balance(mock_ctx, str(raw_file), presets=["Daylight", "Tungsten"])
            assert isinstance(result, ToolResult)
            previews = result.structured_content["previews"]
            assert previews[0]["temperature_k"] == 5500
            assert previews[1]["temperature_k"] == 3200


# ---------------------------------------------------------------------------
# F2 — batch_analyze
# ---------------------------------------------------------------------------


class TestBatchAnalyze:
    """Tests for batch_analyze tool."""

    async def test_file_not_found(self, mock_ctx):
        result = await batch_analyze(mock_ctx, ["/nonexistent/image.jpg"], include_thumbnails=False)
        if isinstance(result, dict):
            analyses = result["analyses"]
        else:
            analyses = result.structured_content["analyses"]
        assert "error" in analyses[0]

    async def test_returns_exif_and_histogram(self, mock_ctx, tmp_path):
        img_path = tmp_path / "photo.jpg"
        PILImage.new("RGB", (100, 100), "green").save(str(img_path), "JPEG")

        mock_exif = {
            "camera_make": "Canon",
            "camera_model": "EOS R5",
            "iso": "400",
            "aperture": "5.6",
            "shutter_speed": "1/250",
            "focal_length": "85",
            "white_balance": "",
            "datetime": "",
            "width": "100",
            "height": "100",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
            "lens_model": "",
        }

        with patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_exif):
            result = await batch_analyze(mock_ctx, [str(img_path)], include_thumbnails=False)
            if isinstance(result, dict):
                analyses = result["analyses"]
            else:
                analyses = result.structured_content["analyses"]
            assert "exif" in analyses[0]
            assert "recommendations" in analyses[0]
            assert "histogram_summary" in analyses[0]
            # Should NOT have full channel data or SVG
            assert "svg" not in analyses[0].get("histogram_summary", {})

    async def test_caps_at_max(self, mock_ctx, tmp_path):
        files = []
        for i in range(10):
            p = tmp_path / f"photo{i}.jpg"
            PILImage.new("RGB", (50, 50), "blue").save(str(p), "JPEG")
            files.append(str(p))

        mock_exif = {
            "camera_make": "",
            "camera_model": "",
            "iso": "",
            "aperture": "",
            "shutter_speed": "",
            "focal_length": "",
            "white_balance": "",
            "datetime": "",
            "width": "",
            "height": "",
            "gps_latitude": "",
            "gps_longitude": "",
            "orientation": "",
            "lens_model": "",
        }

        with patch("rawtherapee_mcp.server.read_exif_data", return_value=mock_exif):
            result = await batch_analyze(mock_ctx, files, max_images=3, include_thumbnails=False)
            if isinstance(result, dict):
                assert result["total"] == 3
                assert result["capped"] is True
            else:
                assert result.structured_content["total"] == 3
                assert result.structured_content["capped"] is True


# ---------------------------------------------------------------------------
# F3 — interpolate_profiles
# ---------------------------------------------------------------------------


class TestInterpolateProfiles:
    """Tests for interpolate_profiles tool."""

    async def test_profile_not_found(self, mock_ctx):
        result = await interpolate_profiles(mock_ctx, "/nonexistent_a.pp3", "/nonexistent_b.pp3")
        assert "error" in result

    async def test_basic_interpolation(self, mock_ctx, tmp_path):
        pp3_a = tmp_path / "a.pp3"
        pp3_a.write_text("[Exposure]\nCompensation=0\n")
        pp3_b = tmp_path / "b.pp3"
        pp3_b.write_text("[Exposure]\nCompensation=2\n")

        result = await interpolate_profiles(mock_ctx, str(pp3_a), str(pp3_b), factor=0.5, output_name="blend")
        assert "error" not in result
        assert result["factor"] == 0.5
        assert "output_path" in result
        assert result["summary"]["Exposure"]["Compensation"] == "1"

    async def test_factor_zero(self, mock_ctx, tmp_path):
        pp3_a = tmp_path / "a.pp3"
        pp3_a.write_text("[Exposure]\nCompensation=1.5\n")
        pp3_b = tmp_path / "b.pp3"
        pp3_b.write_text("[Exposure]\nCompensation=3.0\n")

        result = await interpolate_profiles(mock_ctx, str(pp3_a), str(pp3_b), factor=0.0)
        assert result["summary"]["Exposure"]["Compensation"] == "1.5"

    async def test_factor_one(self, mock_ctx, tmp_path):
        pp3_a = tmp_path / "a.pp3"
        pp3_a.write_text("[Exposure]\nCompensation=1.5\n")
        pp3_b = tmp_path / "b.pp3"
        pp3_b.write_text("[Exposure]\nCompensation=3.0\n")

        result = await interpolate_profiles(mock_ctx, str(pp3_a), str(pp3_b), factor=1.0)
        assert result["summary"]["Exposure"]["Compensation"] == "3"


# ---------------------------------------------------------------------------
# Locallab tools
# ---------------------------------------------------------------------------


class TestAddLuminanceAdjustment:
    """Tests for add_luminance_adjustment tool."""

    async def test_add_shadow_adjustment(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5})
        assert "error" not in result
        assert result["spot_index"] == 0
        assert result["adjustment_type"] == "shadows"
        assert result["total_spots"] == 1

    async def test_add_highlight_adjustment(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await add_luminance_adjustment(mock_ctx, str(pp3), "highlights", {"exposure": -0.3, "saturation": -10})
        assert "error" not in result
        assert result["parameters_applied"]["exposure"] == -0.3

    async def test_add_custom_range(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await add_luminance_adjustment(
            mock_ctx,
            str(pp3),
            "custom",
            {"contrast": 20},
            luminance_range={"lower": 40, "upper": 80},
        )
        assert "error" not in result
        assert result["adjustment_type"] == "custom"

    async def test_add_multiple(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5})
        result = await add_luminance_adjustment(mock_ctx, str(pp3), "highlights", {"exposure": -0.3})
        assert result["spot_index"] == 1
        assert result["total_spots"] == 2

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        result = await add_luminance_adjustment(mock_ctx, str(tmp_path / "nope.pp3"), "shadows", {"exposure": 0.5})
        assert "error" in result

    async def test_invalid_type(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await add_luminance_adjustment(mock_ctx, str(pp3), "invalid", {"exposure": 0.5})
        assert "error" in result

    async def test_save_as(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")
        out = tmp_path / "out.pp3"

        result = await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5}, save_as=str(out))
        assert result["profile_path"] == str(out)
        assert out.is_file()


class TestListLocalAdjustments:
    """Tests for list_local_adjustments tool."""

    async def test_empty_profile(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await list_local_adjustments(mock_ctx, str(pp3))
        assert result["total_spots"] == 0
        assert result["spots"] == []

    async def test_with_spots(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5})
        await add_luminance_adjustment(mock_ctx, str(pp3), "highlights", {"exposure": -0.3})

        result = await list_local_adjustments(mock_ctx, str(pp3))
        assert result["total_spots"] == 2
        assert len(result["spots"]) == 2
        assert result["spots"][0]["type"] == "shadows"
        assert result["spots"][1]["type"] == "highlights"

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        result = await list_local_adjustments(mock_ctx, str(tmp_path / "nope.pp3"))
        assert "error" in result


class TestAdjustLocalSpot:
    """Tests for adjust_local_spot tool."""

    async def test_update_parameters(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5})

        result = await adjust_local_spot(mock_ctx, str(pp3), 0, parameters={"exposure": 0.25})
        assert "error" not in result
        assert result["spot_index"] == 0

    async def test_disable_spot(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5})

        result = await adjust_local_spot(mock_ctx, str(pp3), 0, enabled=False)
        assert "error" not in result
        assert result["updated"]["enabled"] is False

    async def test_invalid_index(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await adjust_local_spot(mock_ctx, str(pp3), 0, parameters={"exposure": 0.5})
        assert "error" in result

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        result = await adjust_local_spot(mock_ctx, str(tmp_path / "nope.pp3"), 0, parameters={"exposure": 0.5})
        assert "error" in result


class TestRemoveLocalAdjustment:
    """Tests for remove_local_adjustment tool."""

    async def test_remove_spot(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5})

        result = await remove_local_adjustment(mock_ctx, str(pp3), 0)
        assert "error" not in result
        assert result["removed_index"] == 0
        assert result["total_spots"] == 0

    async def test_remove_invalid_index(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await remove_local_adjustment(mock_ctx, str(pp3), 0)
        assert "error" in result

    async def test_remove_preserves_others(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        await add_luminance_adjustment(mock_ctx, str(pp3), "shadows", {"exposure": 0.5}, spot_name="Shadow")
        await add_luminance_adjustment(mock_ctx, str(pp3), "highlights", {"exposure": -0.3}, spot_name="Highlight")

        result = await remove_local_adjustment(mock_ctx, str(pp3), 0)
        assert result["total_spots"] == 1

        # The highlight spot should now be at index 0
        listing = await list_local_adjustments(mock_ctx, str(pp3))
        assert listing["spots"][0]["name"] == "Highlight"

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        result = await remove_local_adjustment(mock_ctx, str(tmp_path / "nope.pp3"), 0)
        assert "error" in result


class TestApplyLocalPreset:
    """Tests for apply_local_preset tool."""

    async def test_apply_shadow_recovery(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await apply_local_preset(mock_ctx, str(pp3), "shadow_recovery")
        assert "error" not in result
        assert result["preset"] == "shadow_recovery"
        assert len(result["spots_added"]) == 1
        assert result["total_spots"] == 1

    async def test_apply_hdr_natural(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await apply_local_preset(mock_ctx, str(pp3), "hdr_natural")
        assert "error" not in result
        assert len(result["spots_added"]) == 3
        assert result["total_spots"] == 3

    async def test_apply_split_tone(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await apply_local_preset(mock_ctx, str(pp3), "split_tone_warm_cool")
        assert "error" not in result
        assert len(result["spots_added"]) == 2

    async def test_unknown_preset(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await apply_local_preset(mock_ctx, str(pp3), "nonexistent")
        assert "error" in result
        assert "available_presets" in result

    async def test_intensity_parameter(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")

        result = await apply_local_preset(mock_ctx, str(pp3), "shadow_recovery", intensity=100)
        assert "error" not in result
        assert result["intensity"] == 100

    async def test_save_as(self, mock_ctx, tmp_path):
        pp3 = tmp_path / "test.pp3"
        pp3.write_text("[Version]\nAppVersion=5.11\n")
        out = tmp_path / "preset_out.pp3"

        result = await apply_local_preset(mock_ctx, str(pp3), "shadow_recovery", save_as=str(out))
        assert result["profile_path"] == str(out)
        assert out.is_file()

    async def test_profile_not_found(self, mock_ctx, tmp_path):
        result = await apply_local_preset(mock_ctx, str(tmp_path / "nope.pp3"), "shadow_recovery")
        assert "error" in result
