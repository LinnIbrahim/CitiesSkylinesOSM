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
- [x] Create spatial chunking algorithm (grid-based, configurable cell size)

### CS2 Mod Side
- [ ] Set up proper C# project with CS2 SDK
- [ ] Research CS2 modding API (road creation, transit, etc.)
- [ ] Implement JSON data loader
- [ ] Create basic road network builder
- [ ] Test single chunk loading in-game

## Phase 3: Dynamic Loading

- [ ] Implement chunk manager (load/unload based on camera)
- [ ] Add LOD system (simplified geometry for distant chunks)
- [ ] Memory management and optimization
- [ ] Performance profiling and tuning
- [ ] Test with large cities

## Phase 4: Public Transit

- [ ] Transit stop placement
- [ ] Bus route creation
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
