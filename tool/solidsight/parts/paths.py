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


def swept(solid: Solid, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
          steps: int | None = None) -> Solid:
    """The volume a part passes through while translating by (dx, dy, dz) —
    place it as a GHOST to test an insertion/removal path against the other
    parts:

        body = from_model("lid.py")
        rigid = body - clips                    # sweep the RIGID body only
        place(parts.swept(rigid, dz=-30), name="lid_path", ghost=True)
        expect("lid_path", "box", status="clear")   # rigid path must be free

    Snap-fit members interfere BY DESIGN during insertion: do not sweep
    them; judge their interference DEPTH (pairs[] overlap patches) against
    the hook's allowed deflection instead.

    Union of `steps` translated copies (default: one copy every 0.5 mm)."""
    travel = math.sqrt(dx * dx + dy * dy + dz * dz)
    if travel < 1e-9:
        raise BadArgumentError("swept() travel is zero",
                               suggestion="pass dx/dy/dz, e.g. swept(lid, dz=-30)")
    n = steps if steps is not None else min(200, max(8, int(travel / 0.5)))
    copies = [solid.translate(dx * i / n, dy * i / n, dz * i / n)
              for i in range(n + 1)]
    out = union(*copies)
    out.desc = (f"swept({fmt_num(travel)} mm along "
                f"({fmt_num(dx)}, {fmt_num(dy)}, {fmt_num(dz)}))")
    return out
