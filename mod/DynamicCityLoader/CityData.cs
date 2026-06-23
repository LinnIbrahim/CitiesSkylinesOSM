// CityData.cs
//
// C# data models mirroring the JSON produced by the Python pipeline
// (python/cs2_converter.py). The property names use [JsonProperty] so the
// lower-case / snake_case keys in the export map cleanly onto C# properties.
//
// Two shapes are supported:
//   * CityData   -> the flat "*_full.json" export
//   * CityChunk  -> one entry of the "*_chunks.json" array
//
// Both reuse the same feature record types.

using System.Collections.Generic;
using Newtonsoft.Json;

namespace DynamicCityLoader
{
    /// <summary>A single point in CS2 world space (metres). Y is elevation.</summary>
    public struct Point3
    {
        [JsonProperty("x")] public float X { get; set; }
        [JsonProperty("y")] public float Y { get; set; }
        [JsonProperty("z")] public float Z { get; set; }
    }

    public class RoadSegment
    {
        [JsonProperty("id")]             public string Id { get; set; }
        [JsonProperty("type")]           public string Type { get; set; }
        [JsonProperty("category")]       public string Category { get; set; }  // "vehicle" | "pedestrian"
        [JsonProperty("name")]           public string Name { get; set; }
        [JsonProperty("points")]         public List<Point3> Points { get; set; }
        [JsonProperty("lanes")]          public int Lanes { get; set; }
        [JsonProperty("width")]          public float? Width { get; set; }
        [JsonProperty("oneWay")]         public bool OneWay { get; set; }
        [JsonProperty("speedLimit")]     public int SpeedLimit { get; set; }
        [JsonProperty("priority")]       public int Priority { get; set; }

        // Set when the real lane count exceeded the vanilla CS2 ceiling and the
        // road was clamped to the widest available type (e.g. Texas freeways).
        [JsonProperty("clamped")]        public bool Clamped { get; set; }
        [JsonProperty("original_lanes")] public int? OriginalLanes { get; set; }

        // Numbered-route shield (e.g. "A12") and its class colour, when present.
        [JsonProperty("ref")]            public string Ref { get; set; }
        [JsonProperty("ref_colour")]     public string RefColour { get; set; }

        [JsonProperty("theme")]          public string Theme { get; set; }
        [JsonProperty("eu_prefab")]      public string EuPrefab { get; set; }
        [JsonProperty("traffic_side")]   public string TrafficSide { get; set; }
    }

    public class RailwaySegment
    {
        [JsonProperty("id")]          public string Id { get; set; }
        [JsonProperty("type")]        public string Type { get; set; }
        [JsonProperty("name")]        public string Name { get; set; }
        [JsonProperty("points")]      public List<Point3> Points { get; set; }
        [JsonProperty("electrified")] public bool Electrified { get; set; }
        [JsonProperty("theme")]       public string Theme { get; set; }
        [JsonProperty("eu_prefab")]   public string EuPrefab { get; set; }
    }

    public class Waterway
    {
        [JsonProperty("id")]     public string Id { get; set; }
        [JsonProperty("type")]   public string Type { get; set; }
        [JsonProperty("name")]   public string Name { get; set; }
        [JsonProperty("isArea")] public bool IsArea { get; set; }
        [JsonProperty("points")] public List<Point3> Points { get; set; }
    }

    public class Building
    {
        [JsonProperty("id")]          public string Id { get; set; }
        [JsonProperty("type")]        public string Type { get; set; }
        [JsonProperty("zone")]        public string Zone { get; set; }
        [JsonProperty("density")]     public string Density { get; set; }
        [JsonProperty("cs2_subtype")] public string Cs2Subtype { get; set; }
        [JsonProperty("name")]        public string Name { get; set; }
        [JsonProperty("height")]      public float Height { get; set; }
        [JsonProperty("levels")]      public int Levels { get; set; }
        [JsonProperty("material")]    public string Material { get; set; }
        [JsonProperty("roof_shape")]  public string RoofShape { get; set; }
        [JsonProperty("colour")]      public string Colour { get; set; }
        [JsonProperty("points")]      public List<Point3> Points { get; set; }
    }

    public class TransitStop
    {
        [JsonProperty("id")]       public string Id { get; set; }
        [JsonProperty("name")]     public string Name { get; set; }
        [JsonProperty("type")]     public string Type { get; set; }
        [JsonProperty("position")] public Point3 Position { get; set; }
    }

    public class TransitRoute
    {
        [JsonProperty("id")]     public string Id { get; set; }
        [JsonProperty("name")]   public string Name { get; set; }
        [JsonProperty("number")] public string Number { get; set; }
        [JsonProperty("type")]   public string Type { get; set; }
        [JsonProperty("stops")]  public List<string> Stops { get; set; }
    }

    public class TransitData
    {
        [JsonProperty("stops")]  public List<TransitStop> Stops { get; set; }
        [JsonProperty("routes")] public List<TransitRoute> Routes { get; set; }
    }

    /// <summary>Axis-aligned chunk bounds in CS2 world space (X/Z plane).</summary>
    public struct ChunkBounds
    {
        [JsonProperty("x_min")] public float XMin { get; set; }
        [JsonProperty("z_min")] public float ZMin { get; set; }
        [JsonProperty("x_max")] public float XMax { get; set; }
        [JsonProperty("z_max")] public float ZMax { get; set; }

        public float CentreX => (XMin + XMax) * 0.5f;
        public float CentreZ => (ZMin + ZMax) * 0.5f;
    }

    /// <summary>One entry from the chunked export array.</summary>
    public class CityChunk
    {
        [JsonProperty("chunk_id")]  public string ChunkId { get; set; }
        [JsonProperty("bounds")]    public ChunkBounds Bounds { get; set; }
        [JsonProperty("roads")]     public List<RoadSegment> Roads { get; set; }
        [JsonProperty("railways")]  public List<RailwaySegment> Railways { get; set; }
        [JsonProperty("waterways")] public List<Waterway> Waterways { get; set; }
        [JsonProperty("buildings")] public List<Building> Buildings { get; set; }
        [JsonProperty("transit")]   public TransitData Transit { get; set; }
    }

    public class CityMeta
    {
        [JsonProperty("city")]            public string City { get; set; }
        [JsonProperty("theme")]           public Newtonsoft.Json.Linq.JObject Theme { get; set; }
        [JsonProperty("elevation_points")] public int ElevationPoints { get; set; }
    }

    /// <summary>The flat "*_full.json" export.</summary>
    public class CityData
    {
        [JsonProperty("roads")]     public List<RoadSegment> Roads { get; set; }
        [JsonProperty("railways")]  public List<RailwaySegment> Railways { get; set; }
        [JsonProperty("waterways")] public List<Waterway> Waterways { get; set; }
        [JsonProperty("buildings")] public List<Building> Buildings { get; set; }
        [JsonProperty("transit")]   public TransitData Transit { get; set; }
        [JsonProperty("_meta")]     public CityMeta Meta { get; set; }
    }
}
