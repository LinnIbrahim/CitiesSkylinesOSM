"""
OSM Data Fetcher
Fetches OpenStreetMap data and elevation for a given city or bounding box.
"""

import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import overpy
import requests


class OSMFetcher:
    """Fetches data from OpenStreetMap (Overpass API) and elevation data."""

    def __init__(self, cache_dir: str = "../data/osm"):
        self.api       = overpy.Overpass()
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # City bounding box
    # ------------------------------------------------------------------

    def fetch_city_bbox(
        self, city_name: str
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Look up a city's bounding box via Nominatim.

        Returns:
            (south, west, north, east) or None on failure.
        """
        url     = "https://nominatim.openstreetmap.org/search"
        params  = {"q": city_name, "format": "json", "limit": 1}
        headers = {"User-Agent": "MapToSkylines2/0.1"}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"  Nominatim request failed: {e}")
            return None
        except ValueError as e:
            print(f"  Nominatim returned invalid JSON: {e}")
            return None

        if not data:
            return None

        try:
            bbox = data[0].get("boundingbox", [])
            if len(bbox) != 4:
                return None
            # Nominatim order: [south, north, west, east]
            south, north, west, east = (float(b) for b in bbox)
            return (south, west, north, east)
        except (ValueError, IndexError, KeyError) as e:
            print(f"  Could not parse Nominatim bbox: {e}")
            return None

    # ------------------------------------------------------------------
    # Bounding box validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_bbox(
        bbox: Tuple[float, float, float, float]
    ) -> Optional[str]:
        """
        Validate a (south, west, north, east) bbox.

        Returns an error string if invalid, or None if OK.
        """
        if len(bbox) != 4:
            return "Bbox must have exactly 4 values (south, west, north, east)."
        south, west, north, east = bbox

        if not (-90 <= south <= 90 and -90 <= north <= 90):
            return f"Latitude out of range: south={south}, north={north}."
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return f"Longitude out of range: west={west}, east={east}."
        if south >= north:
            return (
                f"south ({south}) must be less than north ({north}). "
                "Did you pass the bbox in the wrong order?"
            )
        if west > east:
            # Could be antimeridian-crossing — warn but do not abort
            print(
                f"  Warning: west ({west}) > east ({east}). "
                "This city crosses the antimeridian (e.g. Fiji, eastern Russia). "
                "Coordinate projection will be inaccurate — consider splitting "
                "the bbox at the antimeridian."
            )
        return None

    # ------------------------------------------------------------------
    # OSM feature fetching
    # ------------------------------------------------------------------

    def fetch_city_data(
        self,
        bbox: Tuple[float, float, float, float],
        features: Optional[List[str]] = None,
    ) -> dict:
        """
        Fetch OSM data for a bounding box.

        Args:
            bbox:     (south, west, north, east)
            features: Subset of ["roads", "railways", "waterways", "bus", "tram", "train"].
                      Defaults to all.
        """
        if features is None:
            features = ["roads", "railways", "waterways", "bus", "tram", "train"]

        south, west, north, east = bbox
        bbox_str = f"{south},{west},{north},{east}"
        results  = {}

        if "roads" in features:
            print("Fetching roads...")
            results["roads"] = self._fetch_roads(bbox_str)
            time.sleep(2)

        if "railways" in features:
            print("Fetching railways...")
            results["railways"] = self._fetch_railways(bbox_str)
            time.sleep(2)

        if "waterways" in features:
            print("Fetching waterways...")
            results["waterways"] = self._fetch_waterways(bbox_str)
            time.sleep(2)

        if any(f in features for f in ["bus", "tram", "train"]):
            print("Fetching public transport...")
            results["transit"] = self._fetch_public_transport(bbox_str, features)

        return results

    # ------------------------------------------------------------------
    # Overpass queries
    # ------------------------------------------------------------------

    def _fetch_roads(self, bbox_str: str) -> overpy.Result:
        query = f"""
        [out:json][timeout:180];
        (
          way["highway"~"motorway|trunk|primary|secondary|tertiary|residential|service"]({bbox_str});
        );
        out body;
        >;
        out skel qt;
        """
        return self._query_with_retry(query)

    def _fetch_railways(self, bbox_str: str) -> overpy.Result:
        query = f"""
        [out:json][timeout:180];
        (
          way["railway"~"rail|light_rail|subway|tram"]({bbox_str});
        );
        out body;
        >;
        out skel qt;
        """
        return self._query_with_retry(query)

    def _fetch_waterways(self, bbox_str: str) -> overpy.Result:
        query = f"""
        [out:json][timeout:180];
        (
          way["waterway"~"river|stream|canal|drain|ditch"]({bbox_str});
          way["natural"="coastline"]({bbox_str});
          way["natural"="water"]({bbox_str});
          way["landuse"="reservoir"]({bbox_str});
          relation["natural"="water"]({bbox_str});
          relation["landuse"="reservoir"]({bbox_str});
        );
        out body;
        >;
        out skel qt;
        """
        return self._query_with_retry(query)

    def _fetch_public_transport(
        self, bbox_str: str, features: List[str]
    ) -> overpy.Result:
        transport_types = []
        if "bus"   in features: transport_types.append("bus")
        if "tram"  in features: transport_types.append("tram")
        if "train" in features: transport_types.extend(["train", "subway", "light_rail"])

        route_filter = "|".join(transport_types)

        # Use "out body qt" (not "out skel qt") for the recursive member fetch.
        # This ensures external stop nodes have their tags available for
        # underground and stop-type detection.  For cities with hundreds of
        # routes this produces a larger response but avoids silent data loss.
        query = f"""
        [out:json][timeout:180];
        (
          node["railway"="tram_stop"]({bbox_str});
          node["public_transport"="stop_position"]["bus"="yes"]({bbox_str});
          node["public_transport"="stop_position"]["tram"="yes"]({bbox_str});
          node["public_transport"="stop_position"]["train"="yes"]({bbox_str});
          node["highway"="bus_stop"]({bbox_str});
          relation["type"="route"]["route"~"{route_filter}"]({bbox_str});
        );
        out body;
        >;
        out body qt;
        """
        return self._query_with_retry(query)

    def _query_with_retry(
        self, query: str, max_retries: int = 3
    ) -> overpy.Result:
        """
        Execute an Overpass query with exponential-backoff retry.

        Retries on:
          - Rate-limit / gateway timeout responses from Overpass
          - Transient network errors (ConnectionError, ChunkedEncodingError, …)
        Non-retriable exceptions (e.g. query syntax errors) are re-raised
        immediately.
        """
        RETRIABLE = (
            overpy.exception.OverpassGatewayTimeout,
            overpy.exception.OverpassTooManyRequests,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
            requests.exceptions.Timeout,
            requests.exceptions.ReadTimeout,
        )

        for attempt in range(max_retries):
            try:
                print(f"  Attempt {attempt + 1}/{max_retries}...")
                return self.api.query(query)
            except RETRIABLE as e:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 10  # 10, 20, 40 s
                    print(f"  Retryable error ({type(e).__name__}) — waiting {wait}s…")
                    time.sleep(wait)
                else:
                    print("  Max retries reached.")
                    raise
            except Exception:
                # Non-retriable (syntax error, data error, etc.) — fail fast
                raise

    # ------------------------------------------------------------------
    # Elevation via OpenTopoData (SRTM 30 m)
    # ------------------------------------------------------------------

    def fetch_elevation(
        self,
        coords: List[Tuple[float, float]],
    ) -> Dict[Tuple[float, float], float]:
        """
        Fetch terrain elevation (metres) for a list of (lat, lon) coordinates.

        Uses the free OpenTopoData SRTM 30 m endpoint — no API key needed.
        Results are cached on disk at <cache_dir>/elevation_cache.json.
        Rate limit: 1 request per second, 100 locations per request.

        Args:
            coords: [(lat, lon), …]

        Returns:
            {(lat_rounded, lon_rounded): elevation_metres}
        """
        unique = list({(round(lat, 6), round(lon, 6)) for lat, lon in coords})

        if not unique:
            return {}

        cache_path = os.path.join(self.cache_dir, "elevation_cache.json")
        cache: Dict[str, float] = {}
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cache = json.load(f)
            except (OSError, ValueError):
                cache = {}

        def _key(lat: float, lon: float) -> str:
            return f"{lat},{lon}"

        to_fetch = [c for c in unique if _key(*c) not in cache]

        MAX_POINTS = 2_000
        if len(to_fetch) > MAX_POINTS:
            print(
                f"  Elevation: {len(to_fetch)} unique points — "
                f"sampling {MAX_POINTS} evenly."
            )
            step     = len(to_fetch) / MAX_POINTS
            to_fetch = [to_fetch[int(i * step)] for i in range(MAX_POINTS)]

        if to_fetch:
            print(
                f"  Fetching elevation for {len(to_fetch)} points "
                f"({len(unique) - len(to_fetch)} already cached)…"
            )
            batch_size = 100
            for i in range(0, len(to_fetch), batch_size):
                batch     = to_fetch[i : i + batch_size]
                locations = "|".join(f"{lat},{lon}" for lat, lon in batch)
                url       = f"https://api.opentopodata.org/v1/srtm30m?locations={locations}"

                try:
                    resp = requests.get(url, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        for result in data.get("results", []):
                            try:
                                loc  = result["location"]
                                elev = result.get("elevation")
                                # elevation=null means sea/ocean → treat as 0
                                cache[_key(float(loc["lat"]), float(loc["lng"]))] = (
                                    float(elev) if elev is not None else 0.0
                                )
                            except (KeyError, TypeError, ValueError):
                                pass  # skip malformed individual result
                    else:
                        print(f"  Elevation API {resp.status_code} — skipping batch.")
                except requests.RequestException as e:
                    print(f"  Elevation fetch error: {e} — skipping batch.")

                if i + batch_size < len(to_fetch):
                    time.sleep(1.1)  # respect 1 req/s rate limit

            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(cache, f)
                print(f"  Elevation cache saved ({len(cache)} entries).")
            except OSError as e:
                print(f"  Warning: could not save elevation cache: {e}")

        result: Dict[Tuple[float, float], float] = {}
        for lat, lon in unique:
            v = cache.get(_key(lat, lon))
            if v is not None:
                result[(lat, lon)] = v

        return result

    # ------------------------------------------------------------------
    # Utility: collect all node coordinates from parsed data
    # ------------------------------------------------------------------

    @staticmethod
    def collect_coords(parsed_data: dict) -> List[Tuple[float, float]]:
        """
        Extract all unique (lat, lon) pairs from a parsed-data dict.
        """
        coords: List[Tuple[float, float]] = []

        for feature_list in [
            parsed_data.get("roads", []),
            parsed_data.get("railways", []),
            parsed_data.get("waterways", []),
        ]:
            for feature in feature_list:
                for lon, lat in feature.get("coordinates", []):
                    coords.append((lat, lon))

        for stop in parsed_data.get("transit", {}).get("stops", []):
            lon, lat = stop["coordinates"]
            coords.append((lat, lon))

        return coords

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_filename(name: str) -> str:
        """
        Return a filesystem-safe version of a city/output name.
        Replaces path separators, null bytes, and non-ASCII-printable chars
        with underscores.
        """
        # Replace path separators and other problematic characters
        safe = re.sub(r'[/\\:*?"<>|\x00]', "_", name)
        # Collapse multiple consecutive underscores
        safe = re.sub(r"_+", "_", safe)
        return safe.strip("_") or "city"

    def save_bbox_cache(
        self, city_name: str, bbox: Tuple[float, float, float, float]
    ):
        safe = self._safe_filename(city_name.replace(" ", "_"))
        path = os.path.join(self.cache_dir, f"{safe}_bbox.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"city": city_name, "bbox": bbox}, f)
        except OSError as e:
            print(f"  Warning: could not save bbox cache: {e}")
