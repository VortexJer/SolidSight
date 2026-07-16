# Changelog

## v0.1.0 — 2026-07-16

First public release.

### Engine (`tool/`, pip package `solidsight`)
- Design language over the manifold3d kernel: parametric primitives,
  2D sketches (`stroke`, `round_corners`, offsets, text), booleans,
  transforms, Minkowski-based fillets, named parts via `emit()`.
- Deterministic software renderer (no GPU): multi-view PNGs with part
  legend, crease-aware Gouraud shading, silhouette/sharp-edge overlay,
  10 mm grid, axis triad, dimensions and scale bar; cross-section
  (`--slice`), turntable and exploded views. Byte-identical output for
  identical input.
- Validation report (`report.json`): volume, surface area, bbox, center of
  mass, shells, genus, watertightness, plate-aware minimum wall thickness
  (taper/fold-proof), overhang analysis, sealed internal cavity detection;
  `--print-safe` / `--free` modes, actionable checks with locations.
- Exact spatial query API (`solidsight query`): point classification,
  raycast with per-wall material segments, ASCII cross-section grids,
  voxelization with flood-fill cavity search.
- Assemblies: `place()`, `from_model()`, `from_stl()`; pairwise
  collision analysis (overlap bbox + volume + patch decomposition +
  move/shrink suggestions) and minimum clearances (`pairs[]`), exploded
  renders.
- Parametric catalog: involute spur gears, ISO threads/bolts/nuts,
  print-in-place hinge, snap clip + slot, box with lid, uniform-wall
  container, standoff, hex vent cutter + honeycomb panel, linear/grid/
  circular patterns, 3D tube sweeps, text.
- Errors written for LLM agents: what failed, where (file:line,
  coordinates, bboxes), what to try.

### Skill (`skill/`)
- `SKILL.md` workflow for coding agents + reference docs
  (design language, parts catalog, report guide).
- Six worked examples with committed real renders, reports and STLs,
  including an assembly collision->fixed pair and a hidden-cavity trap.

### Hardened by blind dogfooding (16 findings)
- Fixed: silent Gouraud fallback averaging normals across creases;
  union-touching false positive on interleaved cutters; polygon
  self-intersection silently splitting regions; stroke winding; thread
  twist-fold fins; wall-thickness false zeros on folds and taper wedges;
  misleading collision advice for oversized parts.
- Added: `hex_grid`, `stroke`, `tube_path`; bridge-aware overhang wording;
  patch-decomposed collision reports; regression test suite (14 tests).
