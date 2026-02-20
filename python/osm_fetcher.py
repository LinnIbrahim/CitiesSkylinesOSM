"""
OSM Data Fetcher
Fetches OpenStreetMap data and elevation for a given city or bounding box.
"""

import json
import math
import os
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

    def fetch_city_bbox(self, city_name: str) -> Optional[Tuple[float, float, float, float]]:
        """
        Look up a city's bounding box via Nominatim.

        Returns:
            (south, west, north, east) or None if not found.
        """
        url    = "https://nominatim.openstreetmap.org/search"
        params = {"q": city_name, "format": "json", "limit": 1}
        headers = {"User-Agent": "MapToSkylines2/0.1"}

        resp = requests.get(url, params=params, headers=headers, timeout=15)
        if resp.status_code == 200 and resp.json():
            data = resp.json()[0]
            bbox = data.get("boundingbox", [])
            if len(bbox) == 4:
                # Nominatim: [south, north, west, east]
                return (float(bbox[0]), float(bbox[2]), float(bbox[1]), float(bbox[3]))
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

        Returns:
            Dict keyed by feature type.
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
        """
        Fetch rivers, streams, canals, lakes, reservoirs, and coastline.

        Linear features: waterway=river|stream|canal|drain|ditch|coastline
        Area features:   natural=water, landuse=reservoir
        """
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
        query = f"""
        [out:json][timeout:180];
        (
          node["public_transport"="stop_position"]({bbox_str});
          node["highway"="bus_stop"]({bbox_str});
          relation["type"="route"]["route"~"{route_filter}"]({bbox_str});
        );
        out body;
        >;
        out skel qt;
        """
        return self._query_with_retry(query)

    def _query_with_retry(
        self, query: str, max_retries: int = 3
    ) -> overpy.Result:
        for attempt in range(max_retries):
            try:
                print(f"  Attempt {attempt + 1}/{max_retries}...")
                return self.api.query(query)
            except (
                overpy.exception.OverpassGatewayTimeout,
                overpy.exception.OverpassTooManyRequests,
            ):
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 10
                    print(f"  Rate-limited — waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print("  Max retries reached.")
                    raise
            except Exception as e:
                print(f"  Error: {e}")
                raise

    # ------------------------------------------------------------------
    # Elevation via OpenTopoData (SRTM 30 m)
    # ------------------------------------------------------------------

    def fetch_elevation(
        self,
        coords: List[Tuple[float, float]],
    ) -> Dict[Tuple[float, float], float]:
        """
        Fetch terrain elevation for a list of (lat, lon) coordinates.

        Uses OpenTopoData's free SRTM 30 m endpoint — no API key needed.
        Results are cached on disk at data/osm/elevation_cache.json.

        Elevation at clipped or interpolated geometry points is computed
        by the CoordinateTransformer using nearest-neighbour weighting, so
        every node with a known elevation contributes.

        Args:
            coords: List of (lat, lon) tuples.

        Returns:
            Dict mapping (lat_rounded, lon_rounded) → elevation in metres.
        """
        # Round to 6 decimal places (~0.1 m precision) for deduplication
        unique = list({(round(lat, 6), round(lon, 6)) for lat, lon in coords})

        if not unique:
            return {}

        # Load on-disk cache
        cache_path = os.path.join(self.cache_dir, "elevation_cache.json")
        cache: Dict[str, float] = {}
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                cache = json.load(f)

        def _key(lat: float, lon: float) -> str:
            return f"{lat},{lon}"

        to_fetch = [c for c in unique if _key(*c) not in cache]

        # Cap at 2 000 unique points per run to stay within free-tier limits.
        # For very large cities, a representative sample is already sufficient
        # because the CS2 terrain system smooths height between nodes.
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
                batch = to_fetch[i : i + batch_size]
                locations = "|".join(f"{lat},{lon}" for lat, lon in batch)
                url = f"https://api.opentopodata.org/v1/srtm30m?locations={locations}"

                try:
                    resp = requests.get(url, timeout=30)
                    if resp.status_code == 200:
                        data = resp.json()
                        for result in data.get("results", []):
                            loc   = result.get("location", {})
                            elev  = result.get("elevation") or 0.0
                            cache[_key(loc["lat"], loc["lng"])] = float(elev)
                    else:
                        print(f"  Elevation API returned {resp.status_code} — skipping batch.")
                except requests.RequestException as e:
                    print(f"  Elevation fetch error: {e} — skipping batch.")

                # Respect free-tier rate limit: 1 request / second
                if i + batch_size < len(to_fetch):
                    time.sleep(1.1)

            # Persist updated cache
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f)
            print(f"  Elevation cache saved ({len(cache)} entries).")

        # Build result dict with tuple keys
        result: Dict[Tuple[float, float], float] = {}
        for lat, lon in unique:
            v = cache.get(_key(lat, lon))
            if v is not None:
                result[(lat, lon)] = v

        return result

    # ------------------------------------------------------------------
    # Utility: collect all OSM node coordinates from parsed data
    # ------------------------------------------------------------------

    @staticmethod
    def collect_coords(parsed_data: dict) -> List[Tuple[float, float]]:
        """
        Extract all unique (lat, lon) pairs from a parsed-data dict.

        Accepts the dict produced by OSMParser (roads, railways,
        waterways, transit), so the elevation fetcher can be called
        with a single list covering every feature type.
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
    # Cache helper (raw OSM not serialisable, kept as metadata only)
    # ------------------------------------------------------------------

    def save_bbox_cache(self, city_name: str, bbox: Tuple[float, float, float, float]):
        path = os.path.join(self.cache_dir, f"{city_name.replace(' ', '_')}_bbox.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"city": city_name, "bbox": bbox}, f)
