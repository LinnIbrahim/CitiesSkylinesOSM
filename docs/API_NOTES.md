# API Reference & Notes

Technical documentation for APIs and data formats used in MapToSkylines2.

---

## OpenStreetMap (OSM)

### Overpass API

**Endpoint**: `https://overpass-api.de/api/interpreter`

**Purpose**: Query OSM data by geographic area and feature type.

#### Query Format

```
[out:json][timeout:180];
(
  way["highway"~"motorway|primary|secondary"](<bbox>);
);
out body;
>;
out skel qt;
```

#### Bounding Box Format
`(south,west,north,east)` - Decimal degrees

Example: `(43.5165358, 7.4090279, 43.7519173, 7.5329917)` for Monaco

#### Rate Limits
- **Unknown exact limits** - appears to be request-based and time-based
- **Observed**: ~3-5 queries per minute safe
- **Cooldown**: 10-15 minutes if rate limited
- **Timeout**: 90-180 seconds per query recommended

#### Error Codes

| Error | Meaning | Solution |
|-------|---------|----------|
| `OverpassGatewayTimeout` | Server busy | Retry with backoff |
| `OverpassTooManyRequests` | Rate limited | Wait 10-15 minutes |
| `OverpassBadRequest` | Invalid query | Check query syntax |

#### Best Practices
- Use specific feature filters (not `*`)
- Limit bounding box size for large cities
- Add timeout directives
- Implement exponential backoff
- Add delays between different feature queries

---

### Nominatim API

**Endpoint**: `https://nominatim.openstreetmap.org/search`

**Purpose**: Geocode city names to bounding boxes.

#### Parameters
```python
{
  "q": "Monaco",           # Search query
  "format": "json",        # Response format
  "limit": 1               # Max results
}
```

#### Headers
```python
{
  "User-Agent": "MapToSkylines2/0.1"  # Required!
}
```

#### Response
```json
{
  "boundingbox": ["43.5165358", "43.7519173", "7.4090279", "7.5329917"],
  "lat": "43.7384176",
  "lon": "7.4246158",
  "display_name": "Monaco"
}
```

**Note**: Nominatim returns `[south, north, west, east]` - different order than Overpass!

#### Rate Limits
- **1 request per second**
- **User-Agent required**
- Commercial use requires own instance

---

## OSM Data Model

### Highway (Roads)

**Tag**: `highway=*`

#### Road Types (Relevant)
| OSM Type | Description | CS2 Equivalent (Approx) |
|----------|-------------|------------------------|
| `motorway` | Highway/freeway | Highway |
| `trunk` | Major road | Highway |
| `primary` | Primary road | LargeRoad |
| `secondary` | Secondary road | MediumRoad |
| `tertiary` | Tertiary road | SmallRoad |
| `residential` | Residential street | SmallRoad |
| `service` | Service road | TinyRoad |

#### Properties
```json
{
  "highway": "primary",
  "name": "Main Street",
  "lanes": "2",
  "oneway": "yes",
  "maxspeed": "50",
  "surface": "asphalt"
}
```

### Railway

**Tag**: `railway=*`

#### Types
| OSM Type | Description | CS2 Equivalent (Approx) |
|----------|-------------|------------------------|
| `rail` | Standard rail | Train |
| `light_rail` | Light rail | Metro |
| `subway` | Subway/metro | Subway |
| `tram` | Tramway | Tram |

#### Properties
```json
{
  "railway": "tram",
  "name": "Line 1",
  "gauge": "1435",
  "electrified": "contact_line",
  "voltage": "750"
}
```

### Public Transport

#### Stop Tags
- `public_transport=stop_position` - Where vehicle stops
- `highway=bus_stop` - Bus stop
- `railway=tram_stop` - Tram stop

#### Route Relations
```
type=route
route=bus|tram|train|subway
```

**Members**:
- Nodes: Stops along route
- Ways: Road/rail segments used
- Role: `stop`, `platform`, empty for route segments

---

## CS2 Data Format (Current)

### Coordinate System

**Current** (Simplified):
```python
x = longitude * 100000
y = 0  # Elevation placeholder
z = latitude * 100000
```

**Required** (Future):
- Proper Mercator projection
- CS2 coordinate space mapping
- Elevation from terrain or OSM

### Road Object

```json
{
  "id": "road_4097656",
  "type": "MediumRoad",
  "name": "Avenue Princesse Alice",
  "points": [
    {"x": 742598.81, "y": 0, "z": 4373891.56},
    {"x": 742590.55, "y": 0, "z": 4373896.67}
  ],
  "lanes": 2,
  "oneWay": false,
  "speedLimit": 50,
  "priority": 2
}
```

### Railway Object

```json
{
  "id": "rail_123456",
  "type": "Tram",
  "name": "Tram Line 1",
  "points": [
    {"x": 742000.0, "y": 0, "z": 4373000.0}
  ],
  "electrified": true
}
```

### Transit Stop

```json
{
  "id": "stop_789",
  "name": "Central Station",
  "type": "bus",
  "position": {"x": 742000.0, "y": 0, "z": 4373000.0}
}
```

### Transit Route

```json
{
  "id": "route_101",
  "name": "Route 1 - Downtown",
  "number": "1",
  "type": "BusLine",
  "operator": "City Transit",
  "stops": ["stop_1", "stop_2", "stop_3"]
}
```

### Chunk Format

```json
{
  "chunk_id": "chunk_0_0",
  "bounds": {
    "x": 0,
    "y": 0,
    "width": 1000,
    "height": 1000
  },
  "data": {
    "roads": [...],
    "railways": [...],
    "transit": {...}
  }
}
```

---

## Cities: Skylines 2 Modding (Research Needed)

### Unknown / To Research

- [ ] **Coordinate System**
  - Scale factor
  - Origin point
  - Coordinate ranges
  - Elevation encoding

- [ ] **Road API**
  - Road prefab names
  - How to spawn roads programmatically
  - Node/segment structure
  - Connection logic

- [ ] **Transit API**
  - How to create transit lines
  - Stop placement
  - Route definition
  - Vehicle assignment

- [ ] **Modding Framework**
  - BepInEx version
  - Harmony patches needed
  - Game assemblies to reference
  - Available hooks/events

- [ ] **Performance Limits**
  - Max roads/segments
  - Max transit lines
  - Chunk loading impact
  - Memory constraints

### Resources to Find

- [ ] CS2 Modding documentation
- [ ] CS2 SDK/API reference
- [ ] Example mods (road tools, transit tools)
- [ ] Community Discord/forums
- [ ] Data structure documentation

### Assumptions (To Verify)

1. **BepInEx compatible** - Most Unity games are
2. **JSON readable in C#** - Standard practice
3. **Dynamic spawning possible** - Common in city builders
4. **Road types match names** - "Highway", "LargeRoad" etc.
5. **Transit system exposed** - Needed for gameplay

---

## Data Flow

```
OSM (Real World)
    ↓
[Nominatim API] → Bounding Box
    ↓
[Overpass API] → OSM XML/JSON
    ↓
[osm_fetcher.py] → Python objects (overpy.Result)
    ↓
[osm_parser.py] → Structured dicts
    ↓
[cs2_converter.py] → CS2 format JSON
    ↓
[JSON Files] → Disk storage
    ↓
[CS2 Mod] → Load into game (Future)
    ↓
CS2 (Game World)
```

---

## Coordinate Transformation (Detailed)

### Current Implementation

```python
def _convert_coordinate(coord):
    lon, lat = coord
    return {
        "x": lon * 100000,
        "y": 0,
        "z": lat * 100000
    }
```

**Problems**:
- Not a proper projection
- Distortion increases with latitude
- Elevation ignored
- Scale unknown

### Required Implementation

**Web Mercator Projection**:
```python
from pyproj import Transformer

# WGS84 (lat/lon) to Web Mercator
transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")

def transform(lon, lat):
    x, y = transformer.transform(lat, lon)
    # Then scale to CS2 units (unknown factor)
    return {
        "x": x * CS2_SCALE_FACTOR,
        "y": 0,  # Or elevation from terrain
        "z": y * CS2_SCALE_FACTOR
    }
```

**Needs**:
- CS2_SCALE_FACTOR (unknown)
- Elevation data source
- Origin point alignment

---

## Error Handling

### Python Pipeline

**Retry Logic**:
```python
max_retries = 3
backoff = [10, 20, 40]  # seconds

for attempt in range(max_retries):
    try:
        result = api.query(query)
        return result
    except (Timeout, RateLimit):
        if attempt < max_retries - 1:
            sleep(backoff[attempt])
        else:
            raise
```

**Validation**:
- Bounding box sanity checks
- Road has ≥2 points
- No null coordinates
- Valid JSON output

---

## Performance Considerations

### Query Optimization
- Specific filters vs broad queries
- Smaller bounding boxes
- Separate queries for different features
- Timeout tuning

### Data Processing
- Stream processing for large cities
- Lazy loading
- Chunk-based conversion
- Progress indicators

### Memory
- Don't load entire city at once
- Process by feature type
- Clear intermediate data
- Generator patterns for iteration

---

## Standards & Conventions

### Naming
- OSM IDs prefixed: `road_123`, `rail_456`, `stop_789`
- Chunk IDs: `chunk_x_y` format
- Files: `{cityname}_{type}.json`

### Units
- Coordinates: Game units (unknown scale)
- Speed: km/h
- Elevation: Meters (future)
- Distance: Meters (future)

### Encoding
- UTF-8 for all files
- JSON with 2-space indent
- No escaped Unicode (`ensure_ascii=False`)

---

## Future API Integrations

### Potential
- **SRTM/Terrain**: Elevation data
- **Local Overpass**: Avoid rate limits
- **Building data**: OSM building footprints
- **Traffic data**: Real-world patterns
- **Transit schedules**: GTFS integration

### Nice to Have
- Preview renderer (folium/matplotlib)
- Web interface for city selection
- Progress API for mod
- Telemetry/analytics
