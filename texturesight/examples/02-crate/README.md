# 02 — The starved lid (before / after)

`make_crate.py` writes the same 50 mm crate twice: once with the lid's
UV island packed at 1/3 the scale of the others (the classic "shrank it
to make room and forgot to re-balance" edit), once fixed.

```bash
texturesight inspect --mesh crate_starved.obj --out out_starved
texturesight inspect --mesh crate_fixed.obj   --out out_fixed
texturesight diff out_starved out_fixed
```

## Before

```
texel density @ 1024px: 5.46 px/unit mean (2.05..6.14), spread 3.0x
islands: #4 is the sparsest (2.05 px/unit, 2 face(s)) vs #0 (6.14)
[WARN] texel density varies 3.0x across the mesh (2.05..6.14 px/unit)
       where: island #4 at uv (0.35, 0.35)-(0.45, 0.45): 2.05 px/unit vs 5.46 mesh mean
       try:   scale island #4 up ~2.7x in the UV editor (islands are
              labelled in uv_layout.png); repack if it no longer fits
```

On the model this is invisible until the texture is painted — and then
the lid is blurry forever. In `uv_density.png` it is a dark square.

## After (the `try:` line, applied)

```
texturesight diff out_starved out_fixed
  density: mean 5.46 -> 6.14 px/unit; spread 3.0x -> 1.0x
  packing: 46% -> 54%
  GONE [texel-density-uneven] texel density varies 3.0x across the mesh
  GONE [uv-packing-loose] the UV layout uses 46% of the square
```

<p align="center">
  <img src="out_starved/uv_density.png" width="49%">
  <img src="out_fixed/uv_density.png" width="49%">
</p>
<p align="center"><em>texel density painted per face: before (island #4 dark = starved) and after (uniform)</em></p>
