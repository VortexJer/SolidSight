# The *Sight family: what exists, what does not, and why

A request on the table: build **AnimationSight**, **TextureSight**,
**ShaderSight** and **PCBSight** — the solidsight philosophy (the agent
is blind; give it exact numbers instead of pictures) applied to four
more domains.

This document is the honest scoping. solidsight's credibility rests on
everything in the repo being real, tested and reproducible; shipping
four skeleton products would spend that credibility. What follows is
what actually exists today, and a concrete architecture for each future
product so the work can start from a plan instead of a slogan.

## What exists today (real, tested)

The motion/kinematics slice of AnimationSight lives INSIDE solidsight,
because it shares the geometry kernel:

- `joint()` declarations -> URDF/SDF with exact masses and inertia
  tensors (`solidsight robot`);
- `solidsight motion` sweeps any declared joint through its limits and
  returns the exact collision map (which positions hit which parts,
  with overlap volumes) — rigid-body kinematic validation, measured,
  not watched;
- `parts.swept()` for insertion paths and `expect()` for declared
  clearance specs.

## AnimationSight (skeletal animation as measurable motion)

Not built. Architecture when it is:

- **Input**: glTF/BVH animation clips (trimesh already parses glTF).
- **Core**: sample joint transforms over time; differentiate for
  velocity / acceleration / jerk per joint; contact events from mesh
  proximity per frame (the solidsight pair machinery, batched over
  time); balance = COM trajectory vs support polygon (the stability
  check, animated).
- **Output**: report.json per clip (peaks, discontinuities, contact
  table, penetration events with exact frames), turntable-style frame
  renders, and a diff mode between two takes.
- **Hard part**: none of it is exotic — it is the O(frames x pairs)
  cost and a good report vocabulary.

## TextureSight (UV/texture authoring as data)

Not built. Needs a different substrate than CSG solids: UV-unwrapped
authored meshes.

- **Core measurements**: texel density per face (UV area vs 3D area),
  seam detection (UV islands vs mesh adjacency), stretch/distortion
  (singular values of the per-face UV Jacobian), tiling periodicity
  (autocorrelation), normal-map continuity across seams, AO statistics.
- All deterministic, all reportable without looking at a picture.
- **Blocker**: solidsight models have no UVs; this tool audits meshes
  from DCC pipelines, so it is a sibling package, not a solidsight
  feature.

## ShaderSight (shaders as mathematical systems)

Not built. The honest version requires executing shader graphs on a
deterministic software evaluator (luminance statistics, energy
conservation of a BRDF, gradient/banding analysis, cost models per
node). That is a compiler + evaluator project of solidsight's own size.
A believable first slice: a deterministic BRDF test-harness that
evaluates material definitions over a hemisphere grid and reports
energy conservation + reciprocity numerically.

## PCBSight (board design as AI-readable engineering)

Not built. The realistic path is NOT reimplementing a DRC engine:
KiCad's Python API already exposes nets, courtyards, clearances and DRC
programmatically. PCBSight should be a thin, solidsight-flavored report
layer over kicad-cli (exact findings, where + try, deterministic JSON)
plus the 3D courtyard/enclosure collision check — which solidsight
already does today when you export the board outline as a ghost part
(`from_mesh(board.glb)` + `place(ghost=True)` + pair analysis).

## Why this order

Each product is only worth building the way solidsight was built:
dogfooded blind, every metric pinned by a regression test, every claim
reproducible from the repo. That is one product at a time.
