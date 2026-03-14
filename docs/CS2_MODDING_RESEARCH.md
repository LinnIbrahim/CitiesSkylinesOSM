# CS2 Modding Research — Technical Reference

## Modding Framework

Two options exist. The **official PDX framework** is recommended:

### PDX Framework (Official)
- Mods implement `Game.Modding.IMod` interface
- Entry point: `OnLoad(UpdateSystem updateSystem)` / `OnDispose()`
- Install via Visual Studio/Rider template (search "colossal" in new project)
- Sets `CSII_TOOLPATH` env var, provides `Mod.props`/`Mod.targets` MSBuild imports

### BepInEx + Harmony (Legacy)
- BepInEx 6 (Mono) with HarmonyX
- Mods inherit `BaseUnityPlugin` with `[BepInPlugin]`
- Harmony can't patch Burst-compiled code

## Project Setup

- **Target Framework**: `net472`
- **Unity Version**: 2022.3.7f1
- **Language**: C# 9

### Key Assembly References (from game's `Cities2_Data/Managed/`)
- `Game` — all `Game.*` namespaces
- `Colossal.Core`, `Colossal.Collections`, `Colossal.Mathematics`, `Colossal.IO.AssetDatabase`
- `Colossal.UI`, `Colossal.UI.Binding`, `Colossal.Localization`
- `Unity.Entities`, `Unity.Mathematics`, `Unity.Collections`, `Unity.Burst`
- `UnityEngine.CoreModule`

### Mod Deploy Path
```
%LOCALAPPDATA%Low\Colossal Order\Cities Skylines II\Mods\
```

### .csproj Structure
```xml
<Import Project="$([System.Environment]::GetEnvironmentVariable('CSII_TOOLPATH', 'EnvironmentVariableTarget.User'))\Mod.props" />
<Import Project="$([System.Environment]::GetEnvironmentVariable('CSII_TOOLPATH', 'EnvironmentVariableTarget.User'))\Mod.targets" />
```

## Architecture: Unity ECS (DOTS)

All game objects are **entities** with **components**. Logic runs in **systems**.

### Mod Entry Point
```csharp
using Game; using Game.Modding;
public class Mod : IMod
{
    public void OnLoad(UpdateSystem updateSystem)
    {
        updateSystem.UpdateAt<MySystem>(SystemUpdatePhase.Modification1);
    }
    public void OnDispose() { }
}
```

### Custom System
```csharp
public partial class MySystem : GameSystemBase
{
    protected override void OnCreate() { base.OnCreate(); }
    protected override void OnUpdate() { /* process entities */ }
}
```

### SystemUpdatePhase Values
- `PrefabUpdate` — prefab initialization
- `Modification1`–`Modification5` — game state modifications
- `ToolUpdate` / `ApplyTool` — tool systems
- `UIUpdate` — UI bindings
- `Serialize` / `Deserialize` — save/load

## Road/Network Creation

Roads are **network entities** in ECS:

### Entity Structure
| Component | Purpose |
|-----------|---------|
| `Game.Net.Node` | Intersection/endpoint position |
| `Game.Net.Edge` | Road segment (has `m_Start`, `m_End` node entities) |
| `Game.Net.Curve` | Bezier geometry for edges |
| `Game.Net.Lane`, `CarLane`, `TrackLane`, `PedestrianLane` | Sub-entities for lanes |
| `Game.Net.Composition` | Links edge to network prefab |
| `Game.Net.Elevation` | Height data |

### Key Systems
| System | Purpose |
|--------|---------|
| `GeometrySystem` | Computes geometry from curves |
| `LaneSystem` | Creates/manages lanes |
| `AggregateSystem` | Groups edges into aggregates |
| `SearchSystem` | Spatial search |
| `OutsideConnectionSystem` | Map-edge connections |

### Network Prefab Types
- `RoadPrefab` — roads (`m_SpeedLimit`, `m_RoadType`, `m_ZoneBlock`)
- `TrackPrefab` — railways (`m_SpeedLimit`, `m_TrackType`)
- `PathwayPrefab` — pedestrian paths

### TrackTypes
- `TrackTypes.Train`, `TrackTypes.Subway`, `TrackTypes.Tram`

### Creating Custom Prefabs at Runtime
```csharp
var prefab = ScriptableObject.CreateInstance<RoadPrefab>();
prefab.name = "MyCustomRoad";
prefab.m_SpeedLimit = 60;
prefab.m_Sections = sections;
prefabSystem.AddPrefab(prefab);
Entity prefabEntity = prefabSystem.GetEntity(prefab);
```

### IMPORTANT: Road Placement
Roads are NOT created via `EntityManager.CreateEntity()`. The game uses **tool systems** that create temporary "definition" entities processed by `ApplyNetSystem` into proper network entities with all required components. Use existing `NetToolSystem` or create prefabs placed via tool systems.

## Building Placement

### Key Components
| Component | Purpose |
|-----------|---------|
| `Game.Objects.Transform` | Position + rotation (float3 + quaternion) |
| `Game.Buildings.Building` | Building marker |
| `ResidentialProperty`, `CommercialProperty`, `IndustrialProperty`, `OfficeProperty` | Zone types |
| `PublicTransportStation`, `TransportDepot` | Transit buildings |
| `PrefabRef` | Links entity to prefab definition |
| `Owner` | Parent-child relationships |

### Placement
```csharp
using Transform = Game.Objects.Transform;
var transform = new Transform(position, rotation); // float3, quaternion
```

## Transit/Route Systems

### Key Components
| Component | Purpose |
|-----------|---------|
| `Game.Routes.Route` | Route entity marker |
| `Game.Routes.RouteWaypoint` | Waypoint in a route |
| `BusStop`, `TrainStop`, `TaxiStand` | Transport stop markers |
| `PublicTransportStation` | Station building |

### Key Systems
- `WaypointConnectionSystem` — connects waypoints to stops/nodes
- `RoutePathSystem` — computes paths via pathfinding
- `InitializeSystem`, `SearchSystem`

## Namespace Map

| Namespace | Key Types |
|-----------|-----------|
| `Game.Modding` | `IMod` |
| `Game.Net` | `Edge`, `Node`, `Curve`, `Lane`, `CarLane`, `TrackLane`, `Composition`, `Elevation`, `TrackTypes` |
| `Game.Prefabs` | `PrefabRef`, `PrefabSystem`, `RoadPrefab`, `TrackPrefab`, `NetSectionPrefab`, `BuildingData` |
| `Game.Buildings` | `Building`, `PublicTransportStation`, property components |
| `Game.Objects` | `Transform`, `SubObject`, `Elevation` |
| `Game.Routes` | Route/waypoint/transit components |
| `Game.Common` | `Created`, `Deleted`, `Owner`, `PrefabRef` |
| `Game.Tools` | `ToolBaseSystem`, `ToolSystem`, `ControlPoint`, `TypeMask`, `Layer` |

## Key Open-Source Repos

| Repo | What it does | Key APIs |
|------|-------------|----------|
| [RoadBuilder-CSII](https://github.com/JadHajjar/RoadBuilder-CSII) | Custom road prefabs at runtime | `PrefabSystem`, `RoadPrefab`, `NetSectionPrefab` |
| [Traffic (TM:PE)](https://github.com/krzychu124/Traffic) | Traffic management | `Game.Net`, lane connections |
| [LineTool-CS2](https://github.com/algernon-A/LineTool-CS2) | Place objects in lines/curves | `Game.Objects.Transform`, `EntityCommandBuffer` |
| [Cities2Modding](https://github.com/optimus-code/Cities2Modding) | Modding guide | Setup docs |
| [cs2-ecs-explorer](https://github.com/Captain-Of-Coit/cs2-ecs-explorer) | ECS browser | Component/system mapping |
| [MapExt2](https://github.com/Noel-leoN/MapExt2) | Map size 4x4 | Harmony, map systems |
| [UrbanDevKit](https://github.com/CitiesSkylinesModding/UrbanDevKit) | SDK utilities | Modular SDK |

## Technical Notes

1. **No direct entity creation for roads** — use tool systems or prefab approach
2. **Prefab approach is primary** — create `ScriptableObject` prefabs, register via `PrefabSystem.AddPrefab()`, place with tool systems
3. **Harmony can't patch Burst code** — but ECS lets you create systems reading/writing same components
4. **UI uses web tech** — Coherent GT/cohtml, TypeScript/SCSS, communicate via `GetterValueBinding`/`TriggerBinding`
5. **System order matters** — use `UpdateBefore<T>`, `UpdateAfter<T>`, `UpdateAt<T>`
