# Platform reference — everything beyond build/query

All commands are deterministic and headless. Everything that writes
artifacts writes them reproducibly (no timestamps).

## Live development

```
solidsight watch model.py [any build flags] [--poll 0.5]
```
Rebuilds when the model or any sibling `.py` changes. Exact scene
fingerprints make skips PROVABLE: a cosmetic edit prints
"no geometric change — outputs untouched"; unchanged parts reuse their
export files. Each rebuild prints status + fail/warn counts + duration.

```
solidsight view model.py [--port 8377] [--no-watch]
```
Serves a self-contained browser viewer (vendored three.js, no CDN, no
telemetry) and hot-reloads it after every successful rebuild. Panel:
click a part to isolate; wire / x-ray / normals / bboxes / COM /
findings toggles; explode slider; section plane per axis; two-point
measurement (prints distance + per-axis deltas); findings list — click
one to fly the camera to its location. Ghost parts render translucent.

Progress + machine events on any build:
```
solidsight build model.py --progress                 # live stage lines on stderr
solidsight build model.py --events out/events.ndjson # NDJSON stream (stage, status, pct, eta)
```
Events are telemetry — they never enter report.json or renders.
`--skip-pairs` skips the O(n^2) pair analysis on huge assemblies
(declared expect() specs then FAIL as unverifiable — deliberately).

## Formats

```
solidsight build model.py --stl --3mf --obj --glb    # per part + combined
solidsight build model.py --slice z=5 --dxf --svg    # section outlines as 2D CAD
solidsight convert in.stl out.glb                    # stl/obj/ply/3mf/glb/off
```
`combined.glb` keeps the assembly structure: named parts with colors.
Import anything watertight with `from_mesh("part.glb")`. STEP/IGES are
BREP formats — out of mesh-kernel scope; a plugin can register them.

## Real-world components

```
solidsight components search "m4 socket head"   # ranked matches + exact call
solidsight components show iso4762_m4           # datasheet + free params
```
~70 real parts: ISO 4762/4017/4032/7089 fasteners, 608-class bearings,
NEMA 14/17/23, SG90, GT2 pulleys, MGN rails, T-slot extrusions, Tr8x8.
In models: `parts.component("iso4762_m4", length=16)`. No network —
data ships with the tool, builds reproduce forever.

## Drawings, robots, motion

```
solidsight drawing model.py [--part X]    # third-angle dimensioned PDF per part
solidsight robot model.py [--sdf] [--density 1.24]
solidsight motion model.py [--joint base_to_arm] [--steps 24]
```
- drawing: front/top/right with TRUE hidden lines (dashed), overall
  dims, center marks, hole table from detected circular rims, title
  block. Deterministic PDF.
- robot: `joint(parent, child, type=fixed|revolute|continuous|prismatic,
  axis, origin, limits, damping, name=None)` declared in the model ->
  URDF with exact per-link mass + inertia tensor (density g/cm3), visual
  + simplified collision meshes, tree validation with actionable errors.
  `name=` is the joint's identity in the URDF/SDF and in `motion
  --joint NAME`; it defaults to `<parent>_to_<child>`.
- motion: sweeps each moving joint through its limits; per sampled
  position the child link is intersected against every other part —
  exact collision map + free range. v1 needs principal joint axes.

## Reasoning and review

```
solidsight query model.py distance lid box   # exact min gap / overlap
solidsight fit 8 H7 g6                       # ISO 286-1 real values
solidsight explain internal-cavity           # meaning + evidence + fix menu
solidsight critique model.py                 # prioritized review + verified-good list
solidsight cost model.py --process cnc-alu   # fdm | fdm-petg | sla | cnc-alu
solidsight assembly model.py                 # BOM + axis play + sequence
```

## Benchmarks and plugins

```
solidsight bench run --dir benchmarks                      # self-test references
solidsight bench run 03-gear-pair --dir benchmarks --solution my.py
solidsight plugins
```
Benchmarks: six graded commissions (washer -> engine-lite) with
machine-checkable expectations — use them to calibrate yourself.
Plugins: pip packages exposing `register(api)` under entry-point group
`solidsight.plugins` (exporters, validators, parts packs). A crashing
plugin becomes a warning, never a failed build.
