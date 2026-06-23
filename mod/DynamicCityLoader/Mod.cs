// Mod.cs
//
// Entry point for the DynamicCityLoader mod, built on the official Cities:
// Skylines II PDX modding framework (Game.Modding.IMod). See
// docs/CS2_MODDING_RESEARCH.md for the framework reference.

using System.IO;
using Colossal.IO.AssetDatabase;
using Colossal.Logging;
using Game;
using Game.Modding;
using Game.SceneFlow;
using DynamicCityLoader.Systems;

namespace DynamicCityLoader
{
    public class Mod : IMod
    {
        public const string Name = "DynamicCityLoader";

        public static ILog Log { get; } =
            LogManager.GetLogger(Name).SetShowsErrorsInUI(false);

        /// <summary>Folder this mod was loaded from (used to resolve the data dir).</summary>
        public static string ModDirectory { get; private set; }

        /// <summary>Where the Python pipeline's JSON exports are expected to live.</summary>
        public static string DataDirectory =>
            ModDirectory != null ? Path.Combine(ModDirectory, "data") : null;

        public void OnLoad(UpdateSystem updateSystem)
        {
            Log.Info($"{Name} OnLoad");

            if (GameManager.instance.modManager.TryGetExecutableAsset(this, out var asset))
            {
                ModDirectory = Path.GetDirectoryName(asset.path);
                Log.Info($"Mod directory: {ModDirectory}");
            }

            // Build/teardown of city geometry runs in a Modification phase so it
            // happens after the simulation has set up its core systems.
            updateSystem.UpdateAt<CityBuilderSystem>(SystemUpdatePhase.Modification1);
        }

        public void OnDispose()
        {
            Log.Info($"{Name} OnDispose");
        }
    }
}
