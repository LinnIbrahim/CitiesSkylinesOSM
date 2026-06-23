# Project Progress Report

**Last Updated**: 2026-06-23
**Status**: Phase 2 — Python pipeline complete, CS2 mod loader started

---

## ✅ Completed

### Phase 1: Python Data Pipeline (DONE)

- Modular Python package (`fetcher → parser → converter`) orchestrated by a
  shared `pipeline.generate_city_data` used by both the CLI and the web server.
- OSM fetch via Overpass + Nominatim city lookup, with retry/backoff and rate
  limit handling.
- Parsing of roads, railways, transit (bus/tram/train), waterways and buildings.
- CS2 conversion: road/railway/transit type mapping, building footprint
  conversion, JSON export.

### Phase 2: Core Functionality (Python side DONE)

#### Coordinate system
- Proper Lat/Lon → CS2 conversion via a **local tangent plane** centred on the
  selection (1:1 real-world metres, X/Z ground plane, Y = elevation).
- Cities larger than the CS2 map (57 344 m) are **clipped** at the map edge
  using Shapely intersection.

#### Terrain
- Elevation sampled from **OpenTopoData SRTM 30 m**, batched and cached to
  `data/osm/elevation_cache.json`.

#### Waterways
- Rivers, streams, canals, lakes, reservoirs and coastline, with area polygons
  flagged via `isArea`.

#### Buildings
- Footprint extraction with height/levels estimation, zone + **density**
  classification, **CS2 subtype** for prefab matching, plus material, roof
  shape and colour metadata.

#### Road classification
- Effective width estimated from explicit OSM `width` or `lanes × per-class
  lane width` (+ shoulders for motorway-grade roads).
- CS2 type chosen by lane count, **clamped to the vanilla 5-lane ceiling** with
  a `clamped`/`original_lanes` flag so oversized roads (e.g. Texas freeways)
  degrade honestly instead of silently.
- Multilingual **name hints** (e.g. Dutch *voetweg* → footpath, *steeg* →
  alley) fill missing/generic tags; footways/alleys route to a CS2 pathway.
- Numbered-route **refs** (A12, N15) carried through with a class-based shield
  colour.

#### European theme
- Every asset tagged with its EU prefab (`eu_prefab`), right-hand `traffic_side`,
  and a temperate terrain/climate/vegetation profile. `--theme none` produces
  region-neutral output.

#### Chunking
- Grid-based spatial chunking (configurable cell size) producing
  `selection_chunks.json` with per-chunk bounds and feature lists.

#### Interactive web generator
- `generate_server.py` serves a browser UI: drag a CS2-map-sized box over live
  OpenStreetMap, click **Generate**, and the converted roads/transit/buildings
  are drawn straight back on the map. `preview_server.py` re-renders the latest
  result.

### Tooling
- Unit test suite across fetcher, parser, converter, eu_assets, pipeline and
  both servers (`python/tests`).
- GitHub Actions CI pipeline.

---

## 🚧 In Progress

### CS2 Mod (`mod/DynamicCityLoader`)
Migrated off the BepInEx stub onto the **official PDX `IMod` framework**
(see [CS2_MODDING_RESEARCH.md](CS2_MODDING_RESEARCH.md)). Implemented:

- `Mod.cs` — `IMod` entry point registering the builder system.
- `CityData.cs` — C# data models matching the exact JSON export schema
  (roads, railways, waterways, buildings, transit, chunks, meta).
- `CityDataLoader.cs` — JSON deserialization of full + chunked exports.
- `ChunkManager.cs` — camera-distance based load/unload bookkeeping.
- `CityBuilderSystem.cs` — `GameSystemBase` scaffold that resolves prefabs and
  drives network/building creation.

**Boundary**: the actual ECS network creation (roads are placed via tool
systems / `ApplyNetSystem`, not direct entity creation) is scaffolded with
documented integration points and needs an installed CS2 SDK to compile/run.

---

## ⚠️ Known Issues / Open Questions

- **Road placement API** — must go through tool/definition systems, not
  `EntityManager.CreateEntity`. Approach documented; not yet wired to the game.
- **Prefab name mapping** — `eu_prefab` strings need verification against the
  real CS2 prefab catalogue.
- **Transit routes** — Overpass rate-limits repeated runs; longer waits or a
  local Overpass instance help.
- **Chunk LOD** — chunks exist but no level-of-detail simplification yet.

---

## 🎯 Next Priorities

1. Install CS2 SDK locally; get `DynamicCityLoader.csproj` building against game
   assemblies.
2. Implement road network creation through the tool-system flow for a single
   chunk.
3. Verify `eu_prefab` names against the in-game prefab catalogue.
4. Wire `ChunkManager` to camera position for dynamic load/unload.
5. Add LOD simplification for distant chunks.

---

## 🔬 Research Status

CS2 modding framework, ECS network/building/transit components, prefab creation
and key open-source references are documented in
[CS2_MODDING_RESEARCH.md](CS2_MODDING_RESEARCH.md). Remaining unknowns: exact
prefab catalogue names and tool-system call sequence for batch road creation.
</content>
</invoke>
