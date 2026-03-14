"""Tests for preview_server — reverse projection and GeoJSON conversion."""

import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from preview_server import reverse_project, cs2_to_geojson


class TestReverseProject:
    def test_origin_returns_centre(self):
        lat, lon = reverse_project(0, 0, lat_centre=43.7383, lon_centre=7.4245)
        assert lat == pytest.approx(43.7383, abs=1e-5)
        assert lon == pytest.approx(7.4245, abs=1e-5)

    def test_east_positive_x(self):
        lat, lon = reverse_project(1000, 0, lat_centre=43.7383, lon_centre=7.4245)
        assert lon > 7.4245  # east = positive X = larger longitude

    def test_north_negative_z(self):
        lat, lon = reverse_project(0, -1000, lat_centre=43.7383, lon_centre=7.4245)
        assert lat > 43.7383  # north = negative Z = larger latitude

    def test_roundtrip(self):
        """Forward project then reverse should return original coords."""
        lat_c, lon_c = 43.7383, 7.4245
        test_lat, test_lon = 43.74, 7.43

        m_per_lat = 111_320.0
        m_per_lon = 111_320.0 * math.cos(math.radians(lat_c))
        x = (test_lon - lon_c) * m_per_lon
        z = -(test_lat - lat_c) * m_per_lat

        lat_back, lon_back = reverse_project(x, z, lat_c, lon_c)
        assert lat_back == pytest.approx(test_lat, abs=1e-5)
        assert lon_back == pytest.approx(test_lon, abs=1e-5)


class TestCs2ToGeojson:
    def test_basic_conversion(self):
        cs2_data = {
            "roads": [{
                "id": "road_1", "type": "Highway", "name": "Test Hwy",
                "points": [
                    {"x": -100, "y": 0, "z": 0},
                    {"x": 100, "y": 0, "z": 0},
                ],
                "lanes": 4, "oneWay": True, "speedLimit": 130, "priority": 5,
            }],
            "railways": [],
            "waterways": [],
            "buildings": [],
            "transit": {"stops": [], "routes": []},
            "_meta": {
                "city": "Test",
                "coordinate_system": {
                    "centre": {"lat": 43.7383, "lon": 7.4245},
                },
            },
        }
        geojson = cs2_to_geojson(cs2_data)
        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 1

        road = geojson["features"][0]
        assert road["geometry"]["type"] == "LineString"
        assert road["properties"]["layer"] == "roads"
        assert road["properties"]["cs2_type"] == "Highway"
        assert len(road["geometry"]["coordinates"]) == 2

    def test_polygon_waterway(self):
        cs2_data = {
            "roads": [], "railways": [], "buildings": [],
            "waterways": [{
                "id": "water_1", "type": "Lake", "name": "Test Lake",
                "isArea": True,
                "points": [
                    {"x": 0, "y": 0, "z": 0},
                    {"x": 100, "y": 0, "z": 0},
                    {"x": 100, "y": 0, "z": 100},
                    {"x": 0, "y": 0, "z": 100},
                    {"x": 0, "y": 0, "z": 0},
                ],
            }],
            "transit": {"stops": [], "routes": []},
            "_meta": {"coordinate_system": {"centre": {"lat": 0, "lon": 0}}},
        }
        geojson = cs2_to_geojson(cs2_data)
        assert geojson["features"][0]["geometry"]["type"] == "Polygon"

    def test_transit_stop(self):
        cs2_data = {
            "roads": [], "railways": [], "waterways": [], "buildings": [],
            "transit": {
                "stops": [{
                    "id": "stop_1", "name": "Central",
                    "type": "bus",
                    "position": {"x": 50, "y": 0, "z": -30},
                    "is_external": False,
                    "is_underground": False,
                    "has_shelter": True,
                    "wheelchair": "yes",
                }],
                "routes": [{
                    "id": "route_1", "name": "Bus 1", "number": "1",
                    "type": "BusLine", "from": "A", "to": "B",
                    "is_intercity": False, "stops": ["stop_1"],
                    "fare": {"base_fare": 1.50},
                }],
            },
            "_meta": {"coordinate_system": {"centre": {"lat": 43.0, "lon": 7.0}}},
        }
        geojson = cs2_to_geojson(cs2_data)
        stops = [f for f in geojson["features"] if f["properties"]["layer"] == "transit_stops"]
        assert len(stops) == 1
        assert stops[0]["geometry"]["type"] == "Point"
        assert stops[0]["properties"]["stop_type"] == "bus"
        assert len(geojson["_routes"]) == 1

    def test_buildings(self):
        cs2_data = {
            "roads": [], "railways": [], "waterways": [],
            "buildings": [{
                "id": "bldg_1", "name": "Tower", "zone": "ResidentialZone",
                "height": 30, "levels": 10,
                "points": [
                    {"x": 0, "y": 0, "z": 0},
                    {"x": 20, "y": 0, "z": 0},
                    {"x": 20, "y": 0, "z": 20},
                    {"x": 0, "y": 0, "z": 20},
                    {"x": 0, "y": 0, "z": 0},
                ],
            }],
            "transit": {"stops": [], "routes": []},
            "_meta": {"coordinate_system": {"centre": {"lat": 0, "lon": 0}}},
        }
        geojson = cs2_to_geojson(cs2_data)
        bldgs = [f for f in geojson["features"] if f["properties"]["layer"] == "buildings"]
        assert len(bldgs) == 1
        assert bldgs[0]["geometry"]["type"] == "Polygon"
        assert bldgs[0]["properties"]["height"] == 30

    def test_empty_data(self):
        cs2_data = {
            "roads": [], "railways": [], "waterways": [], "buildings": [],
            "transit": {"stops": [], "routes": []},
            "_meta": {"coordinate_system": {"centre": {"lat": 0, "lon": 0}}},
        }
        geojson = cs2_to_geojson(cs2_data)
        assert len(geojson["features"]) == 0
