"""Repetition helpers: linear, grid and circular patterns."""

from __future__ import annotations

from ..errors import BadArgumentError
from ..geom import Solid, union


def linear_pattern(solid: Solid, count: int, dx: float = 0.0,
                   dy: float = 0.0, dz: float = 0.0) -> Solid:
    """count copies stepped by (dx, dy, dz), unioned. The original is copy 0."""
    if count < 1:
        raise BadArgumentError(f"linear_pattern() count must be >= 1, got {count}")
    if count > 1 and dx == dy == dz == 0:
        raise BadArgumentError(
            "linear_pattern() step is (0,0,0) — all copies would coincide",
            suggestion="pass dx/dy/dz, e.g. linear_pattern(hole, 4, dx=12)")
    return union(*[solid.translate(dx * i, dy * i, dz * i)
                   for i in range(count)])


def grid_pattern(solid: Solid, nx: int, ny: int, dx: float, dy: float) -> Solid:
    """nx x ny grid of copies stepped by dx, dy, unioned."""
    if nx < 1 or ny < 1:
        raise BadArgumentError(f"grid_pattern() needs nx, ny >= 1 (got {nx}, {ny})")
    return union(*[solid.translate(dx * i, dy * j, 0)
                   for i in range(nx) for j in range(ny)])


def circular_pattern(solid: Solid, count: int, angle: float = 360.0) -> Solid:
    """count copies rotated around the Z axis over `angle` degrees, unioned.
    Move the seed solid off-axis first (e.g. .translate(x=radius))."""
    if count < 1:
        raise BadArgumentError(f"circular_pattern() count must be >= 1, got {count}")
    full = abs(angle - 360.0) < 1e-9
    step = angle / (count if full else max(1, count - 1))
    return union(*[solid.rotate(z=step * i) for i in range(count)])
