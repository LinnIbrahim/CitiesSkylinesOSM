# System Architecture

Technical architecture and design decisions for MapToSkylines2.

---

## High-Level Overview

```
┌─────────────────────────────────────────────────────────┐
│                   OpenStreetMap                          │
│              (Real-World Geographic Data)                │
└──────────────┬──────────────────────────────────────────┘
               │
               ├─ Nominatim (Geocoding)
               └─ Overpass API (Data Query)
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│              Python Data Pipeline                        │
│  ┌───────────┐   ┌──────────┐   ┌────────────────┐     │
│  │ Fetcher   │ → │  Parser  │ → │   Converter    │     │
│  └───────────┘   └──────────┘   └────────────────┘     │
│       ↓               ↓                  ↓               │
│   OSM Data    Structured Data      CS2 Format           │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│                   JSON Files                             │
│         (City Data in CS2 Format)                        │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│               CS2 Mod (C# BepInEx)                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐        │
│  │  Loader  │ → │  Chunk   │ → │ Road/Transit │        │
│  │          │   │  Manager │   │   Spawner    │        │
│  └──────────┘   └──────────┘   └──────────────┘        │
└──────────────┬──────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│            Cities: Skylines 2                            │
│               (Game World)                               │
└─────────────────────────────────────────────────────────┘
```

---

## Component Architecture

### 1. Data Fetcher (`osm_fetcher.py`)

**Responsibility**: Acquire raw OSM data from external APIs

**Dependencies**:
- `overpy` - Overpass API client
- `requests` - HTTP library

**Key Classes**:

```python
class OSMFetcher:
    def __init__(self, cache_dir)
    def fetch_city_bbox(self, city_name) → bbox
    def fetch_city_data(self, bbox, features) → dict
    def _fetch_roads(self, bbox_str) → overpy.Result
    def _fetch_railways(self, bbox_str) → overpy.Result
    def _fetch_public_transport(self, bbox_str) → overpy.Result
    def _query_with_retry(self, query) → overpy.Result
```

**Design Patterns**:
- **Retry Pattern**: Exponential backoff for API failures
- **Template Method**: Common query structure, specific feature filters

**Error Handling**:
- Retries with backoff on timeout
- Handles rate limiting
- Logs progress

**Future Enhancements**:
- Disk caching to avoid re-fetching
- Parallel fetching for independent features
- Alternative Overpass servers

---

### 2. Data Parser (`osm_parser.py`)

**Responsibility**: Transform raw OSM data into structured format

**Dependencies**:
- `overpy` - OSM data structures
- `shapely` - Geometric operations

**Key Classes**:

```python
class OSMParser:
    def __init__(self)
    def parse_roads(self, osm_result) → List[Dict]
    def parse_railways(self, osm_result) → List[Dict]
    def parse_transit_routes(self, osm_result) → Dict
    def _parse_lanes(self, tags) → int
    def _determine_stop_type(self, tags) → str
    def _parse_route_members(self, relation) → List
```

**Data Transformations**:

```
overpy.Way → {
    id, type, name,
    lanes, oneway, maxspeed,
    coordinates, geometry
}
```

**Design Decisions**:
- **Immutable Input**: Doesn't modify OSM data
- **Type Safety**: Validates all extracted values
- **Geometry Objects**: Uses shapely for future spatial operations

**Validation**:
- Minimum 2 points per way
- Lane count fallback to 2
- Safe type conversions

---

### 3. CS2 Converter (`cs2_converter.py`)

**Responsibility**: Convert parsed data to CS2 game format

**Dependencies**:
- `json` - Serialization

**Key Classes**:

```python
class CS2Converter:
    def __init__(self, output_dir)
    def convert_roads(self, roads) → List[Dict]
    def convert_railways(self, railways) → List[Dict]
    def convert_transit(self, transit_data) → Dict
    def create_chunks(self, data, chunk_size) → List[Dict]
    def save_to_file(self, data, filename)
    def _convert_coordinates(self, coords) → List[Dict]
```

**Type Mappings**:

```python
road_type_mapping = {
    "motorway": "Highway",
    "primary": "LargeRoad",
    "secondary": "MediumRoad",
    ...
}

transit_type_mapping = {
    "bus": "BusLine",
    "tram": "TramLine",
    ...
}
```

**Coordinate Transform** (Current):
```
(lon, lat) → (lon * 100000, 0, lat * 100000)
```

**Known Issues**:
- ⚠️ Simplified projection (not accurate)
- ⚠️ Elevation always 0
- ⚠️ Scale factor unknown

---

### 4. Main Orchestrator (`main.py`)

**Responsibility**: CLI and workflow coordination

**Architecture**:

```python
def main():
    parse_arguments()
    ↓
    initialize_components()
    ↓
    determine_bbox()
    ↓
    fetch_data()
    ↓
    parse_data()
    ↓
    convert_to_cs2()
    ↓
    create_chunks()
    ↓
    save_output()
```

**CLI Arguments**:
- `--city` - City name lookup
- `--bbox` - Manual bounding box
- `--features` - Feature selection
- `--output` - Output filename

**Error Flow**:
- Catches exceptions at top level
- Reports progress throughout
- Fails fast on critical errors

---

### 5. CS2 Mod (Future)

**Responsibility**: Load data into Cities: Skylines 2

**Planned Architecture**:

```csharp
namespace DynamicCityLoader
{
    [BepInPlugin]
    class Plugin : BaseUnityPlugin
    {
        void Awake()
        void OnGUI()  // UI
    }

    class CityDataLoader
    {
        CityData LoadFromFile(string path)
    }

    class ChunkManager
    {
        void UpdateLoadedChunks(Vector3 cameraPos)
        void LoadChunk(Chunk chunk)
        void UnloadChunk(Chunk chunk)
    }

    class RoadNetworkBuilder
    {
        void BuildRoad(RoadSegment road)
        void ConnectNodes(Node a, Node b)
    }

    class TransitSystemBuilder
    {
        void CreateLine(TransitRoute route)
        void PlaceStop(TransitStop stop)
    }
}
```

**Required Research**:
- CS2 road spawning API
- Transit line creation
- Node/segment structure
- Performance considerations

---

## Data Models

### Internal Data Model

```
CityData
├── roads: List[RoadSegment]
├── railways: List[RailwaySegment]
└── transit: TransitData
    ├── stops: List[TransitStop]
    └── routes: List[TransitRoute]

RoadSegment
├── id: str
├── type: str
├── name: str
├── points: List[Coordinate]
├── lanes: int
├── oneWay: bool
├── speedLimit: int
└── priority: int

Coordinate
├── x: float
├── y: float
└── z: float
```

### File Format

**Full Data** (`*_full.json`):
```json
{
  "roads": [...],
  "railways": [...],
  "transit": {...}
}
```

**Chunked Data** (`*_chunks.json`):
```json
[
  {
    "chunk_id": "chunk_0_0",
    "bounds": {x, y, width, height},
    "data": {...}
  }
]
```

---

## Design Patterns

### Pipeline Pattern
Sequential data transformation stages with clear boundaries.

```
Fetch → Parse → Convert → Save
```

Each stage:
- Single responsibility
- Independent testing
- Clear input/output

### Strategy Pattern
Different fetching/parsing strategies for different feature types.

```python
if "roads" in features:
    fetch_roads()
if "railways" in features:
    fetch_railways()
```

### Retry Pattern
Resilient API calls with exponential backoff.

```python
for attempt in range(max_retries):
    try:
        return api_call()
    except TransientError:
        wait(2 ** attempt * base_delay)
```

### Factory Pattern (Future)
Different builders for different CS2 object types.

```csharp
IBuilder builder = BuilderFactory.Create(roadType);
builder.Build(roadData);
```

---

## Scalability Considerations

### Current Limitations
- Single-threaded processing
- Loads entire city in memory
- Single chunk output
- No progress persistence

### Scaling Strategy

**For Large Cities**:

1. **Chunking**:
   ```
   ┌─────┬─────┬─────┐
   │ 0,0 │ 1,0 │ 2,0 │
   ├─────┼─────┼─────┤
   │ 0,1 │ 1,1 │ 2,1 │
   └─────┴─────┴─────┘
   ```
   - Grid-based spatial division
   - Independent processing
   - Parallel loading in CS2

2. **Streaming**:
   - Process features as fetched
   - Don't hold entire city in memory
   - Generator patterns

3. **Caching**:
   - Save raw OSM data
   - Avoid re-fetching
   - Incremental updates

4. **Parallel Processing**:
   - Fetch different features in parallel
   - Convert chunks in parallel
   - Multi-threaded I/O

---

## Performance Optimization

### Current Performance

**Monaco (Small)**:
- Fetch: ~25s
- Parse: <1s
- Convert: <1s
- Total: ~30s

**Bottlenecks**:
1. Overpass API query time (20-25s)
2. Rate limiting delays
3. Network latency

### Optimization Opportunities

**Python Side**:
- [ ] Parallel feature fetching
- [ ] Local Overpass instance
- [ ] Compiled coordinate transform (Cython)
- [ ] Lazy loading with generators
- [ ] Binary output format (MessagePack)

**CS2 Mod Side**:
- [ ] Background loading thread
- [ ] Object pooling
- [ ] LOD (Level of Detail)
- [ ] Occlusion culling
- [ ] Simplified geometry for distant chunks

---

## Error Handling Strategy

### Levels

1. **Transient Errors** → Retry
   - Network timeouts
   - Server busy
   - Rate limits

2. **Validation Errors** → Skip + Log
   - Invalid coordinates
   - Missing required fields
   - Malformed data

3. **Fatal Errors** → Fail Fast
   - Invalid bounding box
   - No data returned
   - Disk write failure

### Logging

```
INFO  - Normal progress
WARN  - Recoverable issues (retry, skip)
ERROR - Fatal errors (abort)
```

---

## Security Considerations

### Current
- No authentication required
- Public APIs only
- Read-only operations
- No user data stored

### Future
- Validate JSON before loading in CS2
- Sanitize city names (path traversal)
- Limit file sizes (DoS prevention)
- Sandbox mod operations

---

## Testing Strategy

### Unit Tests (Not Implemented)
```python
# test_osm_parser.py
def test_parse_road_with_valid_data()
def test_parse_road_handles_missing_name()
def test_coordinate_transform()
```

### Integration Tests
- End-to-end pipeline with Monaco
- Validate output JSON structure
- Check data integrity

### Performance Tests (Future)
- Benchmark with various city sizes
- Memory profiling
- CS2 loading performance

---

## Deployment

### Python Pipeline
**Distribution**:
- Source code + requirements.txt
- No compilation needed
- Cross-platform (Mac/Linux/Windows)

**Installation**:
```bash
pip3 install -r requirements.txt
python3 main.py --city "CityName"
```

### CS2 Mod (Future)
**Distribution**:
- Compiled DLL
- Via mod manager or manual install

**Installation**:
```
1. Install BepInEx
2. Copy DLL to BepInEx/plugins/
3. Copy data files to mod folder
4. Launch CS2
```

---

## Future Architecture Improvements

### Short Term
1. Implement proper coordinate projection
2. Add spatial chunking algorithm
3. Elevation data integration
4. Caching layer

### Medium Term
5. Parallel processing
6. Progress persistence
7. Incremental updates
8. Web preview interface

### Long Term
9. Distributed processing
10. Real-time updates
11. Multi-city management
12. Cloud deployment

---

## Technology Stack

### Python Pipeline
- **Language**: Python 3.9+
- **APIs**: Overpass, Nominatim
- **Geospatial**: shapely, geopy
- **Data**: pandas, numpy
- **I/O**: json, requests

### CS2 Mod (Planned)
- **Language**: C# (.NET)
- **Framework**: BepInEx
- **Serialization**: JSON.NET
- **Game Engine**: Unity (CS2)

### Data Formats
- **OSM**: XML/JSON
- **Output**: JSON
- **Future**: Binary (MessagePack, Protocol Buffers)

---

## Dependencies Graph

```
main.py
├── osm_fetcher.py
│   ├── overpy
│   └── requests
├── osm_parser.py
│   ├── overpy
│   └── shapely
└── cs2_converter.py
    └── json

CS2 Mod (Future)
├── BepInEx
├── Harmony
├── Newtonsoft.Json
└── CS2 Game Assemblies
```

---

## Extensibility Points

### New Features
1. **New OSM Features**:
   - Add fetch method in `osm_fetcher.py`
   - Add parse method in `osm_parser.py`
   - Add convert method in `cs2_converter.py`

2. **New Output Formats**:
   - Subclass `CS2Converter`
   - Implement `save_to_file()`

3. **New Data Sources**:
   - Implement fetcher interface
   - Standardize output format

### Plugin System (Future)
```python
class DataSourcePlugin:
    def fetch(self, bbox) → RawData
    def parse(self, raw) → StructuredData

register_plugin("OSM", OSMPlugin())
register_plugin("GeoJSON", GeoJSONPlugin())
```

---

## Documentation Standards

### Code Comments
- Docstrings for all public methods
- Type hints where applicable
- Explain "why" not "what"

### Architecture Docs
- Keep updated with major changes
- Version with git
- Explain design decisions

---

## Conclusion

This architecture provides:
- ✅ Modular, testable components
- ✅ Clear separation of concerns
- ✅ Extensibility for new features
- ✅ Scalability path for large cities
- ⚠️ Needs CS2 integration research
- ⚠️ Coordinate transform improvement required

The foundation is solid for the MVP. Next step: integrate with CS2.
