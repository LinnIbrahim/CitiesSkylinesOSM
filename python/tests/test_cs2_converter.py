"""Tests for CS2Converter — coordinate transform, clipping, chunking, transit."""

import json
import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cs2_converter import CoordinateTransformer, CS2Converter


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------

MONACO_BBOX = (43.7247, 7.4090, 43.7519, 7.4399)


@pytest.fixture
def transformer():
    return CoordinateTransformer(MONACO_BBOX)


@pytest.fixture
def converter(tmp_path):
    return CS2Converter(
        bbox=MONACO_BBOX,
        elevation_data={(43.73, 7.42): 50.0, (43.74, 7.43): 100.0},
        output_dir=str(tmp_path),
    )


# ---------------------------------------------------------------
# CoordinateTransformer
# ---------------------------------------------------------------

class TestCoordinateTransformer:
    def test_centre_maps_to_origin(self, transformer):
        lat_c = (43.7247 + 43.7519) / 2
        lon_c = (7.4090 + 7.4399) / 2
        pt = transformer.to_cs2(lat_c, lon_c)
        assert pt["x"] == pytest.approx(0.0, abs=0.1)
        assert pt["z"] == pytest.approx(0.0, abs=0.1)

    def test_east_is_positive_x(self, transformer):
        lat_c = (43.7247 + 43.7519) / 2
        lon_c = (7.4090 + 7.4399) / 2
        pt = transformer.to_cs2(lat_c, lon_c + 0.01)
        assert pt["x"] > 0

    def test_north_is_negative_z(self, transformer):
        lat_c = (43.7247 + 43.7519) / 2
        lon_c = (7.4090 + 7.4399) / 2
        pt = transformer.to_cs2(lat_c + 0.01, lon_c)
        assert pt["z"] < 0  # Z+ = South, so north → negative Z

    def test_elevation_passthrough(self, transformer):
        lat_c = (43.7247 + 43.7519) / 2
        lon_c = (7.4090 + 7.4399) / 2
        pt = transformer.to_cs2(lat_c, lon_c, elevation=42.5)
        assert pt["y"] == pytest.approx(42.5)

    def test_in_bounds_centre(self, transformer):
        lat_c = (43.7247 + 43.7519) / 2
        lon_c = (7.4090 + 7.4399) / 2
        assert transformer.in_bounds(lat_c, lon_c) is True

    def test_small_city_no_clipping(self, transformer):
        assert transformer.needs_clipping is False

    def test_large_city_needs_clipping(self):
        # Bbox spanning ~600 km — should need clipping
        t = CoordinateTransformer((40.0, -5.0, 45.0, 5.0))
        assert t.needs_clipping is True

    def test_stats(self, transformer):
        s = transformer.stats()
        assert "centre" in s
        assert "city_size_m" in s
        assert s["cs2_map_size_m"] == 57344.0


# ---------------------------------------------------------------
# clip_and_convert_line
# ---------------------------------------------------------------

class TestClipAndConvertLine:
    def test_line_inside_bounds(self, transformer):
        # Small line near centre — should not be clipped
        coords = [(7.42, 43.73), (7.43, 43.74)]
        segments = transformer.clip_and_convert_line(coords, {})
        assert len(segments) == 1
        assert len(segments[0]) == 2

    def test_line_outside_bounds(self, transformer):
        # Line far outside the map — should return empty
        coords = [(100.0, 0.0), (101.0, 1.0)]
        segments = transformer.clip_and_convert_line(coords, {})
        assert len(segments) == 0

    def test_single_point_returns_empty(self, transformer):
        coords = [(7.42, 43.73)]
        assert transformer.clip_and_convert_line(coords, {}) == []

    def test_elevation_interpolated(self, transformer):
        elevations = {(43.73, 7.42): 50.0, (43.74, 7.43): 100.0}
        coords = [(7.42, 43.73), (7.43, 43.74)]
        segments = transformer.clip_and_convert_line(coords, elevations)
        assert len(segments) == 1
        # First point should have elevation ~50, second ~100
        assert segments[0][0]["y"] == pytest.approx(50.0, abs=5)
        assert segments[0][1]["y"] == pytest.approx(100.0, abs=5)


# ---------------------------------------------------------------
# clip_and_convert_polygon
# ---------------------------------------------------------------

class TestClipAndConvertPolygon:
    def test_polygon_inside_bounds(self, transformer):
        coords = [
            (7.42, 43.73), (7.43, 43.73),
            (7.43, 43.74), (7.42, 43.74),
            (7.42, 43.73),  # closed
        ]
        points = transformer.clip_and_convert_polygon(coords, {})
        assert points is not None
        assert len(points) >= 4

    def test_too_few_points(self, transformer):
        coords = [(7.42, 43.73), (7.43, 43.73)]
        assert transformer.clip_and_convert_polygon(coords, {}) is None


# ---------------------------------------------------------------
# CS2Converter.convert_roads
# ---------------------------------------------------------------

class TestConvertRoads:
    def test_converts_road(self, converter):
        roads = [{
            "id": 1,
            "type": "primary",
            "name": "Test Road",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "lanes": 2,
            "oneway": False,
            "maxspeed": "50",
            "priority": 3,
            "geometry": None,
        }]
        cs2_roads = converter.convert_roads(roads)
        assert len(cs2_roads) == 1
        assert cs2_roads[0]["type"] == "LargeRoad"
        assert cs2_roads[0]["speedLimit"] == 50
        assert cs2_roads[0]["id"].startswith("road_")

    def test_speed_mph_conversion(self, converter):
        roads = [{
            "id": 2, "type": "motorway", "name": "",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "lanes": 3, "oneway": True, "maxspeed": "60 mph",
            "priority": 5, "geometry": None,
        }]
        cs2_roads = converter.convert_roads(roads)
        assert cs2_roads[0]["speedLimit"] == 96  # 60 * 1.609

    def test_unknown_road_type_defaults(self, converter):
        roads = [{
            "id": 3, "type": "unknown_type", "name": "",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "lanes": 1, "oneway": False, "maxspeed": "",
            "priority": 0, "geometry": None,
        }]
        cs2_roads = converter.convert_roads(roads)
        assert cs2_roads[0]["type"] == "SmallRoad"  # default


# ---------------------------------------------------------------
# CS2Converter.convert_railways
# ---------------------------------------------------------------

class TestConvertRailways:
    def test_rail_type_mapping(self, converter):
        railways = [{
            "id": 10, "type": "subway", "name": "Metro 1",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "electrified": "yes", "geometry": None,
        }]
        cs2 = converter.convert_railways(railways)
        assert cs2[0]["type"] == "Subway"
        assert cs2[0]["electrified"] is True


# ---------------------------------------------------------------
# CS2Converter.convert_waterways
# ---------------------------------------------------------------

class TestConvertWaterways:
    def test_linear_waterway(self, converter):
        wws = [{
            "id": 20, "type": "river", "name": "Test River",
            "is_area": False, "width": 10.0,
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "geometry": None,
        }]
        cs2 = converter.convert_waterways(wws)
        assert len(cs2) == 1
        assert cs2[0]["type"] == "River"
        assert cs2[0]["isArea"] is False

    def test_area_waterway(self, converter):
        coords = [
            (7.42, 43.73), (7.43, 43.73),
            (7.43, 43.74), (7.42, 43.74),
            (7.42, 43.73),
        ]
        wws = [{
            "id": 21, "type": "water", "name": "Test Lake",
            "is_area": True, "width": None,
            "coordinates": coords, "geometry": None,
        }]
        cs2 = converter.convert_waterways(wws)
        assert len(cs2) == 1
        assert cs2[0]["isArea"] is True


# ---------------------------------------------------------------
# CS2Converter.convert_transit
# ---------------------------------------------------------------

class TestConvertTransit:
    def test_stop_conversion(self, converter):
        transit = {
            "stops": [{
                "id": 1, "name": "Central", "type": "bus",
                "coordinates": (7.42, 43.73),
                "is_external": False, "is_underground": False,
                "has_shelter": True, "has_bench": False,
                "wheelchair": "yes",
            }],
            "routes": [],
        }
        cs2 = converter.convert_transit(transit)
        assert len(cs2["stops"]) == 1
        assert cs2["stops"][0]["id"] == "stop_1"
        assert cs2["stops"][0]["has_shelter"] is True

    def test_external_stop_clamped(self, converter):
        transit = {
            "stops": [{
                "id": 2, "name": "Far Away", "type": "train",
                "coordinates": (100.0, 80.0),  # far outside
                "is_external": True, "is_underground": False,
                "has_shelter": False, "has_bench": False,
                "wheelchair": "unknown",
            }],
            "routes": [],
        }
        cs2 = converter.convert_transit(transit)
        assert len(cs2["stops"]) == 1
        pos = cs2["stops"][0]["position"]
        half = converter.transformer.CS2_HALF_MAP
        assert abs(pos["x"]) <= half + 1
        assert abs(pos["z"]) <= half + 1

    def test_route_with_fare(self, converter):
        transit = {
            "stops": [{
                "id": 10, "name": "A", "type": "bus",
                "coordinates": (7.42, 43.73),
                "is_external": False, "is_underground": False,
                "has_shelter": False, "has_bench": False,
                "wheelchair": "unknown",
            }],
            "routes": [{
                "id": 100, "name": "Bus 1", "ref": "1",
                "route_type": "bus", "operator": "RATP",
                "colour": "#FF0000", "network": "Nice", "from": "A", "to": "B",
                "is_intercity": False,
                "stop_ids": [10],
                "fare": {"base_fare": 2.50, "currency": "EUR", "source": "osm"},
            }],
        }
        cs2 = converter.convert_transit(transit)
        assert len(cs2["routes"]) == 1
        assert cs2["routes"][0]["fare"]["base_fare"] == 2.50


# ---------------------------------------------------------------
# CS2Converter.create_chunks
# ---------------------------------------------------------------

class TestCreateChunks:
    def test_single_chunk_for_small_data(self, converter):
        data = {
            "roads": [{
                "id": "road_1", "type": "SmallRoad", "name": "X",
                "points": [{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 100}],
                "lanes": 2, "oneWay": False, "speedLimit": 50, "priority": 0,
            }],
            "railways": [],
            "waterways": [],
            "transit": {"stops": [], "routes": []},
        }
        chunks = converter.create_chunks(data, chunk_size_m=60000)
        assert len(chunks) == 1
        assert len(chunks[0]["roads"]) == 1

    def test_multiple_chunks(self, converter):
        data = {
            "roads": [
                {
                    "id": f"road_{i}", "type": "SmallRoad", "name": "",
                    "points": [{"x": x, "y": 0, "z": 0}],
                    "lanes": 2, "oneWay": False, "speedLimit": 50, "priority": 0,
                }
                for i, x in enumerate([-20000, 0, 20000])
            ],
            "railways": [],
            "waterways": [],
            "transit": {"stops": [], "routes": []},
        }
        chunks = converter.create_chunks(data, chunk_size_m=5000)
        # Roads at different x positions should end up in different chunks
        assert len(chunks) >= 2


# ---------------------------------------------------------------
# CS2Converter.save_to_file
# ---------------------------------------------------------------

class TestSaveToFile:
    def test_saves_json(self, converter, tmp_path):
        data = {"test": [1, 2, 3]}
        converter.save_to_file(data, "test_output.json")
        path = os.path.join(str(tmp_path), "test_output.json")
        assert os.path.exists(path)
        with open(path) as f:
            loaded = json.load(f)
        assert loaded == data
