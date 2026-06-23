# MapToSkylines2

Transform real-world city maps into Cities: Skylines 2 builds with public transportation.

## Overview

This project converts OpenStreetMap data into Cities: Skylines 2 mod format, with dynamic loading to handle the game's performance limitations.

## Architecture

### Components

1. **Python Data Processor** (`/python`)
   - Fetch city data from OpenStreetMap
   - Parse roads, railways, tram lines, bus routes
   - Convert to CS2-compatible format
   - Generate chunked data for dynamic loading

2. **CS2 Mod** (`/mod`)
   - Dynamic city loader
   - Loads map chunks progressively
   - Handles road networks and transit systems

3. **Data Storage** (`/data`)
   - Cached OSM data
   - Processed CS2 data chunks

## MVP Features

- [x] Project structure
- [ ] OSM data fetcher
- [ ] Road network parser
- [ ] Public transit parser (bus, tram, train)
- [ ] CS2 format converter
- [ ] Dynamic loading mod
- [ ] Chunking/LOD system for performance

## Tech Stack

- **Python 3.x** - Data processing
- **C#** - CS2 mod development
- **OpenStreetMap API** - Map data source

## Getting Started

### Prerequisites

```bash
# Python dependencies
pip install -r python/requirements.txt
```

### Usage

#### Option A — Interactive generator (recommended)

Launch the browser-based selector, **drag the red box** (locked to the
Cities: Skylines 2 map size, 57.3 × 57.3 km) over the area you want on the real
OpenStreetMap, then click **Generate**. The server fetches live OSM data and
transforms roads, terrain, transit stops and buildings into European-themed
CS2 assets, drawing the converted result straight back on the map.

```bash
cd python
python generate_server.py            # opens http://127.0.0.1:8001
python generate_server.py --no-elevation   # faster (flat terrain)
```

- **Map size** — pick the full CS2 map or a half/quarter selection.
- **Theme** — `European` (default) tags every asset with its EU prefab, or
  `None` for vanilla/region-neutral output.
- Output JSON (`selection_full.json`, `selection_chunks.json`) is written to
  `data/processed/`.
- **Import to Cities: Skylines 2** — after generating, tick the options
  (unlimited money, unlock all, all map tiles, enable mods) and click
  **Import into CS2 folder**. The files are copied to the
  `DynamicCityLoader/data` mod folder along with an `import_manifest.json` that
  the mod reads on load.

> Set `CS2_MODS_DIR` to your Cities: Skylines II `Mods` folder so Import
> targets the game directly; otherwise files go to a local `data/cs2_import/`
> staging folder for you to copy in manually.
>
> **Why unlimited money / unlock all:** a 1:1 real-world city is huge, and
> pegged finances drain on road upkeep before you can build anything — so the
> import defaults these on. **Map tiles:** the base game caps the purchasable
> area below a full map, so playing the whole import needs a tiles-unlock mod.

#### Option B — Command line

```bash
python python/main.py --city "City Name"
python python/main.py --bbox "south,west,north,east" --theme european
```

Then preview an existing result on a map (the preview also has the same
**Import into CS2 folder** button as the generator):

```bash
python python/preview_server.py      # auto-finds the latest *_full.json
```

#### Install & play

1. Install the mod in the CS2 mods folder
2. Load the city in-game

## Status

🚧 In Development — Phase 2: Python pipeline complete, CS2 mod loader in progress.

See [ROADMAP.md](ROADMAP.md) for the full plan and [docs/PROGRESS.md](docs/PROGRESS.md)
for the latest progress report.
