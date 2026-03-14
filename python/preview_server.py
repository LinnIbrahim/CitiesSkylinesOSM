#!/usr/bin/env python3
"""
Web Preview Server for MapToSkylines2

Reads a CS2-format JSON file (_full.json), reverse-projects coordinates
back to lat/lon, and serves an interactive Leaflet map for visual validation.

Usage:
    python preview_server.py                          # auto-finds latest _full.json
    python preview_server.py path/to/city_full.json   # specify file
    python preview_server.py --port 8080              # custom port
"""

import argparse
import glob
import json
import math
import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def reverse_project(x, z, lat_centre, lon_centre):
    """CS2 (x, z) → (lat, lon). Inverse of the local tangent plane projection."""
    m_per_lat = 111_320.0
    m_per_lon = 111_320.0 * math.cos(math.radians(lat_centre))
    lat = lat_centre - z / m_per_lat   # z is negated in the forward transform
    lon = lon_centre + x / m_per_lon
    return round(lat, 7), round(lon, 7)


def cs2_to_geojson(cs2_data):
    """Convert CS2-format city data to a GeoJSON FeatureCollection for Leaflet."""
    meta = cs2_data.get("_meta", {})
    coord_sys = meta.get("coordinate_system", {})
    centre = coord_sys.get("centre", {})
    lat_c = centre.get("lat", 0)
    lon_c = centre.get("lon", 0)

    features = []

    def _rev(pt):
        return reverse_project(pt["x"], pt["z"], lat_c, lon_c)

    # --- Roads ---
    for road in cs2_data.get("roads", []):
        pts = road.get("points", [])
        if len(pts) < 2:
            continue
        coords = [list(reversed(_rev(p))) for p in pts]  # [lon, lat]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "layer": "roads",
                "id": road.get("id", ""),
                "name": road.get("name", ""),
                "cs2_type": road.get("type", ""),
                "lanes": road.get("lanes", 0),
                "oneWay": road.get("oneWay", False),
                "speedLimit": road.get("speedLimit", 0),
                "priority": road.get("priority", 0),
            },
        })

    # --- Railways ---
    for rail in cs2_data.get("railways", []):
        pts = rail.get("points", [])
        if len(pts) < 2:
            continue
        coords = [list(reversed(_rev(p))) for p in pts]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "layer": "railways",
                "id": rail.get("id", ""),
                "name": rail.get("name", ""),
                "cs2_type": rail.get("type", ""),
                "electrified": rail.get("electrified", False),
            },
        })

    # --- Waterways ---
    for ww in cs2_data.get("waterways", []):
        pts = ww.get("points", [])
        if len(pts) < 2:
            continue
        coords = [list(reversed(_rev(p))) for p in pts]
        is_area = ww.get("isArea", False)

        if is_area and len(coords) >= 4:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [coords]},
                "properties": {
                    "layer": "waterways",
                    "id": ww.get("id", ""),
                    "name": ww.get("name", ""),
                    "cs2_type": ww.get("type", ""),
                    "isArea": True,
                },
            })
        else:
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "layer": "waterways",
                    "id": ww.get("id", ""),
                    "name": ww.get("name", ""),
                    "cs2_type": ww.get("type", ""),
                    "isArea": False,
                },
            })

    # --- Buildings ---
    for bldg in cs2_data.get("buildings", []):
        pts = bldg.get("points", [])
        if len(pts) < 4:
            continue
        coords = [list(reversed(_rev(p))) for p in pts]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {
                "layer": "buildings",
                "id": bldg.get("id", ""),
                "name": bldg.get("name", ""),
                "zone": bldg.get("zone", ""),
                "height": bldg.get("height", 0),
                "levels": bldg.get("levels", 0),
            },
        })

    # --- Transit stops ---
    transit = cs2_data.get("transit", {})
    for stop in transit.get("stops", []):
        pos = stop.get("position", {})
        lat, lon = _rev(pos)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "layer": "transit_stops",
                "id": stop.get("id", ""),
                "name": stop.get("name", ""),
                "stop_type": stop.get("type", ""),
                "is_external": stop.get("is_external", False),
                "is_underground": stop.get("is_underground", False),
                "has_shelter": stop.get("has_shelter", False),
                "wheelchair": stop.get("wheelchair", ""),
            },
        })

    # --- Transit routes (as metadata only, no geometry) ---
    route_list = []
    for route in transit.get("routes", []):
        route_list.append({
            "id": route.get("id", ""),
            "name": route.get("name", ""),
            "number": route.get("number", ""),
            "type": route.get("type", ""),
            "from": route.get("from", ""),
            "to": route.get("to", ""),
            "is_intercity": route.get("is_intercity", False),
            "stops": route.get("stops", []),
            "fare": route.get("fare", {}),
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "_meta": meta,
        "_routes": route_list,
    }


# ---------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MapToSkylines2 — Preview</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
#map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; }

#panel {
    position: absolute; top: 10px; right: 10px; z-index: 1000;
    background: rgba(255,255,255,0.95); border-radius: 8px;
    padding: 14px 16px; max-width: 320px; max-height: calc(100vh - 40px);
    overflow-y: auto; box-shadow: 0 2px 12px rgba(0,0,0,0.2);
    font-size: 13px;
}
#panel h2 { font-size: 15px; margin-bottom: 8px; }
#panel h3 { font-size: 13px; margin: 10px 0 4px; color: #555; }
.stat { display: flex; justify-content: space-between; padding: 2px 0; }
.stat .label { color: #666; }
.stat .value { font-weight: 600; }

.layer-toggle { display: flex; align-items: center; gap: 6px; padding: 3px 0; }
.layer-toggle input { margin: 0; }
.legend-swatch {
    display: inline-block; width: 14px; height: 4px; border-radius: 2px;
    vertical-align: middle;
}
.legend-swatch.circle { width: 8px; height: 8px; border-radius: 50%; }
.legend-swatch.polygon { width: 12px; height: 10px; border-radius: 1px; }

#info {
    position: absolute; bottom: 10px; left: 10px; z-index: 1000;
    background: rgba(255,255,255,0.95); border-radius: 8px;
    padding: 10px 14px; max-width: 400px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    font-size: 12px; display: none;
}
#info .close { float: right; cursor: pointer; font-size: 16px; color: #999; }
#info table { border-collapse: collapse; width: 100%; margin-top: 4px; }
#info td { padding: 2px 6px; border-bottom: 1px solid #eee; }
#info td:first-child { color: #666; white-space: nowrap; }

#cs2-bounds { stroke: #e74c3c; stroke-width: 2; stroke-dasharray: 8,6; fill: none; }
</style>
</head>
<body>
<div id="map"></div>

<div id="panel">
    <h2 id="city-title">MapToSkylines2 Preview</h2>
    <div id="stats"></div>
    <h3>Layers</h3>
    <div id="layers"></div>
    <h3>Routes</h3>
    <div id="routes-info" style="max-height:200px;overflow-y:auto;font-size:11px;"></div>
</div>

<div id="info">
    <span class="close" onclick="document.getElementById('info').style.display='none'">&times;</span>
    <strong id="info-title"></strong>
    <table id="info-table"></table>
</div>

<script>
// Data is injected by the server at /api/geojson
let DATA = null;
let map, layerGroups = {}, boundsRect;

const LAYER_CONFIG = {
    roads:         { color: '#3498db', weight: 2.5, label: 'Roads',     swatch: 'line' },
    railways:      { color: '#e67e22', weight: 3,   label: 'Railways',  swatch: 'line' },
    waterways:     { color: '#2980b9', weight: 2,   label: 'Waterways', swatch: 'line' },
    buildings:     { color: '#9b59b6', weight: 1,   label: 'Buildings', swatch: 'polygon', fillOpacity: 0.35 },
    transit_stops: { color: '#e74c3c', weight: 0,   label: 'Stops',     swatch: 'circle', radius: 5 },
    cs2_bounds:    { color: '#e74c3c', weight: 2,   label: 'CS2 Map Edge', swatch: 'line', dashArray: '8,6' },
};

const ROAD_COLORS = {
    Highway:   '#c0392b',
    LargeRoad: '#e67e22',
    MediumRoad:'#f39c12',
    SmallRoad: '#3498db',
    TinyRoad:  '#95a5a6',
};

const STOP_COLORS = {
    bus:   '#27ae60',
    tram:  '#e67e22',
    train: '#c0392b',
    subway:'#8e44ad',
    stop:  '#7f8c8d',
};

function init() {
    map = L.map('map', { zoomControl: true });
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
    }).addTo(map);

    fetch('/api/geojson')
        .then(r => r.json())
        .then(data => { DATA = data; render(); })
        .catch(e => { document.getElementById('city-title').textContent = 'Error loading data: ' + e; });
}

function render() {
    const meta = DATA._meta || {};
    const bbox = meta.bbox || {};
    const coordSys = meta.coordinate_system || {};

    // Title
    document.getElementById('city-title').textContent = (meta.city || 'City') + ' — Preview';

    // Stats
    const statsDiv = document.getElementById('stats');
    const counts = {};
    DATA.features.forEach(f => {
        const l = f.properties.layer;
        counts[l] = (counts[l] || 0) + 1;
    });
    let statsHTML = '';
    const citySize = coordSys.city_size_m || {};
    if (citySize.width) {
        statsHTML += `<div class="stat"><span class="label">City size</span><span class="value">${(citySize.width/1000).toFixed(1)} × ${(citySize.height/1000).toFixed(1)} km</span></div>`;
    }
    if (coordSys.needs_clipping) {
        statsHTML += `<div class="stat"><span class="label">Clipping</span><span class="value" style="color:#e74c3c">Active</span></div>`;
    }
    Object.entries(counts).forEach(([layer, count]) => {
        const cfg = LAYER_CONFIG[layer] || {};
        statsHTML += `<div class="stat"><span class="label">${cfg.label || layer}</span><span class="value">${count.toLocaleString()}</span></div>`;
    });
    statsHTML += `<div class="stat"><span class="label">Routes</span><span class="value">${(DATA._routes || []).length}</span></div>`;
    statsDiv.innerHTML = statsHTML;

    // Create layer groups
    Object.keys(LAYER_CONFIG).forEach(key => {
        layerGroups[key] = L.layerGroup().addTo(map);
    });

    // Add features to layers
    DATA.features.forEach(f => {
        const layer = f.properties.layer;
        const geom = f.geometry;
        let leafletLayer;

        if (geom.type === 'Point') {
            const [lon, lat] = geom.coordinates;
            const stopType = f.properties.stop_type || 'stop';
            const color = STOP_COLORS[stopType] || STOP_COLORS.stop;
            const radius = f.properties.is_external ? 7 : 5;
            leafletLayer = L.circleMarker([lat, lon], {
                radius: radius,
                color: color,
                fillColor: color,
                fillOpacity: 0.8,
                weight: f.properties.is_external ? 2 : 1,
            });
        } else if (geom.type === 'LineString') {
            const coords = geom.coordinates.map(c => [c[1], c[0]]);
            let color, weight;
            if (layer === 'roads') {
                color = ROAD_COLORS[f.properties.cs2_type] || '#3498db';
                weight = f.properties.priority >= 3 ? 4 : f.properties.priority >= 1 ? 2.5 : 1.5;
            } else if (layer === 'railways') {
                color = '#e67e22';
                weight = 3;
            } else {
                color = '#2980b9';
                weight = 2;
            }
            leafletLayer = L.polyline(coords, { color, weight, opacity: 0.8 });
        } else if (geom.type === 'Polygon') {
            const coords = geom.coordinates[0].map(c => [c[1], c[0]]);
            const cfg = LAYER_CONFIG[layer] || {};
            let fillColor = cfg.color;
            if (layer === 'buildings') {
                const ZONE_COLORS = {
                    ResidentialZone: '#27ae60',
                    CommercialZone:  '#3498db',
                    IndustrialZone:  '#e67e22',
                    OfficeZone:      '#9b59b6',
                    CivicBuilding:   '#e74c3c',
                };
                fillColor = ZONE_COLORS[f.properties.zone] || '#9b59b6';
            }
            leafletLayer = L.polygon(coords, {
                color: fillColor,
                fillColor: fillColor,
                fillOpacity: layer === 'waterways' ? 0.4 : 0.35,
                weight: 1,
            });
        }

        if (leafletLayer) {
            leafletLayer.on('click', () => showInfo(f.properties));
            layerGroups[layer].addLayer(leafletLayer);
        }
    });

    // CS2 map bounds rectangle
    if (bbox.south) {
        const mapSize = coordSys.cs2_map_size_m || 57344;
        const half = mapSize / 2;
        const centre = coordSys.centre || {};
        const lat_c = centre.lat || 0, lon_c = centre.lon || 0;
        const m_per_lat = 111320;
        const m_per_lon = 111320 * Math.cos(lat_c * Math.PI / 180);

        const s = lat_c - half / m_per_lat;
        const n = lat_c + half / m_per_lat;
        const w = lon_c - half / m_per_lon;
        const e = lon_c + half / m_per_lon;

        const rect = L.rectangle([[s, w], [n, e]], {
            color: '#e74c3c', weight: 2, dashArray: '8,6',
            fill: false, interactive: false,
        });
        layerGroups.cs2_bounds.addLayer(rect);
    }

    // Layer toggles
    const layersDiv = document.getElementById('layers');
    let layersHTML = '';
    Object.entries(LAYER_CONFIG).forEach(([key, cfg]) => {
        const swatchClass = cfg.swatch === 'circle' ? 'circle' : cfg.swatch === 'polygon' ? 'polygon' : '';
        layersHTML += `<div class="layer-toggle">
            <input type="checkbox" id="toggle-${key}" checked onchange="toggleLayer('${key}', this.checked)">
            <span class="legend-swatch ${swatchClass}" style="background:${cfg.color}"></span>
            <label for="toggle-${key}">${cfg.label}</label>
        </div>`;
    });
    layersDiv.innerHTML = layersHTML;

    // Routes info
    const routesDiv = document.getElementById('routes-info');
    const routes = DATA._routes || [];
    if (routes.length === 0) {
        routesDiv.innerHTML = '<em>No routes</em>';
    } else {
        const TYPE_EMOJI = { BusLine: 'Bus', TramLine: 'Tram', TrainLine: 'Train', SubwayLine: 'Subway', MetroLine: 'Metro' };
        let html = '';
        routes.slice(0, 50).forEach(r => {
            const typ = TYPE_EMOJI[r.type] || r.type;
            const ic = r.is_intercity ? ' [IC]' : '';
            const name = r.name || r.number || r.id;
            html += `<div style="padding:2px 0;border-bottom:1px solid #eee">${typ}: <strong>${name}</strong>${ic} (${r.stops.length} stops)</div>`;
        });
        if (routes.length > 50) html += `<div style="color:#999">… and ${routes.length - 50} more</div>`;
        routesDiv.innerHTML = html;
    }

    // Fit map to data
    const allBounds = [];
    DATA.features.forEach(f => {
        if (f.geometry.type === 'Point') {
            allBounds.push([f.geometry.coordinates[1], f.geometry.coordinates[0]]);
        } else if (f.geometry.type === 'LineString') {
            f.geometry.coordinates.forEach(c => allBounds.push([c[1], c[0]]));
        } else if (f.geometry.type === 'Polygon') {
            f.geometry.coordinates[0].forEach(c => allBounds.push([c[1], c[0]]));
        }
    });
    if (allBounds.length > 0) {
        // Sample to avoid perf issues with huge datasets
        const sample = allBounds.length > 1000
            ? allBounds.filter((_, i) => i % Math.ceil(allBounds.length / 1000) === 0)
            : allBounds;
        map.fitBounds(L.latLngBounds(sample).pad(0.05));
    } else if (bbox.south) {
        map.fitBounds([[bbox.south, bbox.west], [bbox.north, bbox.east]]);
    } else {
        map.setView([0, 0], 2);
    }
}

function toggleLayer(key, visible) {
    if (visible) map.addLayer(layerGroups[key]);
    else map.removeLayer(layerGroups[key]);
}

function showInfo(props) {
    const infoDiv = document.getElementById('info');
    const title = document.getElementById('info-title');
    const table = document.getElementById('info-table');

    title.textContent = props.name || props.id || 'Feature';
    let html = '';
    const skip = new Set(['layer', 'name']);
    Object.entries(props).forEach(([k, v]) => {
        if (skip.has(k) || v === '' || v === null || v === undefined) return;
        let display = v;
        if (typeof v === 'boolean') display = v ? 'Yes' : 'No';
        html += `<tr><td>${k}</td><td>${display}</td></tr>`;
    });
    table.innerHTML = html;
    infoDiv.style.display = 'block';
}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""


# ---------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------

class PreviewHandler(SimpleHTTPRequestHandler):
    """Serves the preview HTML and GeoJSON API."""

    geojson_data = None  # set by serve()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/geojson":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(self.geojson_data).encode("utf-8"))
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        # Suppress per-request logs
        pass


def find_latest_json(search_dir=None):
    """Find the most recently modified *_full.json file."""
    if search_dir is None:
        search_dir = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
    pattern = os.path.join(search_dir, "*_full.json")
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def serve(json_path, port=8000):
    """Load the JSON, convert to GeoJSON, and start the preview server."""
    print(f"Loading {json_path}…")
    with open(json_path, encoding="utf-8") as f:
        cs2_data = json.load(f)

    meta = cs2_data.get("_meta", {})
    city = meta.get("city", "unknown")
    print(f"  City: {city}")
    print(f"  Roads: {len(cs2_data.get('roads', []))}")
    print(f"  Railways: {len(cs2_data.get('railways', []))}")
    print(f"  Waterways: {len(cs2_data.get('waterways', []))}")
    print(f"  Buildings: {len(cs2_data.get('buildings', []))}")
    transit = cs2_data.get("transit", {})
    print(f"  Stops: {len(transit.get('stops', []))}")
    print(f"  Routes: {len(transit.get('routes', []))}")

    print("\nConverting to GeoJSON…")
    geojson = cs2_to_geojson(cs2_data)
    n_features = len(geojson["features"])
    print(f"  {n_features} features")

    PreviewHandler.geojson_data = geojson

    server = HTTPServer(("127.0.0.1", port), PreviewHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"\nPreview server running at {url}")
    print("Press Ctrl+C to stop.\n")

    webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Preview CS2 city data on a Leaflet map")
    parser.add_argument("json_file", nargs="?", help="Path to a _full.json file (auto-detected if omitted)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    args = parser.parse_args()

    if args.json_file:
        json_path = args.json_file
    else:
        json_path = find_latest_json()
        if json_path is None:
            print("No *_full.json file found in data/processed/.")
            print("Run the pipeline first:  python main.py --city Monaco")
            print("Or specify a file:       python preview_server.py path/to/file.json")
            sys.exit(1)

    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        sys.exit(1)

    serve(json_path, port=args.port)


if __name__ == "__main__":
    main()
