# Example 03 — gear train (difficulty: parametric parts catalog)
# Two meshing involute spur gears from the catalog. The pair analysis in
# report.json proves the mesh: teeth interleave with a small positive
# clearance (the backlash), instead of colliding.
# Build: solidsight build model.py --print-safe --stl
from solidsight import *

MODULE = 2.0
T_GEAR, T_PINION = 20, 12
THICK = 8

# meshing center distance for spur gears = module * (za + zb) / 2
CENTER_DIST = MODULE * (T_GEAR + T_PINION) / 2   # = 32

gear = parts.spur_gear(module=MODULE, teeth=T_GEAR, thickness=THICK,
                       bore=5, backlash=0.2)
# lighten the big gear with a bolt circle of holes
lighten = cylinder(h=THICK + 2, d=8).translate(11, 0, -1)
gear = gear - parts.circular_pattern(lighten, 5)

pinion = parts.spur_gear(module=MODULE, teeth=T_PINION, thickness=THICK,
                         bore=5, backlash=0.2)
# rotate the pinion half a tooth so teeth interleave with the gear's
pinion = pinion.rotate(z=180.0 / T_PINION)

emit(gear, name="gear", color="steel")
emit(pinion.translate(CENTER_DIST, 0, 0), name="pinion", color="amber")
