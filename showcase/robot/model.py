# Vigia — a desk robot, the AISight showcase.
#
# bill of parts (mm):
#   body      78 x 62 x 42 shell, wall 2.4: standoffs AT THE BOARD'S OWN
#             mount positions (read from vigia_board.kicad_pcb through
#             pcbsight), USB window aligned to the board's J1, side
#             shaft holes for the arms, vented floor
#   head      52 dome on a 22 neck, engraved eye ring (head_pan servo)
#   arm_l/r   34 x 14 paddles on 5 mm servo shafts (pitch servos)
#   ghosts    the PCB (real outline + component envelope) and two micro
#             servos: measured in pairs[], never printed
#
# The geometry lives in vigia.py as build(head, arm_l, arm_r) so the
# same robot can be posed - the gesture renderer sweeps its servos.
from vigia import build

build()   # neutral pose, with the joint()/expect() declarations
