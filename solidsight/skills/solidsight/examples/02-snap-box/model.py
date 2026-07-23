# Example 02 — snap-fit box (difficulty: booleans + mechanism)
# Two printable parts: a rounded enclosure with snap windows, and a lid whose
# cantilever clips latch into them. Printed side by side (lid lip up).
# Build: solidsight build model.py --print-safe --stl --slice z=12
from solidsight import *

# -- shared parameters (mm) -------------------------------------------------
OX, OY, OZ = 50, 34, 24        # body outer size
WALL = 2.5
R = 3                          # corner radius
CLEAR = 0.25                   # printed snap clearance

CLIP_L, CLIP_W, CLIP_T = 10, 8, 1.8
HOOK, HOOK_L = 1.2, 3
LID_T, LIP_H = 2.5, 4

# When assembled, the lid plate rests on the body top (underside at z = OZ)
# and the clip hangs upside-down. The clip's retention edge sits at
# CLIP_L - 0.6 * HOOK_L above its base, so flipped:
ENGAGE_Z = OZ - CLIP_L + 0.6 * HOOK_L          # = 15.8
# upside-down clip: window must clear the insertion ramp too
WIN_H = HOOK_L * 0.6 + 2 * CLEAR

# -- body -------------------------------------------------------------------
body = rounded_box(OX, OY, OZ, R, vertical_only=True)
cavity = rounded_box(OX - 2 * WALL, OY - 2 * WALL, OZ, max(1, R - WALL),
                     vertical_only=True).translate(0, 0, WALL)
body = body - cavity

# snap windows through the +/-X walls; the hook grabs the window's TOP edge,
# so the window top must sit at ENGAGE_Z + CLEAR
window = parts.snap_slot(width=CLIP_W, t=CLIP_T, hook=HOOK, hook_len=HOOK_L,
                         wall=WALL, clearance=CLEAR, height=WIN_H)
window = window.rotate(z=90)                    # thickness along X
win_z = ENGAGE_Z + CLEAR - WIN_H
body = (body
        - window.translate(OX / 2 - WALL, 0, win_z)
        - window.mirror("x").translate(-OX / 2 + WALL, 0, win_z))

emit(body, name="box", color="steel")

# -- lid (printed lip-up next to the body) ----------------------------------
lid_plate = rounded_box(OX, OY, LID_T, R, vertical_only=True)
# lip is 0.5 taller and sunk 0.5 into the plate so the union truly fuses
lip = rounded_box(OX - 2 * WALL - 2 * CLEAR, OY - 2 * WALL - 2 * CLEAR,
                  LIP_H + 0.5, max(0.8, R - WALL), vertical_only=True)
lip = lip - rounded_box(OX - 2 * WALL - 2 * CLEAR - 4,
                        OY - 2 * WALL - 2 * CLEAR - 4,
                        LIP_H + 3, max(0.5, R - WALL - 2),
                        vertical_only=True).translate(0, 0, -1)
lid = lid_plate + lip.translate(0, 0, LID_T - 0.5)

# clips ride on the +/-X ends of the lip, hooks pointing outward (+/-X).
# snap_clip() is built hook +Y, so rotate it hook -> +X.
clip = parts.snap_clip(length=CLIP_L, width=CLIP_W, t=CLIP_T,
                       hook=HOOK, hook_len=HOOK_L).rotate(z=-90)
# arm outer face flush with the cavity wall (lip outer face), base on lid
clip_x = (OX - 2 * WALL) / 2 - CLEAR - CLIP_T
lid = (lid + clip.translate(clip_x, 0, LID_T)
           + clip.mirror("x").translate(-clip_x, 0, LID_T))

emit(lid.translate(OX + 12, 0, 0), name="lid", color="amber")
