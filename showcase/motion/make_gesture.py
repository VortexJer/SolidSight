"""Vigia's greeting gesture — its SERVOS, twice.

The clip's skeleton IS the robot's URDF tree: Body (fixed), Head
panning about Z, ArmL/ArmR pitching about Y — the same three revolute
joints solidsight exports and sweeps. The gesture: look left, look
right, wave the left arm twice, settle.

  gesture_stepped.bvh  what naive servo code does: write the target
                       angle and wait. Every keyframe is an instant
                       step - the servo slams, the whole robot buzzes.
  gesture_eased.bvh    the same keyframes through smoothstep easing,
                       the way a motion profile should drive a servo.

animationsight cannot know what an SG90 can do — but it measures what
the clip ASKS: peak angular velocity per joint and the discontinuity
events. An SG90 tops out near 600 deg/s; the stepped clip demands over
5000. The numbers are the review.

Run: python make_gesture.py
"""

from __future__ import annotations

import math
from pathlib import Path

FPS = 30.0

# Vigia's joint tree, offsets in cm (BVH convention; the robot is
# 7.8 x 6.2 x 4.2 cm). Head sits on the case top; arms at the shafts.
HIER = """HIERARCHY
ROOT Body
{
  OFFSET 0 0 0
  CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
  JOINT Head
  {
    OFFSET 0 4.6 0
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 0 2.9 0
    }
  }
  JOINT ArmL
  {
    OFFSET 1.8 2.6 3.7
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 2.6 0 0
    }
  }
  JOINT ArmR
  {
    OFFSET 1.8 2.6 -3.7
    CHANNELS 3 Zrotation Xrotation Yrotation
    End Site
    {
      OFFSET 2.6 0 0
    }
  }
}
"""

# the gesture as servo keyframes: (t_seconds, head_pan, arm_l, arm_r)
KEYS = [
    (0.0, 0, 0, 0),
    (0.6, 0, 0, 0),
    (1.1, 60, 0, 0),          # look left
    (1.7, 60, 0, 0),
    (2.3, -60, 0, 0),         # look right
    (2.9, -60, 0, 0),
    (3.4, 0, 0, 0),           # face front
    (3.9, 0, 95, 0),          # arm up
    (4.3, 0, 55, 0),          # wave down
    (4.7, 0, 95, 0),          # wave up
    (5.1, 0, 55, 0),
    (5.5, 0, 95, 0),
    (6.1, 0, 0, 0),           # settle
    (6.6, 0, 0, 0),
]
DURATION = KEYS[-1][0]


def smoothstep(s: float) -> float:
    return s * s * (3.0 - 2.0 * s)


def angles_at(t: float, eased: bool) -> tuple[float, float, float]:
    for (t0, *a0), (t1, *a1) in zip(KEYS, KEYS[1:]):
        if t0 <= t <= t1:
            if not eased:
                # naive servo code: write the target, wait -> a step
                return tuple(a1)
            s = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            e = smoothstep(s)
            return tuple(v0 + (v1 - v0) * e for v0, v1 in zip(a0, a1))
    return tuple(KEYS[-1][1:])


def build(eased: bool) -> str:
    n = int(round(DURATION * FPS)) + 1
    rows = []
    for f in range(n):
        head, al, ar = angles_at(f / FPS, eased)
        rows.append(" ".join(f"{v:.4f}" for v in
                             [0, 4.2, 0, 0, 0, 0,      # Body root
                              head, 0, 0,              # Head (Z pan)
                              0, 0, al,                # ArmL (Y pitch)
                              0, 0, ar]))              # ArmR
    return "\n".join([HIER, "MOTION", f"Frames: {n}",
                      f"Frame Time: {1.0 / FPS:.6f}"] + rows) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "gesture_stepped.bvh").write_text(build(False), encoding="utf-8")
    (here / "gesture_eased.bvh").write_text(build(True), encoding="utf-8")
    print(f"gesture: {DURATION}s, {len(KEYS)} servo keyframes, "
          f"joints = the URDF's (head_pan, arm_l_pitch, arm_r_pitch)")
