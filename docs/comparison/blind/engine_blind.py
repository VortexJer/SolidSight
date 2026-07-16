# BASELINE for the before/after comparison in the README.
#
# The condition: an agent asked "make me a 3D model of an inline-4 engine
# block", WITHOUT solidsight — no renders, no validation report, no parts
# catalog, no workflow. Just plain Python + trimesh (the standard mesh
# library such an agent would reach for), written in ONE blind pass and
# shipped without ever seeing the result. Nothing here was verified or
# fixed after the fact; crashes were retried (an agent sees stderr) but
# invisible geometric defects stay, because that is exactly the point.
import numpy as np
import trimesh
from trimesh.creation import box, cylinder


def tb(extents, at=(0, 0, 0)):
    m = box(extents=extents)
    m.apply_translation(at)
    return m


def tc(radius, height, at=(0, 0, 0), along="z"):
    m = cylinder(radius=radius, height=height, sections=48)
    if along == "x":
        m.apply_transform(trimesh.transformations.rotation_matrix(
            np.pi / 2, [0, 1, 0]))
    return m.apply_translation(at) or m


# main block body, deck at top
block = tb([220, 90, 130], (0, 0, 65))

# crankcase cavity, open at the bottom
block = trimesh.boolean.difference(
    [block, tb([204, 74, 60], (0, 0, 25))])

# pan rail flange
block = trimesh.boolean.union(
    [block, tb([220, 114, 7], (0, 0, 3.5))])

# four cylinder bores from the deck
for i in range(4):
    x = -72 + i * 48
    bore = tc(20, 110, (x, 0, 130 - 55))
    block = trimesh.boolean.difference([block, bore])

# head bolt holes around the bores
for x in (-96, -48, 0, 48, 96):
    for y in (-30, 30):
        hole = tc(3.4, 25, (x, y, 130 - 12.5))
        block = trimesh.boolean.difference([block, hole])

# water jacket ring around each bore
for i in range(4):
    x = -72 + i * 48
    outer = tc(27, 45, (x, 0, 130 - 22.5))
    inner = tc(23, 50, (x, 0, 130 - 22.5))
    ring = trimesh.boolean.difference([outer, inner])
    block = trimesh.boolean.difference([block, ring])

# camshaft tunnel along the block
cam = tc(12, 224, (0, -24, 100), along="x")
block = trimesh.boolean.difference([block, cam])

# main bearing saddle
saddle = tc(22, 224, (0, 0, 30), along="x")
block = trimesh.boolean.difference([block, saddle])

# oil galleries
for y in (-34, 34):
    gal = tc(4, 205, (0, y, 118), along="x")
    block = trimesh.boolean.difference([block, gal])

# pan rail bolt holes
for i in range(6):
    x = -100 + i * 40
    for y in (-50, 50):
        hole = tc(3.5, 12, (x, y, 3.5))
        block = trimesh.boolean.difference([block, hole])

# oil filter boss on the side with two ports
boss = tb([46, 12, 38], (-30, 50, 78))
block = trimesh.boolean.union([block, boss])
for x in (-42, -18):
    port = tc(7, 24, (x, 50, 78), along="x")   # ports into the boss
    block = trimesh.boolean.difference([block, port])

# engine mounts
for x in (-70, 70):
    mount = tc(16, 16, (x, 52, 24), along="x")
    block = trimesh.boolean.union([block, mount])

block.export("engine_blind.stl")
print("exported", block.is_watertight, len(block.faces))
