"""Tests for the shared OSM → CS2 pipeline (no network — fakes injected)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import generate_city_data


class FakeFetcher:
    """Stand-in for OSMFetcher — returns canned OSM result handles."""

    def fetch_city_data(self, bbox, features, log=None):
        # Values are opaque; the FakeParser ignores them.
        return {"roads": "ROADS", "buildings": "BLDGS"}

    def fetch_elevation(self, coords, log=None):
        return {}


class FakeParser:
    """Stand-in for OSMParser — returns structured parsed features."""

    def parse_roads(self, _osm):
        return [{
            "id": 1, "type": "primary", "name": "Main St",
            "lanes": 2, "oneway": False, "maxspeed": "50", "priority": 3,
            "coordinates": [(7.0000, 43.0000), (7.0010, 43.0010)],
        }]

    def get_underground_way_ids(self, _osm):
        return set()

    def parse_buildings(self, _osm):
        return [{
            "id": 2, "type": "house", "zone": "residential", "density": "low",
            "cs2_subtype": "LowDensityDetachedHouse", "name": "",
            "height": 6.0, "levels": 2,
            "coordinates": [
                (7.0000, 43.0000), (7.0002, 43.0000),
                (7.0002, 43.0002), (7.0000, 43.0002), (7.0000, 43.0000),
            ],
        }]


BBOX = (42.99, 6.99, 43.01, 7.01)


def _run(theme="european"):
    return generate_city_data(
        BBOX,
        features=["roads", "buildings"],
        city_name="Test",
        theme=theme,
        fetch_elevation=False,
        fetcher=FakeFetcher(),
        parser=FakeParser(),
        log=lambda *_: None,
    )


class TestGeneratePipeline:
    def test_produces_roads_and_buildings(self):
        out = _run()
        assert out["counts"]["roads"] == 1
        assert out["counts"]["buildings"] == 1
        assert out["cs2_data"]["roads"][0]["type"] == "LargeRoad"  # primary → LargeRoad

    def test_eu_theme_applied(self):
        out = _run(theme="european")
        road = out["cs2_data"]["roads"][0]
        bldg = out["cs2_data"]["buildings"][0]
        assert road["eu_prefab"] == "EU_LargeAvenue"
        assert bldg["eu_prefab"] == "EU_LowDensityDetachedHouse"
        assert out["cs2_data"]["_meta"]["theme"]["name"] == "European"

    def test_no_theme(self):
        out = _run(theme="none")
        assert "eu_prefab" not in out["cs2_data"]["roads"][0]
        assert "theme" not in out["cs2_data"]["_meta"]

    def test_meta_and_chunks(self):
        out = _run()
        meta = out["cs2_data"]["_meta"]
        assert meta["city"] == "Test"
        assert meta["bbox"]["south"] == BBOX[0]
        assert out["counts"]["chunks"] >= 1
        assert isinstance(out["chunks"], list)

    def test_converter_returned(self):
        out = _run()
        assert out["converter"] is not None
        assert hasattr(out["converter"], "save_to_file")
