"""
MapToSkylines2 — Main Entry Point
Orchestrates: OSM fetch → parse → elevation → CS2 convert → chunk → save.
"""

import argparse

from osm_fetcher import OSMFetcher
from osm_parser  import OSMParser
from cs2_converter import CS2Converter


def main():
    parser = argparse.ArgumentParser(
        description="Convert OpenStreetMap data to Cities: Skylines 2 format"
    )
    parser.add_argument("--city",   type=str, help="City name (looked up via Nominatim)")
    parser.add_argument(
        "--bbox", type=str,
        help="Manual bounding box as 'south,west,north,east' in decimal degrees"
    )
    parser.add_argument(
        "--features", type=str,
        default="roads,railways,waterways,bus,tram,train",
        help="Comma-separated features to fetch (default: all)"
    )
    parser.add_argument(
        "--output", type=str, default="city_data",
        help="Output filename stem (without extension)"
    )
    parser.add_argument(
        "--chunk-size", type=float, default=5000.0,
        help="Spatial chunk size in metres (default: 5000 = 5 km)"
    )
    parser.add_argument(
        "--no-elevation", action="store_true",
        help="Skip elevation fetching (use flat terrain)"
    )
    parser.add_argument(
        "--fare-config", type=str, default=None,
        help="Path to a JSON file with per-route-type fare overrides. "
             "Keys: bus, tram, train, subway, light_rail, ferry. "
             'Values: {"base_fare": 2.00, "day_pass": 7.00, "currency": "GBP"}'
    )

    args = parser.parse_args()

    fetcher    = OSMFetcher()
    parser_obj = OSMParser()

    # ----------------------------------------------------------------
    # 1. Resolve bounding box
    # ----------------------------------------------------------------
    if args.bbox:
        try:
            parts = [p.strip() for p in args.bbox.split(",")]
            if len(parts) != 4:
                print("ERROR: --bbox requires exactly 4 comma-separated values: south,west,north,east")
                return
            bbox = tuple(float(p) for p in parts)
        except ValueError as e:
            print(f"ERROR: --bbox contains a non-numeric value: {e}")
            return
        city_name = args.output
    elif args.city:
        print(f"Looking up bounding box for '{args.city}'…")
        bbox = fetcher.fetch_city_bbox(args.city)
        if not bbox:
            print(f"ERROR: Could not find city '{args.city}'. "
                  "Try a more specific name or use --bbox.")
            return
        city_name = args.city
        print(f"  Bounding box: south={bbox[0]}, west={bbox[1]}, north={bbox[2]}, east={bbox[3]}")
        fetcher.save_bbox_cache(city_name, bbox)
    else:
        print("Please provide --city or --bbox.")
        return

    # Validate the bbox before doing any heavy fetching
    err = fetcher.validate_bbox(bbox)
    if err:
        print(f"ERROR: Invalid bounding box — {err}")
        return

    features = [f.strip() for f in args.features.split(",")]

    # ----------------------------------------------------------------
    # 2. Fetch OSM data
    # ----------------------------------------------------------------
    print(f"\nFetching OSM data for {city_name}…")
    osm_data = fetcher.fetch_city_data(bbox, features)

    # ----------------------------------------------------------------
    # 3. Parse OSM data
    # ----------------------------------------------------------------
    print("\nParsing OSM data…")
    parsed: dict = {}

    if "roads" in osm_data:
        parsed["roads"] = parser_obj.parse_roads(osm_data["roads"])
        print(f"  Roads:      {len(parsed['roads'])} segments")

    # Build underground way ID set from railway data (used to filter tram routes)
    underground_way_ids = set()

    if "railways" in osm_data:
        parsed["railways"] = parser_obj.parse_railways(osm_data["railways"])
        underground_way_ids = parser_obj.get_underground_way_ids(osm_data["railways"])
        print(f"  Railways:   {len(parsed['railways'])} segments "
              f"({len(underground_way_ids)} underground way(s) detected)")

    if "waterways" in osm_data:
        parsed["waterways"] = parser_obj.parse_waterways(osm_data["waterways"])
        n_lines = sum(1 for w in parsed["waterways"] if not w["is_area"])
        n_areas = sum(1 for w in parsed["waterways"] if     w["is_area"])
        print(f"  Waterways:  {n_lines} linear, {n_areas} area features")

    if "transit" in osm_data:
        parsed["transit"] = parser_obj.parse_transit_routes(
            osm_data["transit"],
            underground_way_ids=underground_way_ids,
            bbox=bbox,
        )
        stops  = parsed["transit"]["stops"]
        routes = parsed["transit"]["routes"]
        n_ext  = sum(1 for s in stops  if s.get("is_external"))
        n_ic   = sum(1 for r in routes if r.get("is_intercity"))
        print(f"  Transit stops:   {len(stops)}  ({n_ext} external/intercity endpoints)")
        print(f"  Transit routes:  {len(routes)} ({n_ic} intercity)")

    # ----------------------------------------------------------------
    # 4. Fetch elevation
    # ----------------------------------------------------------------
    elevation_data = {}
    if not args.no_elevation:
        print("\nFetching terrain elevation…")
        all_coords   = OSMFetcher.collect_coords(parsed)
        elevation_data = fetcher.fetch_elevation(all_coords)
        print(f"  Elevation data: {len(elevation_data)} points")
    else:
        print("\nSkipping elevation (--no-elevation flag set) — flat terrain.")

    # ----------------------------------------------------------------
    # 5. Convert to CS2 format
    # ----------------------------------------------------------------
    print("\nConverting to CS2 format…")
    # Load optional city-specific fare overrides
    fare_overrides = None
    if args.fare_config:
        import json as _json
        try:
            with open(args.fare_config, encoding="utf-8") as f:
                fare_overrides = _json.load(f)
            print(f"  Loaded fare config from {args.fare_config}")
        except (OSError, ValueError) as e:
            print(f"  Warning: could not load fare config — {e}")

    converter = CS2Converter(
        bbox=bbox,
        elevation_data=elevation_data,
        output_dir="../data/processed",
        fare_overrides=fare_overrides,
    )

    # Print coordinate system info
    stats = converter.transformer.stats()
    print(f"  Map centre:  lat={stats['centre']['lat']}, lon={stats['centre']['lon']}")
    print(f"  City size:   {stats['city_size_m']['width']} m × {stats['city_size_m']['height']} m")
    if stats["needs_clipping"]:
        print("  ⚠ City exceeds CS2 map bounds — edge features will be clipped.")

    cs2_data: dict = {}

    if "roads" in parsed:
        cs2_data["roads"] = converter.convert_roads(parsed["roads"])
        print(f"  Roads converted:     {len(cs2_data['roads'])} segments (after clipping)")

    if "railways" in parsed:
        cs2_data["railways"] = converter.convert_railways(parsed["railways"])
        print(f"  Railways converted:  {len(cs2_data['railways'])} segments")

    if "waterways" in parsed:
        cs2_data["waterways"] = converter.convert_waterways(parsed["waterways"])
        print(f"  Waterways converted: {len(cs2_data['waterways'])} features")

    if "transit" in parsed:
        cs2_data["transit"] = converter.convert_transit(parsed["transit"])
        t = cs2_data["transit"]
        n_bus  = sum(1 for r in t["routes"] if r["type"] == "BusLine")
        n_tram = sum(1 for r in t["routes"] if r["type"] == "TramLine")
        n_rail = sum(1 for r in t["routes"] if r["type"] in ("TrainLine", "SubwayLine", "MetroLine"))
        n_ic   = sum(1 for r in t["routes"] if r.get("is_intercity"))
        print(f"  Transit stops:   {len(t['stops'])}")
        print(f"  Transit routes:  {len(t['routes'])} "
              f"(bus={n_bus}, tram={n_tram}, rail={n_rail}, intercity={n_ic})")

    # Attach coordinate metadata to the full output
    cs2_data["_meta"] = {
        "city":              city_name,
        "bbox":              {"south": bbox[0], "west": bbox[1], "north": bbox[2], "east": bbox[3]},
        "coordinate_system": stats,
        "elevation_points":  len(elevation_data),
    }

    # ----------------------------------------------------------------
    # 6. Chunk for dynamic loading
    # ----------------------------------------------------------------
    print("\nCreating spatial chunks for dynamic loading…")
    chunks = converter.create_chunks(cs2_data, chunk_size_m=args.chunk_size)

    # ----------------------------------------------------------------
    # 7. Save
    # ----------------------------------------------------------------
    print("\nSaving output…")
    safe_output = OSMFetcher._safe_filename(args.output)
    converter.save_to_file(cs2_data, f"{safe_output}_full.json")
    converter.save_to_file(chunks,   f"{safe_output}_chunks.json")

    print(f"\n✓ Done! Output written to data/processed/")
    print(f"  {safe_output}_full.json   — complete city data")
    print(f"  {safe_output}_chunks.json — {len(chunks)} spatial chunk(s)")
    print("\nNext step: load the CS2 mod and import the chunk file in-game.")


if __name__ == "__main__":
    main()
