"""Tests for EXIF-based processing recommendations."""

from __future__ import annotations

from rawtherapee_mcp.exif_reader import generate_recommendations


def _make_exif(**kwargs: str) -> dict[str, str]:
    """Create a minimal EXIF data dict with defaults."""
    base: dict[str, str] = {
        "camera_make": "",
        "camera_model": "",
        "lens_model": "",
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
    }
    base.update(kwargs)
    return base


class TestISORecommendations:
    """ISO-based noise reduction recommendations."""

    def test_very_high_iso(self) -> None:
        recs = generate_recommendations(_make_exif(iso="12800"))
        assert any("aggressive noise reduction" in r.lower() for r in recs["text"])
        assert "Directional Pyramid Denoising" in recs["suggested_parameters"]

    def test_high_iso(self) -> None:
        recs = generate_recommendations(_make_exif(iso="6400"))
        assert any("moderate noise reduction" in r.lower() for r in recs["text"])
        nr = recs["suggested_parameters"]["Directional Pyramid Denoising"]
        assert int(nr["Luma"]) >= 20

    def test_moderate_iso(self) -> None:
        recs = generate_recommendations(_make_exif(iso="1600"))
        assert any("light noise reduction" in r.lower() for r in recs["text"])
        nr = recs["suggested_parameters"]["Directional Pyramid Denoising"]
        assert int(nr["Luma"]) <= 20

    def test_medium_iso(self) -> None:
        recs = generate_recommendations(_make_exif(iso="800"))
        assert any("light noise reduction" in r.lower() for r in recs["text"])
        nr = recs["suggested_parameters"]["Directional Pyramid Denoising"]
        assert int(nr["Luma"]) <= 20

    def test_low_iso(self) -> None:
        recs = generate_recommendations(_make_exif(iso="100"))
        assert any("minimal noise" in r.lower() for r in recs["text"])
        nr = recs["suggested_parameters"]["Directional Pyramid Denoising"]
        assert int(nr["Luma"]) <= 10

    def test_pp3_format(self) -> None:
        """suggested_parameters should be in raw PP3 section/key format."""
        recs = generate_recommendations(_make_exif(iso="12800"))
        nr = recs["suggested_parameters"]["Directional Pyramid Denoising"]
        assert nr["Enabled"] == "true"
        assert isinstance(nr["Luma"], str)
        assert isinstance(nr["Chroma"], str)
        assert isinstance(nr["Ldetail"], str)


class TestApertureRecommendations:
    """Aperture-based lens correction recommendations."""

    def test_wide_aperture_fraction(self) -> None:
        """Aperture as fraction (e.g. exifread format)."""
        recs = generate_recommendations(_make_exif(aperture="14/10"))
        assert any("wide aperture" in r.lower() for r in recs["text"])
        assert "LensProfile" in recs["suggested_parameters"]

    def test_wide_aperture_float(self) -> None:
        recs = generate_recommendations(_make_exif(aperture="1.4"))
        assert any("wide aperture" in r.lower() for r in recs["text"])

    def test_narrow_aperture(self) -> None:
        recs = generate_recommendations(_make_exif(aperture="16"))
        assert any("diffraction" in r.lower() for r in recs["text"])
        assert any("diffraction" in w.lower() for w in recs["warnings"])
        assert "Sharpening" in recs["suggested_parameters"]

    def test_mid_aperture_no_warning(self) -> None:
        """Mid-range apertures should not trigger warnings."""
        recs = generate_recommendations(_make_exif(aperture="56/10"))  # f/5.6
        assert not any("wide aperture" in r.lower() or "diffraction" in r.lower() for r in recs["text"])

    def test_sharpening_pp3_format(self) -> None:
        """Sharpening params should use raw PP3 keys."""
        recs = generate_recommendations(_make_exif(aperture="16"))
        sharp = recs["suggested_parameters"]["Sharpening"]
        assert sharp["Enabled"] == "true"
        assert isinstance(sharp["Amount"], str)
        assert isinstance(sharp["Radius"], str)
        assert isinstance(sharp["Threshold"], str)


class TestShutterSpeedRecommendations:
    """Shutter speed recommendations."""

    def test_long_exposure(self) -> None:
        recs = generate_recommendations(_make_exif(shutter_speed="2"))
        assert any("long exposure" in r.lower() for r in recs["text"])
        assert any("motion" in w.lower() or "long" in w.lower() for w in recs["warnings"])

    def test_slow_shutter(self) -> None:
        recs = generate_recommendations(_make_exif(shutter_speed="1/2"))
        assert any("slow shutter" in r.lower() or "camera shake" in r.lower() for r in recs["text"])
        assert any("shake" in w.lower() for w in recs["warnings"])

    def test_fast_shutter_no_warning(self) -> None:
        """Fast shutters should not trigger motion warnings."""
        recs = generate_recommendations(_make_exif(shutter_speed="1/1000"))
        assert not any("motion" in r.lower() or "shake" in r.lower() for r in recs["text"])
        assert not any("motion" in w.lower() or "shake" in w.lower() for w in recs["warnings"])


class TestWhiteBalanceRecommendations:
    """White balance recommendations."""

    def test_auto_wb(self) -> None:
        recs = generate_recommendations(_make_exif(white_balance="0"))
        assert any("white balance" in r.lower() for r in recs["text"])
        assert any("white balance" in w.lower() for w in recs["warnings"])

    def test_manual_wb_no_warning(self) -> None:
        """Manual WB should not trigger auto-WB warning."""
        recs = generate_recommendations(_make_exif(white_balance="1"))
        assert not any("auto white balance" in r.lower() for r in recs["text"])


class TestFocalLengthRecommendations:
    """Focal length and lens recommendations."""

    def test_wide_angle(self) -> None:
        recs = generate_recommendations(_make_exif(focal_length="16"))
        assert any("wide-angle" in r.lower() for r in recs["text"])
        assert any("wide-angle" in w.lower() for w in recs["warnings"])

    def test_wide_angle_fraction(self) -> None:
        recs = generate_recommendations(_make_exif(focal_length="24/1"))
        assert any("wide-angle" in r.lower() for r in recs["text"])

    def test_telephoto_no_wide_warning(self) -> None:
        recs = generate_recommendations(_make_exif(focal_length="200"))
        assert not any("wide-angle" in r.lower() for r in recs["text"])

    def test_lens_model(self) -> None:
        recs = generate_recommendations(_make_exif(lens_model="RF 85mm F1.2L USM"))
        assert any("rf 85mm" in r.lower() for r in recs["text"])


class TestStructuredOutput:
    """Tests for the structured recommendation format."""

    def test_return_type(self) -> None:
        recs = generate_recommendations(_make_exif(iso="6400"))
        assert isinstance(recs, dict)
        assert "text" in recs
        assert "suggested_parameters" in recs
        assert "warnings" in recs

    def test_text_is_list(self) -> None:
        recs = generate_recommendations(_make_exif(iso="6400"))
        assert isinstance(recs["text"], list)
        assert all(isinstance(t, str) for t in recs["text"])

    def test_suggested_parameters_is_dict(self) -> None:
        recs = generate_recommendations(_make_exif(iso="6400"))
        assert isinstance(recs["suggested_parameters"], dict)

    def test_warnings_is_list(self) -> None:
        recs = generate_recommendations(_make_exif(iso="6400"))
        assert isinstance(recs["warnings"], list)


class TestEdgeCases:
    """Edge cases and empty data."""

    def test_empty_exif(self) -> None:
        """Empty EXIF should return fallback message."""
        recs = generate_recommendations(_make_exif())
        assert len(recs["text"]) == 1
        assert "no specific recommendations" in recs["text"][0].lower()

    def test_invalid_iso_string(self) -> None:
        """Non-numeric ISO should not crash."""
        recs = generate_recommendations(_make_exif(iso="Auto"))
        assert isinstance(recs, dict)

    def test_invalid_aperture(self) -> None:
        """Non-parseable aperture should not crash."""
        recs = generate_recommendations(_make_exif(aperture="unknown"))
        assert isinstance(recs, dict)

    def test_zero_denominator(self) -> None:
        """Zero-denominator fractions should not crash."""
        recs = generate_recommendations(_make_exif(aperture="14/0"))
        assert isinstance(recs, dict)

    def test_combined_recommendations(self) -> None:
        """Multiple EXIF values should produce multiple recommendations."""
        recs = generate_recommendations(
            _make_exif(
                iso="6400",
                aperture="14/10",
                shutter_speed="2",
                white_balance="0",
                focal_length="16",
                lens_model="EF 16-35mm f/2.8L",
            )
        )
        # Should have recommendations for: ISO, aperture, shutter, WB, focal, lens
        assert len(recs["text"]) >= 5
        # Should have multiple suggested parameters
        assert len(recs["suggested_parameters"]) >= 2
        # Should have warnings
        assert len(recs["warnings"]) >= 2
