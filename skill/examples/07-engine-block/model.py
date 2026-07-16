# Example 07 — DETAIL MODE: inline-4 engine block (representative scale)
# Built with the Feature Specification method (references/detail-mode.md).
#
# FEATURE SPEC (assumed dims: bore 40, pitch 48, M6-class fasteners)
# R1 main volume & crankcase
#   deep-skirt prism 220 x 88 x 130; crankcase cavity open to the pan
#   pan rail: flange to +/-112 wide x 7 tall, 6 bolt holes per side
#   gussets: 5 triangular ribs per side tying skirt to rail
#   main bearing saddle: half-cylinder d44, axis X at CRANK_Z
# R2 deck (top, -Z ops)
#   4 bores d40 pitch 48, open into the crankcase
#   liner step d45 x 4 deep at each bore mouth
#   head-bolt matrix: 10 tapped blind holes (tap drill 6.8) at y = +/-33
#   siamese water jacket: stadium annulus flanking the bank, 45 deep
#   2 locating dowels d6 near opposite corners
# R3 front face (-X)
#   cam tunnel d24 through, offset (y -24, z +70 from crank)
#   2 oil galleries d8, blind 205 deep, chamfered mouths, axis X
#   2 coolant ports (irregular pockets) breaking into the water jacket
# R4 accessory side (+Y)
#   oil filter pad 46 x 38 boss with 2 fluid ports d14 + 6-hole M5 ring
#   2 engine mounts: d32 bosses truncated by a 25 deg inclined plane,
#     tapped hole normal to the inclined face
from solidsight import *

# ---- datums (mm) ----------------------------------------------------------
BORE, PITCH, N = 40.0, 48.0, 4
BLOCK_X, BLOCK_Y = 220.0, 88.0
DECK_Z, CRANK_Z, RAIL_T = 130.0, 30.0, 7.0
WALL_Y = BLOCK_Y / 2                      # 44
BORE_XS = [PITCH * (i - (N - 1) / 2) for i in range(N)]   # -72,-24,24,72

# ---- R1: body, pan rail, gussets, crankcase, saddle -----------------------
body = box(BLOCK_X, BLOCK_Y, DECK_Z)
rail = box(BLOCK_X, 112, RAIL_T)
block = body + rail.translate(0, 0, 0)    # same base plane: fuses via body

pan_bolt = parts.hole(7, RAIL_T + 2)
for sx in range(-5, 6, 2):                # 6 holes per side
    for sy in (-50, 50):
        block = block - pan_bolt.translate(sx * 20, sy, RAIL_T + 0.5)

gusset = wedge(6, 11, 18)
for side in (-1, 1):
    g = gusset if side > 0 else gusset.rotate(z=180)
    row = parts.linear_pattern(g, 5, dx=44)
    block = block + row.translate(-88, side * (WALL_Y + 5.0), RAIL_T - 0.5)

crankcase = box(BLOCK_X - 16, BLOCK_Y - 16, 51).translate(0, 0, -1)
block = block - crankcase
saddle = cylinder(h=BLOCK_X + 2, d=44).aim("+x").translate(BLOCK_X / 2 + 1,
                                                           0, CRANK_Z)
block = block - saddle

# ---- R2: deck operations ---------------------------------------------------
for cx in BORE_XS:
    block = block - cylinder(h=DECK_Z, d=BORE).translate(cx, 0, 25)
    block = block - parts.hole(BORE, 6, counterbore=(45, 4)).translate(
        cx, 0, DECK_Z)                    # liner step (shallow spigot)

# depth 15: a 22 mm drilling (plus its 118-deg point) broke through into
# the cam tunnel on the y=-33 row — found with `query ray 0 -33 132 0 0 -1`
head_bolt = parts.hole(6.8, 15, chamfer=0.5, drill_point=True)
for hx in (-96, -48, 0, 48, 96):
    for hy in (-33, 33):
        block = block - head_bolt.translate(hx, hy, DECK_Z)

# water jacket: a stadium ANNULUS around the whole bank (siamese bores have
# no water between adjacent cylinders — the jacket flanks the bank)
bank = [(BORE_XS[0], 0), (BORE_XS[-1], 0)]
jacket = stroke(bank, BORE + 15.5) - stroke(bank, BORE + 9.5)
block = block - jacket.extrude(46).translate(0, 0, DECK_Z - 45)

for dx, dy in ((-104, 36), (104, -36)):   # locating dowels
    block = block + cylinder(h=5, d=6).translate(dx, dy, DECK_Z - 0.5)

# ---- R3: front face (timing) ----------------------------------------------
cam = cylinder(h=BLOCK_X + 2, d=24).aim("+x").translate(
    BLOCK_X / 2 + 1, -24, CRANK_Z + 70)
block = block - cam

gallery = parts.hole(8, 205, chamfer=0.6).aim("+x")
block = block - gallery.translate(-BLOCK_X / 2, 34, 118) \
              - gallery.translate(-BLOCK_X / 2, -34, 118)

# pockets: extrusions grow +Z, so make them downward tools before aiming
port = (polygon([(0, 0), (14, -3), (19, 6), (12, 14), (2, 12)])
        .extrude(14).translate(0, 0, -14).aim("+x"))
block = block - port.translate(-BLOCK_X / 2 - 1, 14, 96) \
              - port.translate(-BLOCK_X / 2 - 1, 30, 108)

# ---- R4: accessory side (+Y) ------------------------------------------------
pad = box(46, 12, 38).translate(-30, WALL_Y + 2.5, 78)   # sunk 3.5 into wall
block = block + pad
pad_face_y = WALL_Y + 8.5
fluid_port = parts.hole(14, 20).aim("-y")
block = block - fluid_port.translate(-42, pad_face_y, 78) \
              - fluid_port.translate(-18, pad_face_y, 78)
ring = parts.bolt_circle(parts.hole(5, 12, chamfer=0.4), 6, 36).aim("-y")
block = block - ring.translate(-30, pad_face_y, 78)

# engine mounts: boss truncated by an inclined plane + tapped hole normal
# to that plane (built at the origin pointing +Y, then placed)
mount = cylinder(h=17, d=32).aim("-y")               # extends 0..17 in +Y
cap = box(60, 40, 60, center=True).rotate(x=-25).translate(0, -4, 0)
mount = mount & cap
# tapped hole normal to the inclined face; generous through_margin so the
# entry cone always breaks OUT of the inclined surface (a buried entry
# creates a sealed cavity — the validator catches it)
mount = mount - parts.hole(5, 14, chamfer=0.4, through_margin=10).aim(
    "-y").rotate(x=-25).translate(0, 13, 4)
for mx in (-70, 70):
    block = block + mount.translate(mx, WALL_Y - 1, 24)

emit(block, name="block", color="gray")
