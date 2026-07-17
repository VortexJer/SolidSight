"""Vigia's geometry as a function of its servo angles.

build(head, arm_l, arm_r) emits the robot posed at those joint angles
(degrees) — head_pan about +Z, the arms pitching about +Y at their
shaft axes, exactly the joints the URDF declares. model.py calls it at
the neutral pose; the gesture renderer sweeps it.
"""

from solidsight import (Solid, box, cylinder, emit, expect, joint, parts,  # noqa: F401,E501
                        place, rect, sphere, torus)

from params import (ARM_L, ARM_T, ARM_W, BOARD_H, BOARD_T, BOARD_W,  # noqa: E501
                    CASE_X, CASE_Y, CASE_Z, DOME_D, FLOOR, MOUNTS,
                    NECK_D, NECK_H, SHAFT_D, STANDOFF_H, USB_Y, WALL,
                    board_to_case)

SHAFT_Z = 26.0
ARM_LX = 18.0
ARM_LY = CASE_Y / 2 + 6


def _body() -> Solid:
    profile = rect(CASE_X, CASE_Y).round_corners(8)
    body = parts.container(profile, CASE_Z, wall=WALL, floor=FLOOR)
    for bx, by in MOUNTS:
        cx, cy = board_to_case(bx, by)
        body = body + parts.standoff(h=STANDOFF_H, od=6.0, id_=2.4) \
            .translate(cx, cy, FLOOR - 0.5)
    usb = box(WALL + 2, 13, 7)
    body = body - usb.translate(-CASE_X / 2 + WALL / 2, 0.0,
                                FLOOR + STANDOFF_H + BOARD_T + 3.5)
    shaft_hole = cylinder(h=WALL + 2, d=SHAFT_D + 0.5).aim("+y")
    body = body - shaft_hole.translate(ARM_LX, CASE_Y / 2 + 1, SHAFT_Z) \
        - shaft_hole.rotate(z=180).translate(ARM_LX, -CASE_Y / 2 - 1,
                                             SHAFT_Z)
    body = body - parts.hex_grid(40, 26, FLOOR + 2, cell=6, wall=1.8) \
        .translate(0, 0, -1)
    roof = profile.extrude(2.4) - cylinder(h=4.4, d=NECK_D + 0.6) \
        .translate(0, 0, -1)
    body = body + roof.translate(0, 0, CASE_Z - 2.2)
    body = body + (cylinder(h=4.5, d=NECK_D + 8)
                   - cylinder(h=6.5, d=NECK_D + 0.6).translate(0, 0, -1)) \
        .translate(0, 0, CASE_Z - 0.3)
    return body


def _head(pan_deg: float) -> Solid:
    dome = sphere(d=DOME_D) & box(DOME_D + 2, DOME_D + 2, DOME_D / 2 + 1) \
        .translate(0, 0, DOME_D / 4)
    dome = dome.translate(0, 0, NECK_H - DOME_D / 4 + 2)
    neck = cylinder(h=NECK_H + 4, d=NECK_D)
    head = neck + dome
    eye = (torus(r_ring=8, r_tube=1.25) + cylinder(h=3, d=6)).rotate(y=-90) \
        .translate(-DOME_D / 2 + 3.5, 0, NECK_H + DOME_D / 5)
    head = (head - eye).translate(0, 0, CASE_Z + 3.0)
    # head_pan about +Z through (0, 0): the head is centred there
    return head.rotate(z=pan_deg)


def _arm(side: int, pitch_deg: float) -> Solid:
    paddle = rect(ARM_L, ARM_W).round_corners(6).extrude(ARM_T)
    hub = cylinder(h=10, d=12)
    shaft = cylinder(h=8, d=SHAFT_D)
    a = paddle.translate(ARM_L / 2 - 8, 0, 0) + hub \
        + shaft.translate(0, 0, -7.5)
    a = a.rotate(x=90)
    if side > 0:                      # the +Y arm mirrors so its shaft
        a = a.rotate(z=180)           # points INTO the case wall
    # pitch about +Y at the shaft axis (ARM_LX, ., SHAFT_Z)
    a = a.rotate(y=pitch_deg)
    return a.translate(ARM_LX, side * ARM_LY, SHAFT_Z)


def build(head: float = 0.0, arm_l: float = 0.0, arm_r: float = 0.0,
          joints: bool = True) -> None:
    emit(_body(), name="body", color="steel",
         features=[{"type": "standoff_pattern", "source": "vigia_board",
                    "at": [list(board_to_case(*m)) for m in MOUNTS]},
                   {"type": "usb_window", "aligned_to": "J1"}])
    emit(_head(head), name="head", color="light",
         features=[{"type": "eye", "d": 16}])
    emit(_arm(+1, arm_l), name="arm_l", color="clay")
    emit(_arm(-1, arm_r), name="arm_r", color="clay")

    pcb = box(BOARD_W, BOARD_H, BOARD_T) \
        + box(8, 36, 10).translate(BOARD_W / 2 - 6, 0, BOARD_T - 0.2) \
        + box(10, 10, 4).translate(0, 0, BOARD_T - 0.2)
    place(pcb, name="pcb", at=(0, 0, FLOOR + STANDOFF_H - 0.5), ghost=True)
    servo = parts.micro_servo()
    place(servo, name="servo_l", at=(-20, 12, 9.0), ghost=True)
    place(servo, name="servo_r", at=(-20, -12, 9.0), ghost=True)

    if not joints:
        return
    expect("pcb", "body", status="touching")
    expect("head", "body", status="clear", clearance=(0.2, 1.0))
    expect("arm_l", "body", status="clear", clearance=(0.1, 2.0))
    expect("arm_r", "body", status="clear", clearance=(0.1, 2.0))
    expect("servo_l", "pcb", status="clear", clearance=(0.2, 30.0))
    expect("servo_r", "pcb", status="clear", clearance=(0.2, 30.0))
    joint("body", "head", type="revolute", name="head_pan",
          origin=(0, 0, CASE_Z + 4), axis=(0, 0, 1), limits=(-120, 120))
    joint("body", "arm_l", type="revolute", name="arm_l_pitch",
          origin=(ARM_LX, ARM_LY, SHAFT_Z), axis=(0, 1, 0),
          limits=(-40, 100))
    joint("body", "arm_r", type="revolute", name="arm_r_pitch",
          origin=(ARM_LX, -ARM_LY, SHAFT_Z), axis=(0, 1, 0),
          limits=(-40, 100))
    joint("body", "pcb", type="fixed")
    joint("body", "servo_l", type="fixed")
    joint("body", "servo_r", type="fixed")
