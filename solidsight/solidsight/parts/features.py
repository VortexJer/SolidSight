"""Machining-style features: real holes and their patterns.

Most functional detail on mechanical parts is holes — plain, counterbored,
countersunk, tapped, chamfered, in matrices and bolt circles. hole() builds
the CUTTER with its entry point at the origin drilling straight down (-Z);
orient with .aim(axis) and position with .translate(entry point), then
subtract.
"""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Solid, cone, cylinder, union
from .patterns import circular_pattern


def hole(d: float, depth: float,
         counterbore: tuple[float, float] | None = None,
         countersink: float | tuple[float, float] | None = None,
         chamfer: float = 0.0,
         drill_point: bool = False,
         through_margin: float = 1.0,
         segments: int | None = None) -> Solid:
    """Drilling CUTTER: entry at the origin, drilling -Z, `depth` measured
    from the entry surface. Subtract it from the part.

    counterbore=(D, cb_depth): flat-bottom enlargement at the entry (socket
    head screws).
    countersink=D or (D, total_angle_deg): conical entry (flat head screws;
    default angle 90).
    chamfer=c: break the entry edge with a c x 45 deg cone (deburring).
    drill_point=True: 118 deg conical tip at the bottom (realistic blind
    holes).
    through_margin: how far the cutter sticks up ABOVE the entry surface so
    the boolean always pierces (default 1 mm).

        # M5 socket-head counterbored hole into the top face at (10, 0):
        part -= parts.hole(5.5, 12, counterbore=(9.5, 5.5)).translate(10, 0, 20)
        # tapped-look blind hole into a +Y wall:
        part -= parts.hole(4.2, 10, chamfer=0.5).aim("-y").translate(0, 15, 6)
    """
    if d <= 0 or depth <= 0:
        raise BadArgumentError(
            f"hole() needs positive d and depth (got d={fmt_num(d)}, "
            f"depth={fmt_num(depth)})")
    pieces = [cylinder(h=depth + through_margin, d=d, segments=segments)
              .translate(0, 0, -depth)]

    if counterbore is not None:
        try:
            cb_d, cb_depth = float(counterbore[0]), float(counterbore[1])
        except (TypeError, IndexError):
            raise BadArgumentError(
                "hole() counterbore must be a (diameter, depth) pair",
                suggestion="e.g. counterbore=(9.5, 5.5) for an M5 socket head")
        if cb_d <= d:
            raise BadArgumentError(
                f"hole() counterbore D {fmt_num(cb_d)} must exceed the hole "
                f"d {fmt_num(d)}")
        pieces.append(cylinder(h=cb_depth + through_margin, d=cb_d,
                               segments=segments).translate(0, 0, -cb_depth))

    if countersink is not None:
        if isinstance(countersink, (int, float)):
            cs_d, cs_angle = float(countersink), 90.0
        else:
            cs_d = float(countersink[0])
            cs_angle = float(countersink[1]) if len(countersink) > 1 else 90.0
        if cs_d <= d:
            raise BadArgumentError(
                f"hole() countersink D {fmt_num(cs_d)} must exceed the hole "
                f"d {fmt_num(d)}")
        cs_depth = (cs_d - d) / 2 / math.tan(math.radians(cs_angle / 2))
        pieces.append(
            cone(h=cs_depth, d1=d, d2=cs_d, segments=segments)
            .translate(0, 0, -cs_depth))
        pieces.append(cylinder(h=through_margin, d=cs_d, segments=segments))

    if chamfer > 0:
        pieces.append(cone(h=chamfer, d1=d, d2=d + 2 * chamfer,
                           segments=segments).translate(0, 0, -chamfer))
        pieces.append(cylinder(h=through_margin, d=d + 2 * chamfer,
                               segments=segments))

    if drill_point:
        tip = (d / 2) / math.tan(math.radians(118 / 2))
        pieces.append(cone(h=tip, d1=0, d2=d, segments=segments)
                      .translate(0, 0, -depth - tip))

    out = union(*pieces)
    out.desc = f"hole(d={fmt_num(d)}, depth={fmt_num(depth)})"
    return out


def bolt_circle(cutter: Solid, count: int, d: float) -> Solid:
    """`count` copies of a hole/boss cutter on a circle of diameter d around
    the Z axis (first copy on +X). Aim/translate the RESULT onto the face."""
    if count < 1:
        raise BadArgumentError(f"bolt_circle() count must be >= 1, got {count}")
    if d <= 0:
        raise BadArgumentError(f"bolt_circle() circle d must be positive, "
                               f"got {fmt_num(d)}")
    return circular_pattern(cutter.translate(d / 2, 0, 0), count)
