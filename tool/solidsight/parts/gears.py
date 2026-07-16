"""Involute spur gears."""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Sketch, Solid, circle, polygon


def spur_gear(module: float, teeth: int, thickness: float,
              bore: float = 0.0, pressure_angle: float = 20.0,
              backlash: float = 0.0) -> Solid:
    """Standard involute spur gear, centered on XY, base on Z=0.

    module: tooth size in mm (pitch diameter = module * teeth). Two meshing
    gears MUST share the same module and pressure_angle; their center
    distance is module * (teeth_a + teeth_b) / 2.
    bore: central hole diameter (0 = solid).
    backlash: extra angular gap in mm of arc removed from each tooth flank
    pair; 0.1-0.2 is typical for printed gears.
    """
    if teeth < 6:
        raise BadArgumentError(
            f"spur_gear() needs at least 6 teeth, got {teeth}",
            suggestion="use more teeth or a smaller module")
    if module <= 0 or thickness <= 0:
        raise BadArgumentError(
            f"spur_gear() module and thickness must be positive "
            f"(got module={fmt_num(module)}, thickness={fmt_num(thickness)})")

    z = int(teeth)
    m = float(module)
    alpha = math.radians(pressure_angle)
    rp = m * z / 2.0                # pitch radius
    rb = rp * math.cos(alpha)       # base radius
    ra = rp + m                     # addendum (tip) radius
    rd = rp - 1.25 * m              # dedendum (root) radius
    if rd <= 0:
        raise BadArgumentError(
            f"spur_gear() root radius came out {fmt_num(rd)} — module "
            f"{fmt_num(m)} is too large for {z} teeth")
    if bore and bore / 2.0 >= rd:
        raise BadArgumentError(
            f"spur_gear() bore d={fmt_num(bore)} reaches into the teeth "
            f"(root diameter is {fmt_num(2 * rd)})",
            suggestion=f"keep bore below {fmt_num(2 * rd - m)}")

    def inv(a: float) -> float:
        return math.tan(a) - a

    # Angular half-thickness of a tooth at radius r (standard involute
    # relation), minus backlash converted to an angle at the pitch circle.
    half_base = math.pi / (2 * z) + inv(alpha) - (backlash / 2.0) / rp

    def half_angle(r: float) -> float:
        phi = math.acos(min(1.0, rb / r))
        return half_base - inv(phi)

    n_flank = 10
    r_start = max(rd, rb)
    pts: list[tuple[float, float]] = []
    pitch_ang = 2 * math.pi / z
    for k in range(z):
        c = k * pitch_ang  # center angle of this tooth
        flank_rs = [r_start + (ra - r_start) * i / (n_flank - 1)
                    for i in range(n_flank)]
        rising = [(r, c - half_angle(r)) for r in flank_rs]      # leading flank
        falling = [(r, c + half_angle(r)) for r in reversed(flank_rs)]
        # radial root wall down to rd if the base circle sits above the root
        if rd < rb:
            rising.insert(0, (rd, c - half_angle(r_start)))
            falling.append((rd, c + half_angle(r_start)))
        # tip arc
        tip = [(ra, c + a) for a in _arc(-half_angle(ra), half_angle(ra), 4)[1:-1]]
        # root arc to the next tooth
        nxt = (k + 1) * pitch_ang
        root = [(rd, a) for a in _arc(c + half_angle(r_start) if rd < rb
                                      else c + half_angle(rd),
                                      nxt - (half_angle(r_start) if rd < rb
                                             else half_angle(rd)), 5)[1:-1]]
        for r, a in rising + tip + falling + root:
            pts.append((r * math.cos(a), r * math.sin(a)))

    profile: Sketch = polygon(pts)
    gear = profile.extrude(thickness)
    if bore:
        gear = gear - circle(d=bore).extrude(thickness * 3).translate(0, 0, -thickness)
    gear.desc = (f"spur_gear(module={fmt_num(m)}, teeth={z}, "
                 f"thickness={fmt_num(thickness)})")
    return gear


def _arc(a0: float, a1: float, n: int) -> list[float]:
    return [a0 + (a1 - a0) * i / (n - 1) for i in range(n)]
