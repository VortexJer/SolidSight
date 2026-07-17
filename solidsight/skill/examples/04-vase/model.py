# Example 04 — twisted vase (difficulty: organic form, --free mode)
# A hollow vase: rounded-hexagon profile, twisted and flared as it rises.
# Free mode reports the metrics (thin trailing edges, overhangs) without
# blocking the build — this is exploration, not production.
# Build: solidsight build model.py --free --turntable 6 --slice z=60
from solidsight import *

H = 110            # height
D_BASE = 58        # base size across corners
TWIST = 70         # total twist, degrees
FLARE = 1.35       # top/bottom scale ratio
WALL = 2.6
FLOOR = 4

profile = ngon(6, d=D_BASE).round_corners(9)

outer = profile.extrude(H, twist=TWIST, scale_top=FLARE, divisions=90)
inner = (profile.offset(-WALL)
         .extrude(H, twist=TWIST, scale_top=FLARE, divisions=90))
vase = outer - inner.translate(0, 0, FLOOR)

# soft foot: a shallow chamfer ring at the bottom
foot = cone(h=2.5, d1=D_BASE * 0.94, d2=D_BASE * 1.02)
vase = vase + (foot & cylinder(h=2.5, d=D_BASE * 1.02))

emit(vase, name="vase", color="sage")
