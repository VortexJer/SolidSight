# From a photo or drawing to a model

You can see the image; the kernel cannot. Split the work accordingly:
**you** judge what the object is, its real size and which features
matter — **the tool** turns the parts of the image that are literally
geometry into exact shapes, and proves whether your model matches.

## The workflow

1. **LOOK at the image first** (Read tool) and write down, before any
   code: what the object is, its estimated real dimensions (anchor on
   something in frame: a hand ~180 mm, a coin ~24 mm, a USB-A plug
   12 mm wide, paper 210 mm), and the 3-6 features that define it.
   State each estimate with its anchor: "width ~= 64 mm [coin next to
   it]". If nothing in frame gives scale, ask the user for ONE
   dimension rather than guessing silently.
2. **Decide the strategy per feature:**
   - Flat silhouette that must be faithful (logo, gasket, stencil,
     plate outline, engraving artwork) -> `image_outline()` traces it
     exactly. Do not re-draw a complex outline with polygon() by eye.
   - A designed OUTER PROFILE seen straight-on (a car side view, a
     bottle/chair/phone side profile, an aircraft side) -> DON'T
     eyeball its proportions. `profile_read()` MEASURES the silhouette
     into exact mm: overall length/height, and the upper + lower
     envelope sampled station by station, plus wheel axles for a
     vehicle. Build your loft/revolve/`loft_sections` stations by
     SAMPLING those measured numbers. See below and, for cars,
     `car-bodies.md`.
   - Relief / emboss / lithophane / terrain -> `image_heightfield()`.
   - Everything else (the 3D form of the object) -> normal parametric
     modeling from your feature list; the image is reference, not
     input. Photos have perspective — never trace a 3D object's photo
     with image_outline() and call it the object. (A straight-on side
     view is the exception: that IS an orthographic profile, and
     `profile_read()` is built to measure it.)
3. **Build with `--ref photo.png`** — every build then writes
   `renders/00_reference_vs_render.png` with the reference beside your
   first render. LOOK at that sheet after every build and name the
   differences out loud (proportions, missing features, wrong
   corner radii...). Fix the biggest difference, rebuild, repeat.
4. Validate as always: report.json, print-safe if it will be printed.

## image_outline(path, width=|height=, threshold=0.5, invert=False, simplify=0.4, min_area=None) -> Sketch

Traces dark shapes (ink on paper) into a centered Sketch, holes
preserved (even-odd). Give the REAL size via exactly one of width= or
height= (mm) — this is where your size estimate from step 1 goes.
Light-on-dark images need `invert=True`. `simplify` is the max
straightening deviation in mm; `min_area` (mm^2) drops specks (a
`image-specks-dropped` warning tells you when it happened).

```python
logo = image_outline("logo.png", width=60)
badge = rect(70, 70).round_corners(8).extrude(3)
badge = badge - logo.extrude(2).translate(0, 0, 2)   # engrave 1 mm
emit(badge, name="badge", color="steel")
```

Works for: engraved/embossed artwork, cookie cutters (extrude + shell),
gaskets and flat plates from a scan, stencils, sign text drawn by hand.

Photos of flat objects: photograph as straight-on as possible; a
skewed photo traces a skewed outline. Threshold first if the
background is busy (edit the image, or raise/lower `threshold`).

## profile_read(path, length=|wheelbase+axle_px, stations=14, invert=False, threshold=0.5, overlay=) -> dict

MEASURES a straight-on side/front silhouette into exact millimetres so
a designed outer form is built from numbers, not a squint. Also on the
CLI: `solidsight profile side.png --length 4465 --out check.png`.

Give ONE real anchor: `length=<mm>` (published for every car/product),
or `wheelbase=<mm>` with `axle_px=(front_col, rear_col)` if you read
the axle pixel columns yourself. Returns a dict:

- `length_mm`, `height_mm` — the silhouette's two in-plane extents.
- `stations`: a list of `{x, top_z, bottom_z}` — the UPPER envelope
  (roofline / crown / top profile) and LOWER envelope (underside)
  sampled left-to-right. These are the numbers your loft stations copy.
- `axles`: ground-touching wheel clusters `{x, radius}` and
  `wheelbase_measured_mm` (compare it to the published wheelbase to
  confirm your scale is right).

Always pass `overlay=` and LOOK at the result: red dots on the crown,
green on the underside, orange lines through the wheels. A wrong read
shows up instantly — fix the image/threshold before you model.

```python
r = profile_read("vantage_side.png", length=4465, stations=14,
                 overlay="vantage.measured.png")
# ...then build loft_sections stations whose top z = r["stations"][i]["top_z"]
```

Works for: car bodywork (with `car-bodies.md`), and any revolve/loft
whose profile is defined by a straight-on view (bottles, chairs,
fuselages, appliance shells). Run it on a FRONT view too — same tool,
that view's own two axes — to get width and taper a side view can't show.

## image_heightfield(path, width, relief, base=0.6, invert=False, max_cells=240) -> Solid

Brightness -> height on top of a solid base slab (z=0..base, relief on
top). y size follows the aspect ratio. For a lithophane use
`invert=True` (dark = thick) with relief ~2.4, base ~0.8, and hold it
against light. For terrain from a heightmap, keep invert=False.
`max_cells` caps resolution (240 -> ~115k top triangles; lower it
while iterating, raise for the final build).

```python
litho = image_heightfield("portrait.jpg", width=90, relief=2.4,
                          base=0.8, invert=True)
emit(litho, name="lithophane", color="light")
```

## Honesty rules for image work

- Report which dimensions were estimated from the image and which were
  given, with the anchor used. Never present a guessed size as fact.
- The traced outline is exact FOR THE IMAGE; if the image was skewed,
  low-res or noisy, say so and show the comparison sheet.
- If the request needs the true 3D shape of a photographed object
  (not a silhouette or relief), model it parametrically and use the
  photo only to check proportions on the comparison sheet.
