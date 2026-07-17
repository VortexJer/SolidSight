"""Generate the jump example: the same jump twice.

  jump_floaty.bvh   the flight is an arbitrary parabola — apex +300 mm
                    over 0.67 s of air. Feels wrong, looks fine in any
                    still frame. (This is the clip that motivated the
                    ballistics metric: its author shipped it without
                    noticing.)
  jump_fixed.bvh    same crouch, same launch, same apex — but the
                    airtime satisfies T = 2*sqrt(2h/g), so the COM falls
                    at 1.0 g.

Run: python make_jump.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from make_clips import ANKLE_H, HIERARCHY, JOINTS, leg_ik  # noqa: E402

FPS = 30.0
G_CM = 981.0                     # gravity in cm/s^2 (the clip is in cm)
STAND, CROUCH = 78.0, 62.0
APEX_RISE = 30.0                 # cm above standing


def build(floaty: bool) -> str:
    # phase durations in seconds
    t_crouch, t_launch, t_land, t_recover = 0.5, 0.10, 0.10, 0.5
    if floaty:
        t_air = 0.667                       # arbitrary: looks "nice"
    else:
        t_air = 2.0 * math.sqrt(2.0 * APEX_RISE / G_CM)   # physics: 0.495 s

    T = t_crouch + t_launch + t_air + t_land + t_recover
    n = int(round(T * FPS))

    def hip_y(t: float) -> float:
        if t < t_crouch:
            return STAND - (STAND - CROUCH) * math.sin(
                math.pi * t / t_crouch / 2)
        t -= t_crouch
        if t < t_launch:
            return CROUCH + (STAND - CROUCH) * (t / t_launch)
        t -= t_launch
        if t < t_air:
            s = t / t_air
            return STAND + 4.0 * APEX_RISE * s * (1.0 - s)  # parabola
        t -= t_air
        if t < t_land:
            return STAND - (STAND - 68.0) * (t / t_land)
        t -= t_land
        return 68.0 + (STAND - 68.0) * math.sin(
            math.pi * min(t / t_recover, 1.0) / 2)

    def airborne(t: float) -> bool:
        return t_crouch + t_launch <= t < t_crouch + t_launch + t_air

    rows = []
    for f in range(n):
        t = f / FPS
        hy = hip_y(t)
        air = airborne(t)
        vals = {"Hips": [0.0, hy, 0.0, 0, 0, 0],
                "Spine": [0, 6 if t < t_crouch else 0, 0],
                "Chest": [0, 2, 0], "Neck": [0, 0, 0], "Head": [0, 0, 0]}
        arm = -40 if t < t_crouch else (60 if air else -10)
        for s_ in ("Left", "Right"):
            vals[f"{s_}UpperArm"] = [0, arm if s_ == "Left" else arm, 0]
            vals[f"{s_}Forearm"] = [0, -15, 0]
            vals[f"{s_}Hand"] = [0, 0, 0]
        for s_ in ("Left", "Right"):
            if air:
                vals[f"{s_}Thigh"] = [0, -60, 0]
                vals[f"{s_}Shin"] = [0, 80, 0]
                vals[f"{s_}Foot"] = [0, -20, 0]
            else:
                th, sh = leg_ik(hy, 0.0, ANKLE_H, 4.0)
                vals[f"{s_}Thigh"] = [0, th, 0]
                vals[f"{s_}Shin"] = [0, sh, 0]
                vals[f"{s_}Foot"] = [0, -(th + sh), 0]
        row = []
        for name, nch in JOINTS:
            row += vals[name]
        rows.append(" ".join(f"{v:.4f}" for v in row))

    return "\n".join([HIERARCHY, "MOTION", f"Frames: {n}",
                      f"Frame Time: {1.0 / FPS:.6f}"] + rows) + "\n"


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "jump_floaty.bvh").write_text(build(True), encoding="utf-8")
    (here / "jump_fixed.bvh").write_text(build(False), encoding="utf-8")
    t_fix = 2.0 * math.sqrt(2.0 * APEX_RISE / G_CM)
    print(f"floaty: {APEX_RISE} cm apex over 0.667 s  "
          f"(needs {t_fix:.3f} s at 1 g)")
    print("fixed:  same apex, airtime matched to gravity")
