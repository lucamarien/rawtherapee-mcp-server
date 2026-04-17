"""Tests for LUT listing, apply_lut, and preview_lut_comparison validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rawtherapee_mcp.pp3_parser import PP3Profile


@pytest.fixture
def lut_dir(tmp_path: Path) -> Path:
    """Create a fake HaldCLUT directory tree."""
    base = tmp_path / "HaldCLUT"
    base.mkdir()
    (base / "Fuji").mkdir()
    (base / "Kodak").mkdir()
    (base / "Fuji" / "Fuji Velvia 50.png").write_bytes(b"\x89PNG")
    (base / "Fuji" / "Fuji Provia 100F.png").write_bytes(b"\x89PNG")
    (base / "Kodak" / "Kodak Portra 160.png").write_bytes(b"\x89PNG")
    (base / "root_lut.tif").write_bytes(b"TIFF")
    return base


@pytest.fixture
def neutral_pp3(tmp_path: Path) -> Path:
    profile = PP3Profile()
    profile.set("Version", "AppVersion", "5.11")
    profile.set("Version", "Version", "351")
    out = tmp_path / "neutral.pp3"
    profile.save(out)
    return out


# ---------------------------------------------------------------------------
# list_luts
# ---------------------------------------------------------------------------


def test_list_luts_groups_by_subdir(lut_dir: Path) -> None:
    from unittest.mock import MagicMock

    from rawtherapee_mcp.config import RTConfig
    from rawtherapee_mcp.server import list_luts

    config = RTConfig(
        rt_cli_path=None,
        output_dir=lut_dir,
        preview_dir=lut_dir,
        custom_templates_dir=lut_dir,
        preview_max_width=1200,
        default_jpeg_quality=95,
        haldclut_dir=lut_dir,
        lcp_dir=None,
        lensfun_dir=None,
    )
    ctx = MagicMock()
    ctx.lifespan_context = {"config": config}

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(list_luts(ctx, directory=str(lut_dir)))

    assert result["total"] == 4
    assert "Fuji" in result["categories"]
    assert result["categories"]["Fuji"]["count"] == 2
    assert "Kodak" in result["categories"]
    assert result["categories"]["Kodak"]["count"] == 1


def test_list_luts_category_filter(lut_dir: Path) -> None:
    from unittest.mock import MagicMock

    from rawtherapee_mcp.config import RTConfig
    from rawtherapee_mcp.server import list_luts

    config = RTConfig(
        rt_cli_path=None,
        output_dir=lut_dir,
        preview_dir=lut_dir,
        custom_templates_dir=lut_dir,
        preview_max_width=1200,
        default_jpeg_quality=95,
        haldclut_dir=lut_dir,
        lcp_dir=None,
        lensfun_dir=None,
    )
    ctx = MagicMock()
    ctx.lifespan_context = {"config": config}

    import asyncio

    result = asyncio.get_event_loop().run_until_complete(list_luts(ctx, directory=str(lut_dir), category="Fuji"))

    assert result["total"] == 2
    assert list(result["categories"].keys()) == ["Fuji"]


def test_list_luts_no_dir_returns_error(mock_ctx: MagicMock) -> None:
    import asyncio

    from rawtherapee_mcp.server import list_luts

    result = asyncio.get_event_loop().run_until_complete(list_luts(mock_ctx))
    assert "error" in result


# ---------------------------------------------------------------------------
# apply_lut writes correct PP3 sections
# ---------------------------------------------------------------------------


def test_apply_lut_writes_film_simulation(neutral_pp3: Path, mock_ctx: MagicMock) -> None:
    import asyncio

    from rawtherapee_mcp.server import apply_lut

    result = asyncio.get_event_loop().run_until_complete(
        apply_lut(mock_ctx, profile_path=str(neutral_pp3), lut_name="Fuji/Fuji Velvia 50.png", strength=80)
    )
    assert "error" not in result

    profile = PP3Profile()
    profile.load(neutral_pp3)
    assert profile.get("Film Simulation", "Enabled") == "true"
    assert profile.get("Film Simulation", "ClutFilename") == "Fuji/Fuji Velvia 50.png"
    assert profile.get("Film Simulation", "Strength") == "80"


def test_apply_lut_invalid_strength_returns_error(neutral_pp3: Path, mock_ctx: MagicMock) -> None:
    import asyncio

    from rawtherapee_mcp.server import apply_lut

    result = asyncio.get_event_loop().run_until_complete(
        apply_lut(mock_ctx, profile_path=str(neutral_pp3), lut_name="test.png", strength=150)
    )
    assert "error" in result


# ---------------------------------------------------------------------------
# preview_lut_comparison — input validation (no RT CLI needed)
# ---------------------------------------------------------------------------


def test_preview_lut_comparison_too_few_luts(mock_ctx: MagicMock, tmp_path: Path) -> None:
    import asyncio

    from rawtherapee_mcp.server import preview_lut_comparison

    raw = tmp_path / "photo.cr2"
    raw.write_bytes(b"FAKE")
    result = asyncio.get_event_loop().run_until_complete(
        preview_lut_comparison(mock_ctx, file_path=str(raw), lut_names=["one.png"])
    )
    assert isinstance(result, dict)
    assert "error" in result


def test_preview_lut_comparison_too_many_luts(mock_ctx: MagicMock, tmp_path: Path) -> None:
    import asyncio

    from rawtherapee_mcp.server import preview_lut_comparison

    raw = tmp_path / "photo.cr2"
    raw.write_bytes(b"FAKE")
    luts = ["a.png", "b.png", "c.png", "d.png", "e.png", "f.png"]
    result = asyncio.get_event_loop().run_until_complete(
        preview_lut_comparison(mock_ctx, file_path=str(raw), lut_names=luts)
    )
    assert isinstance(result, dict)
    assert "error" in result


def test_preview_lut_comparison_missing_raw(mock_ctx: MagicMock) -> None:
    import asyncio

    from rawtherapee_mcp.server import preview_lut_comparison

    result = asyncio.get_event_loop().run_until_complete(
        preview_lut_comparison(mock_ctx, file_path="/nonexistent/photo.cr2", lut_names=["a.png", "b.png"])
    )
    assert isinstance(result, dict)
    assert "error" in result
