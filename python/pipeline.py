"""
Shared OSM → CS2 generation pipeline.

A single ``generate_city_data`` entry point drives the full conversion:
    OSM fetch → parse → elevation → CS2 convert → theme → simplify → chunk.

Both the CLI (``main.py``) and the interactive web generator
(``generate_server.py``) call this so the logic lives in exactly one place.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from osm_fetcher import OSMFetcher
from osm_parser import OSMParser
from cs2_converter import CS2Converter
from eu_assets import apply_theme

Bbox = Tuple[float, float, float, float]

DEFAULT_FEATURES = ["roads", "railways", "waterways", "bus", "tram", "train",
                    "buildings", "districts"]


def generate_city_data(
    bbox: Bbox,
    features: Optional[List[str]] = None,
    *,
    city_name: str = "city",
    theme: str = "european",
    fetch_elevation: bool = True,
    simplify_tolerance: float = 2.0,
    chunk_size_m: float = 5_000.0,
    min_waterway_width: float = 0.0,
    fare_overrides: Optional[Dict[str, Dict]] = None,
    output_dir: str = "../data/processed",
    fetcher: Optional[OSMFetcher] = None,
    parser: Optional[OSMParser] = None,
    log: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """
    Run the full OSM → CS2 pipeline for a bounding box.

    Args:
        bbox:               (south, west, north, east) in decimal degrees.
        features:           Subset of DEFAULT_FEATURES (defaults to all).
        city_name:          Used in the output metadata.
        theme:              Asset theme to apply ("european" or "none").
        fetch_elevation:    When False, terrain is flat (skips elevation API).
        simplify_tolerance: Douglas-Peucker tolerance in metres (0 = off).
        chunk_size_m:       Spatial chunk side length in metres.
        fare_overrides:     Per-route-type fare overrides for the converter.
        output_dir:         Where the converter writes (only used if saving).
        fetcher/parser:     Injectable for reuse/testing; created if omitted.
        log:                Progress callback (defaults to ``print``).

    Returns:
        {
          "cs2_data": {...},          # full themed CS2 city data (+ _meta)
          "chunks":   [...],          # spatial chunks for dynamic loading
          "stats":    {...},          # coordinate-system stats
          "counts":   {...},          # per-feature counts (for UI/summary)
        }
    """
    features = features or list(DEFAULT_FEATURES)
    fetcher = fetcher or OSMFetcher()
    parser = parser or OSMParser()

    # ----------------------------------------------------------------
    # 1. Fetch OSM data
    # ----------------------------------------------------------------
    log(f"Fetching OSM data for {city_name}…")
    osm_data = fetcher.fetch_city_data(bbox, features, log=log)

    # ----------------------------------------------------------------
    # 2. Parse OSM data
    # ----------------------------------------------------------------
    log("Parsing OSM data…")
    parsed: Dict[str, Any] = {}

    if "roads" in osm_data:
        parsed["roads"] = parser.parse_roads(osm_data["roads"])
        log(f"  Roads:      {len(parsed['roads'])} segments")

    underground_way_ids: set = set()
    if "railways" in osm_data:
        parsed["railways"] = parser.parse_railways(osm_data["railways"])
        underground_way_ids = parser.get_underground_way_ids(osm_data["railways"])
        log(f"  Railways:   {len(parsed['railways'])} segments "
            f"({len(underground_way_ids)} underground way(s))")

    if "waterways" in osm_data:
        parsed["waterways"] = parser.parse_waterways(osm_data["waterways"])
        log(f"  Waterways:  {len(parsed['waterways'])} features")

    if "transit" in osm_data:
        parsed["transit"] = parser.parse_transit_routes(
            osm_data["transit"],
            underground_way_ids=underground_way_ids,
            bbox=bbox,
        )
        log(f"  Transit:    {len(parsed['transit']['stops'])} stops, "
            f"{len(parsed['transit']['routes'])} routes")

    if "buildings" in osm_data:
        parsed["buildings"] = parser.parse_buildings(osm_data["buildings"])
        log(f"  Buildings:  {len(parsed['buildings'])} total")

    if "places" in osm_data:
        parsed["places"] = parser.parse_places(osm_data["places"])
        log(f"  Places:     {len(parsed['places'])} settlements")

    # ----------------------------------------------------------------
    # 3. Fetch elevation
    # ----------------------------------------------------------------
    elevation_data: Dict = {}
    if fetch_elevation:
        log("Fetching terrain elevation…")
        all_coords = OSMFetcher.collect_coords(parsed)
        elevation_data = fetcher.fetch_elevation(all_coords, log=log)
        log(f"  Elevation data: {len(elevation_data)} points")
    else:
        log("Skipping elevation — flat terrain.")

    # ----------------------------------------------------------------
    # 4. Convert to CS2 format
    # ----------------------------------------------------------------
    log("Converting to CS2 format…")
    converter = CS2Converter(
        bbox=bbox,
        elevation_data=elevation_data,
        output_dir=output_dir,
        fare_overrides=fare_overrides,
    )

    stats = converter.transformer.stats()
    if stats["needs_clipping"]:
        log("  ⚠ City exceeds CS2 map bounds — edge features will be clipped.")

    cs2_data: Dict[str, Any] = {}
    if "roads" in parsed:
        cs2_data["roads"] = converter.convert_roads(parsed["roads"])
    if "railways" in parsed:
        cs2_data["railways"] = converter.convert_railways(parsed["railways"])
    if "waterways" in parsed:
        cs2_data["waterways"] = converter.convert_waterways(
            parsed["waterways"], min_width=min_waterway_width)
    if "transit" in parsed:
        cs2_data["transit"] = converter.convert_transit(parsed["transit"])
    if "buildings" in parsed:
        cs2_data["buildings"] = converter.convert_buildings(parsed["buildings"])
    if "places" in parsed:
        cs2_data["districts"] = converter.convert_districts(parsed["places"])

    # ----------------------------------------------------------------
    # 5. Simplify geometry
    # ----------------------------------------------------------------
    if simplify_tolerance > 0:
        log(f"Simplifying geometry (tolerance={simplify_tolerance} m)…")
        cs2_data = converter.simplify_all(cs2_data, tolerance=simplify_tolerance)

    # Outside connections: where highway/rail/waterway networks reach the map
    # edge, so the city can link to the world beyond the map.
    cs2_data["outside_connections"] = converter.find_outside_connections(cs2_data)
    log(f"  Outside connections: {len(cs2_data['outside_connections'])}")

    # Metadata (before theming, so the theme block can be added on top)
    cs2_data["_meta"] = {
        "city":              city_name,
        "bbox":              {"south": bbox[0], "west": bbox[1],
                              "north": bbox[2], "east": bbox[3]},
        "coordinate_system": stats,
        "elevation_points":  len(elevation_data),
    }

    # ----------------------------------------------------------------
    # 6. Apply asset theme (European by default)
    # ----------------------------------------------------------------
    if theme and theme.strip().lower() not in ("none", "vanilla", "neutral"):
        log(f"Applying '{theme}' asset theme…")
        cs2_data = apply_theme(cs2_data, theme)

    # ----------------------------------------------------------------
    # 7. Chunk for dynamic loading
    # ----------------------------------------------------------------
    log("Creating spatial chunks…")
    chunks = converter.create_chunks(cs2_data, chunk_size_m=chunk_size_m)

    counts = {
        "roads":     len(cs2_data.get("roads", [])),
        "railways":  len(cs2_data.get("railways", [])),
        "waterways": len(cs2_data.get("waterways", [])),
        "buildings": len(cs2_data.get("buildings", [])),
        "districts": len(cs2_data.get("districts", [])),
        "stops":     len(cs2_data.get("transit", {}).get("stops", [])),
        "routes":    len(cs2_data.get("transit", {}).get("routes", [])),
        "chunks":    len(chunks),
    }

    return {
        "cs2_data": cs2_data,
        "chunks":   chunks,
        "stats":    stats,
        "counts":   counts,
        "converter": converter,
    }
