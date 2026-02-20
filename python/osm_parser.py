"""
OSM Data Parser
Parses raw OSM data into structured format for CS2 conversion.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

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
            coords    = self._safe_way_coords(way)

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
                "geometry":    LineString(self._dedup_coords(coords)),
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
            coords       = self._safe_way_coords(way)

            if len(coords) < 2:
                continue

            railways.append({
                "id":          way.id,
                "type":        railway_type,
                "name":        way.tags.get("name", ""),
                "gauge":       way.tags.get("gauge", ""),
                "electrified": way.tags.get("electrified", ""),
                "coordinates": coords,
                "geometry":    LineString(self._dedup_coords(coords)),
            })

        return railways

    # ------------------------------------------------------------------
    # Underground way detection  (call on the railway OSM result)
    # ------------------------------------------------------------------

    def get_underground_way_ids(self, railway_result: overpy.Result) -> set:
        """
        Return the set of OSM way IDs that run underground / in tunnel.

        Detection criteria (any one suffices):
          - tunnel=yes
          - location=underground
          - layer < 0
          - covered=yes
        """
        underground = set()
        for way in railway_result.ways:
            tags  = way.tags
            layer = 0
            try:
                layer = int(tags.get("layer", "0") or "0")
            except ValueError:
                pass

            if (
                tags.get("tunnel") == "yes"
                or tags.get("location") == "underground"
                or layer < 0
                or tags.get("covered") == "yes"
            ):
                underground.add(way.id)
        return underground

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
            coords = self._safe_way_coords(way)

            if len(coords) < 2:
                continue

            ww_type, is_area = self._classify_waterway(tags)
            if ww_type is None:
                continue

            is_closed = len(coords) >= 4 and coords[0] == coords[-1]
            if is_area and not is_closed:
                continue

            width = self._parse_width(tags)
            deduped = self._dedup_coords(coords)

            entry: Dict[str, Any] = {
                "id":          way.id,
                "type":        ww_type,
                "name":        tags.get("name", ""),
                "is_area":     is_area and is_closed,
                "coordinates": coords,
                "width":       width,
            }

            if is_area and is_closed and len(deduped) >= 3:
                entry["geometry"] = Polygon(deduped)
            elif len(deduped) >= 2:
                entry["geometry"] = LineString(deduped)
            else:
                continue

            waterways.append(entry)

        return waterways

    # ------------------------------------------------------------------
    # Transit
    # ------------------------------------------------------------------

    # Node roles used for stop positions in route relations.
    # Includes old-style empty role and directional variants.
    _STOP_ROLES = frozenset({
        "stop",
        "stop_entry_only",
        "stop_exit_only",
        "forward:stop",
        "backward:stop",
        "platform",          # PT v2 — sometimes used for boarding nodes
        "",                  # old-style routes
    })

    def parse_transit_routes(
        self,
        osm_result: overpy.Result,
        underground_way_ids: set = None,
        bbox: tuple = None,
    ) -> Dict[str, Any]:
        """
        Parse public transport routes and stops.

        Args:
            osm_result:          Result of the transit Overpass query.
            underground_way_ids: Way IDs known to be tunnelled/underground
                                 (from get_underground_way_ids on railway result).
            bbox:                (south, west, north, east) for external stop detection.

        Underground tram lines are dropped entirely.
        Stops outside the bbox are kept as external connection markers.
        """
        if underground_way_ids is None:
            underground_way_ids = set()

        # ------------------------------------------------------------------
        # Build a coordinate index for ALL nodes in the result.
        # This covers both fully-tagged in-bbox nodes AND skel-only route
        # member nodes (e.g. external stops).
        # ------------------------------------------------------------------
        all_node_latlons: Dict[int, Tuple[float, float]] = {}
        for node in osm_result.nodes:
            try:
                all_node_latlons[node.id] = (float(node.lat), float(node.lon))
            except (TypeError, ValueError):
                pass

        # ------------------------------------------------------------------
        # Collect tagged stop nodes (in-bbox, full details)
        # ------------------------------------------------------------------
        STOP_KEYS = {"railway", "public_transport", "highway"}

        raw_stops: Dict[int, Dict[str, Any]] = {}
        for node in osm_result.nodes:
            if not any(k in node.tags for k in STOP_KEYS):
                continue
            stop_type = self._determine_stop_type(node.tags)
            if stop_type == "unknown":
                continue
            if node.id not in all_node_latlons:
                continue

            lat, lon = all_node_latlons[node.id]
            is_ug    = self._node_is_underground(node.tags)
            is_ext   = self._node_is_external(lat, lon, bbox)

            raw_stops[node.id] = {
                "id":            node.id,
                "name":          node.tags.get("name", ""),
                "type":          stop_type,
                "coordinates":   (lon, lat),
                "geometry":      Point(lon, lat),
                "is_underground":is_ug,
                "is_external":   is_ext,
                "has_shelter":   node.tags.get("shelter") == "yes",
                "has_bench":     node.tags.get("bench") == "yes",
                "wheelchair":    node.tags.get("wheelchair", "unknown"),
            }

        # ------------------------------------------------------------------
        # Parse route relations
        # ------------------------------------------------------------------
        routes: List[Dict[str, Any]] = []
        # Tracks which stop IDs are actually used by an accepted route,
        # and what type to assign them if we need to synthesise external entries.
        used_stop_type: Dict[int, str] = {}

        for relation in osm_result.relations:
            if relation.tags.get("type") != "route":
                continue

            route_type = relation.tags.get("route", "")
            members    = self._parse_route_members(relation)

            stop_members = [
                m for m in members
                if m["type"] == "node" and m["role"] in self._STOP_ROLES
            ]
            way_members = [m for m in members if m["type"] == "way"]

            # Only keep stops for which we have coordinates
            route_stop_ids = [
                m["ref"] for m in stop_members
                if m["ref"] in all_node_latlons
            ]
            route_way_ids = [m["ref"] for m in way_members]

            if not route_stop_ids:
                continue  # no usable stops → skip

            # ------ Underground tram filtering ----------------------------
            if route_type == "tram":
                has_tunnel_way = any(wid in underground_way_ids for wid in route_way_ids)
                has_ug_stop    = any(
                    raw_stops.get(sid, {}).get("is_underground", False)
                    for sid in route_stop_ids
                )
                if has_tunnel_way or has_ug_stop:
                    continue  # drop entire tram line

            # ------ Intercity detection -----------------------------------
            has_external = any(
                raw_stops.get(sid, {}).get("is_external", False)
                or sid not in raw_stops
                for sid in route_stop_ids
            )

            fare = self._parse_osm_fare(relation.tags)

            routes.append({
                "id":           relation.id,
                "name":         relation.tags.get("name", ""),
                "ref":          relation.tags.get("ref", ""),
                "route_type":   route_type,
                "operator":     relation.tags.get("operator", ""),
                "colour":       relation.tags.get("colour", ""),
                "network":      relation.tags.get("network", ""),
                "from":         relation.tags.get("from", ""),
                "to":           relation.tags.get("to", ""),
                "is_intercity": has_external,
                "members":      members,
                "stop_ids":     route_stop_ids,
                "way_ids":      route_way_ids,
                "fare":         fare,
            })

            for sid in route_stop_ids:
                if sid not in used_stop_type:
                    used_stop_type[sid] = route_type

        # ------------------------------------------------------------------
        # Synthesise minimal entries for stops referenced by accepted routes
        # but absent from raw_stops (i.e. external stops with skel-only data).
        # ------------------------------------------------------------------
        for sid, inferred_type in used_stop_type.items():
            if sid in raw_stops:
                continue
            if sid not in all_node_latlons:
                continue
            lat, lon = all_node_latlons[sid]
            is_ext   = self._node_is_external(lat, lon, bbox)
            raw_stops[sid] = {
                "id":            sid,
                "name":          "",
                "type":          inferred_type,
                "coordinates":   (lon, lat),
                "geometry":      Point(lon, lat),
                "is_underground":False,
                "is_external":   is_ext,
                "has_shelter":   False,
                "has_bench":     False,
                "wheelchair":    "unknown",
            }

        # Only emit stops actually used by an accepted route
        used_ids = set(used_stop_type.keys())
        stops    = [s for sid, s in raw_stops.items() if sid in used_ids]

        return {"stops": stops, "routes": routes}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_way_coords(way: overpy.Way) -> List[Tuple[float, float]]:
        """
        Extract (lon, lat) pairs from a way's nodes.
        Silently skips nodes whose coordinates are not resolved (lat/lon = None).
        This handles ways that straddle the query bbox edge.
        """
        coords = []
        for node in way.nodes:
            try:
                coords.append((float(node.lon), float(node.lat)))
            except (TypeError, ValueError):
                pass
        return coords

    @staticmethod
    def _dedup_coords(
        coords: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """
        Remove consecutive duplicate coordinate pairs.
        Prevents Shapely from creating degenerate/invalid geometries.
        """
        if not coords:
            return coords
        deduped = [coords[0]]
        for pt in coords[1:]:
            if pt != deduped[-1]:
                deduped.append(pt)
        return deduped

    def _node_is_underground(self, tags: dict) -> bool:
        layer = 0
        try:
            layer = int(tags.get("layer", "0") or "0")
        except ValueError:
            pass
        return (
            tags.get("location") == "underground"
            or tags.get("tunnel") == "yes"
            or layer < 0
        )

    def _node_is_external(self, lat: float, lon: float, bbox: tuple) -> bool:
        if bbox is None:
            return False
        south, west, north, east = bbox
        return lat < south or lat > north or lon < west or lon > east

    def _parse_osm_fare(self, tags: dict) -> Optional[Dict]:
        """
        Extract fare data from OSM charge= / fare= tags.
        Handles currency symbols attached to numbers (€1.50, £2, CHF 2.00).
        Returns None if no usable fare found (caller uses defaults).
        """
        charge = tags.get("charge") or tags.get("fare")
        if not charge or charge in ("yes", "no", ""):
            return None
        try:
            parts    = str(charge).strip().split()
            amount   = None
            currency = None

            for part in parts:
                # Strip everything except digits and decimal separators
                numeric = re.sub(r"[^\d.,]", "", part).replace(",", ".")
                # Extract any ASCII letters that look like a currency code
                alpha   = re.sub(r"[^A-Za-z]", "", part).upper()
                # Check for non-ASCII currency symbols (£, €, ¥ …)
                sym_currency = self._extract_currency_symbol(part)

                if numeric and amount is None:
                    amount = float(numeric)
                    # Currency symbol may be embedded in the same token
                    if sym_currency and currency is None:
                        currency = sym_currency
                    elif alpha and currency is None:
                        currency = self._symbol_to_currency(alpha)
                elif sym_currency and currency is None:
                    currency = sym_currency  # standalone £, €, …
                elif alpha and 2 <= len(alpha) <= 3 and currency is None:
                    currency = alpha  # standalone "EUR", "GBP", "USD", …

            if amount is None:
                return None
            return {
                "base_fare": round(amount, 2),
                "currency":  currency or "EUR",
                "source":    "osm",
            }
        except Exception:
            return None

    # Maps non-ASCII currency symbols AND 3-letter ISO codes to their ISO code
    _CURRENCY_SYMBOLS: Dict[str, str] = {
        "€": "EUR", "£": "GBP", "$": "USD", "¥": "JPY", "¥": "CNY",
        "CHF": "CHF", "NOK": "NOK", "SEK": "SEK", "DKK": "DKK",
        "CZK": "CZK", "PLN": "PLN", "HUF": "HUF", "RON": "RON",
        "RUB": "RUB", "JPY": "JPY", "CNY": "CNY", "AUD": "AUD",
        "CAD": "CAD", "NZD": "NZD", "SGD": "SGD", "HKD": "HKD",
    }
    # Non-ASCII symbol characters that indicate a currency
    _SYMBOL_CHARS = frozenset("€£$¥₩₽₹₺₪฿")

    def _symbol_to_currency(self, sym: str) -> str:
        return self._CURRENCY_SYMBOLS.get(sym, sym[:3] if len(sym) <= 3 else "EUR")

    def _extract_currency_symbol(self, token: str) -> Optional[str]:
        """Check if a token contains a non-ASCII currency symbol (£, €, ¥ …)."""
        for ch in token:
            if ch in self._SYMBOL_CHARS:
                return self._CURRENCY_SYMBOLS.get(ch, "EUR")
        return None

    def _classify_waterway(self, tags: dict):
        ww = tags.get("waterway")
        if ww in ("river", "stream", "canal", "drain", "ditch"):
            return ww, False
        if tags.get("natural") == "coastline":
            return "coastline", False
        if tags.get("natural") == "water":
            return tags.get("water", "water"), True
        if tags.get("landuse") == "reservoir":
            return "reservoir", True
        return None, False

    def _parse_lanes(self, tags: dict) -> int:
        raw = tags.get("lanes", "2")
        try:
            # Handle "2;3" or "2+1" — take the first number
            return int(re.split(r"[^0-9]", str(raw))[0])
        except (ValueError, IndexError):
            return 2

    def _parse_width(self, tags: dict) -> Optional[float]:
        raw = tags.get("width") or tags.get("est_width")
        if raw is None:
            return None
        try:
            return float(re.sub(r"[^\d.,]", "", str(raw)).replace(",", ".") or "0") or None
        except ValueError:
            return None

    def _determine_stop_type(self, tags: dict) -> str:
        if tags.get("railway") == "tram_stop":
            return "tram"
        if tags.get("railway") in ("station", "halt", "stop"):
            return "train"
        if tags.get("highway") == "bus_stop":
            return "bus"
        if tags.get("bus") == "yes":
            return "bus"
        if tags.get("tram") == "yes":
            return "tram"
        if tags.get("train") == "yes":
            return "train"
        if tags.get("subway") == "yes":
            return "subway"
        if "public_transport" in tags:
            return "stop"
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
