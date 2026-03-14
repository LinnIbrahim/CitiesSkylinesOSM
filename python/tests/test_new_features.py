"""Tests for new pipeline features: simplification, buildings, improved chunking."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from cs2_converter import CS2Converter, CoordinateTransformer
from osm_parser import OSMParser
from unittest.mock import MagicMock


MONACO_BBOX = (43.7247, 7.4090, 43.7519, 7.4399)


# ---------------------------------------------------------------
# Douglas-Peucker simplification
# ---------------------------------------------------------------

class TestSimplifyPoints:
    def test_straight_line_simplified(self):
        # 5 collinear points → should simplify to 2
        points = [
            {"x": 0, "y": 0, "z": 0},
            {"x": 25, "y": 0, "z": 0},
            {"x": 50, "y": 0, "z": 0},
            {"x": 75, "y": 0, "z": 0},
            {"x": 100, "y": 0, "z": 0},
        ]
        result = CS2Converter.simplify_points(points, tolerance=1.0)
        assert len(result) == 2
        assert result[0]["x"] == 0
        assert result[-1]["x"] == 100

    def test_curve_preserved(self):
        # Point significantly off the line → should be kept
        points = [
            {"x": 0, "y": 0, "z": 0},
            {"x": 50, "y": 0, "z": 50},  # 50m off the straight line
            {"x": 100, "y": 0, "z": 0},
        ]
        result = CS2Converter.simplify_points(points, tolerance=2.0)
        assert len(result) == 3

    def test_two_points_unchanged(self):
        points = [{"x": 0, "y": 0, "z": 0}, {"x": 100, "y": 0, "z": 100}]
        result = CS2Converter.simplify_points(points, tolerance=1.0)
        assert len(result) == 2

    def test_empty_input(self):
        assert CS2Converter.simplify_points([], tolerance=1.0) == []

    def test_single_point(self):
        points = [{"x": 5, "y": 0, "z": 5}]
        assert len(CS2Converter.simplify_points(points, tolerance=1.0)) == 1

    def test_tolerance_zero_keeps_all(self):
        points = [
            {"x": 0, "y": 0, "z": 0},
            {"x": 50, "y": 0, "z": 0.001},  # tiny deviation
            {"x": 100, "y": 0, "z": 0},
        ]
        result = CS2Converter.simplify_points(points, tolerance=0.0)
        assert len(result) == 3


class TestSimplifyAll:
    def test_simplifies_roads(self, tmp_path):
        converter = CS2Converter(bbox=MONACO_BBOX, output_dir=str(tmp_path))
        data = {
            "roads": [{
                "id": "road_1", "type": "SmallRoad", "name": "Test",
                "points": [
                    {"x": 0, "y": 0, "z": 0},
                    {"x": 50, "y": 0, "z": 0},
                    {"x": 100, "y": 0, "z": 0},
                ],
                "lanes": 2, "oneWay": False, "speedLimit": 50, "priority": 0,
            }],
        }
        result = converter.simplify_all(data, tolerance=1.0)
        assert len(result["roads"][0]["points"]) == 2  # collinear → simplified


# ---------------------------------------------------------------
# Building parsing
# ---------------------------------------------------------------

def _mock_node(node_id, lat, lon, tags=None):
    node = MagicMock()
    node.id = node_id
    node.lat = lat
    node.lon = lon
    node.tags = tags or {}
    return node


def _make_way_nodes(coords):
    return [_mock_node(i, lat, lon) for i, (lon, lat) in enumerate(coords)]


class TestParseBuildings:
    def test_basic_building(self):
        parser = OSMParser()
        coords = [(7.42, 43.73), (7.43, 43.73), (7.43, 43.74), (7.42, 43.74), (7.42, 43.73)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 500
        way.tags = {"building": "apartments", "name": "Test Bldg", "building:levels": "5", "height": "15"}
        way.nodes = nodes

        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert len(buildings) == 1
        b = buildings[0]
        assert b["type"] == "apartments"
        assert b["zone"] == "residential"
        assert b["levels"] == 5
        assert b["height"] == 15.0
        assert b["density"] == "high"  # 5 levels, apartments = high density
        assert "Apartment" in b["cs2_subtype"]

    def test_unclosed_building_skipped(self):
        parser = OSMParser()
        coords = [(7.42, 43.73), (7.43, 43.73), (7.43, 43.74), (7.42, 43.74)]  # not closed
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 501
        way.tags = {"building": "yes"}
        way.nodes = nodes

        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert len(buildings) == 0

    def test_commercial_zone(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 502
        way.tags = {"building": "retail"}
        way.nodes = nodes

        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["zone"] == "commercial"

    def test_default_levels(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 503
        way.tags = {"building": "yes"}
        way.nodes = nodes

        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["levels"] == 1

    def test_detached_house_low_density(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 504
        way.tags = {"building": "detached"}
        way.nodes = nodes
        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["density"] == "low"
        assert "DetachedHouse" in buildings[0]["cs2_subtype"]

    def test_high_rise_apartments(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 505
        way.tags = {"building": "apartments", "building:levels": "12"}
        way.nodes = nodes
        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["density"] == "high"
        assert "HighDensity" in buildings[0]["cs2_subtype"]

    def test_civic_school(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 506
        way.tags = {"building": "school"}
        way.nodes = nodes
        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["zone"] == "civic"
        assert buildings[0]["cs2_subtype"] == "School"

    def test_hotel_high_density_commercial(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 507
        way.tags = {"building": "hotel", "building:levels": "8"}
        way.nodes = nodes
        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["zone"] == "commercial"
        assert buildings[0]["density"] == "high"
        assert "Hotel" in buildings[0]["cs2_subtype"]

    def test_material_and_roof_extracted(self):
        parser = OSMParser()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = MagicMock()
        way.id = 508
        way.tags = {"building": "house", "building:material": "brick", "roof:shape": "gabled", "building:colour": "red"}
        way.nodes = nodes
        result = MagicMock()
        result.ways = [way]

        buildings = parser.parse_buildings(result)
        assert buildings[0]["material"] == "brick"
        assert buildings[0]["roof_shape"] == "gabled"
        assert buildings[0]["colour"] == "red"


# ---------------------------------------------------------------
# Building conversion
# ---------------------------------------------------------------

class TestConvertBuildings:
    def test_converts_building(self, tmp_path):
        converter = CS2Converter(bbox=MONACO_BBOX, output_dir=str(tmp_path))
        buildings = [{
            "id": 600, "type": "apartments", "zone": "residential",
            "density": "high", "cs2_subtype": "HighDensityApartment",
            "name": "Test", "height": 15.0, "levels": 5,
            "material": "concrete", "roof_shape": "flat", "colour": "",
            "coordinates": [
                (7.42, 43.73), (7.43, 43.73),
                (7.43, 43.74), (7.42, 43.74),
                (7.42, 43.73),
            ],
            "geometry": None,
        }]
        cs2 = converter.convert_buildings(buildings)
        assert len(cs2) == 1
        assert cs2[0]["zone"] == "ResidentialZone"
        assert cs2[0]["density"] == "high"
        assert cs2[0]["cs2_subtype"] == "HighDensityApartment"
        assert cs2[0]["height"] == 15.0
        assert cs2[0]["material"] == "concrete"

    def test_height_estimated_from_levels(self, tmp_path):
        converter = CS2Converter(bbox=MONACO_BBOX, output_dir=str(tmp_path))
        buildings = [{
            "id": 601, "type": "yes", "zone": "residential",
            "density": "medium", "cs2_subtype": "MediumDensityResidential",
            "name": "", "height": None, "levels": 4,
            "material": "", "roof_shape": "", "colour": "",
            "coordinates": [
                (7.42, 43.73), (7.43, 43.73),
                (7.43, 43.74), (7.42, 43.74),
                (7.42, 43.73),
            ],
            "geometry": None,
        }]
        cs2 = converter.convert_buildings(buildings)
        assert cs2[0]["height"] == 12.0  # 4 levels * 3m


# ---------------------------------------------------------------
# Improved chunking (bbox-based assignment)
# ---------------------------------------------------------------

class TestImprovedChunking:
    def test_long_road_in_multiple_chunks(self, tmp_path):
        converter = CS2Converter(bbox=MONACO_BBOX, output_dir=str(tmp_path))
        data = {
            "roads": [{
                "id": "road_long", "type": "Highway", "name": "Long Hwy",
                "points": [
                    {"x": -20000, "y": 0, "z": 0},
                    {"x": 20000, "y": 0, "z": 0},
                ],
                "lanes": 4, "oneWay": True, "speedLimit": 120, "priority": 5,
            }],
            "railways": [],
            "waterways": [],
            "buildings": [],
            "transit": {"stops": [], "routes": []},
        }
        chunks = converter.create_chunks(data, chunk_size_m=5000)
        # Road spans 40km, with 5km chunks it should appear in multiple
        road_chunks = [c for c in chunks if c["roads"]]
        assert len(road_chunks) >= 2

    def test_buildings_in_chunks(self, tmp_path):
        converter = CS2Converter(bbox=MONACO_BBOX, output_dir=str(tmp_path))
        data = {
            "roads": [],
            "railways": [],
            "waterways": [],
            "buildings": [{
                "id": "bldg_1", "type": "apartments", "zone": "ResidentialZone",
                "name": "Test", "height": 15, "levels": 5,
                "points": [
                    {"x": 100, "y": 0, "z": 100},
                    {"x": 200, "y": 0, "z": 100},
                    {"x": 200, "y": 0, "z": 200},
                    {"x": 100, "y": 0, "z": 200},
                    {"x": 100, "y": 0, "z": 100},
                ],
            }],
            "transit": {"stops": [], "routes": []},
        }
        chunks = converter.create_chunks(data, chunk_size_m=5000)
        bldg_chunks = [c for c in chunks if c["buildings"]]
        assert len(bldg_chunks) >= 1
