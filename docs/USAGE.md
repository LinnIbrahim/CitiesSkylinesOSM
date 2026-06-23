# How to use MapToSkylines2

A simple, step-by-step guide. No maths — just the steps.

---

## 1. Install

You need **Python 3.9+** and an internet connection (to download map data).

```bash
pip install -r python/requirements.txt
```

---

## 2. Generate a map (browser — recommended)

```bash
cd python
python generate_server.py
```

This opens **http://127.0.0.1:8001** in your browser.

1. **Find your area** — search or pan the map.
2. **Drag the red box** over the area you want. The box is locked to the size of
   a Cities: Skylines 2 map (about 57 × 57 km), so whatever is inside it becomes
   your map.
3. Pick a **theme** (European by default).
4. Click **Generate**. Live map data is downloaded and converted, then drawn
   back on the map so you can check it.

Tip: very large/dense areas take longer and can occasionally hit download
limits — if a generate fails, wait a couple of minutes and try again.

---

## 3. View what you made

The result is drawn on the map straight after generating. To re-open the latest
result later:

```bash
python preview_server.py        # opens http://127.0.0.1:8000
```

In the panel on the right:
- **Layers** — pick **one layer at a time** (roads, railways, waterways,
  buildings, stops, districts, outside connections). Big maps are smoother this
  way; there's an "All layers" option if you want everything at once.
- **Routes** — the bus/tram/train lines found.
- Click any feature to see its details.

---

## 4. Import into Cities: Skylines 2

In either the generator or the preview, tick the options and click
**Import into CS2 folder**:

- **Unlimited money** — recommended. A real city is huge and normal finances
  drain on upkeep before you can do anything.
- **Unlock all** — recommended, so the whole map is usable from the start.
- **All map tiles** — lets you use the whole map (needs a tiles-unlock mod).
- **Enable mods**.

By default files go to a local `data/cs2_import/` folder. To send them straight
to the game, set `CS2_MODS_DIR` to your Cities: Skylines II **Mods** folder
before launching:

```bash
export CS2_MODS_DIR="/path/to/Cities Skylines II/Mods"
```

---

## 5. Play it

1. Launch **Cities: Skylines 2**.
2. Use the **Load** option to open the imported map.
3. The first load may take a while because of the map's size — that's normal.

---

## Command line (optional)

Prefer the terminal? Generate without the browser:

```bash
# A whole CS2-sized map centred on a city (default)
python main.py --city "Ghent, Belgium"

# Just the city's admin area, or a smaller slice
python main.py --city "Ghent, Belgium" --map-size city
python main.py --city "Ghent, Belgium" --map-size half

# A manual area (south,west,north,east)
python main.py --bbox "51.0,3.6,51.1,3.8"
```

Useful options:

| Option | What it does |
|---|---|
| `--map-size` | `full` (default), `half`, `quarter`, or `city` (admin boundary only) |
| `--features` | Comma list: `roads,railways,waterways,bus,tram,train,buildings,districts` |
| `--theme` | `european` (default) or `none` |
| `--min-waterway-width` | Drop waterways narrower than this many metres (e.g. `2` removes ditches) |
| `--no-elevation` | Flat terrain — faster |
| `--output` | Output file name stem |

Output is written to `data/processed/` as `<name>_full.json` and
`<name>_chunks.json`. Then view it with `python preview_server.py`.

---

## Tips

- **Buildings are heavy.** For very large areas, downloading every building can
  be slow or time out. Leave them out with
  `--features "roads,railways,waterways,bus,tram,train,districts"` if needed.
- **Map full of "rivers"?** Rural areas have many drainage ditches. Add
  `--min-waterway-width 2` to clean them up.
- **For smoother play**, `--map-size half` produces a smaller, lighter map than
  the full 57 km.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: python` | Use `python3` |
| Generate fails / "too many requests" | Wait a few minutes and retry |
| Nothing found for a city | Check spelling, or use `--bbox` |
| Import says "staging folder" | Set `CS2_MODS_DIR` to your game Mods folder |
</content>
