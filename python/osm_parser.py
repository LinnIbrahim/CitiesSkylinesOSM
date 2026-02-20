"""
OSM Data Parser
Parses raw OSM data into structured format for CS2 conversion.
"""

from typing import Any, Dict, List

import overpy
from shapely.geometry import LineString, Point, Polygon


class OSMParser:
    """Parses OSM data into structured road, railway, waterway, and transit networks."""

    def __init__(self):
        self.road_hierarchy = {
            "motorway":   5,
            "trunk":      4,
            "primary":    3,
            "secondary":  2,
            "tertiary":   1,
            "residential":0,
            "service":    0,
        }

    # ------------------------------------------------------------------
    # Roads
    # ------------------------------------------------------------------

    def parse_roads(self, osm_result: overpy.Result) -> List[Dict[str, Any]]:
        """Parse road network from an OSM query result."""
        roads = []

        for way in osm_result.ways:
            road_type = way.tags.get("highway", "unknown")
            coords    = [(float(node.lon), float(node.lat)) for node in way.nodes]

            if len(coords) < 2:
                continue

            roads.append({
                "id":          way.id,
                "type":        road_type,
                "priority":    self.road_hierarchy.get(road_type, 0),
                "name":        way.tags.get("name", ""),
                "lanes":       self._parse_lanes(way.tags),
                "oneway":      way.tags.get("oneway") == "yes",
                "maxspeed":    way.tags.get("maxspeed", ""),
                "coordinates": coords,
                "geometry":    LineString(coords),
            })

        return roads

    # ------------------------------------------------------------------
    # Railways
    # ------------------------------------------------------------------

    def parse_railways(self, osm_result: overpy.Result) -> List[Dict[str, Any]]:
        """Parse railway network from an OSM query result."""
        railways = []

        for way in osm_result.ways:
            railway_type = way.tags.get("railway", "unknown")
            coords       = [(float(node.lon), float(node.lat)) for node in way.nodes]

            if len(coords) < 2:
                continue

            railways.append({
                "id":          way.id,
                "type":        railway_type,
                "name":        way.tags.get("name", ""),
                "gauge":       way.tags.get("gauge", ""),
                "electrified": way.tags.get("electrified", ""),
                "coordinates": coords,
                "geometry":    LineString(coords),
            })

        return railways

    # ------------------------------------------------------------------
    # Waterways
    # ------------------------------------------------------------------

    def parse_waterways(self, osm_result: overpy.Result) -> List[Dict[str, Any]]:
        """
        Parse waterway features from an OSM query result.

        Handles:
          - Linear waterways: rivers, streams, canals, drains, coastline
          - Area waterways:   natural=water (lakes, ponds), landuse=reservoir
        """
        waterways = []

        for way in osm_result.ways:
            tags   = way.tags
            coords = [(float(node.lon), float(node.lat)) for node in way.nodes]

            if len(coords) < 2:
                continue

            ww_type, is_area = self._classify_waterway(tags)
            if ww_type is None:
                continue

            # A closed way with 3+ nodes that is tagged as an area
            is_closed = (
                len(coords) >= 4
                and coords[0] == coords[-1]
            )
            if is_area and not is_closed:
                # Unclosed ways tagged as areas are rare but exist — skip them
                continue

            width = self._parse_width(tags)

            entry: Dict[str, Any] = {
                "id":          way.id,
                "type":        ww_type,
                "name":        tags.get("name", ""),
                "is_area":     is_area and is_closed,
                "coordinates": coords,
                "width":       width,
            }

            if is_area and is_closed:
                entry["geometry"] = Polygon(coords)
            else:
                entry["geometry"] = LineString(coords)

            waterways.append(entry)

        return waterways

    # ------------------------------------------------------------------
    # Transit
    # ------------------------------------------------------------------

    def parse_transit_routes(self, osm_result: overpy.Result) -> Dict[str, Any]:
        """Parse public transport routes and stops."""
        stops  = []
        routes = []

        for node in osm_result.nodes:
            if any(k in node.tags for k in ["public_transport", "highway"]):
                stops.append({
                    "id":          node.id,
                    "name":        node.tags.get("name", ""),
                    "type":        self._determine_stop_type(node.tags),
                    "coordinates": (float(node.lon), float(node.lat)),
                    "geometry":    Point(float(node.lon), float(node.lat)),
                })

        for relation in osm_result.relations:
            if relation.tags.get("type") == "route":
                routes.append({
                    "id":         relation.id,
                    "name":       relation.tags.get("name", ""),
                    "ref":        relation.tags.get("ref", ""),
                    "route_type": relation.tags.get("route", ""),
                    "operator":   relation.tags.get("operator", ""),
                    "members":    self._parse_route_members(relation),
                })

        return {"stops": stops, "routes": routes}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_waterway(self, tags: dict):
        """
        Return (waterway_type_str, is_area) or (None, False) if not a
        recognised waterway feature.
        """
        # Linear waterways
        ww = tags.get("waterway")
        if ww in ("river", "stream", "canal", "drain", "ditch"):
            return ww, False
        if tags.get("natural") == "coastline":
            return "coastline", False

        # Area waterways
        if tags.get("natural") == "water":
            # water=lake|pond|reservoir|river — treat all as "water"
            return tags.get("water", "water"), True
        if tags.get("landuse") == "reservoir":
            return "reservoir", True

        return None, False

    def _parse_lanes(self, tags: dict) -> int:
        try:
            return int(tags.get("lanes", "2"))
        except (ValueError, TypeError):
            return 2

    def _parse_width(self, tags: dict):
        """Return width in metres as a float, or None if not specified."""
        raw = tags.get("width") or tags.get("est_width")
        if raw is None:
            return None
        try:
            # Handle "12 m" or "12.5"
            return float(str(raw).split()[0])
        except (ValueError, IndexError):
            return None

    def _determine_stop_type(self, tags: dict) -> str:
        if tags.get("highway") == "bus_stop":
            return "bus"
        if "railway" in tags:
            return "train"
        if "public_transport" in tags:
            return tags.get("public_transport", "stop")
        return "unknown"

    def _parse_route_members(self, relation: overpy.Relation) -> List[Dict]:
        members = []
        for member in relation.members:
            if isinstance(member, overpy.RelationNode):
                m_type = "node"
            elif isinstance(member, overpy.RelationWay):
                m_type = "way"
            else:
                m_type = "relation"

            members.append({
                "type": m_type,
                "ref":  member.ref,
                "role": getattr(member, "role", ""),
            })
        return members
