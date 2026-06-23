# Development Roadmap

## Phase 1: MVP - Basic Infrastructure ✅

- [x] Project structure
- [x] Python data fetcher (OSM)
- [x] Python parser (roads, railways, transit)
- [x] Python to CS2 converter
- [x] Basic mod stub/placeholder

## Phase 2: Core Functionality 🚧

### Python Side
- [x] Test OSM data fetching with real city (Monaco)
- [x] Implement proper coordinate transformation (Lat/Lon → CS2 via local tangent plane)
- [x] Terrain elevation via OpenTopoData SRTM 30m (batched, cached)
- [x] Waterways: rivers, streams, canals, lakes, reservoirs, coastline
- [x] Clipping: cities larger than 57 344 m use Shapely intersection to clip at map edge
- [x] Refine road type mapping to CS2 equivalents
- [x] Lane-width estimation + lane-count road classification (clamped to the
      vanilla 5-lane ceiling, flagged when exceeded — e.g. Texas freeways)
- [x] Name-based class hints (multilingual, e.g. Dutch *voetweg* → footpath) and
      pedestrian/alley routing to a CS2 pathway
- [x] Numbered-route refs (A12, N15) with class-based shield colour
- [x] Bike infrastructure: dedicated cycle paths + on-road bike-lane variants
- [x] Tram roads: rails embedded in a road → tram-upgraded road
- [x] Utilities flag (surface roads carry water/sewage/power; highways don't)
- [x] Railway vertical structure: ground/embankment/elevated/bridge/viaduct/cutting/tunnel
- [x] Waterway width + depth, with a min-width filter for ditches
- [x] Districts: named settlement areas (city/town/village/…)
- [x] Outside connections at the map edge (highway/rail/ship)
- [x] `--map-size` (full/half/quarter/city) to fill the whole CS2 map
- [x] Create spatial chunking algorithm (grid-based, configurable cell size)
- [x] European asset theme (roads, railways, buildings, transit, terrain/climate)
- [x] Interactive web generator + preview (one layer at a time) and CS2 import button
- [x] Shared `generate_city_data` pipeline used by both the CLI and the web generator

### CS2 Mod Side
- [x] Set up the C# project on the official PDX `IMod` framework
- [x] Data models matching the JSON export + JSON loader
- [x] Chunk manager + builder-system scaffold
- [x] Import manifest handling (unlimited money / unlock all / tiles / mods)
- [ ] Research CS2 network-creation API (tool systems / ApplyNetSystem)
- [ ] Build the road/rail network from the data in-game
- [ ] Place buildings, transit lines, districts and outside connections
- [ ] Test single chunk loading in-game

## Phase 3: Dynamic Loading

- [ ] Implement chunk manager (load/unload based on camera)
- [ ] Add LOD system (simplified geometry for distant chunks)
- [ ] Memory management and optimization
- [ ] Performance profiling and tuning
- [ ] Test with large cities

## Phase 4: Public Transit

- [ ] Transit stop placement
- [x] Bus route data: ordered in-map stops, edge stops dropped, lines cut at
      the boundary and looped back (`loop` / `cut_at_edge`); connect in-game
      with the transport line tool
- [ ] Tram line implementation
- [ ] Train/metro line implementation
- [ ] Route scheduling (if supported by CS2)

## Phase 5: Polish & Features

- [ ] In-game UI for city selection
- [ ] Configuration options (chunk distance, detail level)
- [ ] Progress indicators for loading
- [ ] Error messages and recovery
- [ ] City preview/metadata
- [ ] Multiple city management

## Phase 6: Advanced Features (Future)

- [ ] Building placement (if feasible)
- [ ] Terrain/elevation from OSM
- [ ] Water bodies and coastlines
- [ ] Parks and landmarks
- [ ] Traffic signal placement
- [ ] Real-world traffic patterns

## Known Challenges

1. **Coordinate Transformation**: Need accurate Mercator → CS2 projection
2. **CS2 API Discovery**: CS2 modding documentation may be limited
3. **Performance**: Large cities may still struggle even with chunking
4. **Road Matching**: OSM roads may not perfectly match CS2 road types
5. **Transit Complexity**: Advanced transit features may not be exposed in mod API

## Research Needed

- [ ] CS2 coordinate system and scale
- [ ] CS2 modding SDK/API documentation
- [ ] BepInEx compatibility with CS2
- [ ] Existing CS2 mods for reference
- [ ] Maximum chunk sizes before performance degrades
- [ ] Transit system limitations in CS2

## Testing Cities (Suggested)

Start small, scale up:
1. **Small**: Monaco, Vatican City
2. **Medium**: Cambridge, Santa Monica
3. **Large**: Amsterdam, San Francisco
4. **Very Large**: London, Tokyo (stress test)
