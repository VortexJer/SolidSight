"""
Blind one-shot 3D model of an inline-4 engine block.
Built purely from numpy + trimesh primitives and booleans.

Coordinate system (mm):
  X = crank axis, 0 at front face, 420 at rear face
  Y = lateral, 0 on crank centerline (+Y = intake side, -Y = exhaust/filter side)
  Z = up, 0 at crank centerline, deck face at +220, pan rail at -60

Design basis: ~2.0 L four, bore 86 mm, bore spacing 93 mm, deck height 220 mm.
"""

import numpy as np
import trimesh


# ---------------------------------------------------------------- helpers
def box(x0, x1, y0, y1, z0, z1):
    ext = [x1 - x0, y1 - y0, z1 - z0]
    T = np.eye(4)
    T[:3, 3] = [(x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0]
    return trimesh.creation.box(extents=ext, transform=T)


def cyl(p1, p2, r, sec=64):
    """Cylinder from point p1 to p2, radius r."""
    return trimesh.creation.cylinder(
        radius=r, segment=[list(p1), list(p2)], sections=sec)


def cylz(x, y, z0, z1, r, sec=64):
    return cyl([x, y, z0], [x, y, z1], r, sec)


# ---------------------------------------------------------------- layout
L = 420.0                      # block length
DECK = 220.0                   # deck face height above crank CL
RAIL = -60.0                   # oil pan rail
BORE_R = 43.0                  # 86 mm bore
LINER_R = 49.0                 # 6 mm liner wall, siamesed (spacing 93 < 98)
XC = [70.5, 163.5, 256.5, 349.5]          # cylinder centers, 93 mm spacing
XB = [12.0, 117.0, 210.0, 303.0, 408.0]   # main bearing bulkhead centers
BULK = [(0.0, 24.0), (106.0, 128.0), (199.0, 221.0),
        (292.0, 314.0), (396.0, 420.0)]   # bulkhead material x-ranges
BAYS = [(24.0, 106.0), (128.0, 199.0), (221.0, 292.0), (314.0, 396.0)]
XH = [25.0, 117.0, 210.0, 303.0, 395.0]   # head bolt columns (2 rows, y=+-52)

# ---------------------------------------------------------------- positives
upper = box(0, L, -75, 75, 60, DECK)              # cylinder bank
crankcase = box(0, L, -110, 110, RAIL, 80)        # wider crankcase / skirt
rearplate = box(412, L, -125, 125, RAIL, 170)     # bellhousing flange

base = trimesh.boolean.union([upper, crankcase, rearplate])

# closed-deck water jacket cavity (deck plate 10 mm thick above it)
jacket = box(12.5, 407.5, -59, 59, 110, 210)
base = trimesh.boolean.difference([base, jacket])

adds = []
for xc in XC:                                     # siamesed cylinder liners
    adds.append(cylz(xc, 0, 100, 215, LINER_R, sec=96))
for xh in XH:                                     # head-bolt columns in jacket
    for s in (1, -1):
        adds.append(cylz(xh, 52 * s, 100, 215, 12.0))
adds.append(box(130, 200, 105, 132, -25, 35))     # engine mount boss +Y
adds.append(box(130, 200, -132, -105, -25, 35))   # engine mount boss -Y
adds.append(cyl([303, -136, 30], [303, -104, 30], 38.0))   # oil filter pad
adds.append(cyl([187, 73, 95], [187, 86, 95], 14.0))       # knock sensor boss
adds.append(cyl([250, -82, 95], [250, -73, 95], 10.0))     # oil pressure boss
adds.append(cyl([-6, 42, 160], [1, 42, 160], 20.0))        # water inlet boss

block = trimesh.boolean.union([base] + adds)

# ---------------------------------------------------------------- negatives
negs = []

# cylinder bores (open into crankcase)
for xc in XC:
    negs.append(cylz(xc, 0, 70, 230, BORE_R, sec=96))

# crank tunnel (main bearing line bore, dia 59) + rear main seal counterbore
negs.append(cyl([-5, 0, 0], [425, 0, 0], 29.5, sec=96))
negs.append(cyl([412, 0, 0], [426, 0, 0], 44.0, sec=96))

# crankcase bays between bulkheads, open to the pan rail
for a, b in BAYS:
    negs.append(box(a, b, -95, 95, -66, 85))

# main bearing cap pockets (register faces at crank CL)
for a, b in BULK:
    negs.append(box(a - 1, b + 1, -40, 40, -66, 0))

# main cap bolt holes, thread up into the bulkheads (M10, 2 per main)
XMB = [12.0, 117.0, 210.0, 303.0, 405.0]
for xb in XMB:
    for s in (1, -1):
        negs.append(cylz(xb, 37 * s, -6, 45, 5.5, sec=32))

# head bolt holes, blind tapped 90 mm from deck (M12 class)
for xh in XH:
    for s in (1, -1):
        negs.append(cylz(xh, 52 * s, 130, 226, 5.4, sec=32))

# deck coolant transfer holes through the closed deck into the jacket
for xc in XC:
    for s in (1, -1):
        negs.append(cylz(xc, 54 * s, 198, 226, 4.5, sec=24))
for xm in (117.0, 210.0, 303.0):
    for s in (1, -1):
        negs.append(cylz(xm, 34 * s, 198, 226, 4.5, sec=24))

# main oil gallery (dia 16, full length, exhaust side) + drillings
negs.append(cyl([-5, -67, 95], [425, -67, 95], 8.0, sec=48))
for xb in XB:                                    # diagonal feeds to each main
    negs.append(cyl([xb, -67, 95], [xb, -8, 4], 4.0, sec=24))
negs.append(cylz(410, -68, 90, 226, 4.0, sec=24))          # oil riser to head
negs.append(cylz(90, 66, 68, 226, 6.0, sec=24))            # head oil drain 1
negs.append(cylz(330, 66, 68, 226, 6.0, sec=24))           # head oil drain 2

# oil filter: thread bore + drilling up to the main gallery
negs.append(cyl([303, -142, 30], [303, -100, 30], 9.0, sec=32))
negs.append(cyl([303, -102, 30], [303, -67, 95], 5.0, sec=24))

# coolant ports: front inlet into jacket, rear heater return
negs.append(cyl([-12, 42, 160], [24, 42, 160], 13.0, sec=32))
negs.append(cyl([385, 45, 160], [426, 45, 160], 8.0, sec=24))

# core (freeze) plug holes, dia 34, both sides into the jacket
for xp in (163.5, 256.5):
    negs.append(cyl([xp, 52, 160], [xp, 82, 160], 17.0, sec=48))
    negs.append(cyl([xp, -82, 160], [xp, -52, 160], 17.0, sec=48))

# bellhousing flange: 8 bolt holes + 2 dowels
for y, z in [(118, 80), (-118, 80), (118, -40), (-118, -40),
             (80, 150), (-80, 150), (60, -50), (-60, -50)]:
    negs.append(cyl([404, y, z], [426, y, z], 5.5, sec=24))
for s in (1, -1):
    negs.append(cyl([404, 118 * s, 20], [426, 118 * s, 20], 6.5, sec=24))

# engine mount bolt holes (M10, blind, 2 per boss)
for xm in (145.0, 185.0):
    negs.append(cyl([xm, 112, 5], [xm, 136, 5], 5.5, sec=24))
    negs.append(cyl([xm, -136, 5], [xm, -112, 5], 5.5, sec=24))

# knock sensor tap (blind) and oil pressure sender tap (into gallery)
negs.append(cyl([187, 64, 95], [187, 92, 95], 4.0, sec=24))
negs.append(cyl([250, -88, 95], [250, -60, 95], 5.0, sec=24))

# oil pan rail bolt holes (M8, blind, 7 per side)
for xp in (20, 85, 150, 215, 280, 345, 400):
    for s in (1, -1):
        negs.append(cylz(xp, 102 * s, -66, -42, 4.2, sec=24))

# front (timing) cover bolt holes, blind into front face
for y, z in [(68, 195), (-68, 195), (68, 100), (-68, 100),
             (95, -10), (-95, -10), (60, -55), (-60, -55)]:
    negs.append(cyl([-6, y, z], [15, y, z], 3.5, sec=24))

# head locating ring-dowel counterbores on the deck
negs.append(cylz(14, 30, 214, 226, 8.0, sec=32))
negs.append(cylz(406, -30, 214, 226, 8.0, sec=32))

block = trimesh.boolean.difference([block] + negs)

# ---------------------------------------------------------------- export
block.process(validate=True)
out = r"C:\Users\Joaquin ERE\.claude\jobs\5c31aa11\tmp\blind\engine_blind.stl"
block.export(out)

print("exported:", out)
print("is_watertight:", block.is_watertight)
print("volume (mm^3): %.1f" % block.volume)
print("bounds (mm):", np.round(block.bounds, 1).tolist())
print("faces:", len(block.faces), " vertices:", len(block.vertices))
