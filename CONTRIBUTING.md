# Contributing

AISight is five tools for AI agents — solidsight, animationsight,
texturesight, shadersight, pcbsight — with one shared contract:
**determinism and actionable feedback**. Keep both intact:

- Same input must produce byte-identical reports, renders and exports.
  No randomness (fixed seeds where sampling is involved), no timestamps,
  no machine-dependent paths in outputs.
- Every error and finding must say what failed, where (names, frames,
  coordinates, bboxes), and what to try. "Invalid geometry" is a
  rejected review.
- Don't reinvent the foundations: geometry goes through manifold3d,
  meshes through trimesh. Each Sight's value is the measurement and
  feedback loop on top.
- Findings must earn belief: a check that can false-positive on a clean
  reference loses the tool the right to be trusted. Every example keeps
  a clean side that must stay clean.

## Setup

Each tool folder is self-contained (`pyproject.toml`, package, `skills/<tool>/`,
`examples/`, `tests/`). Install only what you are touching:

```bash
pip install -e ./animationsight        # or solidsight, texturesight, ...
pip install pytest ruff
cd animationsight && python -m pytest tests
```

Run each suite from its own tool directory, not the repo root — from the
root, the outer folders shadow the installed packages and imports break.

## Pull requests

1. Bug fixes come with a regression test in that tool's `tests/` that
   fails before the fix.
2. New checks, catalog parts or metrics need: a docstring with the
   conventions, an entry in the tool's `skills/<tool>/references/`, and at least
   one test asserting the right answer on known ground truth.
3. If a change affects reports, renders or evidence images, regenerate
   the affected `examples/*/` outputs with a clean install and commit
   them — they are the proof the loop works.
4. CI runs `ruff check` (errors only), all five test suites, and a
   solidsight CLI smoke test on Linux, macOS and Windows, Python 3.10
   and 3.13; everything must pass.
5. The skills ship inside the pip packages (`skill_data/`); a drift
   test keeps them identical to the repo's `skills/<tool>/` copies. Edit the
   `skills/<tool>/` copy and sync, or the test fails.

## Filing issues

Include the input file (model .py, .bvh, .obj+maps, material/graph
.json, or .kicad_pcb), the full CLI output, and `report.json` if the
run got that far. The error text is designed to be self-locating; paste
it verbatim.
