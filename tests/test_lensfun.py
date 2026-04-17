"""Tests for the Lensfun XML database parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from rawtherapee_mcp.lensfun import check_lens_support

SAMPLE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<lensdatabase>
  <camera>
    <maker>Canon</maker>
    <model>Canon EOS 5D Mark IV</model>
    <mount>Canon EF</mount>
  </camera>
  <lens>
    <maker>Canon</maker>
    <model>Canon EF 135mm f/2L USM</model>
    <mount>Canon EF</mount>
    <calibration>
      <distortion model="ptlens" focal="135" a="0.001" b="-0.004" c="0.001"/>
      <vignetting model="pa" focal="135" aperture="2" distance="10" k1="-0.1"/>
      <tca model="linear" focal="135" kr="1.0001" kb="0.9999"/>
    </calibration>
  </lens>
  <lens>
    <maker>Sigma</maker>
    <model>Sigma 50mm f/1.4 DG HSM A</model>
    <mount>Canon EF</mount>
    <calibration>
      <distortion model="ptlens" focal="50" a="0.001" b="-0.002" c="0.001"/>
    </calibration>
  </lens>
</lensdatabase>
"""


@pytest.fixture
def lensfun_dir(tmp_path: Path) -> Path:
    db_dir = tmp_path / "lensfun"
    db_dir.mkdir()
    (db_dir / "canon.xml").write_text(SAMPLE_XML, encoding="utf-8")
    return db_dir


def test_camera_found(lensfun_dir: Path) -> None:
    result = check_lens_support(
        lensfun_dir,
        camera_make="Canon",
        camera_model="Canon EOS 5D Mark IV",
    )
    assert result["camera_found"] is True


def test_camera_not_found(lensfun_dir: Path) -> None:
    result = check_lens_support(
        lensfun_dir,
        camera_make="Nikon",
        camera_model="Z9",
    )
    assert result["camera_found"] is False


def test_camera_match_case_insensitive(lensfun_dir: Path) -> None:
    result = check_lens_support(
        lensfun_dir,
        camera_make="canon",
        camera_model="canon eos 5d mark iv",
    )
    assert result["camera_found"] is True


def test_lens_found_with_all_calibrations(lensfun_dir: Path) -> None:
    result = check_lens_support(lensfun_dir, lens_model="EF 135mm")
    assert result["lens_found"] is True
    corrections = result["corrections_available"]
    assert isinstance(corrections, dict)
    assert corrections["distortion"] is True
    assert corrections["vignetting"] is True
    assert corrections["tca"] is True


def test_lens_found_partial_calibration(lensfun_dir: Path) -> None:
    result = check_lens_support(lensfun_dir, lens_model="Sigma 50mm")
    assert result["lens_found"] is True
    corrections = result["corrections_available"]
    assert isinstance(corrections, dict)
    assert corrections["distortion"] is True
    assert corrections["vignetting"] is False
    assert corrections["tca"] is False


def test_lens_not_found(lensfun_dir: Path) -> None:
    result = check_lens_support(lensfun_dir, lens_model="Tamron 17-28mm")
    assert result["lens_found"] is False


def test_missing_directory_returns_error() -> None:
    result = check_lens_support(Path("/nonexistent/lensfun"))
    assert "error" in result


def test_empty_directory_returns_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = check_lens_support(empty)
    assert "error" in result


def test_recommendation_present_when_lens_supported(lensfun_dir: Path) -> None:
    result = check_lens_support(lensfun_dir, lens_model="EF 135mm")
    assert result["recommendation"] is not None
    assert "auto" in str(result["recommendation"]).lower()


def test_matched_lens_name_returned(lensfun_dir: Path) -> None:
    result = check_lens_support(lensfun_dir, lens_model="EF 135mm")
    assert result["matched_lens_name"] == "Canon EF 135mm f/2L USM"
