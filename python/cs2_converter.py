"""
CS2 Converter
Converts parsed OSM data into Cities: Skylines 2 format.

CS2 coordinate system (Unity-based):
  - Origin (0, 0, 0) at map centre
  - X+ = East,  X- = West
  - Y+ = Up (elevation in metres above sea level)
  - Z+ = South, Z- = North  (Unity forward = into screen = South)
  - Map total size: 57,344 m × 57,344 m  →  bounds ±28,672 m
  - 1 unit = 1 metre
"""

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from shapely.geometry import LineString, Point, Polygon, box


# ---------------------------------------------------------------------------
# Coordinate Transformer
# ---------------------------------------------------------------------------

class CoordinateTransformer:
    """
    Projects geographic coordinates (lat/lon) into CS2 game-space.

    A local tangent-plane projection is used:
      dx = (lon − lon_centre) × cos(lat_centre) × 111,320 m/°  →  CS2 X
      dz = (lat − lat_centre) × 111,320 m/°                    →  CS2 Z (negated)

    Accuracy: < 0.1 % error for areas up to ~200 km across — plenty for any
    city that fits inside the CS2 map.
    """

    CS2_MAP_SIZE = 57_344.0        # total map edge in metres
    CS2_HALF_MAP = CS2_MAP_SIZE / 2  # ±28,672 m

    def __init__(self, bbox: Tuple[float, float, float, float]):
        """
        Args:
            bbox: (south, west, north, east) in decimal degrees.
        """
        south, west, north, east = bbox
        self.lat_centre = (south + north) / 2.0
        self.lon_centre = (west  + east)  / 2.0

        # Metres per degree at this latitude
        self.m_per_lat = 111_320.0
        self.m_per_lon = 111_320.0 * math.cos(math.radians(self.lat_centre))

        # City footprint in metres
        self.city_width_m  = (east  - west)  * self.m_per_lon
        self.city_height_m = (north - south) * self.m_per_lat

        self.needs_clipping = (
            self.city_width_m  > self.CS2_MAP_SIZE
            or self.city_height_m > self.CS2_MAP_SIZE
        )

        if self.needs_clipping:
            print(
                f"  City is {self.city_width_m:.0f} m × {self.city_height_m:.0f} m "
                f"— larger than the CS2 map ({self.CS2_MAP_SIZE:.0f} m). "
                "Features outside the map boundary will be clipped."
            )

        # Shapely clip rectangle in CS2 (x, z) space
        self._clip_box = box(
            -self.CS2_HALF_MAP, -self.CS2_HALF_MAP,
             self.CS2_HALF_MAP,  self.CS2_HALF_MAP,
        )

    # ------------------------------------------------------------------
    # Core projection helpers
    # ------------------------------------------------------------------

    def _xz(self, lat: float, lon: float) -> Tuple[float, float]:
        """Lat/lon → (CS2_x, CS2_z). Internal; no rounding."""
        x =  (lon - self.lon_centre) * self.m_per_lon
        z = -(lat - self.lat_centre) * self.m_per_lat  # negate: Z+ = South
        return x, z

    def to_cs2(
        self, lat: float, lon: float, elevation: float = 0.0
    ) -> Dict[str, float]:
        """Convert a single lat/lon/elevation to a CS2 {x, y, z} dict."""
        x, z = self._xz(lat, lon)
        return {"x": round(x, 2), "y": round(elevation, 2), "z": round(z, 2)}

    def in_bounds(self, lat: float, lon: float) -> bool:
        x, z = self._xz(lat, lon)
        return abs(x) <= self.CS2_HALF_MAP and abs(z) <= self.CS2_HALF_MAP

    # ------------------------------------------------------------------
    # Elevation interpolation
    # ------------------------------------------------------------------

    def _interp_elevation(
        self,
        cx: float, cz: float,
        nodes_xze: List[Tuple[float, float, float]],
    ) -> float:
        """
        Inverse-distance weighted elevation for point (cx, cz) from the
        two nearest source nodes.
        """
        if not nodes_xze:
            return 0.0

        distances = [((cx - nx) ** 2 + (cz - nz) ** 2, ne) for nx, nz, ne in nodes_xze]
        distances.sort(key=lambda t: t[0])

        d1, e1 = distances[0]
        if d1 == 0.0:
            return e1
        if len(distances) == 1:
            return e1

        d2, e2 = distances[1]
        w1, w2 = 1.0 / (d1 + 1e-9), 1.0 / (d2 + 1e-9)
        return (w1 * e1 + w2 * e2) / (w1 + w2)

    # ------------------------------------------------------------------
    # Clip + convert lines  (roads, railways, waterway lines)
    # ------------------------------------------------------------------

    def clip_and_convert_line(
        self,
        coords: List[Tuple[float, float]],
        elevations: Dict[Tuple[float, float], float],
    ) -> List[List[Dict[str, float]]]:
        """
        Convert a (lon, lat) coordinate list to CS2 points, clipping to map
        bounds.  A single input segment may be split into multiple output
        segments when it crosses the map boundary more than once.

        Args:
            coords:     [(lon, lat), …] as returned by the OSM parser.
            elevations: {(lat, lon): elevation_metres} lookup table.

        Returns:
            List of segments; each segment is a list of {x, y, z} dicts.
            Returns [] when the geometry is entirely outside the map.
        """
        if len(coords) < 2:
            return []

        # Project every node; skip any with non-finite coordinates
        nodes_xze: List[Tuple[float, float, float]] = []
        for lon, lat in coords:
            try:
                x, z = self._xz(float(lat), float(lon))
            except (TypeError, ValueError):
                continue
            elev = elevations.get((round(lat, 6), round(lon, 6)), 0.0)
            nodes_xze.append((x, z, elev))

        if len(nodes_xze) < 2:
            return []

        # Remove consecutive duplicate (x, z) pairs to avoid degenerate geometries
        deduped = [nodes_xze[0]]
        for pt in nodes_xze[1:]:
            if (pt[0], pt[1]) != (deduped[-1][0], deduped[-1][1]):
                deduped.append(pt)

        if len(deduped) < 2:
            return []

        # Clip the 2-D polyline
        try:
            xz_line = LineString([(x, z) for x, z, _ in deduped])
            clipped  = xz_line.intersection(self._clip_box)
        except Exception:
            return []

        if clipped.is_empty:
            return []

        # Normalise to a list of LineString geometries
        if clipped.geom_type == "MultiLineString":
            geoms = list(clipped.geoms)
        elif clipped.geom_type == "LineString":
            geoms = [clipped]
        elif hasattr(clipped, "geoms"):
            # GeometryCollection — keep only LineString members
            geoms = [g for g in clipped.geoms if g.geom_type == "LineString"]
        else:
            return []

        results = []
        for geom in geoms:
            if geom.is_empty:
                continue
            seg = []
            for cx, cz in geom.coords:
                elev = self._interp_elevation(cx, cz, deduped)
                seg.append({"x": round(cx, 2), "y": round(elev, 2), "z": round(cz, 2)})
            if len(seg) >= 2:
                results.append(seg)

        return results

    # ------------------------------------------------------------------
    # Clip + convert polygons  (lakes, reservoirs, etc.)
    # ------------------------------------------------------------------

    def clip_and_convert_polygon(
        self,
        coords: List[Tuple[float, float]],
        elevations: Dict[Tuple[float, float], float],
    ) -> Optional[List[Dict[str, float]]]:
        """
        Convert and clip a closed polygon (e.g. a lake).

        Returns the exterior ring as CS2 points, or None if entirely outside.
        """
        if len(coords) < 3:
            return None

        nodes_xze: List[Tuple[float, float, float]] = []
        xz_coords: List[Tuple[float, float]] = []
        for lon, lat in coords:
            try:
                x, z = self._xz(float(lat), float(lon))
            except (TypeError, ValueError):
                continue
            elev = elevations.get((round(lat, 6), round(lon, 6)), 0.0)
            nodes_xze.append((x, z, elev))
            xz_coords.append((x, z))

        # Deduplicate consecutive identical points to avoid degenerate polygons
        deduped_xz: List[Tuple[float, float]] = []
        for pt in xz_coords:
            if not deduped_xz or pt != deduped_xz[-1]:
                deduped_xz.append(pt)
        xz_coords = deduped_xz

        if len(xz_coords) < 3:
            return None

        try:
            poly    = Polygon(xz_coords)
            clipped = poly.intersection(self._clip_box)
        except Exception:
            return None

        if clipped.is_empty:
            return None

        # If multi-polygon, keep the largest piece
        if clipped.geom_type == "MultiPolygon":
            clipped = max(clipped.geoms, key=lambda g: g.area)

        if clipped.geom_type != "Polygon":
            return None

        points = []
        for cx, cz in clipped.exterior.coords:
            elev = self._interp_elevation(cx, cz, nodes_xze)
            points.append({"x": round(cx, 2), "y": round(elev, 2), "z": round(cz, 2)})

        return points if len(points) >= 3 else None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "centre":          {"lat": round(self.lat_centre, 6), "lon": round(self.lon_centre, 6)},
            "city_size_m":     {"width": round(self.city_width_m), "height": round(self.city_height_m)},
            "cs2_map_size_m":  self.CS2_MAP_SIZE,
            "needs_clipping":  self.needs_clipping,
            "scale":           "1:1 (real-world metres)",
        }


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

class CS2Converter:
    """Converts parsed OSM data to Cities: Skylines 2 mod format."""

    # Default fares by route type.
    # Used when OSM has no charge= tag.  All amounts are a sensible
    # single-trip adult fare; the mod uses these to initialise CS2
    # transit line ticket prices.
    #
    # Override per city by passing a fare_overrides dict to __init__:
    #   {"bus": {"base_fare": 2.00, "currency": "GBP"}, ...}
    TRANSIT_FARES: Dict[str, Dict] = {
        "bus":        {"base_fare": 1.50, "day_pass": 5.00,  "currency": "EUR"},
        "tram":       {"base_fare": 1.50, "day_pass": 5.00,  "currency": "EUR"},
        "train":      {"base_fare": 3.50, "day_pass": 18.00, "currency": "EUR"},
        "subway":     {"base_fare": 1.80, "day_pass": 7.00,  "currency": "EUR"},
        "light_rail": {"base_fare": 1.80, "day_pass": 7.00,  "currency": "EUR"},
        "ferry":      {"base_fare": 2.50, "day_pass": 10.00, "currency": "EUR"},
    }

    # Road-type → CS2 prefab name
    ROAD_TYPE_MAP = {
        "motorway":   "Highway",
        "trunk":      "Highway",
        "primary":    "LargeRoad",
        "secondary":  "MediumRoad",
        "tertiary":   "SmallRoad",
        "residential":"SmallRoad",
        "service":    "TinyRoad",
    }

    # Transit-route-type → CS2 line type
    TRANSIT_TYPE_MAP = {
        "bus":        "BusLine",
        "tram":       "TramLine",
        "train":      "TrainLine",
        "subway":     "SubwayLine",
        "light_rail": "MetroLine",
    }

    # Waterway → CS2 water type
    WATERWAY_TYPE_MAP = {
        "river":      "River",
        "canal":      "Canal",
        "stream":     "Stream",
        "drain":      "Drain",
        "ditch":      "Drain",
        "coastline":  "Coastline",
        "water":      "Lake",        # natural=water areas
        "reservoir":  "Reservoir",
    }

    def __init__(
        self,
        bbox: Tuple[float, float, float, float],
        elevation_data: Optional[Dict[Tuple[float, float], float]] = None,
        output_dir: str = "../data/processed",
        fare_overrides: Optional[Dict[str, Dict]] = None,
    ):
        """
        Args:
            bbox:           (south, west, north, east) in decimal degrees.
            elevation_data: {(lat, lon): metres} from the elevation fetcher.
            output_dir:     Where to write JSON output files.
            fare_overrides: Per-route-type fare overrides, e.g.
                            {"bus": {"base_fare": 2.00, "currency": "GBP"}}.
                            Merged on top of TRANSIT_FARES defaults.
        """
        self.transformer    = CoordinateTransformer(bbox)
        self.elevations     = elevation_data or {}
        self.output_dir     = output_dir
        os.makedirs(output_dir, exist_ok=True)

        # Merge defaults with any city-specific overrides
        self._fares: Dict[str, Dict] = {}
        for rt, defaults in self.TRANSIT_FARES.items():
            self._fares[rt] = {**defaults, **(fare_overrides or {}).get(rt, {})}

    # ------------------------------------------------------------------
    # Roads
    # ------------------------------------------------------------------

    def convert_roads(
        self, roads: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert road segments to CS2 format with proper projection and clipping.

        A single OSM way that crosses the map boundary produces multiple
        CS2 road entries (one per clipped sub-segment).
        """
        cs2_roads = []

        for road in roads:
            segments = self.transformer.clip_and_convert_line(
                road["coordinates"], self.elevations
            )
            for idx, seg in enumerate(segments):
                seg_id = f"road_{road['id']}" if len(segments) == 1 else f"road_{road['id']}_{idx}"
                cs2_roads.append({
                    "id":         seg_id,
                    "type":       self.ROAD_TYPE_MAP.get(road["type"], "SmallRoad"),
                    "name":       road["name"],
                    "points":     seg,
                    "lanes":      road["lanes"],
                    "oneWay":     road["oneway"],
                    "speedLimit": self._parse_speed(road["maxspeed"]),
                    "priority":   road["priority"],
                })

        return cs2_roads

    # ------------------------------------------------------------------
    # Railways
    # ------------------------------------------------------------------

    def convert_railways(
        self, railways: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        cs2_railways = []

        for rail in railways:
            segments = self.transformer.clip_and_convert_line(
                rail["coordinates"], self.elevations
            )
            for idx, seg in enumerate(segments):
                seg_id = f"rail_{rail['id']}" if len(segments) == 1 else f"rail_{rail['id']}_{idx}"
                cs2_railways.append({
                    "id":          seg_id,
                    "type":        self._map_railway_type(rail["type"]),
                    "name":        rail["name"],
                    "points":      seg,
                    "electrified": rail.get("electrified") == "yes",
                })

        return cs2_railways

    # ------------------------------------------------------------------
    # Waterways
    # ------------------------------------------------------------------

    def convert_waterways(
        self, waterways: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert waterway features (rivers, canals, lakes …) to CS2 format.

        Linear waterways (rivers, streams, canals) → list of points.
        Area waterways  (lakes, reservoirs)         → closed polygon points.
        """
        cs2_waterways = []

        for ww in waterways:
            cs2_type = self.WATERWAY_TYPE_MAP.get(ww["type"], "Stream")
            is_area  = ww.get("is_area", False)

            if is_area:
                points = self.transformer.clip_and_convert_polygon(
                    ww["coordinates"], self.elevations
                )
                if points is None:
                    continue
                cs2_waterways.append({
                    "id":     f"water_{ww['id']}",
                    "type":   cs2_type,
                    "name":   ww["name"],
                    "isArea": True,
                    "points": points,
                    "width":  None,
                })
            else:
                segments = self.transformer.clip_and_convert_line(
                    ww["coordinates"], self.elevations
                )
                for idx, seg in enumerate(segments):
                    seg_id = (
                        f"water_{ww['id']}"
                        if len(segments) == 1
                        else f"water_{ww['id']}_{idx}"
                    )
                    cs2_waterways.append({
                        "id":     seg_id,
                        "type":   cs2_type,
                        "name":   ww["name"],
                        "isArea": False,
                        "points": seg,
                        "width":  ww.get("width"),
                    })

        return cs2_waterways

    # ------------------------------------------------------------------
    # Transit
    # ------------------------------------------------------------------

    def convert_transit(
        self, transit_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert stops and routes to CS2 format.

        External stops (intercity route endpoints that lie outside the
        map boundary) are pinned to the nearest point on the map edge so
        the CS2 mod can place a visible "external connection" marker
        rather than dropping the endpoint entirely.
        """
        cs2_stops:  List[Dict[str, Any]] = []
        cs2_routes: List[Dict[str, Any]] = []

        # ---- Stops -------------------------------------------------------
        for stop in transit_data["stops"]:
            try:
                lon, lat = stop["coordinates"]
                lon, lat = float(lon), float(lat)
            except (TypeError, ValueError, KeyError):
                continue
            elev   = self.elevations.get((round(lat, 6), round(lon, 6)), 0.0)
            is_ext = stop.get("is_external", False)

            if is_ext:
                position = self._clamp_to_map_edge(lat, lon, elev)
            else:
                if not self.transformer.in_bounds(lat, lon):
                    continue  # entirely outside — shouldn't happen after filtering
                position = self.transformer.to_cs2(lat, lon, elev)

            cs2_stops.append({
                "id":            f"stop_{stop['id']}",
                "name":          stop["name"],
                "type":          stop["type"],
                "position":      position,
                "is_external":   is_ext,
                "is_underground":stop.get("is_underground", False),
                "has_shelter":   stop.get("has_shelter", False),
                "has_bench":     stop.get("has_bench", False),
                "wheelchair":    stop.get("wheelchair", "unknown"),
            })

        stop_id_set = {s["id"] for s in cs2_stops}

        # ---- Routes ------------------------------------------------------
        for route in transit_data["routes"]:
            route_type = route["route_type"]
            cs2_type   = self.TRANSIT_TYPE_MAP.get(route_type, "BusLine")

            # Ordered list of stop IDs that exist in our converted stop set
            route_stops = [
                f"stop_{sid}"
                for sid in route.get("stop_ids", [])
                if f"stop_{sid}" in stop_id_set
            ]

            # Fare: use OSM data if present, else defaults for this route type
            osm_fare  = route.get("fare")
            fare_defaults = self._fares.get(route_type, self._fares.get("bus", {}))
            if osm_fare:
                fare = {**fare_defaults, **osm_fare}
            else:
                fare = {**fare_defaults, "source": "default"}

            cs2_routes.append({
                "id":          f"route_{route['id']}",
                "name":        route["name"],
                "number":      route["ref"],
                "type":        cs2_type,
                "operator":    route["operator"],
                "colour":      route.get("colour", ""),
                "network":     route.get("network", ""),
                "from":        route.get("from", ""),
                "to":          route.get("to", ""),
                "is_intercity":route.get("is_intercity", False),
                "stops":       route_stops,
                "fare":        fare,
            })

        return {"stops": cs2_stops, "routes": cs2_routes}

    def _clamp_to_map_edge(
        self, lat: float, lon: float, elev: float
    ) -> Dict[str, float]:
        """
        For external stops that lie beyond the CS2 map boundary, pin them
        to the nearest point on the map edge at the same bearing.

        This gives the CS2 mod a valid in-map anchor for route endpoints.
        """
        x, z    = self.transformer._xz(lat, lon)
        half    = self.transformer.CS2_HALF_MAP
        # Clamp to [-half, +half] in both axes
        cx = max(-half, min(half, x))
        cz = max(-half, min(half, z))
        return {"x": round(cx, 2), "y": round(elev, 2), "z": round(cz, 2)}

    # ------------------------------------------------------------------
    # Spatial chunking
    # ------------------------------------------------------------------

    def create_chunks(
        self,
        data: Dict[str, Any],
        chunk_size_m: float = 5_000.0,
    ) -> List[Dict[str, Any]]:
        """
        Divide city data into a spatial grid for dynamic loading.

        Each chunk covers chunk_size_m × chunk_size_m metres in CS2 space.
        Only chunks that contain at least one feature are emitted.

        Args:
            data:         CS2-format city data (roads, railways, waterways, transit).
            chunk_size_m: Side length of each chunk in metres (default 5 km).

        Returns:
            List of chunk dicts, each with bounds and its subset of features.
        """
        half = self.transformer.CS2_HALF_MAP
        n_cells = math.ceil(self.transformer.CS2_MAP_SIZE / chunk_size_m)

        # Build a grid of empty chunks indexed by (col, row)
        chunks: Dict[Tuple[int, int], Dict[str, Any]] = {}

        def _cell(x: float, z: float) -> Tuple[int, int]:
            col = int((x + half) / chunk_size_m)
            row = int((z + half) / chunk_size_m)
            return (
                max(0, min(col, n_cells - 1)),
                max(0, min(row, n_cells - 1)),
            )

        def _get_chunk(col: int, row: int) -> Dict[str, Any]:
            if (col, row) not in chunks:
                x_min = -half + col * chunk_size_m
                z_min = -half + row * chunk_size_m
                chunks[(col, row)] = {
                    "chunk_id": f"chunk_{col}_{row}",
                    "bounds": {
                        "x_min": round(x_min, 1),
                        "z_min": round(z_min, 1),
                        "x_max": round(x_min + chunk_size_m, 1),
                        "z_max": round(z_min + chunk_size_m, 1),
                    },
                    "roads":      [],
                    "railways":   [],
                    "waterways":  [],
                    "transit":    {"stops": [], "routes": []},
                }
            return chunks[(col, row)]

        # Assign roads by their first point's cell
        for road in data.get("roads", []):
            if road["points"]:
                pt = road["points"][0]
                chunk = _get_chunk(*_cell(pt["x"], pt["z"]))
                chunk["roads"].append(road)

        for rail in data.get("railways", []):
            if rail["points"]:
                pt = rail["points"][0]
                chunk = _get_chunk(*_cell(pt["x"], pt["z"]))
                chunk["railways"].append(rail)

        for ww in data.get("waterways", []):
            if ww["points"]:
                pt = ww["points"][0]
                chunk = _get_chunk(*_cell(pt["x"], pt["z"]))
                chunk["waterways"].append(ww)

        for stop in data.get("transit", {}).get("stops", []):
            pos = stop["position"]
            chunk = _get_chunk(*_cell(pos["x"], pos["z"]))
            chunk["transit"]["stops"].append(stop)

        # Routes are not spatial — put them all in every chunk that has at
        # least one of their stops.
        routes = data.get("transit", {}).get("routes", [])
        stop_to_chunk: Dict[str, Tuple[int, int]] = {}
        for (col, row), chunk in chunks.items():
            for stop in chunk["transit"]["stops"]:
                stop_to_chunk[stop["id"]] = (col, row)

        for route in routes:
            seen: set = set()
            for stop_id in route["stops"]:
                key = stop_to_chunk.get(stop_id)
                if key and key not in seen:
                    seen.add(key)
                    chunks[key]["transit"]["routes"].append(route)

        result = list(chunks.values())
        print(f"  Created {len(result)} chunk(s) ({n_cells}×{n_cells} grid, {chunk_size_m/1000:.0f} km cells)")
        return result

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def save_to_file(self, data: Any, filename: str):
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        size_kb = os.path.getsize(path) / 1024
        print(f"  Saved {filename} ({size_kb:.0f} KB)")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_speed(self, maxspeed: str) -> int:
        if not maxspeed:
            return 50
        try:
            speed = int(str(maxspeed).split()[0])
            if "mph" in str(maxspeed).lower():
                speed = int(speed * 1.60934)
            return speed
        except (ValueError, IndexError):
            return 50

    def _map_railway_type(self, osm_type: str) -> str:
        return {
            "rail":       "Train",
            "light_rail": "Metro",
            "subway":     "Subway",
            "tram":       "Tram",
        }.get(osm_type, "Train")
