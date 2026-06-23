#!/usr/bin/env python3
"""
Interactive Generator Server for MapToSkylines2

Serves a Leaflet map where you drag a box — locked to the Cities: Skylines 2
map size (57.344 km) — over the real OpenStreetMap.  Click **Generate** and the
server runs the full OSM → CS2 pipeline for the selected area, transforming the
roads, terrain and tram/train tracks into European-themed assets, streaming
live progress to a loading screen, then drawing the converted result on the map.

Progress is streamed with Server-Sent Events (SSE): the browser opens
``/api/generate`` as an ``EventSource`` and receives one ``data:`` event per
pipeline step, then a final ``done`` (or ``error``) event.

Usage:
    python generate_server.py                 # opens the selector at :8001
    python generate_server.py --port 9000
    python generate_server.py --no-elevation  # faster (flat terrain)
"""

import argparse
import contextlib
import io
import json
import os
import sys
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))

from osm_fetcher import OSMFetcher
from preview_server import cs2_to_geojson
from pipeline import generate_city_data
from cs2_converter import CoordinateTransformer
from eu_assets import available_themes
from cs2_import import cs2_import_target, perform_import

# CS2 playable map edge in metres (mirrors CoordinateTransformer.CS2_MAP_SIZE).
CS2_MAP_SIZE = CoordinateTransformer.CS2_MAP_SIZE


# ---------------------------------------------------------------------------
# Progress mapping: pipeline log line → (phase key, percent complete)
# ---------------------------------------------------------------------------
# Phases (in order) shown on the loading screen.  Keep keys in sync with the
# PHASES array in the page's JavaScript.
PROGRESS_MAP = [
    ("fetching osm",        "fetch",    4),
    ("fetching roads",      "fetch",    8),
    ("tram & train",        "fetch",    14),
    ("fetching waterways",  "fetch",    18),
    ("public transport",    "fetch",    20),
    ("fetching buildings",  "fetch",    22),
    ("overpass busy",       "fetch",    24),   # retry/backoff message
    ("parsing",             "parse",    34),
    ("roads:",              "parse",    38),
    ("railways:",           "parse",    42),
    ("waterways:",          "parse",    44),
    ("transit:",            "parse",    46),
    ("buildings:",          "parse",    48),
    ("terrain elevation",   "terrain",  52),
    ("sampling terrain",    "terrain",  56),
    ("terrain batch",       "terrain",  62),
    ("elevation data",      "terrain",  68),
    ("skipping elevation",  "terrain",  68),
    ("converting",          "convert",  74),
    ("simplifying",         "simplify", 82),
    ("simplified",          "simplify", 85),
    ("asset theme",         "theme",    90),
    ("spatial chunks",      "chunk",    95),
    ("created",             "chunk",    97),
]


def progress_for(msg: str, floor_pct: int):
    """Map a log line to (phase, pct). pct never goes below floor_pct."""
    low = msg.lower()
    phase, pct = "fetch", floor_pct
    for needle, ph, p in PROGRESS_MAP:
        if needle in low:
            phase, pct = ph, p
            break
    return phase, max(pct, floor_pct)


class _LineTee(io.TextIOBase):
    """
    A writable stream that forwards each completed line to ``on_line`` and
    mirrors everything to ``mirror`` (the real stdout).  Used to capture the
    ``print()`` output of the converter so it can be streamed to the web log.
    """

    def __init__(self, on_line, mirror=None):
        self._on_line = on_line
        self._mirror = mirror
        self._buf = ""

    def write(self, s):
        if self._mirror is not None:
            try:
                self._mirror.write(s)
            except Exception:
                pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._on_line(line)
        return len(s)

    def flush(self):
        if self._buf.strip():
            self._on_line(self._buf)
            self._buf = ""
        if self._mirror is not None:
            try:
                self._mirror.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MapToSkylines2 — Generate</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
#map { position: absolute; top: 0; left: 0; right: 0; bottom: 0; }

#panel {
    position: absolute; top: 10px; left: 10px; z-index: 1000;
    background: rgba(255,255,255,0.97); border-radius: 10px;
    padding: 16px; width: 300px; max-height: calc(100vh - 20px);
    overflow-y: auto; box-shadow: 0 2px 14px rgba(0,0,0,0.25); font-size: 13px;
}
#panel h2 { font-size: 16px; margin-bottom: 4px; }
#panel .sub { color: #777; font-size: 11px; margin-bottom: 12px; }
#panel h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .04em;
            color: #888; margin: 14px 0 6px; }
.row { display: flex; gap: 6px; margin-bottom: 8px; }
.row input, .row select, #panel select { flex: 1; padding: 6px 8px; font-size: 13px;
    border: 1px solid #ccc; border-radius: 6px; }
button { width: 100%; padding: 10px; font-size: 14px; font-weight: 600;
    border: none; border-radius: 8px; cursor: pointer; background: #2d8a4e;
    color: #fff; }
button:hover { background: #257041; }
button:disabled { background: #9bbfa8; cursor: progress; }
button.sec { background: #eee; color: #333; }
button.sec:hover { background: #ddd; }
.stat { display: flex; justify-content: space-between; padding: 2px 0; }
.stat .label { color: #666; } .stat .value { font-weight: 600; }
#status { margin-top: 10px; font-size: 12px; min-height: 16px; }
.opt { display:block; font-size:12px; color:#333; margin:3px 0; cursor:pointer; }
.opt input { margin-right:6px; vertical-align:middle; }
#import-status { margin-top:8px; font-size:11px; line-height:1.4; word-break:break-all; }
#import-status code { background:#f0f0f0; padding:1px 3px; border-radius:2px; }
.box-handle { font-size: 22px; color: #e74c3c; text-shadow: 0 0 3px #fff;
    cursor: move; line-height: 1; }
.theme-badge { display:inline-block; background:#2d8a4e; color:#fff; font-size:11px;
    padding:2px 8px; border-radius:10px; margin-left:6px; }
.feat { display:flex; align-items:center; gap:6px; padding:2px 0; cursor:pointer; }
.feat input { margin:0; }

/* ---- Loading overlay (Minecraft-style) ---- */
#overlay { position: absolute; inset: 0; z-index: 2000; display: none;
    background: #1b1f24; color: #e8eef2; flex-direction: column;
    align-items: center; justify-content: center;
    font-family: 'Courier New', ui-monospace, monospace; }
#overlay.show { display: flex; }
.ov-card { width: min(640px, 92vw); }
.ov-title { font-size: 26px; font-weight: 700; letter-spacing: .04em;
    text-align: center; margin-bottom: 4px; }
.ov-flavor { text-align: center; color: #8fd19e; font-size: 15px;
    min-height: 22px; margin-bottom: 18px; }
.ov-bar { height: 26px; border: 3px solid #3a4250; background: #11151a;
    border-radius: 4px; overflow: hidden; box-shadow: inset 0 0 0 2px #0b0e12; }
.ov-fill { height: 100%; width: 0%;
    background: repeating-linear-gradient(45deg,#3fae5f 0 14px,#349a52 14px 28px);
    transition: width .3s ease; }
.ov-pct { text-align: center; font-size: 18px; margin: 8px 0 16px; }
.ov-phases { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 18px;
    margin-bottom: 16px; }
.ov-phase { font-size: 13px; color: #6b7682; }
.ov-phase .dot { display:inline-block; width:10px; text-align:center; }
.ov-phase.active { color: #ffd479; }
.ov-phase.done   { color: #8fd19e; }
.ov-log { height: 150px; overflow-y: auto; background: #0d1014; border: 1px solid #2a313c;
    border-radius: 4px; padding: 8px 10px; font-size: 12px; color: #9fb0bd;
    white-space: pre-wrap; }
.ov-log .err { color: #ff8a80; }
.ov-btns { display: flex; gap: 10px; justify-content: center; margin-top: 16px; }
.ov-btns button { width: auto; padding: 8px 20px; }
button.danger { background: #c0392b; color: #fff; }
button.danger:hover { background: #a83224; }
#ov-close { display: none; }
</style>
</head>
<body>
<div id="map"></div>

<div id="panel">
    <h2>MapToSkylines2</h2>
    <div class="sub">Drag the red box over the area you want, then Generate.</div>

    <h3>Find a place</h3>
    <div class="row">
        <input id="search" type="text" placeholder="City, address…"
               onkeydown="if(event.key==='Enter')doSearch()">
        <button class="sec" style="flex:0 0 64px" onclick="doSearch()">Go</button>
    </div>

    <h3>Map size</h3>
    <select id="size" onchange="onSizeChange()">
        <option value="57344">Full CS2 map — 57.3 × 57.3 km</option>
        <option value="28672">Half — 28.7 × 28.7 km</option>
        <option value="14336" selected>Quarter — 14.3 × 14.3 km</option>
    </select>
    <div class="row" style="margin-top:8px">
        <button class="sec" onclick="centerBoxOnView()">Center box on view</button>
    </div>

    <div id="selinfo"></div>

    <h3>Convert</h3>
    <div id="features">
        <label class="feat"><input type="checkbox" value="roads" checked> Roads</label>
        <label class="feat"><input type="checkbox" value="railways" checked> Tram &amp; train tracks</label>
        <label class="feat"><input type="checkbox" value="waterways" checked> Waterways</label>
        <label class="feat"><input type="checkbox" value="buildings"> Buildings</label>
        <label class="feat"><input type="checkbox" value="transit"> Transit lines &amp; stops</label>
    </div>
    <div class="sub" style="margin-top:4px">Terrain elevation is applied automatically. Train stations are not placed.</div>

    <h3>Theme</h3>
    <select id="theme">__THEME_OPTIONS__</select>

    <h3>Generate</h3>
    <button id="genbtn" onclick="generate()">⚙ Generate CS2 city</button>
    <div id="status"></div>

    <div id="results" style="display:none">
        <h3>Result</h3>
        <div id="stats"></div>

        <h3>Import to Cities: Skylines 2</h3>
        <label class="opt"><input type="checkbox" id="opt-money" checked> Unlimited money</label>
        <label class="opt"><input type="checkbox" id="opt-unlock" checked> Unlock all</label>
        <label class="opt"><input type="checkbox" id="opt-tiles" checked> All map tiles</label>
        <label class="opt"><input type="checkbox" id="opt-mods" checked> Enable mods</label>
        <button id="importbtn" onclick="importToCS2()">⬇ Import into CS2 folder</button>
        <div id="import-status"></div>
    </div>
</div>

<!-- Loading screen -->
<div id="overlay">
    <div class="ov-card">
        <div class="ov-title">Generating your city</div>
        <div class="ov-flavor" id="ov-flavor">Starting…</div>
        <div class="ov-bar"><div class="ov-fill" id="ov-fill"></div></div>
        <div class="ov-pct" id="ov-pct">0%</div>
        <div class="ov-phases" id="ov-phases"></div>
        <div class="ov-log" id="ov-log"></div>
        <div class="ov-btns">
            <button class="danger" id="ov-cancel" onclick="cancelGenerate()">Cancel</button>
            <button class="sec" id="ov-close" onclick="hideOverlay()">Close &amp; view map</button>
        </div>
    </div>
</div>

<script>
const CS2_MAP_SIZE = __CS2_MAP_SIZE__;
const M_PER_LAT = 111320;
let map, boxRect, boxHandle, resultLayer, evtSource;
let boxCenter = { lat: 48.8566, lon: 2.3522 };   // default: Paris
let boxSize = 14336;

const PHASES = [
    { key:'fetch',    label:'Download map data',     flavor:'Downloading map data…' },
    { key:'parse',    label:'Lay roads & tracks',    flavor:'Laying roads & tracks…' },
    { key:'terrain',  label:'Raise terrain',         flavor:'Raising terrain…' },
    { key:'convert',  label:'Convert to CS2 assets', flavor:'Converting to CS2 assets…' },
    { key:'simplify', label:'Smooth geometry',       flavor:'Smoothing geometry…' },
    { key:'theme',    label:'Apply theme',           flavor:'Applying theme…' },
    { key:'chunk',    label:'Slice into chunks',     flavor:'Slicing into chunks…' },
];

const ROAD_COLORS = {
    Highway:'#c0392b', LargeRoad:'#e67e22', MediumRoad:'#f39c12',
    SmallRoad:'#3498db', TinyRoad:'#95a5a6',
};
const STOP_COLORS = {
    bus:'#27ae60', tram:'#e67e22', train:'#c0392b', subway:'#8e44ad', stop:'#7f8c8d',
};
const BLDG_COLORS = {
    'ResidentialZone_low':'#a8e6a3','ResidentialZone_medium':'#4caf50','ResidentialZone_high':'#1b5e20',
    'CommercialZone_low':'#90caf9','CommercialZone_medium':'#2196f3','CommercialZone_high':'#0d47a1',
    'IndustrialZone_low':'#ffcc80','IndustrialZone_medium':'#ff9800','IndustrialZone_high':'#e65100',
    'OfficeZone_low':'#ce93d8','OfficeZone_medium':'#9c27b0','OfficeZone_high':'#4a148c',
    'CivicBuilding_low':'#ef9a9a','CivicBuilding_medium':'#e53935','CivicBuilding_high':'#b71c1c',
};

function mPerLon(lat) { return M_PER_LAT * Math.cos(lat * Math.PI / 180); }

function boxBounds() {
    const half = boxSize / 2;
    const dLat = half / M_PER_LAT;
    const dLon = half / mPerLon(boxCenter.lat);
    return [
        [boxCenter.lat - dLat, boxCenter.lon - dLon],
        [boxCenter.lat + dLat, boxCenter.lon + dLon],
    ];
}

function selectedBbox() {
    const b = boxBounds();
    return { south: b[0][0], west: b[0][1], north: b[1][0], east: b[1][1] };
}

function redrawBox() {
    const bounds = boxBounds();
    if (boxRect) boxRect.setBounds(bounds);
    else boxRect = L.rectangle(bounds, {
        color:'#e74c3c', weight:2, dashArray:'8,6', fill:true,
        fillColor:'#e74c3c', fillOpacity:0.06, interactive:false,
    }).addTo(map);

    if (boxHandle) boxHandle.setLatLng([boxCenter.lat, boxCenter.lon]);
    else {
        const icon = L.divIcon({ className:'', html:'<div class="box-handle">✛</div>',
            iconSize:[22,22], iconAnchor:[11,11] });
        boxHandle = L.marker([boxCenter.lat, boxCenter.lon], { icon, draggable:true }).addTo(map);
        boxHandle.on('drag', e => { const ll = e.latlng; boxCenter = { lat: ll.lat, lon: ll.lng }; redrawBox(); });
        boxHandle.on('dragend', updateSelInfo);
    }
    updateSelInfo();
}

function updateSelInfo() {
    const bb = selectedBbox();
    const km = (boxSize/1000).toFixed(1);
    document.getElementById('selinfo').innerHTML =
        `<div class="stat"><span class="label">Coverage</span><span class="value">${km} × ${km} km</span></div>`
      + `<div class="stat"><span class="label">Center</span><span class="value">${boxCenter.lat.toFixed(4)}, ${boxCenter.lon.toFixed(4)}</span></div>`;
}

function onSizeChange() { boxSize = parseFloat(document.getElementById('size').value); redrawBox(); }
function centerBoxOnView() { const c = map.getCenter(); boxCenter = { lat: c.lat, lon: c.lng }; redrawBox(); }

function doSearch() {
    const q = document.getElementById('search').value.trim();
    if (!q) return;
    setStatus('Searching…');
    fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q=' + encodeURIComponent(q))
        .then(r => r.json())
        .then(d => {
            if (!d.length) { setStatus('No match found.'); return; }
            const lat = parseFloat(d[0].lat), lon = parseFloat(d[0].lon);
            map.setView([lat, lon], 12);
            boxCenter = { lat, lon }; redrawBox(); setStatus('');
        })
        .catch(() => setStatus('Search failed.'));
}

function setStatus(html) { document.getElementById('status').innerHTML = html; }

/* ---------- Loading overlay ---------- */
function phaseIndex(key) { return PHASES.findIndex(p => p.key === key); }

function showOverlay() {
    document.getElementById('ov-fill').style.width = '0%';
    document.getElementById('ov-pct').textContent = '0%';
    document.getElementById('ov-flavor').textContent = 'Starting…';
    document.getElementById('ov-log').innerHTML = '';
    document.getElementById('ov-close').style.display = 'none';
    document.getElementById('ov-cancel').style.display = 'block';
    const ph = document.getElementById('ov-phases');
    ph.innerHTML = PHASES.map(p =>
        `<div class="ov-phase" id="ph-${p.key}"><span class="dot">•</span> ${p.label}</div>`).join('');
    document.getElementById('overlay').classList.add('show');
}
function hideOverlay() { document.getElementById('overlay').classList.remove('show'); }

function cancelGenerate() {
    if (evtSource) evtSource.close();
    document.getElementById('genbtn').disabled = false;
    document.getElementById('ov-cancel').style.display = 'none';
    document.getElementById('ov-close').style.display = 'block';
    document.getElementById('ov-flavor').textContent = 'Cancelled';
    logLine('Cancelled by user.', true);
    setStatus('Generation cancelled.');
}

function logLine(msg, isErr) {
    const el = document.getElementById('ov-log');
    const div = document.createElement('div');
    if (isErr) div.className = 'err';
    div.textContent = msg;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
}

function updateProgress(d) {
    if (typeof d.pct === 'number') {
        document.getElementById('ov-fill').style.width = d.pct + '%';
        document.getElementById('ov-pct').textContent = d.pct + '%';
    }
    const idx = phaseIndex(d.phase);
    if (idx >= 0) {
        document.getElementById('ov-flavor').textContent = PHASES[idx].flavor;
        PHASES.forEach((p, i) => {
            const row = document.getElementById('ph-' + p.key);
            if (!row) return;
            row.className = 'ov-phase' + (i < idx ? ' done' : i === idx ? ' active' : '');
            row.querySelector('.dot').textContent = i < idx ? '✔' : i === idx ? '▸' : '•';
        });
    }
    if (d.msg) logLine(d.msg);
}

function finishProgress() {
    document.getElementById('ov-fill').style.width = '100%';
    document.getElementById('ov-pct').textContent = '100%';
    document.getElementById('ov-flavor').textContent = 'Done! Result is on the map behind this screen.';
    PHASES.forEach(p => {
        const row = document.getElementById('ph-' + p.key);
        if (row) { row.className = 'ov-phase done'; row.querySelector('.dot').textContent = '✔'; }
    });
    // Keep the overlay open so the full log stays readable; user closes it.
    document.getElementById('ov-cancel').style.display = 'none';
    const close = document.getElementById('ov-close');
    close.textContent = 'Close & view map';
    close.style.display = 'block';
}

/* ---------- Generate via SSE ---------- */
function generate() {
    const btn = document.getElementById('genbtn');
    btn.disabled = true;
    setStatus('');

    const features = [];
    document.querySelectorAll('#features input:checked').forEach(cb => {
        if (cb.value === 'transit') features.push('bus', 'tram', 'train');
        else features.push(cb.value);
    });
    if (features.length === 0) { setStatus('Select at least one thing to convert.'); btn.disabled = false; return; }

    const bb = selectedBbox();
    const qs = new URLSearchParams({
        bbox: [bb.south, bb.west, bb.north, bb.east].join(','),
        theme: document.getElementById('theme').value,
        features: features.join(','),
    });

    showOverlay();
    if (evtSource) evtSource.close();
    evtSource = new EventSource('/api/generate?' + qs.toString());

    evtSource.onmessage = e => {
        try {
            const d = JSON.parse(e.data);
            if (d.raw) logLine(d.msg);   // converter output — log only
            else updateProgress(d);
        } catch (_) {}
    };

    evtSource.addEventListener('done', e => {
        evtSource.close(); btn.disabled = false;
        const d = JSON.parse(e.data);
        finishProgress();
        setStatus('✓ Generated. Saved ' + (d.files || []).join(', '));
        lastFiles = d.files || [];
        renderResult(d.geojson, d.counts, d.theme);
    });

    evtSource.addEventListener('error', e => {
        // Named server error carries data; a bare connection error does not.
        if (e.data) {
            try { logLine('Error: ' + JSON.parse(e.data).error, true); }
            catch (_) { logLine('Error during generation.', true); }
        } else {
            logLine('Connection lost.', true);
        }
        evtSource.close(); btn.disabled = false;
        document.getElementById('ov-cancel').style.display = 'none';
        document.getElementById('ov-close').style.display = 'block';
        document.getElementById('ov-flavor').textContent = 'Generation failed';
    });
}

function renderResult(geojson, counts, theme) {
    if (resultLayer) map.removeLayer(resultLayer);
    resultLayer = L.layerGroup().addTo(map);

    (geojson.features || []).forEach(f => {
        const p = f.properties, g = f.geometry;
        let layer;
        if (g.type === 'Point') {
            const [lon, lat] = g.coordinates;
            const c = STOP_COLORS[p.stop_type] || STOP_COLORS.stop;
            layer = L.circleMarker([lat, lon], { radius: p.is_external?7:5, color:c,
                fillColor:c, fillOpacity:0.85, weight:1 });
        } else if (g.type === 'LineString') {
            const coords = g.coordinates.map(c => [c[1], c[0]]);
            let color = '#2980b9', weight = 2, dash = null;
            if (p.layer === 'roads') { color = ROAD_COLORS[p.cs2_type] || '#3498db';
                weight = p.priority >= 3 ? 4 : p.priority >= 1 ? 2.5 : 1.5; }
            else if (p.layer === 'railways') { color = '#e67e22'; weight = 3;
                if (p.is_underground) { color = '#7f4fc7'; dash = '4,6'; } }  // tunnels dashed purple
            layer = L.polyline(coords, { color, weight, opacity:0.85, dashArray: dash });
        } else if (g.type === 'Polygon') {
            const coords = g.coordinates[0].map(c => [c[1], c[0]]);
            let fill = '#9e9e9e';
            if (p.layer === 'buildings') fill = BLDG_COLORS[(p.zone||'')+'_'+(p.density||'low')] || '#9e9e9e';
            else if (p.layer === 'waterways') fill = '#2980b9';
            layer = L.polygon(coords, { color: fill, fillColor: fill, fillOpacity:0.4, weight:1 });
        }
        if (layer) {
            const eu = p.eu_prefab ? ('<br><b>EU prefab:</b> ' + p.eu_prefab) : '';
            const ug = p.is_underground ? ' · underground (tunnel)' : '';
            const cm = p.is_commuter ? ' · commuter' : '';
            layer.bindPopup('<b>' + (p.name || p.id || p.layer) + '</b><br>' +
                (p.cs2_type || p.cs2_subtype || p.stop_type || '') + ug + cm + eu);
            resultLayer.addLayer(layer);
        }
    });

    const badge = theme && theme !== 'none' ? `<span class="theme-badge">${theme}</span>` : '';
    let html = '';
    Object.entries(counts || {}).forEach(([k, v]) => {
        html += `<div class="stat"><span class="label">${k}</span><span class="value">${v.toLocaleString()}</span></div>`;
    });
    document.getElementById('stats').innerHTML = html;
    document.querySelector('#results h3').innerHTML = 'Result' + badge;
    document.getElementById('results').style.display = 'block';
}

let lastFiles = [];

function importToCS2() {
    if (!lastFiles.length) { setImportStatus('Generate a city first.', true); return; }
    const btn = document.getElementById('importbtn');
    btn.disabled = true;
    setImportStatus('Importing…');
    fetch('/api/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            files: lastFiles,
            city: 'selection',
            options: {
                unlimitedMoney: document.getElementById('opt-money').checked,
                unlockAll:      document.getElementById('opt-unlock').checked,
                allTiles:       document.getElementById('opt-tiles').checked,
                useMods:        document.getElementById('opt-mods').checked,
            },
        }),
    }).then(r => r.json()).then(d => {
        btn.disabled = false;
        if (d.error) { setImportStatus(d.error, true); return; }
        const where = d.realMods
            ? 'CS2 Mods folder'
            : 'local staging folder (set CS2_MODS_DIR to auto-target the game)';
        setImportStatus('✓ Copied ' + d.copied.length + ' file(s) to the ' +
            where + ':<br><code>' + d.dest + '</code>');
    }).catch(e => { btn.disabled = false; setImportStatus('Import failed: ' + e, true); });
}

function setImportStatus(html, isErr) {
    const el = document.getElementById('import-status');
    el.innerHTML = html;
    el.style.color = isErr ? '#c0392b' : '#2e7d32';
}

function init() {
    map = L.map('map').setView([boxCenter.lat, boxCenter.lon], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors', maxZoom: 19,
    }).addTo(map);
    redrawBox();
}
document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""


def _build_page() -> str:
    theme_opts = "".join(
        f'<option value="{t}">{t.capitalize()}</option>' for t in available_themes()
    )
    return (
        HTML_PAGE
        .replace("__THEME_OPTIONS__", theme_opts)
        .replace("__CS2_MAP_SIZE__", repr(CS2_MAP_SIZE))
    )


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class GenerateHandler(BaseHTTPRequestHandler):
    """Serves the selector page and streams /api/generate via SSE."""

    options: dict = {}
    page_html: str = ""

    # -- page --------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = self.page_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/generate":
            self._handle_generate_sse(parse_qs(parsed.query))
        else:
            self.send_error(404)

    # -- SSE generation ----------------------------------------------------
    def _sse(self, data: dict, event: str = None):
        buf = ""
        if event:
            buf += f"event: {event}\n"
        buf += "data: " + json.dumps(data) + "\n\n"
        self.wfile.write(buf.encode("utf-8"))
        self.wfile.flush()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/import":
            self._handle_import()
        else:
            self.send_error(404, "Not found")

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_import(self):
        """Copy generated city files into the CS2 mod folder + write a manifest."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json({"error": "Invalid request body."}, status=400)
            return

        output_dir = self.options.get("output_dir", "../data/processed")
        payload, status = perform_import(
            output_dir,
            req.get("files") or [],
            city=req.get("city", "selection"),
            options=req.get("options") or {},
        )
        self._send_json(payload, status=status)

    def _handle_generate_sse(self, qs: dict):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # ---- Parse query params ----
        try:
            bbox = tuple(float(x) for x in qs.get("bbox", [""])[0].split(","))
            if len(bbox) != 4:
                raise ValueError
        except ValueError:
            self._sse({"error": "bbox must be 'south,west,north,east'."}, event="error")
            return

        err = OSMFetcher.validate_bbox(bbox)
        if err:
            self._sse({"error": err}, event="error")
            return

        theme = qs.get("theme", ["european"])[0]
        features = [f for f in qs.get("features", [""])[0].split(",") if f]
        if not features:
            features = ["roads", "railways", "waterways"]

        opts = self.options
        floor = [0]  # mutable cell so the log closure can carry forward pct

        def emit(msg: str):
            phase, pct = progress_for(msg, floor[0])
            floor[0] = pct
            self._sse({"msg": msg.strip(), "phase": phase, "pct": pct})

        def raw_line(msg: str):
            # Converter print() output — show in the log without moving the bar.
            self._sse({"msg": msg.strip(), "raw": True})

        self._sse({"msg": "Starting…", "phase": "fetch", "pct": 0})

        tee = _LineTee(raw_line, mirror=sys.__stdout__)
        try:
            # Capture the converter's print() output so the full log reaches
            # the browser, not just the structured pipeline progress.
            with contextlib.redirect_stdout(tee):
                result = generate_city_data(
                    bbox,
                    features=features,
                    city_name="selection",
                    theme=theme,
                    fetch_elevation=opts.get("fetch_elevation", True),
                    simplify_tolerance=opts.get("simplify_tolerance", 2.0),
                    chunk_size_m=opts.get("chunk_size_m", 5_000.0),
                    output_dir=opts.get("output_dir", "../data/processed"),
                    fetcher=None,   # fresh per request (safe with a streaming log)
                    parser=None,
                    log=emit,
                )

                cs2_data = result["cs2_data"]
                files = []
                if opts.get("save", True):
                    stem = OSMFetcher._safe_filename("selection")
                    conv = result["converter"]
                    conv.save_to_file(cs2_data, f"{stem}_full.json")
                    conv.save_to_file(result["chunks"], f"{stem}_chunks.json")
                    files = [f"{stem}_full.json", f"{stem}_chunks.json"]
                tee.flush()

            self._sse({
                "geojson": cs2_to_geojson(cs2_data),
                "counts":  result["counts"],
                "theme":   theme,
                "files":   files,
            }, event="done")
        except (BrokenPipeError, ConnectionResetError):
            # Client cancelled / disconnected — the next streamed write failed,
            # which aborts the pipeline.  Nothing more to send.
            return
        except Exception as e:
            try:
                self._sse({"error": str(e)}, event="error")
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt, *args):
        pass  # suppress per-request access logs


def serve(port: int = 8001, options: dict = None):
    GenerateHandler.options = options or {}
    GenerateHandler.page_html = _build_page()

    server = HTTPServer(("127.0.0.1", port), GenerateHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"MapToSkylines2 generator running at {url}")
    print("Drag the red box, then click Generate. Press Ctrl+C to stop.\n")

    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Interactive OSM → CS2 generator")
    parser.add_argument("--port", type=int, default=8001, help="Server port (default: 8001)")
    parser.add_argument("--no-elevation", action="store_true",
                        help="Skip elevation fetching (flat terrain, much faster)")
    parser.add_argument("--simplify-tolerance", type=float, default=2.0,
                        help="Douglas-Peucker tolerance in metres (0 = off)")
    parser.add_argument("--chunk-size", type=float, default=5000.0,
                        help="Spatial chunk size in metres")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not write JSON files (preview only)")
    parser.add_argument("--output-dir", type=str, default="../data/processed")
    args = parser.parse_args()

    serve(port=args.port, options={
        "fetch_elevation":    not args.no_elevation,
        "simplify_tolerance": args.simplify_tolerance,
        "chunk_size_m":       args.chunk_size,
        "save":               not args.no_save,
        "output_dir":         args.output_dir,
    })


if __name__ == "__main__":
    main()
