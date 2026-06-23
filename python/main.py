"""
MapToSkylines2 — Main Entry Point
Orchestrates: OSM fetch → parse → elevation → CS2 convert → chunk → save.
"""

import argparse

from osm_fetcher import OSMFetcher
from osm_parser  import OSMParser
from pipeline import generate_city_data


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
        default="roads,railways,waterways,bus,tram,train,buildings",
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
        "--simplify-tolerance", type=float, default=2.0,
        help="Douglas-Peucker simplification tolerance in metres (0 = no simplification)"
    )
    parser.add_argument(
        "--theme", type=str, default="european",
        help="Asset theme to apply: 'european' (default) or 'none' for vanilla."
    )
    parser.add_argument(
        "--fare-config", type=str, default=None,
        help="Path to a JSON file with per-route-type fare overrides "
             "(amounts are in the CS2 in-game currency). "
             "Keys: bus, tram, train, subway, light_rail, ferry. "
             'Values: {"base_fare": 2.00, "day_pass": 7.00}'
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

    # ----------------------------------------------------------------
    # 2-6. Run the shared OSM → CS2 pipeline
    # ----------------------------------------------------------------
    print()
    result = generate_city_data(
        bbox,
        features=features,
        city_name=city_name,
        theme=args.theme,
        fetch_elevation=not args.no_elevation,
        simplify_tolerance=args.simplify_tolerance,
        chunk_size_m=args.chunk_size,
        fare_overrides=fare_overrides,
        output_dir="../data/processed",
        fetcher=fetcher,
        parser=parser_obj,
        log=lambda msg: print(msg),
    )

    cs2_data  = result["cs2_data"]
    chunks    = result["chunks"]
    converter = result["converter"]

    # ----------------------------------------------------------------
    # 7. Save
    # ----------------------------------------------------------------
    print("\nSaving output…")
    safe_output = OSMFetcher._safe_filename(args.output)
    converter.save_to_file(cs2_data, f"{safe_output}_full.json")
    converter.save_to_file(chunks,   f"{safe_output}_chunks.json")

    print("\n✓ Done! Output written to data/processed/")
    print(f"  {safe_output}_full.json   — complete city data (theme: {args.theme})")
    print(f"  {safe_output}_chunks.json — {len(chunks)} spatial chunk(s)")
    print("\nNext step: load the CS2 mod and import the chunk file in-game.")


if __name__ == "__main__":
    main()
