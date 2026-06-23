# MapToSkylines2

Turn any real-world place into a **Cities: Skylines 2** map. Pick an area on
OpenStreetMap and MapToSkylines2 converts its roads, railways, waterways,
buildings, public transport and town names into CS2-ready data — then imports
it straight into the game's mod folder.

👉 **New here? Read the [How to use](docs/USAGE.md) guide.**

## What it captures

| Feature | Details |
|---|---|
| **Roads** | Mapped to CS2 road types by lane count; **bike lanes** and **tram roads** detected; numbered-route shields (A12, R40); one-way & speed limits |
| **Railways** | Train / tram / metro, with vertical structure — **ground, embankment, elevated, bridge, viaduct, cutting, tunnel** |
| **Waterways** | Rivers, canals, streams, lakes & coastline with width and depth; tiny ditches can be filtered out |
| **Buildings** | Footprints with zone, density, height and roof/material info |
| **Public transport** | Bus / tram / train stops and lines; lines that reach the map edge are cut there and loop back |
| **Districts** | Each town and village becomes a **named district** so you can tell which area is which |
| **Outside connections** | Highways, rail and rivers that reach the map edge are marked as links to the outside world |
| **Terrain** | Real elevation; **European** theme by default |

## Quick start

```bash
pip install -r python/requirements.txt
cd python
python generate_server.py        # opens http://127.0.0.1:8001
```

Drag the red box over the area you want, click **Generate**, then click
**Import into CS2 folder**. In Cities: Skylines 2, use **Load** to open the map.

Full step-by-step instructions, options and tips: **[docs/USAGE.md](docs/USAGE.md)**.

## Project layout

```
python/   OSM → CS2 data pipeline + browser generator/preview
mod/      DynamicCityLoader — the in-game CS2 mod
data/     cached OSM data and generated output
docs/     documentation
```

## Status

🚧 In development. The data pipeline, browser generator/preview and CS2 import
are working; the in-game mod that builds the map from the data is in progress.

- [How to use](docs/USAGE.md) — generate, view and import a map
- [Roadmap](ROADMAP.md) — what's planned
- [Progress](docs/PROGRESS.md) — detailed status
</content>
