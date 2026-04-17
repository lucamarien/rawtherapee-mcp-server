"""Tests for the profile inheritance system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rawtherapee_mcp.pp3_parser import PP3Profile
from rawtherapee_mcp.profile_hierarchy import (
    create_variant,
    list_variants,
    load_hierarchy,
    propagate_to_variants,
)


@pytest.fixture
def parent_pp3(tmp_path: Path) -> Path:
    profile = PP3Profile()
    profile.set("Version", "AppVersion", "5.11")
    profile.set("Version", "Version", "351")
    profile.set("White Balance", "Temperature", "5500")
    profile.set("Exposure", "Compensation", "0")
    out = tmp_path / "custom_templates" / "event_base.pp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    profile.save(out)
    return out


@pytest.fixture
def custom_dir(parent_pp3: Path) -> Path:
    return parent_pp3.parent


# ---------------------------------------------------------------------------
# create_variant
# ---------------------------------------------------------------------------


def test_create_variant_generates_merged_pp3(custom_dir: Path, parent_pp3: Path) -> None:
    result = create_variant(
        custom_dir,
        parent_pp3,
        "event_indoor",
        overrides={"White Balance": {"Temperature": "3800"}},
    )

    assert result["variant_name"] == "event_indoor"
    assert result["parent"] == "event_base"
    out_path = Path(result["effective_profile_path"])
    assert out_path.is_file()

    variant = PP3Profile()
    variant.load(out_path)
    assert variant.get("White Balance", "Temperature") == "3800"
    assert variant.get("Exposure", "Compensation") == "0"  # inherited from parent


def test_create_variant_records_in_hierarchy(custom_dir: Path, parent_pp3: Path) -> None:
    create_variant(
        custom_dir,
        parent_pp3,
        "event_outdoor",
        overrides={"Exposure": {"HighlightCompr": "40"}},
        description="Outdoor variant",
    )

    hierarchy = load_hierarchy(custom_dir)
    assert "event_base" in hierarchy
    assert "event_outdoor" in hierarchy["event_base"]["variants"]
    variant_entry = hierarchy["event_base"]["variants"]["event_outdoor"]
    assert variant_entry["description"] == "Outdoor variant"
    assert variant_entry["overrides"] == {"Exposure": {"HighlightCompr": "40"}}


def test_create_multiple_variants(custom_dir: Path, parent_pp3: Path) -> None:
    create_variant(custom_dir, parent_pp3, "var_a", overrides={"Exposure": {"Compensation": "0.5"}})
    create_variant(custom_dir, parent_pp3, "var_b", overrides={"Exposure": {"Compensation": "-0.3"}})

    hierarchy = load_hierarchy(custom_dir)
    assert len(hierarchy["event_base"]["variants"]) == 2


def test_variant_overrides_do_not_bleed_between_variants(custom_dir: Path, parent_pp3: Path) -> None:
    create_variant(custom_dir, parent_pp3, "v_a", overrides={"Exposure": {"Compensation": "1.0"}})
    create_variant(custom_dir, parent_pp3, "v_b", overrides={"White Balance": {"Temperature": "3200"}})

    v_a = PP3Profile()
    v_a.load(custom_dir / "_generated" / "v_a.pp3")
    v_b = PP3Profile()
    v_b.load(custom_dir / "_generated" / "v_b.pp3")

    assert v_a.get("Exposure", "Compensation") == "1.0"
    assert v_b.get("Exposure", "Compensation") == "0"  # parent's value
    assert v_b.get("White Balance", "Temperature") == "3200"
    assert v_a.get("White Balance", "Temperature") == "5500"  # parent's value


# ---------------------------------------------------------------------------
# list_variants
# ---------------------------------------------------------------------------


def test_list_variants_all(custom_dir: Path, parent_pp3: Path) -> None:
    create_variant(custom_dir, parent_pp3, "v1", overrides={})
    create_variant(custom_dir, parent_pp3, "v2", overrides={})

    result = list_variants(custom_dir)
    assert result["total_variants"] == 2
    assert "event_base" in result["profiles"]


def test_list_variants_filtered_by_parent(custom_dir: Path, parent_pp3: Path) -> None:
    create_variant(custom_dir, parent_pp3, "child_1", overrides={})
    result = list_variants(custom_dir, parent_profile="event_base")
    assert result["total"] == 1
    assert result["variants"][0]["variant_name"] == "child_1"


def test_list_variants_nonexistent_parent(custom_dir: Path) -> None:
    result = list_variants(custom_dir, parent_profile="nonexistent")
    assert result["total"] == 0
    assert result["variants"] == []


# ---------------------------------------------------------------------------
# propagate_to_variants
# ---------------------------------------------------------------------------


def test_propagate_updates_all_children(custom_dir: Path, parent_pp3: Path) -> None:
    create_variant(custom_dir, parent_pp3, "p_indoor", overrides={"White Balance": {"Temperature": "3800"}})
    create_variant(custom_dir, parent_pp3, "p_outdoor", overrides={"Exposure": {"HighlightCompr": "40"}})

    parent = PP3Profile()
    parent.load(parent_pp3)
    parent.set("Exposure", "Contrast", "15")
    parent.save(parent_pp3)

    results = propagate_to_variants(custom_dir, "event_base", parent_pp3)
    assert all(r["status"] == "regenerated" for r in results)
    assert len(results) == 2

    for name, expected_temp, expected_hlcompr in [
        ("p_indoor", "3800", "0"),
        ("p_outdoor", "5500", "40"),
    ]:
        v = PP3Profile()
        v.load(custom_dir / "_generated" / f"{name}.pp3")
        assert v.get("Exposure", "Contrast") == "15", f"{name} should inherit updated contrast"
        assert v.get("White Balance", "Temperature") == expected_temp
        if expected_hlcompr != "0":
            assert v.get("Exposure", "HighlightCompr") == expected_hlcompr


# ---------------------------------------------------------------------------
# list_templates skips _generated/
# ---------------------------------------------------------------------------


def test_list_templates_does_not_expose_generated_variants(custom_dir: Path, parent_pp3: Path) -> None:
    import asyncio

    from rawtherapee_mcp.config import RTConfig
    from rawtherapee_mcp.server import list_templates

    config = RTConfig(
        rt_cli_path=None,
        output_dir=custom_dir,
        preview_dir=custom_dir,
        custom_templates_dir=custom_dir,
        preview_max_width=1200,
        default_jpeg_quality=95,
        haldclut_dir=None,
        lcp_dir=None,
        lensfun_dir=None,
    )
    ctx = MagicMock()
    ctx.lifespan_context = {"config": config}

    create_variant(custom_dir, parent_pp3, "generated_v", overrides={})
    result = asyncio.get_event_loop().run_until_complete(list_templates(ctx))

    custom_names = [t["name"] for t in result["custom"]]
    assert "generated_v" not in custom_names
    assert "event_base" in custom_names
