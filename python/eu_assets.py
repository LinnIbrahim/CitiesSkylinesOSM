"""
European Asset Theme

Transforms the generic, region-neutral CS2 feature data produced by
``cs2_converter`` into European-themed assets.

Cities: Skylines 2 ships two map themes — "European" and "North American" —
which control the visual prefabs used for buildings, props, road dressing and
the surrounding terrain/climate.  The Python side cannot know the exact runtime
prefab GUIDs, so this module tags every feature with:

  * ``theme``      — the CS2 theme name ("European")
  * ``eu_prefab``  — the intended European-theme prefab identifier the mod
                     resolves to an actual asset at load time

plus a few European traffic/road conventions (right-hand traffic, metric
speeds).  The mapping is intentionally data-driven so it is easy to extend or
swap for a different region theme later.
"""

from typing import Any, Dict, List, Optional

THEME_NAME = "European"

# Right-hand traffic is the European norm.  A handful of countries drive on the
# left; callers may override per-city, but EU is the sensible default here.
DEFAULT_TRAFFIC_SIDE = "right"

# Temperate European climate — used for the terrain/environment theme.
TERRAIN_THEME = {
    "theme":        THEME_NAME,
    "climate":      "Temperate",
    "vegetation":   "EU_DeciduousMixed",
    "ground_cover": "EU_Grass",
    "water_colour": "EU_Temperate",
}

# Generic CS2 road type → European-theme road prefab identifier.
EU_ROAD_PREFABS: Dict[str, str] = {
    "Highway":    "EU_Highway",
    "LargeRoad":  "EU_LargeAvenue",
    "MediumRoad": "EU_MediumRoad",
    "SmallRoad":  "EU_SmallRoad",
    "TinyRoad":   "EU_Alley",
    "Alley":      "EU_Alley",
    "Pathway":    "EU_PedestrianPath",
    "BikePath":   "EU_BikePath",
}

# Generic CS2 railway type → European-theme track prefab identifier.
EU_RAIL_PREFABS: Dict[str, str] = {
    "Train":  "EU_TrainTrack",
    "Metro":  "EU_MetroTrack",
    "Subway": "EU_SubwayTrack",
    "Tram":   "EU_TramTrack",
}

# Transit stop type → European-theme stop prefab identifier.
EU_STOP_PREFABS: Dict[str, str] = {
    "bus":    "EU_BusStop",
    "tram":   "EU_TramStop",
    "train":  "EU_TrainPlatform",
    "subway": "EU_SubwayEntrance",
    "stop":   "EU_BusStop",
}

# CS2 water type → European-theme water prefab identifier.
EU_WATER_PREFABS: Dict[str, str] = {
    "River":     "EU_River",
    "Canal":     "EU_Canal",
    "Stream":    "EU_Stream",
    "Drain":     "EU_Drain",
    "Coastline": "EU_Coastline",
    "Lake":      "EU_Lake",
    "Reservoir": "EU_Reservoir",
}


class EUAssetMapper:
    """Applies the European theme to converted CS2 city data."""

    def __init__(self, traffic_side: str = DEFAULT_TRAFFIC_SIDE):
        self.traffic_side = traffic_side

    # ------------------------------------------------------------------
    # Per-feature mappers (pure functions of a single feature)
    # ------------------------------------------------------------------

    def road_prefab(self, cs2_type: str) -> str:
        return EU_ROAD_PREFABS.get(cs2_type, f"EU_{cs2_type}")

    def rail_prefab(self, cs2_type: str) -> str:
        return EU_RAIL_PREFABS.get(cs2_type, f"EU_{cs2_type}")

    def stop_prefab(self, stop_type: str) -> str:
        return EU_STOP_PREFABS.get(stop_type, "EU_BusStop")

    def water_prefab(self, cs2_type: str) -> str:
        return EU_WATER_PREFABS.get(cs2_type, f"EU_{cs2_type}")

    def building_prefab(self, cs2_subtype: str) -> str:
        """European-theme building prefab from the generic CS2 subtype."""
        subtype = cs2_subtype or "LowDensityResidential"
        return f"EU_{subtype}"

    # ------------------------------------------------------------------
    # Whole-dataset transformation
    # ------------------------------------------------------------------

    def apply(self, cs2_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a new CS2-data dict with every feature tagged for the European
        theme.  The input is not mutated.
        """
        out: Dict[str, Any] = {**cs2_data}

        if "roads" in out:
            out["roads"] = [self._tag_road(r) for r in out["roads"]]
        if "railways" in out:
            out["railways"] = [self._tag_rail(r) for r in out["railways"]]
        if "waterways" in out:
            out["waterways"] = [self._tag_water(w) for w in out["waterways"]]
        if "buildings" in out:
            out["buildings"] = [self._tag_building(b) for b in out["buildings"]]
        if "transit" in out:
            transit = out["transit"]
            out["transit"] = {
                **transit,
                "stops": [self._tag_stop(s) for s in transit.get("stops", [])],
                "routes": [self._tag_route(r) for r in transit.get("routes", [])],
            }

        # Record the theme on the metadata block so the mod and the preview
        # know which asset set to resolve against.
        meta = {**out.get("_meta", {})}
        meta["theme"] = {
            "name":         THEME_NAME,
            "traffic_side": self.traffic_side,
            "terrain":      TERRAIN_THEME,
        }
        out["_meta"] = meta

        return out

    # ------------------------------------------------------------------
    # Private per-feature taggers
    # ------------------------------------------------------------------

    def _tag_road(self, road: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **road,
            "theme":        THEME_NAME,
            "eu_prefab":    self.road_prefab(road.get("type", "")),
            "traffic_side": self.traffic_side,
        }

    def _tag_rail(self, rail: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **rail,
            "theme":     THEME_NAME,
            "eu_prefab": self.rail_prefab(rail.get("type", "")),
        }

    def _tag_water(self, water: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **water,
            "theme":     THEME_NAME,
            "eu_prefab": self.water_prefab(water.get("type", "")),
        }

    def _tag_building(self, bldg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **bldg,
            "theme":     THEME_NAME,
            "eu_prefab": self.building_prefab(bldg.get("cs2_subtype", "")),
        }

    def _tag_stop(self, stop: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **stop,
            "theme":     THEME_NAME,
            "eu_prefab": self.stop_prefab(stop.get("type", "")),
        }

    def _tag_route(self, route: Dict[str, Any]) -> Dict[str, Any]:
        return {**route, "theme": THEME_NAME}


def apply_eu_theme(
    cs2_data: Dict[str, Any],
    traffic_side: str = DEFAULT_TRAFFIC_SIDE,
) -> Dict[str, Any]:
    """Convenience wrapper: tag ``cs2_data`` with the European theme."""
    return EUAssetMapper(traffic_side=traffic_side).apply(cs2_data)


# Themes registry — makes it trivial to add e.g. a North-American theme later.
THEMES: Dict[str, Any] = {
    "european": apply_eu_theme,
    "eu":       apply_eu_theme,
}


def apply_theme(cs2_data: Dict[str, Any], theme: Optional[str]) -> Dict[str, Any]:
    """
    Apply a named theme to ``cs2_data``.

    ``theme`` of None / "none" / "vanilla" returns the data unchanged.
    Unknown theme names fall back to no transformation (with no error) so the
    pipeline never crashes on a typo.
    """
    if not theme:
        return cs2_data
    key = theme.strip().lower()
    if key in ("none", "vanilla", "neutral"):
        return cs2_data
    fn = THEMES.get(key)
    if fn is None:
        return cs2_data
    return fn(cs2_data)


def available_themes() -> List[str]:
    return ["european", "none"]
