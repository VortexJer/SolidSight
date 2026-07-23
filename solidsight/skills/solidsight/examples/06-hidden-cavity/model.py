# Example 06 — the trap every renderer misses: a sealed internal cavity.
# A knob whose decorative dome cap was fused over an open recess. Every
# outside render looks perfectly solid; the recess is now a sealed air
# pocket that resin cannot drain from and FDM cannot roof.
#
# Build:  solidsight build model.py --print-safe     -> FAILS (internal-cavity)
# Verify without eyes:
#   solidsight query model.py ray 0 0 -1 0 0 1        -> 4 crossings, 2 segments
#   solidsight query model.py voxels --res 1          -> SEALED CAVITY + bbox
#   solidsight query model.py section z=8             -> the hole in ASCII
from solidsight import *

hub = cylinder(h=12, d=30)
recess = cylinder(h=20, d=20).translate(0, 0, 4)     # open pocket... for now
knob = hub - recess

grip = torus(r_ring=15.6, r_tube=2.4).translate(0, 0, 6)
knob = knob + (grip & cylinder(h=12, d=36))          # knurl-ish grip ring

dome = sphere(d=30) & cylinder(h=15, d=30)           # half dome
# sunk 0.5 mm into the hub so the union truly fuses (a union that only
# touches a face leaves a zero-thickness seam — solidsight warns about it)
knob = knob + dome.translate(0, 0, 11.5)             # ...and now it's sealed

emit(knob, name="knob", color="clay")
