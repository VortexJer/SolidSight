"""Exact spatial queries — non-visual "vision" for agents.

Renders answer "does it look right?". These answer "is it geometrically
right, with mathematical certainty?" — equally useful for agents without
image input:

- classify_point:  INSIDE / OUTSIDE / ON_SURFACE for one point
- raycast:         every distance at which a ray crosses the surface
- section_grid:    a 2D INSIDE/OUTSIDE grid at a cut plane (ASCII-friendly)
- voxelize:        the whole part as a boolean voxel grid
- find_voids:      flood-fill detection of sealed internal cavities

All of it is deterministic and runs on the exact build geometry. The phase-1
report uses THESE primitives for wall thickness and cavity checks — there is
no parallel system.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .errors import BadArgumentError, fmt_num


# ---------------------------------------------------------------------------
# Ray casting core (vectorized Moller-Trumbore, chunked to bound memory)
# ---------------------------------------------------------------------------

class TriangleSet:
    """Pre-baked triangle arrays for a mesh; the engine behind every query."""

    def __init__(self, mesh):
        tris = np.asarray(mesh.triangles, float)
        self.v0 = tris[:, 0]
        self.e1 = tris[:, 1] - self.v0
        self.e2 = tris[:, 2] - self.v0
        self.normals = np.asarray(mesh.face_normals, float)
        self.n_tris = len(tris)
        self.bounds = np.asarray(mesh.bounds, float)

    def cast(self, origins: np.ndarray, dirs: np.ndarray,
             chunk: int = 64) -> list[list[tuple[float, int, int]]]:
        """All TRUE surface crossings per ray: list of (t, triangle_index,
        direction), sorted by t, t > 0 only. direction is +1 entering the
        material (front-face), -1 exiting (back-face).

        Hits at the same t are merged by net crossing direction, so a ray
        passing exactly through a shared triangle edge counts once, and a
        tangential graze counts zero times — parity stays correct."""
        out: list[list[tuple[float, int, int]]] = []
        tol = 1e-9
        for s in range(0, len(origins), chunk):
            O = origins[s:s + chunk][:, None, :]
            D = dirs[s:s + chunk][:, None, :]
            p = np.cross(D, self.e2[None, :, :])
            det = np.einsum("rtk,tk->rt", p, self.e1)
            with np.errstate(divide="ignore", invalid="ignore"):
                inv = 1.0 / det
                tvec = O - self.v0[None, :, :]
                u = np.einsum("rtk,rtk->rt", tvec, p) * inv
                q = np.cross(tvec, self.e1[None, :, :])
                v = np.einsum("rtk,rtk->rt", q, D) * inv
                t = np.einsum("rtk,tk->rt", q, self.e2) * inv
                hit = ((np.abs(det) > tol) & (u >= -tol) & (v >= -tol)
                       & (u + v <= 1 + tol) & (t > 1e-9))
            for r in range(hit.shape[0]):
                idx = np.nonzero(hit[r])[0]
                raw = sorted((float(t[r, i]), int(i),
                              1 if det[r, i] > 0 else -1) for i in idx)
                out.append(_merge_coincident(raw))
        return out

    def cast_intervals(self, origins: np.ndarray, dirs: np.ndarray,
                       chunk: int = 64) -> list[list[tuple[float, float]]]:
        """Material intervals (t_enter, t_exit) along each ray, derived from
        cast() by pairing +1/-1 crossings."""
        out = []
        for hits in self.cast(origins, dirs, chunk):
            segs = []
            open_t = None
            depth = 0
            for t, _tri, d in hits:
                if d > 0:
                    if depth == 0:
                        open_t = t
                    depth += 1
                else:
                    depth = max(0, depth - 1)
                    if depth == 0 and open_t is not None:
                        segs.append((open_t, t))
                        open_t = None
            out.append(segs)
        return out

    def first_exit(self, origins: np.ndarray, dirs: np.ndarray,
                   chunk: int = 64) -> tuple[np.ndarray, np.ndarray]:
        """Distance and triangle index of each ray's first BACKFACE hit
        (the ray leaving the material). Front-face grazes on the ray's own
        surface are ignored. Returns (dist, tri_idx); inf / -1 when no hit."""
        dist = np.full(len(origins), np.inf)
        tri = np.full(len(origins), -1, dtype=int)
        tol = 1e-9
        for s in range(0, len(origins), chunk):
            O = origins[s:s + chunk][:, None, :]
            D = dirs[s:s + chunk][:, None, :]
            p = np.cross(D, self.e2[None, :, :])
            det = np.einsum("rtk,tk->rt", p, self.e1)
            with np.errstate(divide="ignore", invalid="ignore"):
                inv = 1.0 / det
                tvec = O - self.v0[None, :, :]
                u = np.einsum("rtk,rtk->rt", tvec, p) * inv
                q = np.cross(tvec, self.e1[None, :, :])
                v = np.einsum("rtk,rtk->rt", q, D) * inv
                t = np.einsum("rtk,tk->rt", q, self.e2) * inv
                # det < 0 <=> ray direction agrees with the outward normal:
                # it EXITS through this triangle.
                hit = ((det < -tol) & (u >= -tol) & (v >= -tol)
                       & (u + v <= 1 + tol) & (t > 1e-9))
            t = np.where(hit, t, np.inf)
            k = np.argmin(t, axis=1)
            rows = np.arange(t.shape[0])
            dist[s:s + chunk] = t[rows, k]
            tri[s:s + chunk] = np.where(np.isfinite(t[rows, k]), k, -1)
        return dist, tri

    def point_surface_distance(self, points: np.ndarray,
                               chunk: int = 8) -> np.ndarray:
        """Exact min distance from each point to the triangle surface."""
        out = np.full(len(points), np.inf)
        for s in range(0, len(points), chunk):
            P = points[s:s + chunk]
            d = _point_tri_distance(P, self.v0, self.e1, self.e2)
            out[s:s + chunk] = d.min(axis=1)
        return out


def _merge_coincident(raw: list[tuple[float, int, int]],
                      tol: float = 1e-7) -> list[tuple[float, int, int]]:
    """Merge hits at (numerically) the same t by net crossing direction."""
    out: list[tuple[float, int, int]] = []
    i = 0
    while i < len(raw):
        j = i
        net = 0
        while j < len(raw) and raw[j][0] - raw[i][0] <= tol * (1 + raw[i][0]):
            net += raw[j][2]
            j += 1
        if net != 0:
            out.append((raw[i][0], raw[i][1], 1 if net > 0 else -1))
        i = j
    return out


def _point_tri_distance(P: np.ndarray, v0, e1, e2) -> np.ndarray:
    """(p, t) matrix of point-to-triangle distances (Eberly's method)."""
    D = v0[None, :, :] - P[:, None, :]
    a = np.einsum("tk,tk->t", e1, e1)[None, :]
    b = np.einsum("tk,tk->t", e1, e2)[None, :]
    c = np.einsum("tk,tk->t", e2, e2)[None, :]
    d = np.einsum("ptk,tk->pt", D, e1)
    e = np.einsum("ptk,tk->pt", D, e2)
    det = a * c - b * b
    s = b * e - c * d
    t = b * d - a * e
    with np.errstate(divide="ignore", invalid="ignore"):
        # clamp barycentric coordinates region by region (vectorized approx:
        # project then clamp; exact enough for tolerance tests)
        s1 = np.clip(np.where(det > 1e-12, s / det, 0.0), 0.0, 1.0)
        t1 = np.clip(np.where(det > 1e-12, t / det, 0.0), 0.0, 1.0)
        over = s1 + t1 > 1.0
        scale = np.where(over, (s1 + t1), 1.0)
        s1 = np.where(over, s1 / scale, s1)
        t1 = np.where(over, t1 / scale, t1)
    # also test the three edges' closest points to fix clamping error
    best = _dist_at(P, v0, e1, e2, s1, t1)
    for (ss, tt) in (((np.clip(-d / np.maximum(a, 1e-12), 0, 1)),
                      np.zeros_like(s1)),
                     (np.zeros_like(s1),
                      np.clip(-e / np.maximum(c, 1e-12), 0, 1))):
        best = np.minimum(best, _dist_at(P, v0, e1, e2, ss, tt))
    # edge s+t=1
    denom = np.maximum(a - 2 * b + c, 1e-12)
    ss = np.clip((c + e - b - d) / denom, 0, 1)
    best = np.minimum(best, _dist_at(P, v0, e1, e2, ss, 1 - ss))
    return best


def _dist_at(P, v0, e1, e2, s, t):
    Q = (v0[None, :, :] + s[:, :, None] * e1[None, :, :]
         + t[:, :, None] * e2[None, :, :])
    return np.linalg.norm(Q - P[:, None, :], axis=2)


# ---------------------------------------------------------------------------
# Public queries (operate on a Solid)
# ---------------------------------------------------------------------------

def _tris(solid, simplify_tol: float = 0.0) -> TriangleSet:
    m = solid.manifold.simplify(simplify_tol) if simplify_tol else solid.manifold
    from .geom import Solid
    return TriangleSet(Solid(m).to_trimesh())


def classify_point(solid, x: float, y: float, z: float,
                   tol: float = 1e-3) -> dict:
    """INSIDE / OUTSIDE / ON_SURFACE with the distance to the surface.
    Parity rule: a ray from the point crosses the surface an odd number of
    times exactly when the point is inside."""
    ts = _tris(solid)
    p = np.array([[float(x), float(y), float(z)]])
    dist_surface = float(ts.point_surface_distance(p)[0])
    if dist_surface <= tol:
        result = "ON_SURFACE"
    else:
        # fixed slightly-irrational direction: avoids hitting edges/vertices
        # exactly, keeps the answer deterministic
        d = np.array([[0.577350269, 0.211324865, 0.788675134]])
        d /= np.linalg.norm(d)
        crossings = len(ts.cast(p, d)[0])
        result = "INSIDE" if crossings % 2 == 1 else "OUTSIDE"
    return {"point": [float(x), float(y), float(z)], "result": result,
            "distance_to_surface_mm": round(dist_surface, 4)}


def raycast(solid, origin, direction) -> dict:
    """Every crossing of the ray with the surface, in order. Two entries and
    two exits where you expected one wall means an internal cavity or a
    second shell sits on that line."""
    o = np.asarray([origin], float)
    d = np.asarray([direction], float)
    n = np.linalg.norm(d[0])
    if n < 1e-12:
        raise BadArgumentError("raycast() direction is a zero vector",
                               suggestion="e.g. direction=(0, 0, -1)")
    d = d / n
    ts = _tris(solid)
    hits = []
    inside_now = classify_point(solid, *origin)["result"] == "INSIDE"
    for t, _tri, direction in ts.cast(o, d)[0]:
        point = (o[0] + d[0] * t)
        hits.append({"t_mm": round(float(t), 4),
                     "point": [round(float(v), 4) for v in point],
                     "entering": direction > 0})
    segments = []
    open_t = 0.0 if inside_now else None
    for h in hits:
        if h["entering"]:
            open_t = h["t_mm"]
        elif open_t is not None:
            segments.append({"from_mm": open_t, "to_mm": h["t_mm"],
                             "thickness_mm": round(h["t_mm"] - open_t, 4)})
            open_t = None
    return {"origin": [float(v) for v in origin],
            "direction": [round(float(v), 6) for v in d[0]],
            "origin_inside": inside_now,
            "crossings": len(hits), "hits": hits,
            "material_segments": segments,
            "note": ("more than one material segment on this line means an "
                     "internal cavity, a second shell, or a concave shape "
                     "re-entered" if len(segments) > 1 else None)}


def section_grid(solid, axis: str, value: float,
                 res: float | None = None, max_cells: int = 160) -> dict:
    """2D INSIDE/OUTSIDE grid at axis=value. '#' = material, '.' = empty.
    Row rays are cast with the same engine as every other query."""
    if axis not in ("x", "y", "z"):
        raise BadArgumentError(f"section axis must be x, y or z, got {axis!r}")
    ts = _tris(solid, simplify_tol=0.01)
    lo3, hi3 = solid.bbox
    axes = {"x": (1, 2, 0), "y": (0, 2, 1), "z": (0, 1, 2)}
    ua, va, wa = axes[axis]  # u = grid columns, v = grid rows, w = cut axis
    if not (lo3[wa] - 1e-9 <= value <= hi3[wa] + 1e-9):
        raise BadArgumentError(
            f"section {axis}={fmt_num(value)} misses the part entirely",
            where=f"part spans {axis} {fmt_num(lo3[wa])}..{fmt_num(hi3[wa])}",
            suggestion=f"pick a value inside that range, e.g. "
                       f"{axis}={fmt_num((lo3[wa] + hi3[wa]) / 2)}")
    span_u = hi3[ua] - lo3[ua]
    span_v = hi3[va] - lo3[va]
    if res is None:
        res = max(max(span_u, span_v) / 78, 0.05)
    nu = min(max_cells, max(2, int(math.ceil(span_u / res)) + 1))
    nv = min(max_cells, max(2, int(math.ceil(span_v / res)) + 1))
    us = lo3[ua] + (np.arange(nu) + 0.5) * (span_u / nu)
    vs = lo3[va] + (np.arange(nv) + 0.5) * (span_v / nv)

    # one ray per row, along +u
    origins = np.zeros((nv, 3))
    origins[:, ua] = lo3[ua] - 1.0
    origins[:, va] = vs
    origins[:, wa] = value
    dirs = np.zeros((nv, 3))
    dirs[:, ua] = 1.0
    all_segs = ts.cast_intervals(origins, dirs)

    grid = np.zeros((nv, nu), dtype=bool)
    for r, segs in enumerate(all_segs):
        for a, b in segs:
            grid[r] |= (us >= lo3[ua] - 1.0 + a) & (us <= lo3[ua] - 1.0 + b)

    rows = ["".join("#" if c else "." for c in row) for row in grid[::-1]]
    u_name, v_name = "xyz"[ua], "xyz"[va]
    return {"axis": axis, "value": value, "cell_mm": round(span_u / nu, 4),
            "cols_axis": u_name, "rows_axis": v_name,
            "origin": [round(float(lo3[ua]), 3), round(float(lo3[va]), 3)],
            "size_cells": [nu, nv],
            "legend": "# = material, . = empty; top row = max "
                      + v_name + ", left col = min " + u_name,
            "grid": rows}


def voxelize(solid, res: float | None = None,
             max_voxels: int = 400_000) -> dict:
    """Boolean voxel grid of the part (one Z parity-ray per column).
    Returns grid + metadata; use find_voids() on it for cavities."""
    lo, hi = np.asarray(solid.bbox[0]), np.asarray(solid.bbox[1])
    size = hi - lo
    if res is None:
        res = max(float(size.max()) / 64, 0.05)
    counts = np.maximum((size / res).astype(int) + 1, 1)
    while int(counts.prod()) > max_voxels:
        res *= 1.26
        counts = np.maximum((size / res).astype(int) + 1, 1)
    nx, ny, nz = (int(c) for c in counts)
    xs = lo[0] + (np.arange(nx) + 0.5) * (size[0] / nx if nx else 1)
    ys = lo[1] + (np.arange(ny) + 0.5) * (size[1] / ny if ny else 1)
    zs = lo[2] + (np.arange(nz) + 0.5) * (size[2] / nz if nz else 1)

    ts = _tris(solid, simplify_tol=0.01)
    origins = np.zeros((nx * ny, 3))
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    origins[:, 0] = gx.ravel()
    origins[:, 1] = gy.ravel()
    origins[:, 2] = lo[2] - 1.0
    dirs = np.tile(np.array([[0.0, 0.0, 1.0]]), (nx * ny, 1))
    all_segs = ts.cast_intervals(origins, dirs, chunk=128)

    grid = np.zeros((nx, ny, nz), dtype=bool)
    for ci, segs in enumerate(all_segs):
        i, j = divmod(ci, ny)
        for a, b in segs:
            grid[i, j] |= (zs >= lo[2] - 1.0 + a) & (zs <= lo[2] - 1.0 + b)

    return {"grid": grid, "origin": [float(v) for v in lo],
            "res_mm": round(float(res), 4),
            "shape": [nx, ny, nz],
            "filled_voxels": int(grid.sum()),
            "filled_volume_mm3": round(float(grid.sum()) * res ** 3, 2)}


def find_voids(vox: dict) -> list[dict]:
    """Sealed internal cavities: empty voxel regions NOT connected to the
    outside. Flood-fills the exterior, then labels what is left."""
    grid = vox["grid"]
    res = vox["res_mm"]
    origin = np.asarray(vox["origin"])
    empty = ~grid
    # flood fill exterior: start from the padded border
    padded = np.pad(empty, 1, constant_values=True)
    reach = np.zeros_like(padded)
    reach[0, :, :] = reach[-1, :, :] = True
    reach[:, 0, :] = reach[:, -1, :] = True
    reach[:, :, 0] = reach[:, :, -1] = True
    reach &= padded
    while True:
        grown = reach.copy()
        grown[1:, :, :] |= reach[:-1, :, :]
        grown[:-1, :, :] |= reach[1:, :, :]
        grown[:, 1:, :] |= reach[:, :-1, :]
        grown[:, :-1, :] |= reach[:, 1:, :]
        grown[:, :, 1:] |= reach[:, :, :-1]
        grown[:, :, :-1] |= reach[:, :, 1:]
        grown &= padded
        if (grown == reach).all():
            break
        reach = grown
    voids_mask = padded & ~reach
    voids_mask = voids_mask[1:-1, 1:-1, 1:-1]
    if not voids_mask.any():
        return []

    # label connected void components (BFS)
    out = []
    remaining = voids_mask.copy()
    while remaining.any() and len(out) < 16:
        seed = np.transpose(np.nonzero(remaining))[0]
        comp = np.zeros_like(remaining)
        comp[tuple(seed)] = True
        while True:
            grown = comp.copy()
            grown[1:, :, :] |= comp[:-1, :, :]
            grown[:-1, :, :] |= comp[1:, :, :]
            grown[:, 1:, :] |= comp[:, :-1, :]
            grown[:, :-1, :] |= comp[:, 1:, :]
            grown[:, :, 1:] |= comp[:, :, :-1]
            grown[:, :, :-1] |= comp[:, :, 1:]
            grown &= remaining
            if (grown == comp).all():
                break
            comp = grown
        idx = np.transpose(np.nonzero(comp))
        lo_v = origin + idx.min(axis=0) * res
        hi_v = origin + (idx.max(axis=0) + 1) * res
        out.append({
            "voxels": int(comp.sum()),
            "volume_mm3": round(float(comp.sum()) * res ** 3, 2),
            "bbox": {"min": [round(float(v), 2) for v in lo_v],
                     "max": [round(float(v), 2) for v in hi_v]},
        })
        remaining &= ~comp
    out.sort(key=lambda v: -v["volume_mm3"])
    return out
