"""Tests for the interactive generate server's HTML page builder."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generate_server import _build_page, CS2_MAP_SIZE


class TestBuildPage:
    def test_no_unfilled_placeholders(self):
        page = _build_page()
        assert "__THEME_OPTIONS__" not in page
        assert "__CS2_MAP_SIZE__" not in page

    def test_injects_map_size(self):
        page = _build_page()
        assert f"const CS2_MAP_SIZE = {CS2_MAP_SIZE!r}" in page
        assert CS2_MAP_SIZE == 57344.0

    def test_theme_options_present(self):
        page = _build_page()
        assert '<option value="european">European</option>' in page
        assert '<option value="none">None</option>' in page

    def test_has_generate_endpoint_and_box(self):
        page = _build_page()
        assert "/api/generate" in page
        assert "redrawBox" in page          # draggable selection box
        assert "selectedBbox" in page

    def test_feature_checkboxes(self):
        page = _build_page()
        # Roads + tram/train tracks are on by default; transit (stations) is off.
        assert 'value="roads" checked' in page
        assert 'value="railways" checked' in page
        assert 'value="transit">' in page          # present but not checked
        assert "Train stations are not placed" in page

    def test_cancel_button(self):
        page = _build_page()
        assert 'id="ov-cancel"' in page
        assert "cancelGenerate" in page
