# Example 05 (broken variant) — assembly with an INTENTIONAL collision.
# The box and lid come from example 02 via from_model(); a card is placed
# inside — but it is too tall and pokes through the lid plate.
# Build: solidsight build model_collision.py --out out_collision --exploded
# Expected: report.json pairs[] pins the collision to the exact bbox/volume
# and suggests the move; the fixed version lives in model.py.
from solidsight import *

OZ, LID_T = 24, 2.5          # body height / lid plate (from example 02)

body = from_model("../02-snap-box/model.py", "box")
cover = (from_model("../02-snap-box/model.py", "lid")
         .translate(-62, 0, 0)          # undo the print layout offset
         .rotate(x=180)                 # flip lip-down
         .translate(0, 0, OZ + LID_T))  # rest the plate on the box rim

card = box(40, 1.6, 24).translate(0, 5, 2.5)   # TOO TALL: top at z=26.5

place(body, name="box", color="steel")
place(cover, name="lid", color="amber")
place(card, name="card", color="sage")
