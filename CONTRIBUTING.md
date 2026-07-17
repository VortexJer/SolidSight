# Contributing

solidsight is a tool for AI agents; its contract is **determinism and
actionable feedback**. Keep both intact:

- Same input must produce byte-identical geometry, renders and reports.
  No randomness, no timestamps, no machine-dependent paths in outputs.
- Every error and check must say what failed, where (names, coordinates,
  bboxes), and what to try. "Invalid geometry" is a rejected review.
- Don't reinvent the kernel: geometry goes through manifold3d; solidsight's
  value is the feedback loop on top.

## Setup

```bash
pip install -e ./solidsight
pip install pytest ruff
pytest solidsight/tests
```

## Pull requests

1. Bug fixes come with a regression test in `solidsight/tests/` that fails
   before the fix.
2. New catalog parts need: docstring with pairing rules/conventions,
   an entry in `skill/references/parts-catalog.md`, and at least one test.
3. If a change affects renders or reports, regenerate the example outputs
   (`skill/examples/*/out`) with a clean install and commit them — they are
   the proof the loop works.
4. CI runs `ruff check` (errors only) and the test suite on Linux, macOS
   and Windows; all three must pass.

## Filing issues

Include the model file, the full CLI output, and `report.json` if the build
got that far. The error text is designed to be self-locating; paste it
verbatim.
