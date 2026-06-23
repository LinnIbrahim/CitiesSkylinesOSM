// CityDataLoader.cs
//
// Reads the JSON exports produced by the Python pipeline. The mod expects
// the files to live under the mod's data folder, e.g.:
//
//   <Mods>/DynamicCityLoader/data/selection_full.json
//   <Mods>/DynamicCityLoader/data/selection_chunks.json

using System;
using System.Collections.Generic;
using System.IO;
using Colossal.Logging;
using Newtonsoft.Json;

namespace DynamicCityLoader
{
    public static class CityDataLoader
    {
        private static readonly ILog Log = Mod.Log;

        /// <summary>Load a flat "*_full.json" export. Returns null on failure.</summary>
        public static CityData LoadFull(string path)
        {
            if (!File.Exists(path))
            {
                Log.Warn($"City data file not found: {path}");
                return null;
            }

            try
            {
                var json = File.ReadAllText(path);
                var data = JsonConvert.DeserializeObject<CityData>(json);
                Log.Info(
                    $"Loaded city '{data?.Meta?.City ?? "?"}': " +
                    $"{Count(data?.Roads)} roads, {Count(data?.Railways)} railways, " +
                    $"{Count(data?.Waterways)} waterways, {Count(data?.Buildings)} buildings.");
                return data;
            }
            catch (Exception e)
            {
                Log.Error($"Failed to parse city data '{path}': {e.Message}");
                return null;
            }
        }

        /// <summary>Load a chunked "*_chunks.json" export. Returns an empty list on failure.</summary>
        public static List<CityChunk> LoadChunks(string path)
        {
            if (!File.Exists(path))
            {
                Log.Warn($"Chunk file not found: {path}");
                return new List<CityChunk>();
            }

            try
            {
                var json = File.ReadAllText(path);
                var chunks = JsonConvert.DeserializeObject<List<CityChunk>>(json)
                             ?? new List<CityChunk>();
                Log.Info($"Loaded {chunks.Count} chunks from {Path.GetFileName(path)}.");
                return chunks;
            }
            catch (Exception e)
            {
                Log.Error($"Failed to parse chunk data '{path}': {e.Message}");
                return new List<CityChunk>();
            }
        }

        /// <summary>Load the import manifest if present; null when absent/invalid.</summary>
        public static ImportManifest LoadManifest(string path)
        {
            if (!File.Exists(path))
                return null;

            try
            {
                return JsonConvert.DeserializeObject<ImportManifest>(File.ReadAllText(path));
            }
            catch (Exception e)
            {
                Log.Warn($"Failed to parse import manifest '{path}': {e.Message}");
                return null;
            }
        }

        private static int Count<T>(List<T> list) => list?.Count ?? 0;
    }
}
