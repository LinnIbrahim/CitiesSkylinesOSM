"""Tests for the interactive generate server's HTML page builder."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generate_server import _build_page, CS2_MAP_SIZE
from cs2_import import cs2_import_target


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

    def test_import_controls(self):
        page = _build_page()
        assert "/api/import" in page
        assert 'id="importbtn"' in page
        assert 'id="opt-money"' in page      # unlimited money toggle
        assert 'id="opt-unlock"' in page     # unlock all toggle
        assert 'id="opt-tiles"' in page      # all map tiles toggle


class TestCS2ImportTarget:
    def test_env_var_takes_precedence(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CS2_MODS_DIR", str(tmp_path))
        dest, is_real, source = cs2_import_target("../data/processed")
        assert source == "CS2_MODS_DIR"
        assert is_real is True
        assert dest.endswith(os.path.join("DynamicCityLoader", "data"))
        assert str(tmp_path) in dest

    def test_staging_fallback_when_no_env_or_mods(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CS2_MODS_DIR", raising=False)
        # Point HOME at an empty dir so no default Mods folder exists.
        monkeypatch.setenv("HOME", str(tmp_path))
        out = tmp_path / "processed"
        out.mkdir()
        dest, is_real, source = cs2_import_target(str(out))
        assert source == "staging"
        assert is_real is False
        assert "cs2_import" in dest
