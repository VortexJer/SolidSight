"""Deterministic software renderer: PNG images an agent can actually read.

No GPU, no OpenGL, no external renderer — a numpy z-buffer rasterizer with:
- orthographic named views (iso/front/right/top/back/left/bottom) + turntable
- one muted color per named part + an on-image legend
- sharp-edge and silhouette overlays so geometry reads clearly
- a 10 mm ground grid, an XYZ triad, bounding-box dimensions and a scale bar
- cross-section (--slice) images for inspecting internal walls

Every pixel is a pure function of the input geometry: identical runs produce
identical PNG bytes.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .errors import BadArgumentError, fmt_num
from .scene import Scene

BG = (242, 242, 239)
GRID = (216, 216, 211)
GRID_MAJOR = (198, 198, 192)
INK = (58, 58, 55)
INK_SOFT = (120, 120, 115)
AXIS_COLORS = {"X": (167, 88, 88), "Y": (100, 143, 88), "Z": (88, 116, 116 + 44)}

VIEWS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    # name: (camera direction FROM scene TO camera, up hint)
    "iso":    ((1, -1, 0.9), (0, 0, 1)),
    "iso_back": ((-1, 1, 0.9), (0, 0, 1)),
    "front":  ((0, -1, 0), (0, 0, 1)),
    "back":   ((0, 1, 0), (0, 0, 1)),
    "right":  ((1, 0, 0), (0, 0, 1)),
    "left":   ((-1, 0, 0), (0, 0, 1)),
    "top":    ((0, 0, 1), (0, 1, 0)),
    "bottom": ((0, 0, -1), (0, -1, 0)),
}


def _font(size: int) -> ImageFont.FreeTypeFont:
    from matplotlib import font_manager
    path = font_manager.findfont("DejaVu Sans Mono")
    return ImageFont.truetype(path, size)


def _hex_rgb(hexcolor: str) -> np.ndarray:
    return np.array([int(hexcolor[i:i + 2], 16) for i in (1, 3, 5)], float)


class _Camera:
    def __init__(self, direction, up, center, radius, size_px, margin=70):
        d = np.asarray(direction, float)
        self.dir = d / np.linalg.norm(d)          # scene -> camera
        f = -self.dir                              # camera forward
        u = np.asarray(up, float)
        r = np.cross(f, u)
        if np.linalg.norm(r) < 1e-9:
            r = np.cross(f, np.array([0.0, 1.0, 0.0]))
        self.right = r / np.linalg.norm(r)
        self.up = np.cross(self.right, f)
        self.f = f
        self.center = np.asarray(center, float)
        self.size = size_px
        self.scale = (size_px - 2 * margin) / (2 * radius) if radius > 0 else 1.0

    def project(self, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """world (n,3) -> (pixel (n,2), depth (n,)) — smaller depth = closer."""
        rel = pts - self.center
        x = rel @ self.right
        y = rel @ self.up
        depth = rel @ self.f
        px = self.size / 2 + x * self.scale
        py = self.size / 2 - y * self.scale
        return np.stack([px, py], axis=1), depth


def render_view(scene: Scene, view: str | tuple, size: int = 900,
                title: str = "", subtitle: str = "",
                focus: tuple | None = None) -> Image.Image:
    """focus=(cx, cy, cz, r): zoom the camera onto a sphere of radius r
    around a point instead of framing the whole scene — for inspecting a
    single feature on a large part."""
    meshes = []
    for part in scene.parts:
        # 0.05 mm simplification: invisible at render scale, big speedup on
        # threads and Minkowski fillets
        from .geom import Solid as _S
        tm = _S(part.solid.manifold.simplify(0.05)).to_trimesh()
        meshes.append((part.name, tm, _hex_rgb(part.color),
                       getattr(part, "ghost", False)))

    all_pts = np.vstack([m.vertices for _, m, _, _ in meshes])
    lo, hi = all_pts.min(axis=0), all_pts.max(axis=0)
    if focus is not None:
        center = np.asarray(focus[:3], float)
        radius = max(float(focus[3]), 0.1)
        subtitle = (subtitle + " · " if subtitle else "") + \
            f"focus ({fmt_num(focus[0])}, {fmt_num(focus[1])}, " \
            f"{fmt_num(focus[2])}) r{fmt_num(focus[3])}"
    else:
        center = (lo + hi) / 2
        radius = float(np.linalg.norm(hi - lo)) / 2 or 1.0

    if isinstance(view, str):
        if view not in VIEWS:
            raise BadArgumentError(
                f"unknown view {view!r}",
                suggestion="valid views: " + ", ".join(VIEWS))
        direction, up = VIEWS[view]
        view_name = view
    else:
        direction, up = view
        view_name = "turntable"

    cam = _Camera(direction, up, center, radius, size)
    if focus is None:
        # The frame was sized on the bounding box's 3D DIAGONAL — a length
        # only ever visible looking straight down one corner, so every
        # other view sat needlessly far away (worst on a turntable, where
        # nothing is ever seen from that corner). Measure what this camera
        # actually projects and fit that instead. Nothing can clip: the
        # extent is taken from the same points that get drawn.
        rel = all_pts - center
        radius = max(float(np.abs(rel @ cam.right).max()),
                     float(np.abs(rel @ cam.up).max())) or 1.0
        cam = _Camera(direction, up, center, radius, size)

    color = np.tile(np.array(BG, float), (size, size, 1))
    zbuf = np.full((size, size), np.inf)
    # who wrote each pixel, in draw order. A z-buffer with a strict `<`
    # test means "nearest wins, and on an exact tie the earlier draw wins";
    # keeping the writer's index lets the fast path below honour that
    # second half without having to draw in order.
    zidx = np.full((size, size), -1, dtype=np.int64)

    _draw_grid(color, zbuf, cam, lo, hi)
    base = 0
    for name, tm, rgb, ghost in meshes:
        if not ghost:
            base = _rasterize(color, zbuf, cam, tm, rgb, zidx, base)
    for name, tm, rgb, ghost in meshes:
        # ghosts: X-ray outline only — edges drawn without occlusion so the
        # reference volume reads through the solid parts
        _draw_edges(color, zbuf, cam, tm, rgb, xray=ghost)

    img = Image.fromarray(color.clip(0, 255).astype(np.uint8), "RGB")
    _annotate(img, scene, cam, view_name, lo, hi, title, subtitle)
    return img


# --------------------------------------------------------------------------

# Triangles go through the vectorised path in bands: each one lands in the
# smallest window it fits in, so a 3x3 triangle is not padded out to 32x32.
# Anything bigger than the last band keeps the per-triangle loop — on a real
# mesh that is a couple of percent of them.
BANDS = (2, 4, 8, 16, 32)
BAND_CELLS = 2_000_000      # candidate pixels per batch — bounds memory


def _rasterize(color: np.ndarray, zbuf: np.ndarray, cam: _Camera, tm,
               rgb: np.ndarray, zidx: np.ndarray | None = None,
               base: int = 0) -> int:
    size = cam.size
    # Gouraud shading with creases: split vertices at sharp edges so curved
    # surfaces shade smoothly while flat faces and box edges stay crisp
    verts, faces, vnormals = _crease_split(tm, math.radians(30))
    pix, depth = cam.project(verts)

    key = np.array([0.35, -0.5, 0.79])
    key /= np.linalg.norm(key)
    vshade = np.clip(0.30
                     + 0.42 * np.clip(vnormals @ key, 0, 1)
                     + 0.28 * np.clip(vnormals @ cam.dir, 0, 1), 0.18, 1.0)

    tri_pix = pix[faces]            # (t,3,2)
    tri_z = depth[faces]            # (t,3)
    tri_s = vshade[faces]           # (t,3)

    # Screen box and degeneracy for EVERY triangle in one numpy pass. The
    # loop below used to work these out one triangle at a time — eight numpy
    # round-trips each, on meshes where most triangles cover less than a
    # single pixel, and that was 94% of a render. Same formulas in the same
    # order, so the same triangles are drawn with the same arithmetic.
    px, py = tri_pix[:, :, 0], tri_pix[:, :, 1]
    bx0 = np.maximum(np.floor(px.min(axis=1)), 0).astype(np.intp)
    bx1 = np.minimum(np.ceil(px.max(axis=1)), size - 1).astype(np.intp)
    by0 = np.maximum(np.floor(py.min(axis=1)), 0).astype(np.intp)
    by1 = np.minimum(np.ceil(py.max(axis=1)), size - 1).astype(np.intp)
    den = ((tri_pix[:, 1, 1] - tri_pix[:, 2, 1])
           * (tri_pix[:, 0, 0] - tri_pix[:, 2, 0])
           + (tri_pix[:, 2, 0] - tri_pix[:, 1, 0])
           * (tri_pix[:, 0, 1] - tri_pix[:, 2, 1]))
    drawable = ((bx0 <= bx1) & (by0 <= by1) & (np.abs(den) >= 1e-12)
                & np.isfinite(px).all(axis=1) & np.isfinite(py).all(axis=1))

    # Back faces cannot win a pixel. Every mesh here comes out of manifold3d,
    # so it is closed: along any ray the nearest surface is the one you enter
    # through, which is front-facing. Drawing the far half of every solid and
    # then letting the z-test throw it away is half the work of a render.
    tv = verts[faces]
    fn = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
    drawable &= (fn @ cam.dir) > 0

    # draw far-to-near so equal-depth overwrites are deterministic
    order = np.argsort(-tri_z.mean(axis=1), kind="stable")
    order = order[drawable[order]]
    if zidx is None:                     # standalone use: no fast path
        zidx = np.full_like(zbuf, -1, dtype=np.int64)

    # rank in draw order, per triangle — the tie-breaker the fast path needs
    rank = np.empty(len(tri_z), dtype=np.int64)
    rank[order] = base + np.arange(len(order))

    # A triangle covering one or two pixels per axis costs the same trip
    # through this loop as one covering half the frame, and on a real mesh
    # almost all of them are the former. Those go through _small_batch,
    # which does the identical arithmetic for a quarter-million triangles
    # at a time. Everything else keeps the loop.
    side = np.maximum(bx1 - bx0, by1 - by0) + 1
    band_of = np.full(len(side), -1, dtype=np.int64)
    for bi, k in enumerate(BANDS):
        band_of[(band_of < 0) & (side <= k)] = bi
    big_order = order[band_of[order] < 0]

    for ti in big_order:
        p = tri_pix[ti]
        z = tri_z[ti]
        s = tri_s[ti]
        xmin, xmax = int(bx0[ti]), int(bx1[ti])
        ymin, ymax = int(by0[ti]), int(by1[ti])
        # broadcasting instead of meshgrid: two allocations per triangle
        # fewer, and _bary combines both axes so the values are identical
        xs = (np.arange(xmin, xmax + 1) + 0.5)[None, :]
        ys = (np.arange(ymin, ymax + 1) + 0.5)[:, None]
        d = _bary(p, xs, ys)
        if d is None:
            continue
        w0, w1, w2 = d
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        zi = w0 * z[0] + w1 * z[1] + w2 * z[2]
        sub_z = zbuf[ymin:ymax + 1, xmin:xmax + 1]
        upd = inside & (zi < sub_z)
        if not upd.any():
            continue
        sub_z[upd] = zi[upd]
        zidx[ymin:ymax + 1, xmin:xmax + 1][upd] = rank[ti]
        si = (w0 * s[0] + w1 * s[1] + w2 * s[2])[upd]
        color[ymin:ymax + 1, xmin:xmax + 1][upd] = rgb[None, :] * si[:, None]

    for bi, k in enumerate(BANDS):
        sel = order[band_of[order] == bi]
        step = max(1, BAND_CELLS // (k * k))
        for i in range(0, len(sel), step):
            _small_batch(color, zbuf, zidx, rgb, sel[i:i + step], tri_pix,
                         tri_z, tri_s, den, bx0, bx1, by0, by1, rank, size, k)
    return base + len(order)


def _small_batch(color, zbuf, zidx, rgb, idx, tri_pix, tri_z, tri_s, den,
                 bx0, bx1, by0, by1, rank, size, k) -> None:
    """The loop body above, done for a whole batch of triangles at once.

    Identical arithmetic in the identical order, so the pixels are the
    same. What replaces the sequential z-test is its definition: a strict
    `<` against a running minimum means the winner of a pixel is the
    nearest fragment, and on an exact tie the one drawn earlier — which is
    a lexicographic minimum of (depth, draw index), and that does not care
    what order the fragments are computed in.
    """
    if not len(idx):
        return
    p = tri_pix[idx]                              # (n,3,2)
    x0, y0 = p[:, 0, 0], p[:, 0, 1]
    x1, y1 = p[:, 1, 0], p[:, 1, 1]
    x2, y2 = p[:, 2, 0], p[:, 2, 1]
    d = den[idx]

    # up to k^2 candidate pixels each, masked back to the real box
    off = np.arange(k)
    cx = bx0[idx][:, None, None] + off[None, None, :]
    cy = by0[idx][:, None, None] + off[None, :, None]
    valid = (cx <= bx1[idx][:, None, None]) & (cy <= by1[idx][:, None, None])
    gx = cx + 0.5
    gy = cy + 0.5

    a = (y1 - y2)[:, None, None]
    b = (x2 - x1)[:, None, None]
    c = (y2 - y0)[:, None, None]
    e = (x0 - x2)[:, None, None]
    w0 = (a * (gx - x2[:, None, None]) + b * (gy - y2[:, None, None])) \
        / d[:, None, None]
    w1 = (c * (gx - x2[:, None, None]) + e * (gy - y2[:, None, None])) \
        / d[:, None, None]
    w2 = 1.0 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0) & valid
    if not inside.any():
        return

    z = tri_z[idx]
    s = tri_s[idx]
    zi = (w0 * z[:, 0, None, None] + w1 * z[:, 1, None, None]
          + w2 * z[:, 2, None, None])[inside]
    si = (w0 * s[:, 0, None, None] + w1 * s[:, 1, None, None]
          + w2 * s[:, 2, None, None])[inside]
    flat = (cy * size + cx)[inside]
    gid = np.broadcast_to(rank[idx][:, None, None], inside.shape)[inside]

    # one winner per pixel: nearest, earlier draw breaks a tie
    keep = np.lexsort((gid, zi, flat))
    flat, zi, si, gid = flat[keep], zi[keep], si[keep], gid[keep]
    first = np.ones(len(flat), dtype=bool)
    first[1:] = flat[1:] != flat[:-1]
    flat, zi, si, gid = flat[first], zi[first], si[first], gid[first]

    zb = zbuf.reshape(-1)[flat]
    zx = zidx.reshape(-1)[flat]
    win = (zi < zb) | ((zi == zb) & (gid < zx))
    flat, zi, si = flat[win], zi[win], si[win]
    zbuf.reshape(-1)[flat] = zi
    zidx.reshape(-1)[flat] = gid[win]
    color.reshape(-1, 3)[flat] = rgb[None, :] * si[:, None]


def _sound_faces(tm, min_altitude: float = 5e-3) -> np.ndarray:
    """True per face when the triangle is geometrically sound: its smallest
    altitude (2*area / longest edge) exceeds min_altitude mm. Boolean ops
    triangulate faces with complex outlines into long slivers, and rim ops
    add sub-micron z-noise; a sliver's normal then tilts arbitrarily, so
    nothing about creases or silhouettes may be concluded from it."""
    tri = np.asarray(tm.triangles, float)
    e0 = tri[:, 1] - tri[:, 0]
    e1 = tri[:, 2] - tri[:, 1]
    e2 = tri[:, 0] - tri[:, 2]
    lmax = np.sqrt(np.maximum.reduce([(e0 ** 2).sum(1), (e1 ** 2).sum(1),
                                      (e2 ** 2).sum(1)]))
    area2 = np.linalg.norm(np.cross(e0, -e2), axis=1)
    return area2 / np.maximum(lmax, 1e-12) > min_altitude


def _crease_split(tm, crease_angle: float):
    """Duplicate vertices along sharp edges so per-vertex normals never
    average across a crease. Faces are grouped into smoothing regions
    (union-find over adjacency with dihedral < crease_angle); each vertex
    gets one copy per region, with an area-weighted normal from that region
    only. Flat faces therefore shade perfectly flat. Deterministic."""
    faces = np.asarray(tm.faces)
    verts = np.asarray(tm.vertices, float)
    fnormals = np.asarray(tm.face_normals, float)
    areas = np.asarray(tm.area_faces, float)
    n_faces = len(faces)
    if n_faces == 0:
        return verts, faces, np.zeros_like(verts)

    parent = np.arange(n_faces)

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    adj = np.asarray(tm.face_adjacency)
    if len(adj):
        smooth = np.asarray(tm.face_adjacency_angles) < crease_angle
        # dihedral angles measured against slivers are noise: force-smooth
        # those edges so slivers join their flat neighbours' group instead
        # of fracturing the shading
        ok = _sound_faces(tm)
        smooth |= ~(ok[adj[:, 0]] & ok[adj[:, 1]])
        for (a, b) in adj[smooth]:
            ra, rb = find(int(a)), find(int(b))
            if ra != rb:
                parent[ra] = rb
    group = np.fromiter((find(i) for i in range(n_faces)), dtype=np.int64,
                        count=n_faces)

    # one output vertex per unique (original vertex, smoothing group)
    keys = faces.astype(np.int64) * (group.max() + 1) + group[:, None]
    uniq, new_idx = np.unique(keys.ravel(), return_inverse=True)
    new_faces = new_idx.reshape(-1, 3)
    orig_v = (uniq // (group.max() + 1)).astype(np.int64)
    new_verts = verts[orig_v]

    new_normals = np.zeros((len(uniq), 3))
    w = fnormals * areas[:, None]                    # (F,3)
    for corner in range(3):
        np.add.at(new_normals, new_faces[:, corner], w)
    lens = np.linalg.norm(new_normals, axis=1, keepdims=True)
    new_normals /= np.maximum(lens, 1e-12)
    return new_verts, new_faces, new_normals


def _bary(p: np.ndarray, gx: np.ndarray, gy: np.ndarray):
    x0, y0 = p[0]
    x1, y1 = p[1]
    x2, y2 = p[2]
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) < 1e-12:
        return None
    w0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / den
    w1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / den
    w2 = 1.0 - w0 - w1
    return w0, w1, w2


def _draw_edges(color: np.ndarray, zbuf: np.ndarray, cam: _Camera, tm,
                rgb: np.ndarray, xray: bool = False) -> None:
    verts = np.asarray(tm.vertices, float)
    normals = np.asarray(tm.face_normals, float)
    adj = tm.face_adjacency
    if len(adj) == 0:
        return
    angles = tm.face_adjacency_angles
    edges = tm.face_adjacency_edges

    facing = normals @ cam.dir > 0
    silhouette = facing[adj[:, 0]] != facing[adj[:, 1]]
    sharp = angles > math.radians(28)
    # an edge is only trusted when both its faces are sound (see
    # _sound_faces): sliver normals fake both creases and silhouettes
    ok = _sound_faces(tm)
    keep = (silhouette | sharp) & ok[adj[:, 0]] & ok[adj[:, 1]]

    edge_rgb = (rgb * 0.42).clip(0, 255)
    sil_rgb = (rgb * 0.28).clip(0, 255)
    pix, depth = cam.project(verts)
    for ei in np.nonzero(keep)[0]:
        a, b = edges[ei]
        c = sil_rgb if silhouette[ei] else edge_rgb
        if xray:
            _line(color, zbuf, pix[a], depth[a], pix[b], depth[b],
                  rgb, bias=1e9)      # always visible, never occludes
        else:
            _line(color, zbuf, pix[a], depth[a], pix[b], depth[b], c)


def _line(color: np.ndarray, zbuf: np.ndarray, p0, z0, p1, z1,
          rgb: np.ndarray, bias: float = 0.35) -> None:
    size = color.shape[0]
    length = float(np.hypot(*(p1 - p0)))
    n = max(2, int(length * 2))
    ts = np.linspace(0, 1, n)
    xs = (p0[0] + (p1[0] - p0[0]) * ts).round().astype(int)
    ys = (p0[1] + (p1[1] - p0[1]) * ts).round().astype(int)
    zs = z0 + (z1 - z0) * ts - bias
    ok = (xs >= 0) & (xs < size) & (ys >= 0) & (ys < size)
    xs, ys, zs = xs[ok], ys[ok], zs[ok]
    vis = zs <= zbuf[ys, xs] + 1e-6
    color[ys[vis], xs[vis]] = rgb


def _draw_grid(color: np.ndarray, zbuf: np.ndarray, cam: _Camera,
               lo: np.ndarray, hi: np.ndarray) -> None:
    if cam.dir[2] <= 1e-6 and abs(cam.dir[0]) + abs(cam.dir[1]) > 0:
        pass  # side views still get the grid line at z=0
    pad = 10.0
    x0 = math.floor((lo[0] - pad) / 10) * 10
    x1 = math.ceil((hi[0] + pad) / 10) * 10
    y0 = math.floor((lo[1] - pad) / 10) * 10
    y1 = math.ceil((hi[1] + pad) / 10) * 10
    z = 0.0
    for gx in np.arange(x0, x1 + 1, 10.0):
        c = GRID_MAJOR if gx % 50 == 0 else GRID
        a, da = cam.project(np.array([[gx, y0, z]]))
        b, db = cam.project(np.array([[gx, y1, z]]))
        _line(color, zbuf, a[0], da[0], b[0], db[0], np.array(c, float),
              bias=-0.5)
    for gy in np.arange(y0, y1 + 1, 10.0):
        c = GRID_MAJOR if gy % 50 == 0 else GRID
        a, da = cam.project(np.array([[x0, gy, z]]))
        b, db = cam.project(np.array([[x1, gy, z]]))
        _line(color, zbuf, a[0], da[0], b[0], db[0], np.array(c, float),
              bias=-0.5)


# --------------------------------------------------------------------------

def _annotate(img: Image.Image, scene: Scene, cam: _Camera, view_name: str,
              lo, hi, title: str, subtitle: str) -> None:
    draw = ImageDraw.Draw(img)
    size = img.width
    f_big = _font(15)
    f_small = _font(12)

    # header
    draw.text((18, 14), (title or "MODEL").upper(), fill=INK, font=f_big)
    head2 = f"{view_name.upper()}  ·  {subtitle.upper()}" if subtitle else view_name.upper()
    draw.text((18, 36), head2, fill=INK_SOFT, font=f_small)

    # dimensions footer
    dims = (f"X {fmt_num(hi[0] - lo[0])}   Y {fmt_num(hi[1] - lo[1])}   "
            f"Z {fmt_num(hi[2] - lo[2])}   MM")
    draw.text((18, size - 30), dims, fill=INK, font=f_small)

    # scale bar (nice round length close to 90 px)
    target_mm = 90 / cam.scale
    nice = _nice(target_mm)
    bar = nice * cam.scale
    x1 = size - 24
    x0 = x1 - bar
    y = size - 26
    draw.line([(x0, y), (x1, y)], fill=INK, width=2)
    draw.line([(x0, y - 4), (x0, y + 4)], fill=INK, width=2)
    draw.line([(x1, y - 4), (x1, y + 4)], fill=INK, width=2)
    label = f"{fmt_num(nice)} MM"
    tw = draw.textlength(label, font=f_small)
    draw.text((x1 - tw, y - 20), label, fill=INK, font=f_small)

    # part legend
    ly = 64
    for part in scene.parts[:10]:
        draw.rectangle([18, ly, 30, ly + 12], fill=part.color, outline=None)
        label = part.name.upper()
        if getattr(part, "ghost", False):
            label += " (GHOST)"
        draw.text((38, ly - 1), label, fill=INK_SOFT, font=f_small)
        ly += 20
    if len(scene.parts) > 10:
        draw.text((18, ly), f"+{len(scene.parts) - 10} MORE",
                  fill=INK_SOFT, font=f_small)

    # axis triad, bottom-left above the dims line
    origin = np.array([46.0, size - 72.0])
    L = 26.0
    for label2, vec in (("X", [1, 0, 0]), ("Y", [0, 1, 0]), ("Z", [0, 0, 1])):
        v = np.asarray(vec, float)
        d = np.array([v @ cam.right, -(v @ cam.up)])
        norm = np.linalg.norm(d)
        if norm < 0.12:
            continue
        end = origin + d / max(norm, 1e-9) * L * min(1.0, norm * 1.6)
        draw.line([tuple(origin), tuple(end)], fill=AXIS_COLORS[label2], width=2)
        draw.text(tuple(end + d / max(norm, 1e-9) * 8 - 4),
                  label2, fill=AXIS_COLORS[label2], font=f_small)


def _nice(x: float) -> float:
    if x <= 0:
        return 1.0
    exp = math.floor(math.log10(x))
    frac = x / 10 ** exp
    for n in (1, 2, 5, 10):
        if frac <= n:
            return n * 10 ** exp
    return 10 ** (exp + 1)


# --------------------------------------------------------------------------
# cross-sections
# --------------------------------------------------------------------------

def render_slice(scene: Scene, axis: str, value: float, size: int = 900,
                 title: str = "") -> Image.Image:
    """Filled 2D cross-section of the whole scene at axis=value."""
    if axis not in ("x", "y", "z"):
        raise BadArgumentError(f"slice axis must be x, y or z, got {axis!r}")

    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)

    polys_by_part = []
    for part in scene.parts:
        m = part.solid.manifold
        if axis == "z":
            cs = m.slice(float(value))
        elif axis == "x":
            # rotate +X onto +Z: rotate -90 about Y maps (x,y,z)->(-z,y,x)
            cs = m.rotate([0, -90, 0]).slice(float(value))
        else:
            # rotate +Y onto +Z: rotate +90 about X maps (x,y,z)->(x,-z,y)
            cs = m.rotate([90, 0, 0]).slice(float(value))
        polys = cs.to_polygons()
        if polys:
            polys_by_part.append((part, [np.asarray(p, float) for p in polys]))

    if not polys_by_part:
        draw.text((18, 14), (title or "MODEL").upper(), fill=INK, font=_font(15))
        draw.text((18, 36),
                  f"SLICE {axis.upper()} = {fmt_num(value)} MM — EMPTY "
                  f"(nothing intersects this plane)",
                  fill=INK_SOFT, font=_font(12))
        return img

    all_pts = np.vstack([np.vstack(polys) for _, polys in polys_by_part])
    lo2, hi2 = all_pts.min(axis=0), all_pts.max(axis=0)
    c = (lo2 + hi2) / 2
    extent = max(hi2[0] - lo2[0], hi2[1] - lo2[1]) or 1.0
    scale = (size - 160) / extent

    def to_px(pts: np.ndarray) -> list[tuple[float, float]]:
        return [(size / 2 + (x - c[0]) * scale, size / 2 - (y - c[1]) * scale)
                for x, y in pts]

    for part, polys in polys_by_part:
        # even-odd fill across contours (holes stay holes): XOR-accumulate
        mask_np = np.zeros((size, size), bool)
        for poly in polys:
            tmp = Image.new("1", (size, size), 0)
            ImageDraw.Draw(tmp).polygon(to_px(poly), fill=1)
            mask_np ^= np.array(tmp, bool)
        mask = Image.fromarray((mask_np * 255).astype(np.uint8), "L")
        img.paste(part.color, (0, 0), mask)
        outline = tuple(int(v) for v in _hex_rgb(part.color) * 0.4)
        for poly in polys:
            ImageDraw.Draw(img).line(to_px(np.vstack([poly, poly[:1]])),
                                     fill=outline, width=2)

    f_big = _font(15)
    f_small = _font(12)
    draw = ImageDraw.Draw(img)
    draw.text((18, 14), (title or "MODEL").upper(), fill=INK, font=f_big)
    plane_axes = {"z": ("X", "Y"), "x": ("-Z", "Y"), "y": ("X", "-Z")}[axis]
    draw.text((18, 36),
              f"SLICE {axis.upper()} = {fmt_num(value)} MM   ·   PLANE "
              f"{plane_axes[0]}/{plane_axes[1]}   ·   FILLED = MATERIAL",
              fill=INK_SOFT, font=f_small)
    dims = (f"{plane_axes[0]} {fmt_num(hi2[0] - lo2[0])}   "
            f"{plane_axes[1]} {fmt_num(hi2[1] - lo2[1])}   MM")
    draw.text((18, size - 30), dims, fill=INK, font=f_small)
    return img


def turntable_views(n: int) -> list[tuple[tuple[float, float, float],
                                          tuple[float, float, float]]]:
    out = []
    for i in range(n):
        az = math.radians(360.0 * i / n + 30)
        el = math.radians(28)
        out.append(((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az),
                     math.sin(el)), (0, 0, 1)))
    return out
