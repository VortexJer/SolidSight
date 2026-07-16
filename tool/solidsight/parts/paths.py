"""Sweeps along 3D polylines."""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Solid, hull, sphere, union


def tube_path(points, d: float, segments: int | None = 24) -> Solid:
    """A round tube swept along a 3D polyline: the union of hulls of
    consecutive spheres. Smooth hooks, handles, wire guides, curved feet.
    Sample curves finely (every few degrees) — each pair of points becomes
    one straight capsule segment.

        pts = [(0, 0, z) for z in range(0, 30, 2)] + [...curve...]
        emit(parts.tube_path(pts, d=8), name="hook")
    """
    pts = [(float(x), float(y), float(z)) for x, y, z in points]
    if len(pts) < 2:
        raise BadArgumentError(
            f"tube_path() needs at least 2 points, got {len(pts)}")
    if d <= 0:
        raise BadArgumentError(f"tube_path() diameter must be positive, "
                               f"got {fmt_num(d)}")
    ball = sphere(d=d, segments=segments)
    beads = [ball.translate(*p) for p in pts]
    caps = [hull(a, b) for a, b in zip(beads[:-1], beads[1:])
            if _dist(a.bbox_center, b.bbox_center) > 1e-9]
    if not caps:
        raise BadArgumentError("tube_path() polyline has zero length",
                               suggestion="points are all identical")
    out = union(*caps)
    out.desc = f"tube_path({len(pts)} pts, d={fmt_num(d)})"
    return out


def _dist(a, b) -> float:
    return math.dist(a, b)
