// CityBuilderSystem.cs
//
// Drives realisation of the imported city into the game world. This is the
// integration boundary with the CS2 ECS: it loads the data, resolves prefabs,
// and (chunk by chunk) hands segments to the network-creation flow.
//
// IMPORTANT (see docs/CS2_MODDING_RESEARCH.md): roads/tracks are NOT created
// via EntityManager.CreateEntity. The game realises networks through tool /
// definition systems processed by ApplyNetSystem. The creation helpers below
// mark exactly where that flow plugs in; everything up to that point (loading,
// chunk selection, prefab lookup, control-point construction) is real.

using System.Collections.Generic;
using System.IO;
using Colossal.Logging;
using Game;
using Game.Prefabs;
using Unity.Entities;
using Unity.Mathematics;

namespace DynamicCityLoader.Systems
{
    public partial class CityBuilderSystem : GameSystemBase
    {
        private static readonly ILog Log = Mod.Log;

        private PrefabSystem _prefabSystem;
        private readonly ChunkManager _chunks = new ChunkManager();

        // Cache of resolved network prefab entities keyed by eu_prefab name.
        private readonly Dictionary<string, Entity> _prefabCache =
            new Dictionary<string, Entity>();

        private bool _dataLoaded;

        protected override void OnCreate()
        {
            base.OnCreate();
            _prefabSystem = World.GetOrCreateSystemManaged<PrefabSystem>();
            // Idle until a city is explicitly loaded (e.g. from a mod UI action).
            Enabled = false;
        }

        /// <summary>
        /// Load the chunked export shipped alongside the mod and enable building.
        /// Hook this to a UI button or a keybind.
        /// </summary>
        public void LoadCity(string chunkFileName = "selection_chunks.json")
        {
            if (Mod.DataDirectory == null)
            {
                Log.Error("Data directory unknown; cannot load city.");
                return;
            }

            var path = Path.Combine(Mod.DataDirectory, chunkFileName);
            var chunks = CityDataLoader.LoadChunks(path);
            if (chunks.Count == 0)
            {
                Log.Warn("No chunks loaded; nothing to build.");
                return;
            }

            _chunks.SetChunks(chunks);
            _dataLoaded = true;
            Enabled = true;
            Log.Info($"City loaded: {chunks.Count} chunks ready for realisation.");
        }

        protected override void OnUpdate()
        {
            if (!_dataLoaded)
                return;

            // TODO: derive the focus point from the active camera. Until the
            // camera hook is wired, use the map origin so the central chunks
            // realise on first update.
            float focusX = 0f, focusZ = 0f;

            _chunks.Update(focusX, focusZ, out var toLoad, out var toUnload);

            foreach (var chunk in toLoad)
                RealiseChunk(chunk);

            foreach (var id in toUnload)
                Log.Info($"(unload) chunk {id} — teardown not yet implemented.");
        }

        private void RealiseChunk(CityChunk chunk)
        {
            Log.Info(
                $"Realising chunk {chunk.ChunkId}: {Count(chunk.Roads)} roads, " +
                $"{Count(chunk.Railways)} railways, {Count(chunk.Buildings)} buildings.");

            if (chunk.Roads != null)
                foreach (var road in chunk.Roads)
                    CreateNetwork(road.EuPrefab, road.Type, road.Points);

            if (chunk.Railways != null)
                foreach (var rail in chunk.Railways)
                    CreateNetwork(rail.EuPrefab, rail.Type, rail.Points);

            // Buildings and transit follow once network realisation is proven.
        }

        /// <summary>
        /// Resolve a network prefab by name and create the segment along the
        /// given polyline. The control points are real; the final hand-off to
        /// the net tool / ApplyNetSystem flow is the remaining integration step.
        /// </summary>
        private void CreateNetwork(string prefabName, string fallbackType, List<Point3> points)
        {
            if (points == null || points.Count < 2)
                return;

            Entity prefab = ResolvePrefab(prefabName ?? fallbackType);
            if (prefab == Entity.Null)
                return;

            // Convert the exported polyline into CS2 control points.
            var controlPoints = new List<float3>(points.Count);
            foreach (var p in points)
                controlPoints.Add(new float3(p.X, p.Y, p.Z));

            // INTEGRATION POINT:
            // Feed `prefab` + `controlPoints` into the net creation flow. The
            // game expects temporary "definition" entities (control points +
            // CreationDefinition referencing `prefab`) that ApplyNetSystem turns
            // into Edge/Node/Curve network entities. See RoadBuilder-CSII and
            // LineTool-CS2 (docs/CS2_MODDING_RESEARCH.md) for the concrete flow.
        }

        /// <summary>Look up (and cache) a network prefab entity by name.</summary>
        private Entity ResolvePrefab(string name)
        {
            if (string.IsNullOrEmpty(name))
                return Entity.Null;

            if (_prefabCache.TryGetValue(name, out var cached))
                return cached;

            Entity entity = Entity.Null;
            // NetGeometryPrefab is the base for RoadPrefab/TrackPrefab.
            var id = new PrefabID(nameof(NetGeometryPrefab), name);
            if (_prefabSystem.TryGetPrefab(id, out PrefabBase prefab) &&
                _prefabSystem.TryGetEntity(prefab, out entity))
            {
                // resolved
            }
            else
            {
                Log.Warn($"Prefab not found: '{name}' — needs mapping to a real CS2 prefab.");
            }

            _prefabCache[name] = entity;
            return entity;
        }

        private static int Count<T>(List<T> list) => list?.Count ?? 0;
    }
}
