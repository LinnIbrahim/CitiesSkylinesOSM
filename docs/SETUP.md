# Setup Guide

Complete guide to setting up the MapToSkylines2 development environment.

---

## Prerequisites

### Required
- **Python 3.9+** (tested with 3.9.6)
- **pip3** for package management
- Internet connection (for OSM data)

### For CS2 Mod Development (Future)
- **Cities: Skylines 2** game
- **.NET SDK** (version TBD)
- **BepInEx** (version TBD)
- **CS2 Modding SDK** (location TBD)

---

## Installation

### 1. Clone/Download Project

```bash
cd ~/Desktop
# Project is in MapToSkylines2/
cd MapToSkylines2
```

### 2. Install Python Dependencies

On macOS, use `python3` and `pip3`:

```bash
cd python
pip3 install -r requirements.txt
```

**Expected packages**:
- overpy (OSM Overpass API)
- osmapi (OSM API wrapper)
- shapely (geospatial operations)
- geopy (geocoding)
- pandas (data handling)
- numpy (numerical operations)
- requests (HTTP)
- xmltodict (XML parsing)

**Installation time**: ~2-3 minutes

### 3. Verify Installation

```bash
python3 -c "import overpy, shapely, geopy; print('✓ All packages imported successfully')"
```

---

## Project Structure

```
MapToSkylines2/
├── README.md              # Project overview
├── ROADMAP.md             # Development roadmap
├── .gitignore             # Git ignore rules
│
├── docs/                  # Documentation (this folder)
│   ├── PROGRESS.md        # Current progress
│   ├── SETUP.md           # This file
│   ├── TESTING.md         # Test results
│   ├── API_NOTES.md       # API documentation
│   └── ARCHITECTURE.md    # Technical architecture
│
├── python/                # Python data pipeline
│   ├── requirements.txt   # Dependencies
│   ├── main.py           # Entry point
│   ├── osm_fetcher.py    # OSM data fetcher
│   ├── osm_parser.py     # OSM parser
│   └── cs2_converter.py  # CS2 converter
│
├── mod/                   # CS2 mod
│   └── DynamicCityLoader/
│       ├── README.md
│       └── Plugin.cs      # Mod code (stub)
│
└── data/                  # Data storage
    ├── osm/              # Cached OSM data
    └── processed/        # Converted CS2 data
```

---

## Usage

### Basic Usage

Fetch and convert a city:

```bash
cd python
python3 main.py --city "CityName"
```

### Examples

**Small city (recommended for first test)**:
```bash
python3 main.py --city "Monaco"
```

**Specific features only**:
```bash
python3 main.py --city "Monaco" --features "roads,railways"
```

**Custom bounding box**:
```bash
python3 main.py --bbox "43.5,7.4,43.7,7.5" --output "custom_area"
```

**All features** (be careful of rate limits):
```bash
python3 main.py --city "Amsterdam" --features "roads,railways,bus,tram,train"
```

### Command-Line Options

```
--city CITY_NAME          Name of city to fetch (e.g., "London")
--bbox "S,W,N,E"         Bounding box coordinates
--features "feat1,feat2" Features to fetch (roads,railways,bus,tram,train)
--output FILENAME        Output filename prefix
```

---

## Output

### Generated Files

After running, you'll find in `data/processed/`:

1. **`{output}_full.json`**
   - Complete city data in CS2 format
   - All roads, railways, transit
   - Ready for mod to load

2. **`{output}_chunks.json`**
   - Same data divided into spatial chunks
   - For dynamic loading
   - Currently single chunk (needs improvement)

### File Structure

```json
{
  "roads": [
    {
      "id": "road_123456",
      "type": "MediumRoad",
      "name": "Main Street",
      "points": [{x, y, z}, ...],
      "lanes": 2,
      "oneWay": false,
      "speedLimit": 50,
      "priority": 2
    }
  ],
  "railways": [...],
  "transit": {
    "stops": [...],
    "routes": [...]
  }
}
```

---

## Troubleshooting

### "zsh: command not found: python"

Use `python3` instead:
```bash
python3 main.py --city "Monaco"
```

### "zsh: command not found: pip"

Use `pip3` instead:
```bash
pip3 install -r requirements.txt
```

### "OverpassGatewayTimeout: Server load too high"

The OSM server is busy. The script will retry automatically. If it keeps failing:
- Wait 5-10 minutes
- Try a smaller city
- Reduce features: `--features "roads"`

### "OverpassTooManyRequests: Too many requests"

You've hit the rate limit. Solutions:
- Wait 10-15 minutes before trying again
- Use fewer features: `--features "roads,railways"`
- Add longer delays in code

### SSL/urllib3 Warning

```
NotOpenSSLWarning: urllib3 v2 only supports OpenSSL 1.1.1+
```

This is cosmetic and can be ignored. It doesn't break functionality.

### No Data Returned

If parsing shows 0 roads/railways:
- City name might be misspelled
- Try using `--bbox` with exact coordinates
- Check if city exists in OSM

### Large Files / Out of Memory

For very large cities:
- Process in smaller bounding boxes
- Reduce features
- Increase chunking granularity (future feature)

---

## Development Setup

### Python Development

For editing the Python code:

```bash
cd python
# Edit with your preferred editor
code .  # VS Code
vim osm_fetcher.py
```

**Recommended extensions**:
- Python linter (pylint, flake8)
- Type hints support

### Testing Changes

Quick test after changes:
```bash
python3 main.py --city "Monaco" --features "roads" --output "test"
```

---

## CS2 Mod Setup (Future)

**Status**: Not yet implemented. Waiting for:
- CS2 modding SDK documentation
- BepInEx setup guide
- Example CS2 mods for reference

**Planned steps**:
1. Install BepInEx for CS2
2. Set up C# project with CS2 references
3. Build Plugin.cs
4. Copy to CS2 mods folder
5. Test in-game

---

## Performance Tips

### Faster Fetching
- Start with small cities
- Use fewer features initially
- Cache would help (not implemented yet)

### Avoiding Rate Limits
- Wait 2-3 minutes between runs
- Don't run multiple instances
- Consider local Overpass instance for heavy development

### Disk Space
- Each city: ~1-10 MB depending on size
- London/Tokyo could be 50-100+ MB
- Clear `data/processed/` periodically

---

## Environment

**Tested on**:
- macOS Darwin 25.2.0 (Apple Silicon)
- Python 3.9.6
- pip 21.2.4

**Should work on**:
- macOS (Intel/ARM)
- Linux
- Windows (use `python` instead of `python3`)

---

## Next Steps After Setup

1. **Test the pipeline**:
   ```bash
   python3 main.py --city "Monaco" --features "roads,railways"
   ```

2. **Check output**:
   ```bash
   ls -lh ../data/processed/
   cat ../data/processed/monaco_test_full.json | head -50
   ```

3. **Try your city**:
   ```bash
   python3 main.py --city "YourCity"
   ```

4. **Read documentation**:
   - `docs/TESTING.md` - See test results
   - `docs/ARCHITECTURE.md` - Understand the design
   - `docs/API_NOTES.md` - API reference

---

## Getting Help

**Issues?**
1. Check this SETUP.md
2. Check PROGRESS.md for known issues
3. Check the error message carefully
4. Try with a smaller city (Monaco)
5. Wait if rate-limited

**Common causes**:
- Using `python` instead of `python3`
- Rate limiting (wait 10 minutes)
- City name not found (try bbox)
- No internet connection
