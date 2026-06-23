# MapToSkylines2 Documentation

**Last Updated**: 2026-06-23

Documentation for turning real-world places into Cities: Skylines 2 maps.

## Start here

- **[USAGE.md](USAGE.md)** — how to generate, view and import a map (step by step)
- **[SETUP.md](SETUP.md)** — installation and environment setup

## Reference

- **[PROGRESS.md](PROGRESS.md)** — what's done, in progress and known issues
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the pipeline and mod fit together
- **[API_NOTES.md](API_NOTES.md)** — OSM sources and the CS2 data format
- **[CS2_MODDING_RESEARCH.md](CS2_MODDING_RESEARCH.md)** — CS2 modding (IMod) reference
- **[TESTING.md](TESTING.md)** — test notes
- **[../ROADMAP.md](../ROADMAP.md)** — plan
- **[../mod/DynamicCityLoader/README.md](../mod/DynamicCityLoader/README.md)** — the in-game mod

## In one line

```
OpenStreetMap → Python pipeline → JSON → DynamicCityLoader mod → Cities: Skylines 2
```

The Python pipeline, browser generator/preview and CS2 import are working; the
in-game mod that builds the map from the data is in progress. See
[PROGRESS.md](PROGRESS.md) for detail.
</content>
