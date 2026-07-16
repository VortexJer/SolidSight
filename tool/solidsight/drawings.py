"""Technical drawings: `solidsight drawing model.py` -> dimensioned PDF.

A third-angle multi-view sheet per part: front / top / right projections
with true hidden-line classification (solid = visible, dashed = hidden),
overall dimensions with extension lines, center marks on detected
circular features, a hole table (circular rim loops found on the mesh,
grouped into coaxial pairs with depth), and a title block.

Vector output. Deterministic: the PDF carries no timestamps.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .events import BUS
from .render import VIEWS, _Camera, _crease_split, _bary

SHEET_VIEWS = ["front", "top", "right"]     # third-angle arrangement


# ---------------------------------------------------------------------------
# hidden-line edge extraction (reuses the renderer's camera + zbuffer)
# ---------------------------------------------------------------------------

def _depth_buffer(tm, cam: _Camera) -> np.ndarray:
    """Depth-only rasterization (the renderer's pass minus shading)."""
    size = cam.size
    zbuf = np.full((size, size), np.inf)
    verts, faces, _n = _crease_split(tm, math.radians(30))
    pix, depth = cam.project(verts)
    tri_pix = pix[faces]
    tri_z = depth[faces]
    for ti in range(len(faces)):
        p = tri_pix[ti]
        z = tri_z[ti]
        xmin = max(int(p[:, 0].min()), 0)
        xmax = min(int(p[:, 0].max()) + 1, size - 1)
        ymin = max(int(p[:, 1].min()), 0)
        ymax = min(int(p[:, 1].max()) + 1, size - 1)
        if xmin > xmax or ymin > ymax:
            continue
        gx, gy = np.meshgrid(np.arange(xmin, xmax + 1),
                             np.arange(ymin, ymax + 1))
        bar = _bary(p, gx, gy)
        if bar is None:
            continue
        w0, w1, w2 = bar
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            continue
        zi = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub = zbuf[ymin:ymax + 1, xmin:xmax + 1]
        upd = inside & (zi < sub)
        sub[upd] = zi[upd]
    return zbuf


def view_edges(tm, view: str, res: int = 1400) -> dict:
    """Project one orthographic view: returns visible and hidden segment
    lists in true mm sheet coordinates (u right, v up)."""
    direction, up = VIEWS[view]
    lo, hi = tm.bounds
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2 or 1.0
    cam = _Camera(direction, up, center, radius, res)
    zbuf = _depth_buffer(tm, cam)

    verts = np.asarray(tm.vertices, float)
    normals = np.asarray(tm.face_normals, float)
    adj = tm.face_adjacency
    angles = tm.face_adjacency_angles
    edges = tm.face_adjacency_edges
    facing = normals @ cam.dir > 0
    keep = (facing[adj[:, 0]] != facing[adj[:, 1]]) | (angles >
                                                       math.radians(28))

    rel = verts - center
    u = rel @ cam.right
    v = rel @ cam.up
    pix, depth = cam.project(verts)

    visible: list = []
    hidden: list = []
    for ei in np.nonzero(keep)[0]:
        a, b = edges[ei]
        n = max(3, int(np.hypot(*(pix[b] - pix[a])) / 3))
        ts = np.linspace(0, 1, n)
        xs = (pix[a][0] + (pix[b][0] - pix[a][0]) * ts).round().astype(int)
        ys = (pix[a][1] + (pix[b][1] - pix[a][1]) * ts).round().astype(int)
        zs = depth[a] + (depth[b] - depth[a]) * ts
        ok = (xs >= 0) & (xs < cam.size) & (ys >= 0) & (ys < cam.size)
        vis = np.zeros(n, bool)
        vis[ok] = zs[ok] <= zbuf[ys[ok], xs[ok]] + max(radius * 5e-3, 0.05)
        us = u[a] + (u[b] - u[a]) * ts
        vs = v[a] + (v[b] - v[a]) * ts
        # split the sampled edge into runs of constant visibility
        start = 0
        for i in range(1, n + 1):
            if i == n or vis[i] != vis[start]:
                if i - start >= 2:
                    seg = ([(us[start], vs[start]), (us[i - 1], vs[i - 1])])
                    (visible if vis[start] else hidden).append(seg)
                start = i
    return {"visible": visible, "hidden": hidden,
            "u_range": (float(u.min()), float(u.max())),
            "v_range": (float(v.min()), float(v.max())),
            "axes": _view_axis_labels(view)}


def _view_axis_labels(view: str) -> tuple[str, str]:
    return {"front": ("X", "Z"), "back": ("X", "Z"),
            "right": ("Y", "Z"), "left": ("Y", "Z"),
            "top": ("X", "Y"), "bottom": ("X", "Y")}.get(view, ("U", "V"))


# ---------------------------------------------------------------------------
# circular feature detection (hole table)
# ---------------------------------------------------------------------------

def find_circles(tm, min_d: float = 0.8) -> list[dict]:
    """Closed sharp-edge loops that fit a circle: hole rims, boss edges,
    counterbore steps. Returns center, diameter, axis for each."""
    adj = tm.face_adjacency
    if len(adj) == 0:
        return []
    sharp = tm.face_adjacency_angles > math.radians(28)
    edges = tm.face_adjacency_edges[sharp]
    verts = np.asarray(tm.vertices, float)

    nxt: dict[int, list[int]] = {}
    for a, b in edges:
        nxt.setdefault(int(a), []).append(int(b))
        nxt.setdefault(int(b), []).append(int(a))

    seen: set[int] = set()
    circles: list[dict] = []
    for start in sorted(nxt):
        if start in seen or len(nxt[start]) != 2:
            continue
        loop = [start]
        prev, cur = -1, start
        while True:
            cands = [x for x in nxt.get(cur, []) if x != prev]
            if len(nxt.get(cur, [])) != 2 or not cands:
                loop = []
                break
            prev, cur = cur, cands[0]
            if cur == start:
                break
            if cur in seen or len(loop) > 4096:
                loop = []
                break
            loop.append(cur)
        if len(loop) < 12:
            continue
        seen.update(loop)
        pts = verts[loop]
        c0 = pts.mean(axis=0)
        rel = pts - c0
        _u, _s, vh = np.linalg.svd(rel, full_matrices=False)
        normal = vh[2]
        planarity = float(np.abs(rel @ normal).max())
        radii = np.linalg.norm(rel - np.outer(rel @ normal, normal), axis=1)
        r = float(radii.mean())
        if r * 2 < min_d or r < 1e-6:
            continue
        if planarity > 0.02 * r + 0.02:
            continue
        # a true polygonal circle: EVERY point on the radius, and vertices
        # spread around the full turn (rejects rounded-rectangle outlines)
        if float(np.abs(radii - r).max()) > 0.015 * r + 0.02:
            continue
        angs = np.sort(np.arctan2(rel @ vh[1], rel @ vh[0]))
        gaps = np.diff(np.concatenate([angs, [angs[0] + 2 * math.pi]]))
        if float(gaps.max()) > math.radians(75):
            continue
        circles.append({
            "center": [round(float(x), 3) for x in c0],
            "d": round(2 * r, 3),
            "axis": [round(float(x), 3) for x in normal],
        })
    circles.sort(key=lambda c: (c["d"], c["center"]))
    return circles


def hole_table(circles: list[dict], bbox_size) -> list[dict]:
    """Group coaxial equal-diameter circle pairs into holes with depth."""
    used = [False] * len(circles)
    holes: list[dict] = []
    for i, ci in enumerate(circles):
        if used[i]:
            continue
        best = None
        for j in range(i + 1, len(circles)):
            if used[j]:
                continue
            cj = circles[j]
            if abs(ci["d"] - cj["d"]) > 0.05 * ci["d"] + 0.02:
                continue
            axis = np.asarray(ci["axis"])
            if abs(float(np.dot(axis, cj["axis"]))) < 0.98:
                continue
            dvec = np.asarray(cj["center"]) - np.asarray(ci["center"])
            along = float(np.dot(dvec, axis))
            radial = float(np.linalg.norm(dvec - along * axis))
            if radial > 0.05 * ci["d"] + 0.05:
                continue
            best = (j, abs(along))
            break
        if best is not None:
            j, depth = best
            used[i] = used[j] = True
            span = abs(float(np.dot(np.asarray(bbox_size),
                                    np.asarray(ci["axis"]))))
            holes.append({"d": ci["d"], "at": ci["center"],
                          "depth": round(depth, 3),
                          "thru": depth >= span - 0.05,
                          "axis": ci["axis"]})
        else:
            used[i] = True
            holes.append({"d": ci["d"], "at": ci["center"],
                          "depth": None, "thru": False,
                          "axis": ci["axis"]})
    return holes


# ---------------------------------------------------------------------------
# the sheet
# ---------------------------------------------------------------------------

def draw_sheet(part_name: str, tm, out_pdf: Path, model_name: str,
               tool_version: str, mass_note: str = "") -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with BUS.stage("drawing", f"sheet for '{part_name}'"):
        views = {v: view_edges(tm, v) for v in SHEET_VIEWS}
        circles = find_circles(tm)
        holes = hole_table(circles, tm.extents)

    lo, hi = tm.bounds
    sx, sy, sz = (float(v) for v in tm.extents)

    fig = plt.figure(figsize=(16.54, 11.69))     # A3 landscape, inches
    fig.patch.set_facecolor("#f7f6f2")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 420)                          # sheet mm (A3)
    ax.set_ylim(0, 297)
    ax.set_axis_off()
    ax.plot([8, 412, 412, 8, 8], [8, 8, 289, 289, 8],
            color="#26282b", lw=1.0)

    # layout: third angle — front lower-left, top above it, right beside it
    gap = 24.0
    avail_w, avail_h = 420 - 2 * 30, 297 - 2 * 30
    need_w = sx + gap + sy                       # front + right
    need_h = sz + gap + sy                       # front + top
    scale = min(avail_w / need_w, avail_h / need_h, 4.0)
    std = [10, 5, 2, 1, 0.5, 0.25]
    scale = next((s for s in std if s <= scale), scale)

    fx, fy = 40.0, 40.0                          # front view origin on sheet
    origins = {
        "front": (fx, fy),
        "top": (fx, fy + sz * scale + gap),
        "right": (fx + sx * scale + gap, fy),
    }

    def put(view: str) -> None:
        d = views[view]
        ox, oy = origins[view]
        u0, v0 = d["u_range"][0], d["v_range"][0]
        for seg in d["hidden"]:
            xs = [ox + (p[0] - u0) * scale for p in seg]
            ys = [oy + (p[1] - v0) * scale for p in seg]
            ax.plot(xs, ys, color="#8a8d92", lw=0.5, ls=(0, (4, 3)))
        for seg in d["visible"]:
            xs = [ox + (p[0] - u0) * scale for p in seg]
            ys = [oy + (p[1] - v0) * scale for p in seg]
            ax.plot(xs, ys, color="#26282b", lw=0.9)
        ax.text(ox, oy - 6, view.upper(), fontsize=7, family="monospace",
                color="#7a7d82")

    for v in SHEET_VIEWS:
        put(v)

    def dim(x0, y0, x1, y1, text, offset=8.0, vertical=False):
        if vertical:
            xd = x0 - offset
            ax.plot([xd, xd], [y0, y1], color="#26282b", lw=0.5)
            for y in (y0, y1):
                ax.plot([xd - 1.5, xd + 1.5], [y, y], color="#26282b",
                        lw=0.5)
                ax.plot([xd, x0 - 1], [y, y], color="#9aa0a6", lw=0.35)
            ax.text(xd - 2, (y0 + y1) / 2, text, fontsize=7,
                    family="monospace", rotation=90, ha="right", va="center")
        else:
            yd = y0 - offset
            ax.plot([x0, x1], [yd, yd], color="#26282b", lw=0.5)
            for x in (x0, x1):
                ax.plot([x, x], [yd - 1.5, yd + 1.5], color="#26282b",
                        lw=0.5)
                ax.plot([x, x], [yd, y0 - 1], color="#9aa0a6", lw=0.35)
            ax.text((x0 + x1) / 2, yd - 2, text, fontsize=7,
                    family="monospace", ha="center", va="top")

    fox, foy = origins["front"]
    dim(fox, foy, fox + sx * scale, foy, f"{sx:g}")
    dim(fox, foy, fox, foy + sz * scale, f"{sz:g}", vertical=True)
    tox, toy = origins["top"]
    dim(tox, toy + sy * scale, tox, toy, f"{sy:g}", offset=8.0,
        vertical=True)

    # center marks on the TOP view for z-axis circles
    d_top = views["top"]
    u0, v0 = d_top["u_range"][0], d_top["v_range"][0]
    for c in circles:
        if abs(c["axis"][2]) < 0.95:
            continue
        cu = c["center"][0] - (lo[0] + hi[0]) / 2
        cv = c["center"][1] - (lo[1] + hi[1]) / 2
        mx = tox + (cu - u0) * scale
        my = toy + (cv - v0) * scale
        m = min(max(1.5, c["d"] * scale * 0.18), 5.0)
        ax.plot([mx - m, mx + m], [my, my], color="#b8443c", lw=0.4)
        ax.plot([mx, mx], [my - m, my + m], color="#b8443c", lw=0.4)

    # hole table (top right)
    tx, ty = 300.0, 280.0
    ax.text(tx, ty, "HOLE TABLE (circular rims)", fontsize=7,
            family="monospace", color="#26282b")
    if holes:
        for i, h in enumerate(holes[:14]):
            depth = ("THRU" if h["thru"] else
                     (f"{h['depth']:g} deep" if h["depth"] else "rim"))
            ax.text(tx, ty - 5 - 4.5 * i,
                    f"D{h['d']:g}  at ({h['at'][0]:g}, {h['at'][1]:g}, "
                    f"{h['at'][2]:g})  {depth}",
                    fontsize=6, family="monospace", color="#4a4d52")
    else:
        ax.text(tx, ty - 5, "none detected", fontsize=6,
                family="monospace", color="#7a7d82")

    # title block (bottom right)
    bx, by = 292.0, 10.0
    ax.plot([bx, 412, 412, bx, bx], [by, by, by + 34, by + 34, by],
            color="#26282b", lw=0.8)
    rows = [f"PART   {part_name}",
            f"MODEL  {model_name}",
            f"SIZE   {sx:g} x {sy:g} x {sz:g} mm   SCALE {scale:g}:1",
            f"{mass_note}" if mass_note else "UNITS  mm",
            f"solidsight {tool_version} - third angle, hidden dashed"]
    for i, row in enumerate(r for r in rows if r):
        ax.text(bx + 3, by + 29 - 5.5 * i, row, fontsize=6.5,
                family="monospace", color="#26282b")

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_pdf, format="pdf",
                metadata={"CreationDate": None, "Producer": "solidsight",
                          "Creator": "solidsight"})
    plt.close(fig)
    return {"pdf": str(out_pdf), "holes": holes,
            "circles_found": len(circles), "scale": scale}


def run_drawing(model_path: Path, out_dir: Path,
                only_part: str | None, say) -> int:
    from . import __version__
    from .runner import run_model

    scene = run_model(model_path)
    parts = [p for p in scene.parts if not p.ghost]
    if only_part:
        parts = [p for p in parts if p.name == only_part]
        if not parts:
            say(f"DRAWING FAILED\nno part named {only_part!r}", err=True)
            return 1
    ddir = out_dir / "drawings"
    for p in parts:
        tm = p.solid.to_trimesh()
        mass = f"EST    {round(p.solid.volume * 0.00124, 1)} g PLA"
        info = draw_sheet(p.name, tm, ddir / f"{p.name}.pdf",
                          model_path.name, __version__, mass_note=mass)
        say(f"  drawing: {info['pdf']}  (scale {info['scale']}:1, "
            f"{len(info['holes'])} hole-table rows)")
    return 0
