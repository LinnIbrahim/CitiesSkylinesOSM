# DynamicCityLoader - CS2 Mod

Dynamic city loading mod for Cities: Skylines 2.

## Overview

This mod enables dynamic loading of city data exported from OpenStreetMap, handling the data in chunks to work around CS2's performance limitations.

## Features

- Load city data from JSON files
- Dynamic chunk-based loading (LOD system)
- Road network generation
- Railway/metro placement
- Public transit route creation

## Installation

1. Install BepInEx for Cities: Skylines 2
2. Copy `DynamicCityLoader.dll` to `BepInEx/plugins/`
3. Place city data JSON files in `BepInEx/plugins/DynamicCityLoader/data/`
4. Launch CS2

## Usage

In-game, use the mod menu to:
1. Select a city data file
2. Configure loading settings (chunk distance, detail level)
3. Load the city

## Development

This mod requires:
- Cities: Skylines 2
- BepInEx 5.x or 6.x
- .NET SDK for building

### Building

```bash
dotnet build
```

## Status

🚧 In Development - Stub/Placeholder
Need to implement:
- [ ] BepInEx plugin setup
- [ ] JSON data loader
- [ ] Chunk management system
- [ ] Road network builder
- [ ] Transit system builder
- [ ] UI integration
