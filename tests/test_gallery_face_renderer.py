"""Structural regressions for the single original-pixel overlay path."""

import re

import pytest

from tools import build_gallery


@pytest.mark.parametrize("name", ["renderFaceOverlay", "faceOverlayRect", "applyZoom", "openFacePopover"])
def test_overlay_entrypoint_has_one_definition(name: str) -> None:
    # Given the generated report's executable template.
    template = build_gallery.HTML_TEMPLATE
    # When counting declarations, including formerly hoisted overrides.
    declarations = re.findall(rf"\bfunction\s+{name}\s*\(", template)
    # Then each overlay entrypoint has exactly one authoritative definition.
    assert len(declarations) == 1


def test_renderer_uses_original_space_mapper_once() -> None:
    # Given the generated report, not the unrelated Python geometry helper.
    template = build_gallery.HTML_TEMPLATE
    # When inspecting the rectangle creation and mapping seams.
    definitions = re.findall(r"\bfunction\s+map_face_bbox_to_displayed_rect\s*\(", template)
    # Then there is one box creation site and one shared mapping implementation.
    assert len(definitions) == 1
    assert template.count('button.className="face-box"') == 1
    assert "imageOrientation(" not in template


@pytest.mark.parametrize("scale,pan", [(0.25, (0, 0)), (0.5, (0, 0)), (0.5, (37, -21))])
def test_portrait_original_maps_into_landscape_canvas(scale: float, pan: tuple[int, int]) -> None:
    # Given a portrait original and a landscape viewport, without rotating pixels.
    left, top = 300 + pan[0], 40 + pan[1]
    geometry = build_gallery.FaceOverlayGeometry(
        source_width=800, source_height=1400,
        content=build_gallery.OverlayFrame(left, top, 800 * scale, 1400 * scale),
        canvas=build_gallery.OverlayFrame(10, 20, 1000, 600),
    )
    # When mapping an original-space detection through fit, zoom or pan.
    actual = build_gallery.map_face_bbox_to_displayed_rect([80, 280, 40, 60], geometry)
    # Then all four dimensions use original pixels, including sub-18px faces.
    assert actual == build_gallery.OverlayFrame(
        left - 10 + 80 * scale, top - 20 + 280 * scale, 40 * scale, 60 * scale,
    )
