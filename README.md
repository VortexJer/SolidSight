# AISight

![ci](https://github.com/VortexJer/AISight/actions/workflows/ci.yml/badge.svg)

**Sight for AI agents.** An agent cannot look at a screen — and almost
everything creative software asks a human to *look at* is actually a
measurable property of the data. AISight is a family of five
independent tools, one per domain, that replace looking with measuring:
deterministic builds, exact reports with `where` and `try:` on every
finding, and renders only as evidence for what the numbers found.

| tool | domain | replaces | docs |
|---|---|---|---|
| **solidsight** | 3D design / CAD / 3D printing | eyes on a viewport | [README](solidsight/README.md) |
| **animationsight** | animation clips, mocap (.bvh) | watching the take | [README](animationsight/README.md) |
| **texturesight** | UVs + texture maps | squinting at a checker | [README](texturesight/README.md) |
| **shadersight** | materials/BRDFs + node graphs | rendering a sphere | [README](shadersight/README.md) |
| **pcbsight** | PCB layouts (.kicad_pcb) | eyeballing copper | [README](pcbsight/README.md) |

## Install

Each tool is its own pip package: install **one**, **some**, or **all**.
They share a philosophy, not a dependency — none requires another.

**One tool** (its folder name is its subdirectory):

```bash
pip install "git+https://github.com/VortexJer/AISight#subdirectory=solidsight"
pip install "git+https://github.com/VortexJer/AISight#subdirectory=animationsight"
pip install "git+https://github.com/VortexJer/AISight#subdirectory=texturesight"
pip install "git+https://github.com/VortexJer/AISight#subdirectory=shadersight"
pip install "git+https://github.com/VortexJer/AISight#subdirectory=pcbsight"
```

**All five** in one line:

```bash
for t in solidsight animationsight texturesight shadersight pcbsight; do pip install "git+https://github.com/VortexJer/AISight#subdirectory=$t"; done
```

or from a checkout:

```bash
git clone https://github.com/VortexJer/AISight
pip install ./AISight/solidsight ./AISight/animationsight ./AISight/texturesight ./AISight/shadersight ./AISight/pcbsight
```

Requirements: Python >= 3.10, pip, git. solidsight carries the heavy
dependencies (manifold3d, trimesh, scipy, matplotlib — all wheels); the
other four need only numpy and pillow.

## What installing gives an AI agent

Every tool ships its **Claude Code skill inside the pip package**. The
first time its CLI runs on a machine that has Claude Code (`~/.claude`
exists), the skill installs itself into `~/.claude/skills/<tool>/` and
keeps itself updated on version changes — from then on, any new agent
session routes matching requests to the tool ("design a bracket" ->
solidsight, "review this .bvh" -> animationsight, "check my board" ->
pcbsight). No Claude Code? The CLIs work standalone for humans and
scripts; nothing else is touched.

`<tool> uninstall` removes the skill AND the pip package. No telemetry,
no services, no accounts.

## The standard every tool holds itself to

- **Known ground truth**: every example is synthetic on purpose, with
  defects injected at exact magnitudes, so the tests assert the *right*
  answer — and that the clean reference stays clean, because false
  positives are how a tool loses the right to be believed.
- **Deterministic**: same input, byte-identical report; fixed seeds
  where sampling is involved, resolution stated in the report.
- **The full loop**: inspect -> fix -> **diff to prove the fix did what
  you meant and nothing else**.
- **Honest scope**: each README lists what is NOT read or checked.

The family overview — and the bugs each tool caught in its own
reference, which is the recurring proof of the whole idea:
[docs/roadmap-sights.md](docs/roadmap-sights.md).

## Repository layout

```
solidsight/      3D design: engine + CLI, skill/ (+ domains/), examples, benchmarks
animationsight/  motion clips as measurement
texturesight/    UVs + texture maps
shadersight/     materials + node graphs
pcbsight/        board layouts
docs/            the blind-vs-loop comparison study, plugins, family roadmap
```

Each tool folder is self-contained: `pyproject.toml`, the package, its
`skill/`, `examples/` with committed real outputs, and `tests/`.

## License

MIT
