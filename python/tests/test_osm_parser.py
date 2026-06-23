"""Tests for OSMParser — road, railway, waterway, and transit parsing."""

import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from osm_parser import OSMParser


# ---------------------------------------------------------------
# Helpers to build mock overpy objects
# ---------------------------------------------------------------

def _mock_node(node_id: int, lat: float, lon: float, tags: dict = None):
    node = MagicMock()
    node.id = node_id
    node.lat = lat
    node.lon = lon
    node.tags = tags or {}
    return node


def _mock_way(way_id: int, nodes: list, tags: dict):
    way = MagicMock()
    way.id = way_id
    way.tags = tags
    way.nodes = nodes
    return way


def _mock_result(ways=None, nodes=None, relations=None):
    result = MagicMock()
    result.ways = ways or []
    result.nodes = nodes or []
    result.relations = relations or []
    return result


def _make_way_nodes(coords: List[tuple]) -> list:
    """Create mock node objects from a list of (lon, lat) tuples."""
    return [_mock_node(i, lat, lon) for i, (lon, lat) in enumerate(coords)]


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------

@pytest.fixture
def parser():
    return OSMParser()


# ---------------------------------------------------------------
# parse_roads
# ---------------------------------------------------------------

class TestParseRoads:
    def test_basic_road(self, parser):
        nodes = _make_way_nodes([(7.4, 43.7), (7.41, 43.71)])
        way = _mock_way(100, nodes, {"highway": "primary", "name": "Avenue X", "lanes": "3"})
        result = _mock_result(ways=[way])

        roads = parser.parse_roads(result)
        assert len(roads) == 1
        r = roads[0]
        assert r["id"] == 100
        assert r["type"] == "primary"
        assert r["priority"] == 3
        assert r["name"] == "Avenue X"
        assert r["lanes"] == 3
        assert len(r["coordinates"]) == 2

    def test_skips_single_node_way(self, parser):
        nodes = _make_way_nodes([(7.4, 43.7)])
        way = _mock_way(101, nodes, {"highway": "residential"})
        result = _mock_result(ways=[way])

        roads = parser.parse_roads(result)
        assert len(roads) == 0

    def test_oneway(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(102, nodes, {"highway": "motorway", "oneway": "yes"})
        result = _mock_result(ways=[way])

        roads = parser.parse_roads(result)
        assert roads[0]["oneway"] is True

    def test_default_lanes(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(103, nodes, {"highway": "residential"})
        result = _mock_result(ways=[way])

        roads = parser.parse_roads(result)
        assert roads[0]["lanes"] == 2  # default

    def test_compound_lanes(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(104, nodes, {"highway": "primary", "lanes": "2;3"})
        result = _mock_result(ways=[way])

        roads = parser.parse_roads(result)
        assert roads[0]["lanes"] == 2  # takes first number

    def test_captures_ref(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(105, nodes, {"highway": "motorway", "ref": "A12"})
        result = _mock_result(ways=[way])

        assert parser.parse_roads(result)[0]["ref"] == "A12"

    def test_width_from_explicit_tag(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(106, nodes, {"highway": "primary", "width": "18 m"})
        result = _mock_result(ways=[way])

        assert parser.parse_roads(result)[0]["width_m"] == 18.0

    def test_width_estimated_from_lanes(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(107, nodes, {"highway": "residential", "lanes": "2"})
        result = _mock_result(ways=[way])

        # 2 lanes × 3.0 m residential, no shoulder
        assert parser.parse_roads(result)[0]["width_m"] == 6.0

    def test_motorway_width_includes_shoulders(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(108, nodes, {"highway": "motorway", "lanes": "3"})
        result = _mock_result(ways=[way])

        # 3 × 3.66 + 6 m shoulders = 16.98, rounded to 1 dp
        assert parser.parse_roads(result)[0]["width_m"] == 17.0

    def test_service_alley(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(109, nodes, {"highway": "service", "service": "alley"})
        result = _mock_result(ways=[way])

        assert parser.parse_roads(result)[0]["type"] == "alley"


class TestNameTypeHints:
    def test_dutch_footpath(self, parser):
        # "voetweg" literally = footpath; untagged way falls back to the name.
        assert parser.infer_type_from_name("Oude Voetweg") == "footway"

    def test_alley_token(self, parser):
        assert parser.infer_type_from_name("Lange Steeg") == "alley"

    def test_street_token(self, parser):
        assert parser.infer_type_from_name("Kerkstraat") == "residential"

    def test_no_hint(self, parser):
        assert parser.infer_type_from_name("Grand Place") is None

    def test_name_fills_missing_tag(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(110, nodes, {"name": "Smalle Voetweg"})  # no highway tag
        result = _mock_result(ways=[way])

        assert parser.parse_roads(result)[0]["type"] == "footway"

    def test_name_does_not_override_explicit_tag(self, parser):
        # A primary road named "...straat" stays primary, not residential.
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(111, nodes, {"highway": "primary", "name": "Grote Straat"})
        result = _mock_result(ways=[way])

        assert parser.parse_roads(result)[0]["type"] == "primary"


# ---------------------------------------------------------------
# parse_railways
# ---------------------------------------------------------------

class TestParseRailways:
    def test_basic_railway(self, parser):
        nodes = _make_way_nodes([(7.4, 43.7), (7.41, 43.71), (7.42, 43.72)])
        way = _mock_way(200, nodes, {"railway": "rail", "name": "Main Line"})
        result = _mock_result(ways=[way])

        railways = parser.parse_railways(result)
        assert len(railways) == 1
        assert railways[0]["type"] == "rail"
        assert railways[0]["name"] == "Main Line"

    def test_tram(self, parser):
        nodes = _make_way_nodes([(0.0, 0.0), (1.0, 1.0)])
        way = _mock_way(201, nodes, {"railway": "tram"})
        result = _mock_result(ways=[way])

        railways = parser.parse_railways(result)
        assert railways[0]["type"] == "tram"

    def test_railway_underground_flag(self, parser):
        nodes = _make_way_nodes([(7.4, 43.7), (7.41, 43.71)])
        ug = _mock_way(202, nodes, {"railway": "subway", "tunnel": "yes"})
        surface = _mock_way(203, nodes, {"railway": "subway"})
        result = _mock_result(ways=[ug, surface])

        railways = parser.parse_railways(result)
        by_id = {r["id"]: r for r in railways}
        assert by_id[202]["is_underground"] is True
        assert by_id[203]["is_underground"] is False

    def test_commuter_rail_detection(self, parser):
        assert parser._is_commuter_rail({"network": "S-Bahn Berlin"}) is True
        assert parser._is_commuter_rail({"name": "RER A"}) is True
        assert parser._is_commuter_rail({"network": "Cercanías Madrid"}) is True
        assert parser._is_commuter_rail({"name": "Rodalies"}) is True
        # A real metro must NOT be flagged as commuter.
        assert parser._is_commuter_rail({"network": "U-Bahn", "name": "U6"}) is False
        assert parser._is_commuter_rail({"name": "Line 1"}) is False

    def test_commuter_flag_on_parsed_railway(self, parser):
        nodes = _make_way_nodes([(7.4, 43.7), (7.41, 43.71)])
        way = _mock_way(204, nodes, {"railway": "subway", "network": "S-Bahn"})
        railways = parser.parse_railways(_mock_result(ways=[way]))
        assert railways[0]["is_commuter"] is True


# ---------------------------------------------------------------
# get_underground_way_ids
# ---------------------------------------------------------------

class TestUndergroundDetection:
    def test_tunnel_yes(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1)])
        way = _mock_way(300, nodes, {"railway": "tram", "tunnel": "yes"})
        result = _mock_result(ways=[way])

        ids = parser.get_underground_way_ids(result)
        assert 300 in ids

    def test_negative_layer(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1)])
        way = _mock_way(301, nodes, {"railway": "subway", "layer": "-1"})
        result = _mock_result(ways=[way])

        ids = parser.get_underground_way_ids(result)
        assert 301 in ids

    def test_surface_way_not_underground(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1)])
        way = _mock_way(302, nodes, {"railway": "rail"})
        result = _mock_result(ways=[way])

        ids = parser.get_underground_way_ids(result)
        assert len(ids) == 0

    def test_covered_yes(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1)])
        way = _mock_way(303, nodes, {"railway": "tram", "covered": "yes"})
        result = _mock_result(ways=[way])

        ids = parser.get_underground_way_ids(result)
        assert 303 in ids


# ---------------------------------------------------------------
# parse_waterways
# ---------------------------------------------------------------

class TestParseWaterways:
    def test_river(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1), (2, 2)])
        way = _mock_way(400, nodes, {"waterway": "river", "name": "Rhine"})
        result = _mock_result(ways=[way])

        wws = parser.parse_waterways(result)
        assert len(wws) == 1
        assert wws[0]["type"] == "river"
        assert wws[0]["is_area"] is False

    def test_lake(self, parser):
        # Closed polygon (first == last)
        coords = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
        nodes = _make_way_nodes(coords)
        way = _mock_way(401, nodes, {"natural": "water", "water": "lake"})
        result = _mock_result(ways=[way])

        wws = parser.parse_waterways(result)
        assert len(wws) == 1
        assert wws[0]["type"] == "lake"
        assert wws[0]["is_area"] is True

    def test_unclosed_area_skipped(self, parser):
        # Area type but not closed → should be skipped
        coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
        nodes = _make_way_nodes(coords)
        way = _mock_way(402, nodes, {"natural": "water"})
        result = _mock_result(ways=[way])

        wws = parser.parse_waterways(result)
        assert len(wws) == 0

    def test_width_parsing(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1)])
        way = _mock_way(403, nodes, {"waterway": "canal", "width": "15.5 m"})
        result = _mock_result(ways=[way])

        wws = parser.parse_waterways(result)
        assert wws[0]["width"] == pytest.approx(15.5)

    def test_coastline(self, parser):
        nodes = _make_way_nodes([(0, 0), (1, 1)])
        way = _mock_way(404, nodes, {"natural": "coastline"})
        result = _mock_result(ways=[way])

        wws = parser.parse_waterways(result)
        assert wws[0]["type"] == "coastline"


# ---------------------------------------------------------------
# parse_transit_routes
# ---------------------------------------------------------------

class TestParseTransit:
    def _make_transit_result(self, stops, relations):
        """Build a mock overpy result with stops and route relations."""
        return _mock_result(nodes=stops, relations=relations)

    def _make_relation(self, rel_id, tags, members):
        rel = MagicMock()
        rel.id = rel_id
        rel.tags = tags
        rel.members = members
        return rel

    def _make_rel_node_member(self, ref, role="stop"):
        import overpy
        m = MagicMock(spec=overpy.RelationNode)
        m.ref = ref
        m.role = role
        return m

    def _make_rel_way_member(self, ref, role=""):
        import overpy
        m = MagicMock(spec=overpy.RelationWay)
        m.ref = ref
        m.role = role
        return m

    def test_basic_bus_route(self, parser):
        stop1 = _mock_node(1, 43.7, 7.4, {"highway": "bus_stop", "name": "Stop A"})
        stop2 = _mock_node(2, 43.71, 7.41, {"highway": "bus_stop", "name": "Stop B"})

        members = [
            self._make_rel_node_member(1, "stop"),
            self._make_rel_node_member(2, "stop"),
            self._make_rel_way_member(99),
        ]
        rel = self._make_relation(500, {
            "type": "route", "route": "bus", "name": "Line 1", "ref": "1"
        }, members)

        result = self._make_transit_result([stop1, stop2], [rel])
        transit = parser.parse_transit_routes(result)

        assert len(transit["stops"]) == 2
        assert len(transit["routes"]) == 1
        assert transit["routes"][0]["route_type"] == "bus"
        assert transit["routes"][0]["name"] == "Line 1"

    def test_underground_tram_filtered(self, parser):
        stop = _mock_node(10, 43.7, 7.4, {"railway": "tram_stop", "name": "UG Stop"})
        members = [
            self._make_rel_node_member(10, "stop"),
            self._make_rel_way_member(50),
        ]
        rel = self._make_relation(600, {
            "type": "route", "route": "tram", "name": "Tram 1"
        }, members)

        result = self._make_transit_result([stop], [rel])
        underground_ids = {50}  # way 50 is underground

        transit = parser.parse_transit_routes(result, underground_way_ids=underground_ids)
        assert len(transit["routes"]) == 0  # filtered out

    def test_external_stop_detection(self, parser):
        # Stop outside bbox
        stop = _mock_node(20, 44.0, 8.0, {"highway": "bus_stop", "name": "Far Stop"})
        members = [self._make_rel_node_member(20, "stop")]
        rel = self._make_relation(700, {
            "type": "route", "route": "bus", "name": "Intercity"
        }, members)

        bbox = (43.7, 7.4, 43.75, 7.45)
        result = self._make_transit_result([stop], [rel])

        transit = parser.parse_transit_routes(result, bbox=bbox)
        assert len(transit["routes"]) == 1
        assert transit["routes"][0]["is_intercity"] is True

    def test_no_stops_route_skipped(self, parser):
        members = [self._make_rel_way_member(99)]
        rel = self._make_relation(800, {
            "type": "route", "route": "bus", "name": "Empty"
        }, members)

        result = self._make_transit_result([], [rel])
        transit = parser.parse_transit_routes(result)
        assert len(transit["routes"]) == 0


# ---------------------------------------------------------------
# _determine_stop_type
# ---------------------------------------------------------------

class TestDetermineStopType:
    def test_tram_stop(self, parser):
        assert parser._determine_stop_type({"railway": "tram_stop"}) == "tram"

    def test_bus_stop(self, parser):
        assert parser._determine_stop_type({"highway": "bus_stop"}) == "bus"

    def test_train_station(self, parser):
        assert parser._determine_stop_type({"railway": "station"}) == "train"

    def test_bus_yes(self, parser):
        assert parser._determine_stop_type({"bus": "yes", "public_transport": "stop_position"}) == "bus"

    def test_unknown(self, parser):
        assert parser._determine_stop_type({"building": "yes"}) == "unknown"


# ---------------------------------------------------------------
# _parse_osm_fare
# ---------------------------------------------------------------

class TestParseOsmFare:
    def test_euro_sign(self, parser):
        fare = parser._parse_osm_fare({"charge": "€1.50"})
        assert fare is not None
        assert fare["base_fare"] == 1.5
        assert fare["currency"] == "EUR"

    def test_gbp_code(self, parser):
        fare = parser._parse_osm_fare({"charge": "GBP 2.80"})
        assert fare is not None
        assert fare["base_fare"] == 2.8
        assert fare["currency"] == "GBP"

    def test_no_fare(self, parser):
        assert parser._parse_osm_fare({}) is None
        assert parser._parse_osm_fare({"charge": "yes"}) is None
        assert parser._parse_osm_fare({"charge": ""}) is None

    def test_plain_number(self, parser):
        fare = parser._parse_osm_fare({"fare": "3.50"})
        assert fare is not None
        assert fare["base_fare"] == 3.5


# ---------------------------------------------------------------
# _dedup_coords
# ---------------------------------------------------------------

class TestDedupCoords:
    def test_removes_consecutive_dupes(self, parser):
        coords = [(0, 0), (0, 0), (1, 1), (1, 1), (2, 2)]
        assert parser._dedup_coords(coords) == [(0, 0), (1, 1), (2, 2)]

    def test_keeps_non_consecutive_dupes(self, parser):
        coords = [(0, 0), (1, 1), (0, 0)]
        assert parser._dedup_coords(coords) == [(0, 0), (1, 1), (0, 0)]

    def test_empty(self, parser):
        assert parser._dedup_coords([]) == []
