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

1. Fetch and process OSM data:
```bash
python python/main.py --city "City Name" --bbox "lat1,lon1,lat2,lon2"
```

2. Install mod in CS2 mods folder

3. Load city in-game

## Status

🚧 In Development - MVP Phase
# CitiesSkylinesOSM
