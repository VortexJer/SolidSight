"""UV layout as measurement.

Texel density, distortion, islands, seams, overlap and flipped faces —
each an exact property of the mapping, each normally judged by squinting
at a checker texture.

The per-face UV Jacobian is the object underneath most of this: it maps
the triangle's 3D tangent plane to UV space, and its singular values are
the stretch along the two principal directions. sigma_max / sigma_min is
the classic anisotropy; sqrt(sigma_max*sigma_min) is the local scale.
"""

from __future__ import annotations

import numpy as np

# thresholds, documented rather than magic
STRETCH_WARN = 2.0        # sigma_max/sigma_min above this = visibly smeared
DENSITY_SPREAD_WARN = 2.0  # max/min texel density ratio across the mesh
OVERLAP_EPS = 1e-9


def _uv_jacobian_svd(mesh) -> tuple[np.ndarray, np.ndarray]:
    """Per-face (sigma_max, sigma_min) of the 3D -> UV map.

    Built in the triangle's own tangent frame so it is rotation
    invariant and never depends on how the mesh happens to be oriented.
    """
    p = mesh.verts[mesh.tri_v]                       # (F, 3, 3)
    q = mesh.uvs[mesh.tri_uv]                        # (F, 3, 2)
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    f1, f2 = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]

    # orthonormal basis of the triangle's plane
    n1 = np.linalg.norm(e1, axis=1, keepdims=True)
    t1 = e1 / np.maximum(n1, 1e-12)
    proj = np.sum(e2 * t1, axis=1, keepdims=True)
    perp = e2 - proj * t1
    n2 = np.linalg.norm(perp, axis=1, keepdims=True)
    # (t2 = perp/n2 is the second basis vector; only its LENGTH n2 is
    # needed below, since e2's coordinates in (t1, t2) are (proj, n2).)

    # The 3D edges in the (t1, t2) basis, as the COLUMNS of A:
    #   e1 = (n1, 0),  e2 = (proj, n2)
    A = np.stack([np.stack([n1[:, 0], np.zeros(len(p))], axis=1),
                  np.stack([proj[:, 0], n2[:, 0]], axis=1)], axis=2)
    B = np.stack([f1, f2], axis=2)                   # (F, 2, 2), columns

    # J maps the 3D tangent plane -> UV, so J @ e_i = f_i for both edges,
    # i.e. J @ A = B. (Transposing A here silently rotates the frame and
    # reports a conformal map as 2.6:1 stretched — a cube of square UVs
    # on square faces is the test that catches it.)
    det = np.linalg.det(A)
    ok = np.abs(det) > 1e-12
    J = np.zeros((len(p), 2, 2))
    if ok.any():
        J[ok] = B[ok] @ np.linalg.inv(A[ok])
    sv = np.linalg.svd(J, compute_uv=False)          # (F, 2), descending
    smax, smin = sv[:, 0], sv[:, 1]
    smax[~ok] = smin[~ok] = np.nan                   # degenerate 3D triangle
    return smax, smin


def texel_density(mesh, texture_px: int) -> dict:
    """Texels per unit of surface, per face.

    This is THE number a texture artist quotes ("512 px/m") and the one
    that decides whether two objects look like they belong in the same
    scene. It is exact: UV area x texture area / 3D area.
    """
    a3 = mesh.face_area_3d()
    auv = np.abs(mesh.face_area_uv())
    ok = a3 > 1e-12
    dens = np.full(len(a3), np.nan)
    dens[ok] = np.sqrt(auv[ok] * (texture_px ** 2) / a3[ok])

    valid = dens[np.isfinite(dens) & (dens > 0)]
    if valid.size == 0:
        return {"note": "no faces with usable area", "per_face": dens}
    w = a3[np.isfinite(dens) & (dens > 0)]
    mean = float(np.average(valid, weights=w))       # area-weighted: honest
    lo, hi = float(np.percentile(valid, 2)), float(np.percentile(valid, 98))
    return {
        "px_per_unit": {
            "area_weighted_mean": round(mean, 2),
            "p2": round(lo, 2), "p98": round(hi, 2),
            "min": round(float(valid.min()), 2),
            "max": round(float(valid.max()), 2),
        },
        "spread_ratio": round(float(hi / lo) if lo > 1e-9 else float("inf"),
                              2),
        "worst_face": int(np.nanargmin(np.where(dens > 0, dens, np.nan))),
        "per_face": dens,
        "note": ("texels per world unit at the given texture size; the "
                 "mean is area-weighted, and spread_ratio is p98/p2 "
                 "(robust to a few stray faces)"),
    }


def distortion(mesh) -> dict:
    """Stretch and flip per face."""
    smax, smin = _uv_jacobian_svd(mesh)
    with np.errstate(divide="ignore", invalid="ignore"):
        aniso = smax / smin
    finite = np.isfinite(aniso)
    signed = mesh.face_area_uv()
    flipped = np.nonzero(signed < -OVERLAP_EPS)[0]
    # winding is a convention: only the MINORITY orientation is a defect
    if len(flipped) > len(signed) / 2:
        flipped = np.nonzero(signed > OVERLAP_EPS)[0]

    bad = np.nonzero(finite & (aniso > STRETCH_WARN))[0]
    a3 = mesh.face_area_3d()
    return {
        "anisotropy": {
            "median": round(float(np.nanmedian(aniso[finite])), 3)
            if finite.any() else None,
            "p95": round(float(np.nanpercentile(aniso[finite], 95)), 3)
            if finite.any() else None,
            "max": round(float(np.nanmax(aniso[finite])), 3)
            if finite.any() else None,
            "worst_face": int(np.nanargmax(np.where(finite, aniso, -np.inf)))
            if finite.any() else None,
        },
        "stretched_faces": [int(f) for f in bad[:50]],
        "stretched_face_count": int(len(bad)),
        "stretched_area_fraction": round(
            float(a3[bad].sum() / max(a3.sum(), 1e-12)), 4),
        "flipped_faces": [int(f) for f in flipped[:50]],
        "flipped_face_count": int(len(flipped)),
        "per_face_anisotropy": aniso,
        "note": ("anisotropy = sigma_max/sigma_min of the per-face UV "
                 "Jacobian: 1.0 is conformal, >2 is visibly smeared. "
                 "Flipped = UV winding opposite to the mesh majority"),
    }


def islands(mesh) -> dict:
    """UV islands (connected in UV space) vs mesh shells (connected in
    3D). Every place they disagree is a seam — which is exactly what a
    seam IS, so this counts them instead of looking for them."""
    F = mesh.n_faces
    parent_uv = np.arange(F)
    parent_3d = np.arange(F)

    def find(par, i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def union(par, a, b):
        ra, rb = find(par, a), find(par, b)
        if ra != rb:
            par[ra] = rb

    # edges keyed by their vertex pair; faces sharing a key are joined
    def build(tri, par):
        edges: dict[tuple[int, int], list[int]] = {}
        for f in range(F):
            a, b, c = tri[f]
            for u, v in ((a, b), (b, c), (c, a)):
                edges.setdefault((min(u, v), max(u, v)), []).append(f)
        for faces in edges.values():
            for f in faces[1:]:
                union(par, faces[0], f)
        return edges

    build(mesh.tri_uv, parent_uv)      # unions faces sharing a UV edge
    build(mesh.tri_v, parent_3d)       # ... and faces sharing a 3D edge

    uv_root = np.array([find(parent_uv, f) for f in range(F)])
    tri3_root = np.array([find(parent_3d, f) for f in range(F)])
    n_islands = len(np.unique(uv_root))
    n_shells = len(np.unique(tri3_root))

    # seam length: 3D edges whose two faces are in different UV islands
    seam_len = 0.0
    seam_edges = 0
    edges3: dict[tuple[int, int], list[int]] = {}
    for f in range(F):
        a, b, c = mesh.tri_v[f]
        for u, v in ((a, b), (b, c), (c, a)):
            edges3.setdefault((min(u, v), max(u, v)), []).append(f)
    for (u, v), faces in edges3.items():
        if len(faces) == 2 and uv_root[faces[0]] != uv_root[faces[1]]:
            seam_len += float(np.linalg.norm(mesh.verts[u] - mesh.verts[v]))
            seam_edges += 1

    # island sizes, by UV area
    auv = np.abs(mesh.face_area_uv())
    sizes: dict[int, float] = {}
    for f in range(F):
        sizes[uv_root[f]] = sizes.get(uv_root[f], 0.0) + float(auv[f])
    ordered = sorted(sizes.values(), reverse=True)

    return {
        "uv_islands": int(n_islands),
        "mesh_shells": int(n_shells),
        "seam_edges": seam_edges,
        "seam_length_3d": round(seam_len, 4),
        "largest_island_uv_area": round(ordered[0], 6) if ordered else 0.0,
        "smallest_island_uv_area": round(ordered[-1], 6) if ordered else 0.0,
        "island_uv_areas": [round(v, 6) for v in ordered[:20]],
        "uv_root_per_face": uv_root,
        "note": ("an island is a UV-connected face set; a seam is a 3D "
                 "edge whose two faces land in different islands - so "
                 "seams are counted, not guessed"),
    }


def packing(mesh, isl: dict) -> dict:
    """How much of the 0..1 UV square the layout actually uses, and
    whether islands overlap each other (double-booked texels)."""
    uv = mesh.uvs[mesh.tri_uv]                       # (F, 3, 2)
    lo = uv.reshape(-1, 2).min(axis=0)
    hi = uv.reshape(-1, 2).max(axis=0)
    out_of_bounds = int(((uv < -1e-6) | (uv > 1 + 1e-6)).any(axis=(1, 2))
                        .sum())
    used = float(np.abs(mesh.face_area_uv()).sum())

    # overlap: rasterize island ids into a coarse grid and look for
    # cells claimed by more than one island. Exact per-texel overlap
    # would need a real rasterizer; this finds the real cases (whole
    # islands stacked) without pretending to sub-texel precision.
    N = 256
    grid = np.full((N, N), -1, dtype=np.int64)
    clash = 0
    roots = isl["uv_root_per_face"]
    for f in range(mesh.n_faces):
        tri = uv[f]
        x0, y0 = np.clip(np.floor(tri.min(axis=0) * N).astype(int), 0, N - 1)
        x1, y1 = np.clip(np.ceil(tri.max(axis=0) * N).astype(int), 0, N)
        if x1 <= x0 or y1 <= y0:
            continue
        block = grid[y0:y1, x0:x1]
        other = (block >= 0) & (block != roots[f])
        clash += int(other.sum())
        block[block < 0] = roots[f]

    return {
        "uv_bbox": [round(float(v), 4) for v in (*lo, *hi)],
        "used_uv_area": round(used, 6),
        "utilization": round(used, 4),
        "faces_outside_0_1": out_of_bounds,
        "overlap_cells": clash,
        "overlap_grid": N,
        "note": ("utilization is the summed UV area of all faces (1.0 = "
                 "the whole square, wasted space excluded); overlap is "
                 "measured on a 256x256 grid, so it finds stacked "
                 "islands, not sub-texel touching"),
    }
