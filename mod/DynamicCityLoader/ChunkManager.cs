// ChunkManager.cs
//
// Tracks which chunks are currently realised in the world and decides which
// ones to load / unload based on a focus position (typically the camera).
// This is pure bookkeeping — actual entity creation/removal is delegated to
// the CityBuilderSystem via the events it raises.

using System;
using System.Collections.Generic;

namespace DynamicCityLoader
{
    public class ChunkManager
    {
        private readonly Dictionary<string, CityChunk> _all = new Dictionary<string, CityChunk>();
        private readonly HashSet<string> _loaded = new HashSet<string>();

        /// <summary>Chunks within this distance (metres) of the focus get loaded.</summary>
        public float LoadRadius { get; set; } = 8000f;

        public IReadOnlyCollection<string> LoadedChunkIds => _loaded;

        public void SetChunks(IEnumerable<CityChunk> chunks)
        {
            _all.Clear();
            _loaded.Clear();
            foreach (var c in chunks)
            {
                if (c?.ChunkId != null)
                    _all[c.ChunkId] = c;
            }
        }

        /// <summary>
        /// Recompute the desired loaded set for the given focus point and report
        /// the delta. Caller realises <paramref name="toLoad"/> and tears down
        /// <paramref name="toUnload"/>.
        /// </summary>
        public void Update(float focusX, float focusZ,
                           out List<CityChunk> toLoad,
                           out List<string> toUnload)
        {
            toLoad = new List<CityChunk>();
            toUnload = new List<string>();

            var desired = new HashSet<string>();
            float r2 = LoadRadius * LoadRadius;

            foreach (var kvp in _all)
            {
                var b = kvp.Value.Bounds;
                float dx = focusX - b.CentreX;
                float dz = focusZ - b.CentreZ;
                if (dx * dx + dz * dz <= r2)
                    desired.Add(kvp.Key);
            }

            foreach (var id in desired)
            {
                if (!_loaded.Contains(id))
                    toLoad.Add(_all[id]);
            }

            foreach (var id in _loaded)
            {
                if (!desired.Contains(id))
                    toUnload.Add(id);
            }

            _loaded.Clear();
            foreach (var id in desired)
                _loaded.Add(id);
        }
    }
}
