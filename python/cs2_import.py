"""
Shared "Import to Cities: Skylines 2" helper used by both the interactive
generate server and the preview server.

Copies the generated city JSON into the DynamicCityLoader mod's data folder and
writes an ``import_manifest.json`` describing the files and the game options the
user asked for (unlimited money, unlock all, mods, map tiles).
"""

import os
import platform
import shutil
import json
from datetime import datetime, timezone

# Mod folder name the DynamicCityLoader reads its data from.
MOD_FOLDER_NAME = "DynamicCityLoader"


def cs2_import_target(output_dir: str):
    """
    Resolve where imported city data should be copied for the CS2 mod to read.

    Preference order:
      1. ``CS2_MODS_DIR`` env var → ``<that>/DynamicCityLoader/data`` (the real
         game Mods folder; set this to your install's Mods path).
      2. A best-effort per-OS default Mods path, if it already exists.
      3. A local staging folder under the repo (``data/cs2_import/...``) so the
         import always succeeds; the user then copies it into the game manually.

    Returns ``(dest_dir, is_real_mods_dir, source_label)``.
    """
    env = os.environ.get("CS2_MODS_DIR")
    if env:
        return os.path.join(env, MOD_FOLDER_NAME, "data"), True, "CS2_MODS_DIR"

    home = os.path.expanduser("~")
    system = platform.system()
    if system == "Windows":
        default_mods = os.path.join(
            home, "AppData", "LocalLow", "Colossal Order",
            "Cities Skylines II", "Mods")
    elif system == "Darwin":
        default_mods = os.path.join(
            home, "Library", "Application Support", "Colossal Order",
            "Cities Skylines II", "Mods")
    else:  # Linux / Proton
        default_mods = os.path.join(
            home, ".local", "share", "Colossal Order",
            "Cities Skylines II", "Mods")

    if os.path.isdir(default_mods):
        return os.path.join(default_mods, MOD_FOLDER_NAME, "data"), True, "default"

    staging = os.path.abspath(
        os.path.join(output_dir, "..", "cs2_import", MOD_FOLDER_NAME, "data"))
    return staging, False, "staging"


def perform_import(output_dir, files, city="selection", options=None):
    """
    Copy ``files`` (relative to ``output_dir``) into the resolved CS2 mod folder
    and write the import manifest.

    Returns ``(payload, status_code)`` where payload is a JSON-serialisable dict.
    """
    options = options or {}
    if not files:
        return {"error": "No generated files to import. Generate a city first."}, 400

    dest_dir, is_real, source = cs2_import_target(output_dir)

    try:
        os.makedirs(dest_dir, exist_ok=True)
        copied = []
        for fname in files:
            src = os.path.join(output_dir, os.path.basename(fname))
            if not os.path.isfile(src):
                return {"error": f"Generated file missing: {fname}"}, 400
            shutil.copy2(src, os.path.join(dest_dir, os.path.basename(fname)))
            copied.append(os.path.basename(fname))

        full   = next((f for f in copied if f.endswith("_full.json")), None)
        chunks = next((f for f in copied if f.endswith("_chunks.json")), None)
        manifest = {
            "city":        city or "selection",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "full":        full,
            "chunks":      chunks,
            "options": {
                "unlimitedMoney": bool(options.get("unlimitedMoney", True)),
                "unlockAll":      bool(options.get("unlockAll", True)),
                "useMods":        bool(options.get("useMods", True)),
                "mapTiles":       "all" if options.get("allTiles", True) else "base",
            },
            "notes": (
                "Full-map play and tiles beyond the base purchasable area "
                "require a tiles-unlock mod (e.g. 'All Tiles Unlock'). "
                "Unlimited money / unlock all are applied by DynamicCityLoader "
                "on load, and can also be toggled in CS2's new-game options."
            ),
        }
        with open(os.path.join(dest_dir, "import_manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return {
            "ok":       True,
            "dest":     dest_dir,
            "copied":   copied + ["import_manifest.json"],
            "realMods": is_real,
            "source":   source,
            "manifest": manifest,
        }, 200
    except OSError as e:
        return {"error": f"Could not write to {dest_dir}: {e}. "
                         "Set CS2_MODS_DIR to your Cities: Skylines II Mods "
                         "folder and try again."}, 500
