# 📣 MapToSkylines2 — Milestone: Python Pipeline Complete, CS2 Mod Loader Started

*2026-06-23*

**MapToSkylines2** turns real-world city maps into Cities: Skylines 2 builds.
Pick any area on OpenStreetMap and the toolchain converts its roads, railways,
transit, waterways, terrain and buildings into CS2-ready data.

## What works today

### 🗺️ Interactive web generator
Launch `python generate_server.py`, **drag a CS2-map-sized box** (57.3 × 57.3 km)
over live OpenStreetMap, and click **Generate**. The server fetches OSM data,
converts it, and draws the result straight back on the map. A command-line
generator (`main.py`) is available too.

### 🧱 Full feature extraction
- **Roads & railways** mapped to CS2 road/track types, with lanes, one-way,
  speed limits and priorities.
- **Buildings** with height/levels, zone + density classification, CS2 subtype
  and material/roof/colour metadata.
- **Waterways** — rivers, canals, lakes, reservoirs and coastline.
- **Transit** — bus, tram and train stops and routes, including pinned
  external connections at the map edge.

### 🌍 Accurate geography
- 1:1 real-world metres via a local tangent-plane projection.
- **Real elevation** from SRTM 30 m terrain data (batched + cached).
- Oversized cities are **clipped** cleanly at the CS2 map boundary.

### 🇪🇺 European theming
Every asset is tagged with its EU prefab, right-hand traffic and a temperate
terrain/climate profile — or switch to neutral output with `--theme none`.

### ⚙️ Quality
Unit-tested across the pipeline with a GitHub Actions CI build.

## 🆕 New: CS2 mod loader

The in-game mod has moved off the old BepInEx stub onto the **official PDX
`IMod` framework**. This release lands the foundation:

- C# data models matching the exact JSON export schema.
- A JSON loader for the full and chunked exports.
- A distance-based **chunk manager** for dynamic load/unload.
- A `CityBuilderSystem` that resolves prefabs and iterates chunks, with the
  network-creation flow scaffolded and documented.

## 🔜 Next up

1. Wire network realisation through the CS2 net-tool / `ApplyNetSystem` flow.
2. Verify EU prefab names against the in-game catalogue.
3. Camera-driven chunk loading and LOD for distant chunks.
4. Building and transit placement in-game.

---

See [README.md](README.md) to get started, [ROADMAP.md](ROADMAP.md) for the
plan, and [docs/PROGRESS.md](docs/PROGRESS.md) for the detailed status.
