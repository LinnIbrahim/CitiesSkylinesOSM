# DynamicCityLoader — CS2 Mod

Dynamic city-loading mod for Cities: Skylines II. Loads the JSON city exports
produced by the Python pipeline and realises them in-game, chunk by chunk, to
work around CS2's performance limits on large networks.

Built on the **official PDX modding framework** (`Game.Modding.IMod`) — see
[../../docs/CS2_MODDING_RESEARCH.md](../../docs/CS2_MODDING_RESEARCH.md).

## Structure

| File | Responsibility |
|------|----------------|
| `Mod.cs` | `IMod` entry point; registers `CityBuilderSystem`, resolves data dir. |
| `CityData.cs` | Data models matching the Python JSON export schema. |
| `CityDataLoader.cs` | Deserializes the full + chunked exports. |
| `ChunkManager.cs` | Camera-distance based load/unload bookkeeping. |
| `Systems/CityBuilderSystem.cs` | `GameSystemBase` that resolves prefabs and realises chunks. |

## Installation

1. Build with the CS2 toolchain (sets `CSII_TOOLPATH`):
   ```bash
   dotnet build -c Release
   ```
2. The build deploys `DynamicCityLoader.dll` to
   `%LOCALAPPDATA%Low\Colossal Order\Cities Skylines II\Mods\`.
3. Place the pipeline output (`selection_chunks.json` / `selection_full.json`)
   in the mod's `data/` subfolder.
4. Launch CS2 and load/start a city.

## Status

🚧 In Development

- [x] PDX `IMod` entry point
- [x] JSON data models matching the export schema
- [x] Full + chunked JSON loader
- [x] Chunk load/unload manager (distance based)
- [x] Builder system: prefab resolution + chunk iteration
- [ ] Network realisation via the net tool / `ApplyNetSystem` flow
- [ ] Camera-driven chunk focus
- [ ] Building + transit placement
- [ ] In-game UI
