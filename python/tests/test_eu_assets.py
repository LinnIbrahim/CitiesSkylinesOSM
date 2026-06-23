"""Tests for the European asset theme mapper."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eu_assets import (
    EUAssetMapper,
    apply_eu_theme,
    apply_theme,
    available_themes,
    THEME_NAME,
)


def _sample_data():
    return {
        "roads": [
            {"id": "road_1", "type": "Highway", "name": "A1", "points": []},
            {"id": "road_2", "type": "SmallRoad", "name": "Rue", "points": []},
        ],
        "railways": [{"id": "rail_1", "type": "Tram", "name": "T", "points": []}],
        "waterways": [{"id": "w_1", "type": "River", "name": "Seine", "points": []}],
        "buildings": [
            {"id": "b_1", "cs2_subtype": "LowDensityDetachedHouse",
             "zone": "ResidentialZone", "points": []},
        ],
        "transit": {
            "stops": [{"id": "s_1", "type": "tram", "name": "Stop"}],
            "routes": [{"id": "r_1", "type": "TramLine", "name": "T1"}],
        },
        "_meta": {"city": "Test"},
    }


class TestEUAssetMapper:
    def test_road_prefab_known_and_fallback(self):
        m = EUAssetMapper()
        assert m.road_prefab("Highway") == "EU_Highway"
        assert m.road_prefab("LargeRoad") == "EU_LargeAvenue"
        # Unknown types still get an EU_ prefix (never crash)
        assert m.road_prefab("Weird") == "EU_Weird"

    def test_building_prefab(self):
        m = EUAssetMapper()
        assert m.building_prefab("HighDensityApartment") == "EU_HighDensityApartment"
        assert m.building_prefab("") == "EU_LowDensityResidential"

    def test_apply_tags_every_layer(self):
        out = apply_eu_theme(_sample_data())

        assert out["roads"][0]["eu_prefab"] == "EU_Highway"
        assert out["roads"][0]["theme"] == THEME_NAME
        assert out["roads"][0]["traffic_side"] == "right"
        assert out["roads"][1]["eu_prefab"] == "EU_SmallRoad"

        assert out["railways"][0]["eu_prefab"] == "EU_TramTrack"
        assert out["waterways"][0]["eu_prefab"] == "EU_River"
        assert out["buildings"][0]["eu_prefab"] == "EU_LowDensityDetachedHouse"
        assert out["transit"]["stops"][0]["eu_prefab"] == "EU_TramStop"
        assert out["transit"]["routes"][0]["theme"] == THEME_NAME

    def test_meta_theme_block(self):
        out = apply_eu_theme(_sample_data())
        theme = out["_meta"]["theme"]
        assert theme["name"] == THEME_NAME
        assert theme["traffic_side"] == "right"
        assert theme["terrain"]["climate"] == "Temperate"

    def test_input_not_mutated(self):
        data = _sample_data()
        apply_eu_theme(data)
        assert "eu_prefab" not in data["roads"][0]
        assert "theme" not in data["_meta"]

    def test_left_hand_traffic_override(self):
        out = EUAssetMapper(traffic_side="left").apply(_sample_data())
        assert out["roads"][0]["traffic_side"] == "left"
        assert out["_meta"]["theme"]["traffic_side"] == "left"


class TestApplyTheme:
    def test_european(self):
        out = apply_theme(_sample_data(), "european")
        assert out["roads"][0]["eu_prefab"] == "EU_Highway"

    def test_none_returns_unchanged(self):
        data = _sample_data()
        assert apply_theme(data, "none") is data
        assert apply_theme(data, None) is data
        assert apply_theme(data, "vanilla") is data

    def test_unknown_theme_is_noop(self):
        data = _sample_data()
        # Unknown theme should not crash and not tag anything
        out = apply_theme(data, "martian")
        assert out is data

    def test_available_themes(self):
        assert "european" in available_themes()
        assert "none" in available_themes()
