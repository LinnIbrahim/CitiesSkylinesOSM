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

    def test_unknown_road_type_uses_lane_count(self, converter):
        # No type hint → classification falls back to the lane ladder (1 → Tiny).
        roads = [{
            "id": 3, "type": "unknown_type", "name": "",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "lanes": 1, "oneway": False, "maxspeed": "",
            "priority": 0, "geometry": None,
        }]
        cs2_roads = converter.convert_roads(roads)
        assert cs2_roads[0]["type"] == "TinyRoad"


def _road(road_type, lanes, **extra):
    base = {
        "id": 99, "type": road_type, "name": "", "lanes": lanes,
        "coordinates": [(7.42, 43.73), (7.43, 43.74)],
        "oneway": False, "maxspeed": "", "priority": 0, "geometry": None,
    }
    base.update(extra)
    return base


class TestClassifyRoad:
    def test_pedestrian_routes_to_pathway(self, converter):
        out = converter.classify_road(_road("footway", 1))
        assert out["type"] == "Pathway"
        assert out["category"] == "pedestrian"

    def test_alley(self, converter):
        assert converter.classify_road(_road("alley", 1))["type"] == "Alley"

    def test_surface_lane_ladder(self, converter):
        assert converter.classify_road(_road("residential", 2))["type"] == "SmallRoad"
        assert converter.classify_road(_road("secondary", 4))["type"] == "MediumRoad"
        assert converter.classify_road(_road("secondary", 5))["type"] == "LargeRoad"

    def test_clamp_above_five_lanes(self, converter):
        out = converter.classify_road(_road("primary", 8))
        assert out["type"] == "LargeRoad"
        assert out["lanes"] == 5
        assert out["clamped"] is True
        assert out["original_lanes"] == 8

    def test_texas_freeway_clamps(self, converter):
        # I-10 Katy Freeway scale: 12 mainlanes → clamp to Highway, flagged.
        out = converter.classify_road(_road("motorway", 12))
        assert out["type"] == "Highway"
        assert out["lanes"] == 5
        assert out["clamped"] is True
        assert out["original_lanes"] == 12

    def test_class_hint_beats_narrow_lane_count(self, converter):
        # A primary tagged with only 1 lane should not collapse to TinyRoad.
        assert converter.classify_road(_road("primary", 1))["type"] == "LargeRoad"

    def test_ref_and_colour_emitted(self, converter):
        out = converter.convert_roads([_road("motorway", 3, ref="A12")])
        assert out[0]["ref"] == "A12"
        assert out[0]["ref_colour"] == "#0B5FA5"

    def test_clamped_flag_in_output(self, converter):
        out = converter.convert_roads([_road("primary", 9)])
        assert out[0]["clamped"] is True
        assert out[0]["original_lanes"] == 9

    def test_surface_roads_carry_utilities(self, converter):
        # Surface roads auto-provide water/sewage/electricity in CS2.
        assert converter.classify_road(_road("residential", 2))["utilities"] is True
        assert converter.classify_road(_road("secondary", 4))["utilities"] is True
        assert converter.classify_road(_road("alley", 1))["utilities"] is True

    def test_highway_and_paths_have_no_utilities(self, converter):
        # Highways and pedestrian paths do not carry utilities.
        assert converter.classify_road(_road("motorway", 3))["utilities"] is False
        assert converter.classify_road(_road("footway", 1))["utilities"] is False

    def test_dedicated_cycleway_is_bikepath(self, converter):
        out = converter.classify_road(_road("cycleway", 1))
        assert out["type"] == "BikePath"
        assert out["category"] == "bike"
        assert out["utilities"] is False

    def test_bike_lane_emitted(self, converter):
        out = converter.convert_roads([_road("secondary", 4, bike_lane="lane")])
        assert out[0]["bike_lane"] == "lane"

    def test_no_bike_lane_field_when_none(self, converter):
        out = converter.convert_roads([_road("secondary", 4, bike_lane="none")])
        assert "bike_lane" not in out[0]

    def test_tram_road_flag(self, converter):
        out = converter.convert_roads([_road("secondary", 4, tram=True)])
        assert out[0]["tram"] is True

    def test_no_tram_field_by_default(self, converter):
        out = converter.convert_roads([_road("secondary", 4)])
        assert "tram" not in out[0]


# ---------------------------------------------------------------
# CS2Converter.convert_railways
# ---------------------------------------------------------------

class TestConvertRailways:
    def test_underground_subway_is_tunnel(self, converter):
        railways = [{
            "id": 10, "type": "subway", "name": "Metro 1",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "electrified": "yes", "is_underground": True, "geometry": None,
        }]
        cs2 = converter.convert_railways(railways)
        assert cs2[0]["type"] == "Subway"
        assert cs2[0]["is_underground"] is True
        assert cs2[0]["depth_m"] == converter.TUNNEL_DEPTH_M
        assert cs2[0]["electrified"] is True

    def test_surface_subway_is_commuter_train(self, converter):
        # A subway running on the surface is treated as commuter rail.
        railways = [{
            "id": 11, "type": "subway", "name": "S-Bahn",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "electrified": "no", "is_underground": False, "geometry": None,
        }]
        cs2 = converter.convert_railways(railways)
        assert cs2[0]["type"] == "Train"
        assert cs2[0]["is_underground"] is False
        assert cs2[0]["depth_m"] == 0.0

    def test_elevated_rail_raises_y(self, converter):
        railways = [{
            "id": 30, "type": "rail", "name": "Viaduct Line",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "electrified": "yes", "is_underground": False,
            "structure": "viaduct", "geometry": None,
        }]
        cs2 = converter.convert_railways(railways)
        assert cs2[0]["structure"] == "viaduct"
        assert cs2[0]["height_m"] == converter.STRUCTURE_HEIGHT_M["viaduct"]
        # The structure offset is baked into every point's y.
        assert all(p["y"] >= converter.STRUCTURE_HEIGHT_M["viaduct"] for p in cs2[0]["points"])

    def test_cutting_lowers_y(self, converter):
        def rail(structure):
            return [{
                "id": 31, "type": "rail", "name": "X",
                "coordinates": [(7.42, 43.73), (7.43, 43.74)],
                "electrified": "no", "is_underground": False,
                "structure": structure, "geometry": None,
            }]
        ground  = converter.convert_railways(rail("ground"))[0]
        cutting = converter.convert_railways(rail("cutting"))[0]
        assert cutting["height_m"] == -4.0
        # Cutting sits 4 m below the same track at ground level.
        assert cutting["points"][0]["y"] == pytest.approx(ground["points"][0]["y"] - 4.0)

    def test_ground_rail_unchanged(self, converter):
        railways = [{
            "id": 32, "type": "rail", "name": "Flat",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "electrified": "no", "is_underground": False,
            "structure": "ground", "geometry": None,
        }]
        cs2 = converter.convert_railways(railways)
        assert cs2[0]["height_m"] == 0.0
        assert cs2[0]["structure"] == "ground"

    def test_rail_and_tram_mapping(self, converter):
        assert converter._map_railway_type("rail") == "Train"
        assert converter._map_railway_type("light_rail") == "Metro"
        assert converter._map_railway_type("tram") == "Tram"
        # Underground flag only changes subways.
        assert converter._map_railway_type("rail", is_underground=True) == "Train"
        assert converter._map_railway_type("subway", is_underground=True) == "Subway"
        assert converter._map_railway_type("subway", is_underground=False) == "Train"

    def test_commuter_subway_is_train_even_underground(self, converter):
        # An underground commuter line (e.g. RER through the centre) → Train.
        assert converter._map_railway_type(
            "subway", is_underground=True, is_commuter=True) == "Train"
        railways = [{
            "id": 12, "type": "subway", "name": "RER A",
            "coordinates": [(7.42, 43.73), (7.43, 43.74)],
            "electrified": "yes", "is_underground": True, "is_commuter": True,
            "geometry": None,
        }]
        cs2 = converter.convert_railways(railways)
        assert cs2[0]["type"] == "Train"
        assert cs2[0]["is_commuter"] is True
        # Still placed in a tunnel since it runs underground.
        assert cs2[0]["is_underground"] is True
        assert cs2[0]["depth_m"] == converter.TUNNEL_DEPTH_M


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
        assert cs2[0]["depth"] == converter.WATERWAY_DEPTH_M["Lake"]

    def test_explicit_width_and_depth(self, converter):
        wws = [{"id": 22, "type": "river", "name": "R", "is_area": False,
                "width": 25.0, "coordinates": [(7.42, 43.73), (7.43, 43.74)],
                "geometry": None}]
        cs2 = converter.convert_waterways(wws)
        assert cs2[0]["width"] == 25.0
        assert cs2[0]["depth"] == converter.WATERWAY_DEPTH_M["River"]

    def test_default_width_when_missing(self, converter):
        wws = [{"id": 23, "type": "canal", "name": "C", "is_area": False,
                "width": None, "coordinates": [(7.42, 43.73), (7.43, 43.74)],
                "geometry": None}]
        cs2 = converter.convert_waterways(wws)
        assert cs2[0]["width"] == converter.WATERWAY_WIDTH_M["Canal"]

    def test_min_width_filters_ditches(self, converter):
        wws = [
            {"id": 24, "type": "ditch", "name": "", "is_area": False,
             "width": None, "coordinates": [(7.42, 43.73), (7.43, 43.74)],
             "geometry": None},                                   # Drain ~1.5 m
            {"id": 25, "type": "river", "name": "", "is_area": False,
             "width": None, "coordinates": [(7.42, 43.73), (7.43, 43.74)],
             "geometry": None},                                   # River ~14 m
        ]
        cs2 = converter.convert_waterways(wws, min_width=2.0)
        types = [w["type"] for w in cs2]
        assert "Drain" not in types and "River" in types

    def test_min_width_keeps_areas(self, converter):
        coords = [(7.42, 43.73), (7.43, 43.73), (7.43, 43.74),
                  (7.42, 43.74), (7.42, 43.73)]
        wws = [{"id": 26, "type": "water", "name": "Lake", "is_area": True,
                "width": None, "coordinates": coords, "geometry": None}]
        # Areas have no width, so the filter must not drop them.
        assert len(converter.convert_waterways(wws, min_width=5.0)) == 1


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

    def test_external_stop_dropped_all_modes(self, converter):
        # Edge stops are not supported for any mode (train included) — dropped.
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
        assert converter.convert_transit(transit)["stops"] == []

    def test_route_with_fare(self, converter):
        transit = {
            "stops": [
                {"id": 10, "name": "A", "type": "bus",
                 "coordinates": (7.42, 43.73), "is_external": False,
                 "is_underground": False, "has_shelter": False,
                 "has_bench": False, "wheelchair": "unknown"},
                {"id": 12, "name": "B", "type": "bus",
                 "coordinates": (7.43, 43.74), "is_external": False,
                 "is_underground": False, "has_shelter": False,
                 "has_bench": False, "wheelchair": "unknown"},
            ],
            "routes": [{
                "id": 100, "name": "Bus 1", "ref": "1",
                "route_type": "bus", "operator": "RATP",
                "colour": "#FF0000", "network": "Nice", "from": "A", "to": "B",
                "is_intercity": False,
                "stop_ids": [10, 12],
                "fare": {"base_fare": 2.50, "currency": "EUR", "source": "osm"},
            }],
        }
        cs2 = converter.convert_transit(transit)
        assert len(cs2["routes"]) == 1
        fare = cs2["routes"][0]["fare"]
        assert fare["base_fare"] == 2.50
        # Amount preserved, but currency normalised to the in-game money; the
        # original real-world currency is kept as provenance.
        assert fare["currency"] == converter.GAME_CURRENCY
        assert fare["source_currency"] == "EUR"

    def test_default_fare_uses_game_currency(self, converter):
        transit = {
            "stops": [
                {"id": 11, "name": "B", "type": "bus",
                 "coordinates": (7.42, 43.73), "is_external": False,
                 "is_underground": False, "has_shelter": False,
                 "has_bench": False, "wheelchair": "unknown"},
                {"id": 13, "name": "C", "type": "bus",
                 "coordinates": (7.43, 43.74), "is_external": False,
                 "is_underground": False, "has_shelter": False,
                 "has_bench": False, "wheelchair": "unknown"},
            ],
            "routes": [{
                "id": 101, "name": "Bus 2", "ref": "2",
                "route_type": "bus", "operator": "", "colour": "",
                "network": "", "from": "", "to": "",
                "is_intercity": False, "stop_ids": [11, 13],
                "fare": None,
            }],
        }
        cs2 = converter.convert_transit(transit)
        fare = cs2["routes"][0]["fare"]
        assert fare["currency"] == converter.GAME_CURRENCY
        # No real-world currency was involved, so no provenance label.
        assert "source_currency" not in fare

    def _bus_stop(self, sid, coords, external=False):
        return {"id": sid, "name": f"S{sid}", "type": "bus",
                "coordinates": coords, "is_external": external,
                "is_underground": False, "has_shelter": False,
                "has_bench": False, "wheelchair": "unknown"}

    def test_external_bus_stop_dropped(self, converter):
        # Edge bus stops are not supported — dropped, not pinned to the edge.
        transit = {
            "stops": [self._bus_stop(2, (100.0, 80.0), external=True)],
            "routes": [],
        }
        assert converter.convert_transit(transit)["stops"] == []

    def test_bus_line_cut_at_edge_loops_back(self, converter):
        # A line with an external endpoint keeps its in-map stops, drops the
        # edge stop, and is flagged loop + cut_at_edge.
        transit = {
            "stops": [
                self._bus_stop(1, (7.42, 43.73)),
                self._bus_stop(2, (7.43, 43.74)),
                self._bus_stop(3, (100.0, 80.0), external=True),  # beyond edge
            ],
            "routes": [{
                "id": 100, "name": "Bus 9", "ref": "9", "route_type": "bus",
                "operator": "", "colour": "", "network": "", "from": "", "to": "",
                "is_intercity": True, "stop_ids": [1, 2, 3], "fare": None,
            }],
        }
        cs2 = converter.convert_transit(transit)
        route = cs2["routes"][0]
        assert route["stops"] == ["stop_1", "stop_2"]   # edge stop dropped
        assert route["loop"] is True
        assert route["cut_at_edge"] is True

    def test_train_line_also_cuts_at_edge(self, converter):
        # The same edge handling applies to rail, not just buses.
        s1 = self._bus_stop(1, (7.42, 43.73)); s1["type"] = "train"
        s2 = self._bus_stop(2, (7.43, 43.74)); s2["type"] = "train"
        s3 = self._bus_stop(3, (100.0, 80.0), external=True); s3["type"] = "train"
        transit = {
            "stops": [s1, s2, s3],
            "routes": [{
                "id": 200, "name": "IC Brussels", "ref": "IC", "route_type": "train",
                "operator": "", "colour": "", "network": "", "from": "", "to": "",
                "is_intercity": True, "stop_ids": [1, 2, 3], "fare": None,
            }],
        }
        cs2 = converter.convert_transit(transit)
        assert cs2["stops"] == [] or all(not s["is_external"] for s in cs2["stops"])
        route = cs2["routes"][0]
        assert route["type"] == "TrainLine"
        assert route["stops"] == ["stop_1", "stop_2"]
        assert route["loop"] is True
        assert route["cut_at_edge"] is True

    def test_bus_line_too_few_stops_dropped(self, converter):
        # Only one in-map stop after dropping the edge stop → not a usable line.
        transit = {
            "stops": [
                self._bus_stop(1, (7.42, 43.73)),
                self._bus_stop(2, (100.0, 80.0), external=True),
            ],
            "routes": [{
                "id": 101, "name": "Bus X", "ref": "X", "route_type": "bus",
                "operator": "", "colour": "", "network": "", "from": "", "to": "",
                "is_intercity": True, "stop_ids": [1, 2], "fare": None,
            }],
        }
        assert converter.convert_transit(transit)["routes"] == []


# ---------------------------------------------------------------
# CS2Converter.convert_districts
# ---------------------------------------------------------------

class TestConvertDistricts:
    def test_in_bounds_district(self, converter):
        places = [{"id": 1, "name": "Centre", "place_type": "town",
                   "population": 5000, "coordinates": (7.42, 43.73)}]
        out = converter.convert_districts(places)
        assert len(out) == 1
        assert out[0]["name"] == "Centre"
        assert out[0]["id"] == "district_1"
        assert out[0]["radius_m"] == converter.PLACE_RADIUS_M["town"]
        assert "x" in out[0]["position"]

    def test_out_of_bounds_dropped(self, converter):
        places = [{"id": 2, "name": "Far", "place_type": "city",
                   "population": 0, "coordinates": (100.0, 80.0)}]
        assert converter.convert_districts(places) == []

    def test_radius_by_type(self, converter):
        places = [{"id": 3, "name": "Hmlt", "place_type": "hamlet",
                   "population": 0, "coordinates": (7.42, 43.73)}]
        assert converter.convert_districts(places)[0]["radius_m"] == \
            converter.PLACE_RADIUS_M["hamlet"]


# ---------------------------------------------------------------
# CS2Converter.find_outside_connections
# ---------------------------------------------------------------

class TestOutsideConnections:
    def _seg(self, edge_pt, interior_pt):
        return [edge_pt, interior_pt]

    def test_highway_at_edge_detected(self, converter):
        half = converter.transformer.CS2_HALF_MAP
        data = {"roads": [{"id": "road_1", "type": "Highway", "name": "E40",
                           "points": self._seg({"x": half, "y": 0, "z": 1000},
                                               {"x": 1000, "y": 0, "z": 1000})}]}
        oc = converter.find_outside_connections(data)
        assert len(oc) == 1
        assert oc[0]["type"] == "Highway"
        assert oc[0]["network"] == "road_1"

    def test_surface_road_at_edge_not_connected(self, converter):
        half = converter.transformer.CS2_HALF_MAP
        data = {"roads": [{"id": "road_2", "type": "SmallRoad", "name": "",
                           "points": self._seg({"x": half, "y": 0, "z": 0},
                                               {"x": 0, "y": 0, "z": 0})}]}
        assert converter.find_outside_connections(data) == []

    def test_interior_highway_ignored(self, converter):
        data = {"roads": [{"id": "road_3", "type": "Highway", "name": "",
                           "points": [{"x": 0, "y": 0, "z": 0},
                                      {"x": 5000, "y": 0, "z": 5000}]}]}
        assert converter.find_outside_connections(data) == []

    def test_surface_train_connects_subway_does_not(self, converter):
        half = converter.transformer.CS2_HALF_MAP
        edge = {"x": -half, "y": 0, "z": 200}
        interior = {"x": -5000, "y": 0, "z": 200}
        data = {"railways": [
            {"id": "rail_1", "type": "Train", "is_underground": False,
             "points": [edge, interior]},
            {"id": "rail_2", "type": "Subway", "is_underground": True,
             "points": [edge, interior]},
        ]}
        oc = converter.find_outside_connections(data)
        assert [c["type"] for c in oc] == ["Train"]
        assert oc[0]["network"] == "rail_1"

    def test_river_makes_ship_connection(self, converter):
        half = converter.transformer.CS2_HALF_MAP
        data = {"waterways": [
            {"id": "water_1", "type": "River", "isArea": False,
             "points": [{"x": 0, "y": 0, "z": half}, {"x": 0, "y": 0, "z": 0}]},
            {"id": "water_2", "type": "Stream", "isArea": False,
             "points": [{"x": 100, "y": 0, "z": half}, {"x": 100, "y": 0, "z": 0}]},
        ]}
        oc = converter.find_outside_connections(data)
        assert [c["type"] for c in oc] == ["Ship"]


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
