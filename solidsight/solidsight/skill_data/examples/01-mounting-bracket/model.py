# Example 01 — mounting bracket (difficulty: simple)
# One printable part: L-bracket with mounting holes, a stiffening rib and
# rounded corners. Built with: solidsight build model.py --print-safe --stl
from solidsight import *

# -- parameters (mm) --------------------------------------------------------
base_x, base_y, base_t = 60, 40, 5      # base plate footprint / thickness
wall_h, wall_t = 35, 5                  # upright wall
hole_d = 4.5                            # M4 clearance holes
corner_r = 4

# -- base plate with rounded corners and 4 holes ---------------------------
plate_profile = rect(base_x, base_y).round_corners(corner_r)
plate = plate_profile.extrude(base_t)

hole = cylinder(h=base_t + 2, d=hole_d).translate(0, 0, -1)
holes = parts.grid_pattern(hole, 2, 2, base_x - 16, base_y - 16)
holes = holes.translate(-(base_x - 16) / 2, -(base_y - 16) / 2, 0)
plate = plate - holes

# -- upright wall on the back edge, with two holes -------------------------
# (narrower than the plate so it does not overhang the rounded corners;
# sunk 1 mm into the plate so the union truly fuses instead of just touching)
wall = (box(base_x - 2 * corner_r, wall_t, wall_h + 1)
        .translate(0, (base_y - wall_t) / 2, base_t - 1))
wall_hole = (cylinder(h=wall_t + 2, d=hole_d)
             .rotate(x=-90)                       # drill along +Y
             .translate(0, base_y / 2 - wall_t - 1, base_t + wall_h - 12))
wall = wall - wall_hole.translate(-18, 0, 0) - wall_hole.translate(18, 0, 0)

# -- triangular rib tying wall to plate (also kills the wall overhang) -----
rib = wedge(wall_t, 24, 25).rotate(z=180)
rib = rib.translate(0, (base_y) / 2 - wall_t - 12 + wall_t / 2, base_t - 1)

bracket = plate + wall + rib
emit(bracket, name="bracket", color="steel")
