# Detail mode — modeling real technical objects faithfully

You are here because detailed mode was chosen (the opt-in gate is in
SKILL.md Step 1). **It means: every feature a domain expert would name
must exist in the geometry** — not textures, not branding, functional
geometry.

## Research before the spec (when the user gives no specifications)

If detailed mode is chosen and the user provided no drawings, dimensions or
feature list, DO NOT fill the gap with guesses — research the object first
with your web tools (WebSearch / WebFetch), then write the spec from what
you found:

0. **Commit to ONE exact variant before searching — always, even with no
   human to ask.** "A B58" is not researchable; "the B58B30M0 block, G20
   M340i / A90 Supra, closed-deck aluminium" is. If nobody is in the loop
   to choose, pick the most representative production variant yourself,
   say which one, and research that. Averaging the family is what makes a
   part come out as a vague box — the whole accuracy comes from studying
   ONE real thing.
1. Search for the object's anatomy, not just pictures:
   `"<object> cross section"`, `"<object> engineering drawing"`,
   `"<object> dimensions site:manufacturer"`, `"<object> teardown"`,
   `"how a <object> works"`. 3-6 focused searches, feature INVENTORY first
   (what does a real one have), exact dimensions second — proportions and
   completeness matter more than the third decimal.
2. Extract: overall dimensions, every functional feature a domain expert
   would name, counts and patterns (how many head bolts? what fastener
   sizes?), standard values (ISO/DIN/JIS parts, typical wall thicknesses).
3. **When written specs barely exist — fetch PHOTOS.** For styled
   objects (a specific car, bodywork, consumer products, furniture)
   the drawings are proprietary and searching longer will not produce
   them: the visual record IS the spec. Find 3-6 photos from distinct
   angles (side/front/rear/3-quarter; press kits, brochures, Wikipedia
   are good sources), download them (`curl -o ref_side.jpg <url>`),
   LOOK at each one, then switch to the `from-image.md` workflow:
   anchor scale on the few numbers that ARE published (wheelbase,
   overall length/width/height), derive proportions and features from
   the photos, and build with `--ref ref_side.jpg` so every rebuild
   writes the reference-vs-render sheet and you compare against the
   real thing, not your memory of it. The same fallback applies to a
   mechanical part when no drawing or dimension sheet turns up: photos
   of the real part (teardowns, listings, catalog pages) beat
   guessing.
4. Tag every line of the Feature Specification with its provenance:
   `[researched]`, `[standard]` (known norm), `[photo]` (derived from a
   fetched photo), or `[assumed]`. Never present an assumption as
   research.
5. Tell the user in one line what you researched and what you assumed, and
   ask ONLY if a truly blocking unknown remains (e.g. which specific engine
   family). Otherwise proceed.
6. No web access available? Proceed from domain knowledge, mark everything
   `[assumed]`, and say so explicitly.

## First: what does this part HOUSE, MATE, and RESIST?

A part's outer form is not free — it is derived from its job. A part
modelled in isolation, with no thought to what it works with, comes out as
an abstract prism with holes. The SAME part imagined in its assembly comes
out as a real casting — because every feature exists to serve a neighbour
or a load. So before listing features, write the functional context as
comments, even when you are only building this one part. You do NOT model
the neighbours — you reason about them:

- **HOUSES** — what moves or sits inside, and the space it demands. A
  crankcase houses a crank of stroke S, so its skirt must clear the swing
  radius (S/2 + rod big-end) and drop BELOW the crank axis — that clearance
  is *why* the deep skirt exists. Bearings, gears, pistons all carve out the
  interior form.
- **MATES** — what bolts or seals to each face, and the pattern that
  implies. The deck mates a head → head-bolt matrix + coolant transfer
  holes; the rail mates a pan → bolt ring + gasket land; the ends mate
  timing cover / bell-housing → their flanges and dowels.
- **RESISTS** — the loads it carries, and the ribs/bosses/webs that answer
  them. Combustion + main-bearing loads → bulkheads, side-rib lattice,
  reinforcement frames, mount bosses. On many real castings this webbing is
  the single most recognizable feature; skip it and the part reads as a box.

Then let the geometry FOLLOW: every feature you add should trace back to a
line above. This one reframing — "the crankcase that holds THIS engine",
not "a block" — is the difference between a prism with holes and a casting.

## The method: Feature Specification before code

A detailed object is too much to hold in your head while coding. Write the
specification FIRST, as comments at the top of the model file, organized by
functional region (usually one region per face/direction of the part).
For an inline-4 engine block the spec looks like this (this is the level):

```
REGION 1 — main volume & crankcase
  deep-skirt prism, side walls extend below crank axis (inverted U)
  pan rail: flange out along +/-Y at the bottom, N bolt holes each side
  gussets: triangular ribs tying skirt walls to the pan rail, equally spaced
REGION 2 — deck (top face, -Z operations)
  4 cylinder bores, axis Z, bore D, pitch P
  liner step: coaxial shallow counterbore at each bore mouth
  head-bolt matrix: 10 tapped blind holes around the bores
  water jacket: irregular through/deep pockets between bores and bolts
  2 locating dowels near opposite corners
REGION 3 — front face (timing, -X)
  main bearing saddle: half-cylinder on the bottom center, axis X
  cam tunnel: deep bore, axis X, offset -Y and +Z from the crank
  coolant ports: asymmetric pockets connecting to the water jacket
  oil galleries: small blind drillings, axis X, threaded at the mouth
REGION 4 — accessory side (+Y)
  oil filter pad: rectangular boss, machined face, 2 fluid ports
    intersecting the main gallery, ring of tapped holes
  engine mounts: massive cylindrical bosses truncated by inclined planes,
    tapped hole normal to each inclined face
```

Rules for the spec:
1. One line per feature: name, type, axis, position (relative to named
   datums), count/spacing, key dimensions.
2. Name your datums as constants and derive EVERYTHING from them
   (`DECK_Z`, `CRANK_Z`, `BORE_PITCH`, `PAN_RAIL_Y`...). Detailed models
   die by scattered magic numbers.
3. State assumed real-world dimensions in the header. You know typical
   values (bore pitch ~1.2x bore, deck height, M-series fasteners); if the
   user wants a SPECIFIC machine, ask for its datasheet or say you are
   assuming.

## The build loop in detail mode

Implement ONE region at a time, and after each region:
`solidsight build --slice <through that region>` + look. Verify the feature
COUNT and positions in the top/front/side views before moving on. A detailed
model is 5-8 small verified passes, never one giant unverified dump.

Definition of done (in addition to the standard checklist): walk the spec
line by line against the renders/slices — every feature present, every
count right, report dimensions match the datum constants.

**Know when to stop — do not over-change.** Once the spec is met and the
part reads right, stop. A SMALL imperfection is not worth another build:
a sub-mm misalignment, a rib a hair off, a slightly uneven gap — ignore
it and move on. Only a REAL defect earns another pass: a missing feature
(a boolean that did nothing), a collision, a thin wall, a wrong count.
More edits is not more quality — chasing tiny cosmetics burns effort and
often makes a good part worse.

## Feature -> solidsight toolbox

| real-world feature | how |
|---|---|
| deep skirt / crankcase | outer box minus inner box; skirt = cavity extends below the crank-axis datum |
| flange / pan rail | thin wider box unioned at the base (sink 0.5) |
| gusset / rib | `wedge()` in a `linear_pattern` |
| bore / cylinder barrel | `cylinder` cutter from the deck |
| liner step / spigot counterbore | `parts.hole(bore_d, depth, counterbore=(step_d, step_depth))` or a shallow coaxial cylinder |
| tapped blind hole (cosmetic) | `parts.hole(d, depth, chamfer=0.3, drill_point=True)` — model the tap drill, not the thread, unless the user needs working threads (`parts.iso_thread(internal=True)`) |
| counterbored / countersunk screw hole | `parts.hole(..., counterbore=(D, h))` / `countersink=D` |
| bolt matrix | `parts.grid_pattern` / `linear_pattern` of a `parts.hole` |
| bolt circle around a boss | `parts.bolt_circle(parts.hole(...), n, d_circle)` |
| drilling into any face | build the hole (drills -Z), then `.aim("-y")` etc. + translate to the entry point |
| tunnel (cam, dowel, shaft) | `cylinder().aim("+x")` through the body |
| half-round saddle | cut a cylinder whose axis lies ON the parting plane |
| water jacket / irregular pocket | `polygon()`/`stroke()` outline, `.offset()` for wall clearance, extrude as cutter |
| oil gallery | small `parts.hole` along the axis, `chamfer` at the mouth |
| machined pad / boss with ports | box or cylinder boss (sink 0.5) + holes aimed into it |
| boss truncated by inclined plane | boss `&` (intersect) a large rotated box |
| slot / obround | `stroke([(0,0),(L,0)], width)` extruded |
| locating dowel | small solid `cylinder` boss, or `parts.hole` for its socket |

Everything above is plain composition — no special mode in the engine.
Worked proof: `examples/07-engine-block` (a detailed inline-4 block built
region by region with this method; read its model.py side by side with the
spec in its header).
