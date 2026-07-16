# Domain playbook — picking the modeling strategy

solidsight is one deterministic kernel, but different objects want
different strategies. Pick the row that matches the request, follow its
recipe, and keep the standard loop (build -> LOOK -> measure) in every
domain. When a request spans rows, decompose it into parts and give each
part its own strategy.

| domain | strategy | mode | key tools |
|---|---|---|---|
| enclosures, brackets, jigs | prism + features | print-safe | container, hole, standoff, hex_grid, snap_clip |
| mechanisms, drivetrains | catalog + declared fits | print-safe | spur_gear, bearings, joint(), motion, fit, expect() |
| furniture / framing | profiles + patterns | print-safe or free | extrusion_profile, linear_pattern, drawing |
| architecture / interiors | massing from sketches | free | polygon().extrude, loft, grid patterns, --slice plans |
| product / consumer shells | lofted skins + shelled interiors | print-safe | loft, shell-like offsets, round_rim, wrapped_text |
| vehicles / aircraft / ships | section lofts along a spine | free first | loft (convex sections), warp for fairing, symmetry via mirror |
| organic / artistic | twist, warp, revolve | free | warp(fn), refine, twist extrude, turntable renders |
| terrain / environments | heightfield warp on a refined slab | free | refine + warp with a deterministic height fn |
| jewelry / miniatures | small-scale detail discipline | print-safe --min-wall 0.4..0.8 | wrapped_text, patterns, --focus constantly |
| toys / game props | chunky forms + snap fits | print-safe | box_with_lid, snap_clip/slot, fillet last |

Rules that hold in EVERY domain:

1. **Decide the mode first.** Physical object -> `--print-safe` from
   build one. Visual asset -> `--free`, but still read the report:
   shells and cavities matter to meshes too.
2. **Organic does not mean unmeasured.** `warp()` and `loft()` outputs
   still get volume, walls and stability checked. A vase with a 0.4 mm
   wall is a fail whether or not it looks pretty.
3. **Deterministic noise only.** Terrain/texture displacement must come
   from a pure function of coordinates (e.g. `math.sin` composites or a
   hash you wrote down), never `random` without a fixed seed — the same
   model file must rebuild byte-identically.
4. **Semantic features everywhere.** Whatever the domain, emit parts
   with `features=[...]` metadata for the elements that MEAN something
   (windows, doors, gems, axle holes): downstream consumers get meaning,
   not triangles.
5. **Scale discipline for small things.** Jewelry and miniatures live at
   the printer's resolution floor: set `--min-wall` explicitly, inspect
   with `--focus`, and quote the wall numbers to the user.
6. **When it must exist physically, end with the manufacturing trio**:
   `--print-safe` clean, `--stl`/`--3mf` exported, `solidsight cost` for
   the material/time estimate — and `solidsight drawing` when a human
   will machine or check it.
