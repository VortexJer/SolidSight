# Example 08 — FROM AN IMAGE: coaster with the user's emblem engraved.
# Workflow (references/from-image.md): the agent LOOKED at emblem.png
# (a gear emblem with a hex hole and four windows, ink on paper),
# estimated the coaster at 90 mm [standard coaster], and traced the
# artwork with image_outline() instead of re-drawing it by eye.
#
# Build with the comparison sheet, then LOOK at it:
#   solidsight build model.py --print-safe --ref emblem.png
from solidsight import *

COASTER_D = 90.0     # [standard] coaster diameter
COASTER_T = 4.0
EMBLEM_W = 70.0      # artwork width on the coaster
ENGRAVE = 1.2        # engraving depth

base = cylinder(h=COASTER_T, d=COASTER_D).chamfer_rim(0.8)

emblem = image_outline("emblem.png", width=EMBLEM_W)
cutter = emblem.extrude(ENGRAVE + 1).translate(0, 0, COASTER_T - ENGRAVE)
coaster = base - cutter

emit(coaster, name="coaster", color="clay",
     features=[{"type": "engraving", "source": "emblem.png",
                "depth_mm": ENGRAVE, "width_mm": EMBLEM_W}])
