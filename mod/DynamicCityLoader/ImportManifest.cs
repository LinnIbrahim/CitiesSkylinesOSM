// ImportManifest.cs
//
// Mirrors import_manifest.json, written next to the city data by the web
// generator's "Import to CS2" action. It tells the mod which files to load and
// which game options the user asked to be applied on load.

using Newtonsoft.Json;

namespace DynamicCityLoader
{
    public class ImportOptions
    {
        [JsonProperty("unlimitedMoney")] public bool UnlimitedMoney { get; set; } = true;
        [JsonProperty("unlockAll")]      public bool UnlockAll { get; set; } = true;
        [JsonProperty("useMods")]        public bool UseMods { get; set; } = true;
        [JsonProperty("mapTiles")]       public string MapTiles { get; set; } = "all";
    }

    public class ImportManifest
    {
        [JsonProperty("city")]        public string City { get; set; }
        [JsonProperty("generatedAt")] public string GeneratedAt { get; set; }
        [JsonProperty("full")]        public string Full { get; set; }
        [JsonProperty("chunks")]      public string Chunks { get; set; }
        [JsonProperty("options")]     public ImportOptions Options { get; set; }
        [JsonProperty("notes")]       public string Notes { get; set; }
    }
}
