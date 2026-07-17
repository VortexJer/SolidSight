# 02 — Gold from memory vs measured gold (before / after)

Two materials, identical except for base colour:

```bash
shadersight material --base-color 1.0,0.86,0.57 --roughness 0.35 --metallic 1 --out out_memory
shadersight material --preset gold --roughness 0.35 --out out_preset
shadersight diff out_memory out_preset
```

`out_memory` is a plausible "gold-ish" guess — the kind everyone writes
from memory. `out_preset` is the measured F0 of gold from spectral n/k
data: (1.000, 0.766, 0.336) linear.

```
diff: [ok] -> [ok]
  base_color: [1.0, 0.86, 0.57] -> [1.0, 0.766, 0.336]
  compare: out_preset/compare.png  (before | after - LOOK at it)
```

<p align="center">
  <img src="out_preset/compare.png" width="80%">
</p>
<p align="center"><em>left: the guess (reads as pewter) · right: measured gold. Both conserve energy; only one is gold.</em></p>

Both materials PASS the physics (energy, reciprocity, positivity) —
being physical and being *right* are different questions, which is
exactly why the presets exist.
