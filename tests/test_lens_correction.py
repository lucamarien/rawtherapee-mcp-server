"""Tests for apply_lens_correction tool and _PARAMETER_MAP entries."""

from __future__ import annotations

from pathlib import Path

import pytest

from rawtherapee_mcp.pp3_parser import PP3Profile


@pytest.fixture
def neutral_pp3(tmp_path: Path) -> Path:
    profile = PP3Profile()
    profile.set("Version", "AppVersion", "5.11")
    profile.set("Version", "Version", "351")
    profile.set("Exposure", "Compensation", "0")
    out = tmp_path / "neutral.pp3"
    profile.save(out)
    return out


def test_apply_lens_correction_auto_writes_lc_mode(neutral_pp3: Path) -> None:
    profile = PP3Profile()
    profile.load(neutral_pp3)
    profile.set("LensProfile", "LcMode", "lfauto")
    profile.set("LensProfile", "UseDistortion", "true")
    profile.set("LensProfile", "UseVignette", "true")
    profile.set("LensProfile", "UseCA", "false")
    profile.save(neutral_pp3)

    loaded = PP3Profile()
    loaded.load(neutral_pp3)
    assert loaded.get("LensProfile", "LcMode") == "lfauto"
    assert loaded.get("LensProfile", "UseDistortion") == "true"
    assert loaded.get("LensProfile", "UseVignette") == "true"
    assert loaded.get("LensProfile", "UseCA") == "false"


def test_apply_lens_correction_lcp_mode(neutral_pp3: Path, tmp_path: Path) -> None:
    lcp_file = tmp_path / "lens.lcp"
    lcp_file.write_text("<lcp/>")

    profile = PP3Profile()
    profile.load(neutral_pp3)
    profile.set("LensProfile", "LcMode", "lcp")
    profile.set("LensProfile", "LCPFile", str(lcp_file))
    profile.set("LensProfile", "UseDistortion", "true")
    profile.set("LensProfile", "UseVignette", "false")
    profile.set("LensProfile", "UseCA", "true")
    profile.save(neutral_pp3)

    loaded = PP3Profile()
    loaded.load(neutral_pp3)
    assert loaded.get("LensProfile", "LcMode") == "lcp"
    assert loaded.get("LensProfile", "LCPFile") == str(lcp_file)
    assert loaded.get("LensProfile", "UseCA") == "true"


def test_parameter_map_contains_lens_correction_keys() -> None:
    from rawtherapee_mcp.pp3_generator import _PARAMETER_MAP

    lc = _PARAMETER_MAP["lens_correction"]
    assert lc["mode"] == ("LensProfile", "LcMode")
    assert lc["lcp_file"] == ("LensProfile", "LCPFile")
    assert lc["distortion"] == ("LensProfile", "UseDistortion")
    assert lc["vignetting"] == ("LensProfile", "UseVignette")
    assert lc["ca"] == ("LensProfile", "UseCA")


def test_parameter_map_contains_film_simulation_keys() -> None:
    from rawtherapee_mcp.pp3_generator import _PARAMETER_MAP

    fs = _PARAMETER_MAP["film_simulation"]
    assert fs["enabled"] == ("Film Simulation", "Enabled")
    assert fs["clut_filename"] == ("Film Simulation", "ClutFilename")
    assert fs["strength"] == ("Film Simulation", "Strength")


def test_apply_parameters_sets_lens_correction(neutral_pp3: Path) -> None:
    from rawtherapee_mcp.pp3_generator import apply_parameters

    profile = PP3Profile()
    profile.load(neutral_pp3)
    apply_parameters(
        profile,
        {"lens_correction": {"mode": "lfauto", "distortion": True, "vignetting": True, "ca": False}},
    )
    assert profile.get("LensProfile", "LcMode") == "lfauto"
    assert profile.get("LensProfile", "UseDistortion") == "true"
    assert profile.get("LensProfile", "UseCA") == "false"


def test_apply_parameters_sets_film_simulation(neutral_pp3: Path) -> None:
    from rawtherapee_mcp.pp3_generator import apply_parameters

    profile = PP3Profile()
    profile.load(neutral_pp3)
    apply_parameters(
        profile,
        {"film_simulation": {"enabled": True, "clut_filename": "Fuji/Velvia 50.png", "strength": "80"}},
    )
    assert profile.get("Film Simulation", "Enabled") == "true"
    assert profile.get("Film Simulation", "ClutFilename") == "Fuji/Velvia 50.png"
    assert profile.get("Film Simulation", "Strength") == "80"
