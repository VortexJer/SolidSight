"""Deterministic UV renders — the evidence for what the report says."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = (247, 247, 245)
INK = (46, 48, 51)
GRID = (222, 222, 217)
FLIP = (183, 62, 62)
STRETCH = (206, 138, 46)
ISLAND = [(92, 108, 124), (94, 122, 106), (140, 112, 132), (120, 118, 92),
          (102, 126, 132), (134, 106, 96), (108, 116, 148), (128, 128, 112)]


def _font(size: int = 12):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _setup(size: int, title: str, subtitle: str):
    img = Image.new("RGB", (size, size + 44), BG)
    d = ImageDraw.Draw(img)
    d.text((10, 8), title, fill=INK, font=_font(13))
    d.text((10, 25), subtitle, fill=(120, 124, 128), font=_font(11))
    top = 44
    for k in range(5):                              # the 0..1 square
        v = top + size * k / 4
        d.line([(0, v), (size, v)], fill=GRID)
        h = size * k / 4
        d.line([(h, top), (h, top + size)], fill=GRID)
    return img, d, top


def _tri_px(uv, size, top):
    return [(float(u) * size, top + (1.0 - float(v)) * size) for u, v in uv]


def render_uv_layout(mesh, uv_root: np.ndarray, path: Path,
                     flipped: list[int], stretched: list[int],
                     size: int = 760) -> None:
    """The UV layout, one colour per island, with the defective faces
    filled in. This is the picture a texture artist looks at — so draw
    it, but draw the FINDINGS on it, not just the wireframe."""
    roots = {r: i for i, r in enumerate(sorted(set(uv_root.tolist())))}
    img, d, top = _setup(
        size, f"{mesh.source} - UV layout",
        f"{len(roots)} island(s), {mesh.n_faces} faces  -  "
        f"red = flipped winding, orange = stretched >2:1")
    fl, st = set(flipped), set(stretched)

    for f in range(mesh.n_faces):
        pts = _tri_px(mesh.uvs[mesh.tri_uv[f]], size, top)
        if f in fl:
            d.polygon(pts, fill=FLIP)
        elif f in st:
            d.polygon(pts, fill=STRETCH)
        c = ISLAND[roots[uv_root[f]] % len(ISLAND)]
        d.line(pts + [pts[0]], fill=c, width=1)

    # label each island with its id (the report's island #N) at its
    # centroid — "scale island #4" is useless if nothing says which
    # blob IS island #4
    for r, i in roots.items():
        faces = [f for f in range(mesh.n_faces) if uv_root[f] == r]
        pts = mesh.uvs[mesh.tri_uv[faces]].reshape(-1, 2)
        cx = float(pts[:, 0].mean()) * size
        cy = top + (1.0 - float(pts[:, 1].mean())) * size
        d.text((cx - 8, cy - 7), f"#{i}", fill=INK, font=_font(13))
    img.save(path)


def render_density_map(mesh, density: np.ndarray, path: Path,
                       size: int = 760) -> None:
    """Texel density painted onto the UV layout: dark = starved,
    light = oversampled. Uneven density is invisible on a model and
    obvious here."""
    finite = density[np.isfinite(density) & (density > 0)]
    if finite.size == 0:
        lo = hi = 1.0
    else:
        lo, hi = float(np.percentile(finite, 2)), float(np.percentile(
            finite, 98))
    if hi - lo < 1e-9:
        hi = lo + 1.0
    img, d, top = _setup(
        size, f"{mesh.source} - texel density",
        f"dark = fewer texels/unit ({lo:.0f})  ->  light = more ({hi:.0f})")

    for f in range(mesh.n_faces):
        v = density[f]
        if not np.isfinite(v):
            col = (200, 60, 60)                  # degenerate: not a shade
        else:
            t = float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))
            g = int(40 + 190 * t)
            col = (g, g, int(40 + 190 * t ** 0.8))
        d.polygon(_tri_px(mesh.uvs[mesh.tri_uv[f]], size, top), fill=col)
    img.save(path)


# --------------------------------------------------------------------------
# 3D evidence renders. A UV layout is unreadable to anyone who has never
# unwrapped a mesh; these two pictures explain it without words: the same
# colour on the 3D surface and on the flat layout ("this square IS this
# face"), and a checker seen THROUGH the UVs (mirrored mark = flipped,
# squashed cells = stretch, cell size = texel density).
# --------------------------------------------------------------------------

_LIGHT = np.array([0.38, 0.82, 0.42])
_LIGHT_DIR = _LIGHT / np.linalg.norm(_LIGHT)


def _iso_transform(verts: np.ndarray, w: int, h: int, margin: int = 26,
                   azim: float = -35.0):
    """Project to a fixed isometric-style view, fitted to (w, h)."""
    a, b = math.radians(azim), math.radians(-26.0)
    ry = np.array([[math.cos(a), 0, math.sin(a)],
                   [0, 1, 0],
                   [-math.sin(a), 0, math.cos(a)]])
    rx = np.array([[1, 0, 0],
                   [0, math.cos(b), -math.sin(b)],
                   [0, math.sin(b), math.cos(b)]])
    p = verts @ (rx @ ry).T
    xy = p[:, :2].copy()
    xy[:, 1] *= -1.0                              # screen y grows down
    lo, hi = xy.min(axis=0), xy.max(axis=0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1], 1e-9))
    s = (min(w, h) - 2 * margin) / span
    off = np.array([(w - s * (hi[0] + lo[0])) / 2,
                    (h - s * (hi[1] + lo[1])) / 2])
    return xy * s + off, -p[:, 2]                  # camera looks down -z


def _face_shade(mesh) -> np.ndarray:
    p = mesh.verts[mesh.tri_v]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    # high ambient: the tint must stay recognisable as ITS island colour
    # on every face, or the correspondence picture stops corresponding
    return 0.74 + 0.26 * np.abs(n @ _LIGHT_DIR)


def _raster(mesh, w: int, h: int, pix2d: np.ndarray, depth: np.ndarray,
            face_rgb: np.ndarray | None = None, checker: bool = False):
    """Z-buffered software rasterizer (numpy per-face, deterministic).
    face_rgb paints flat island colours; checker samples an 8x8 checker
    with an asymmetric L mark through the interpolated UVs."""
    img = np.full((h, w, 3), BG, dtype=np.uint8)
    zbuf = np.full((h, w), -np.inf)
    shade = _face_shade(mesh)
    for f in range(mesh.n_faces):
        tri = pix2d[mesh.tri_v[f]]                       # (3, 2)
        zs = depth[mesh.tri_v[f]]
        x0, y0 = np.floor(tri.min(axis=0)).astype(int)
        x1, y1 = np.ceil(tri.max(axis=0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs = np.arange(x0, x1 + 1) + 0.5
        ys = np.arange(y0, y1 + 1) + 0.5
        gx, gy = np.meshgrid(xs, ys)
        (ax, ay), (bx, by), (cx, cy) = tri
        det = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(det) < 1e-12:
            continue
        w0 = ((bx - gx) * (cy - gy) - (by - gy) * (cx - gx)) / det
        w1 = ((cx - gx) * (ay - gy) - (cy - gy) * (ax - gx)) / det
        w2 = 1.0 - w0 - w1
        mask = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not mask.any():
            continue
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        upd = mask & (z > sub)
        if not upd.any():
            continue
        sub[upd] = z[upd]
        if checker:
            uv = mesh.uvs[mesh.tri_uv[f]]                # (3, 2)
            u = (w0 * uv[0, 0] + w1 * uv[1, 0] + w2 * uv[2, 0]) % 1.0
            v = (w0 * uv[0, 1] + w1 * uv[1, 1] + w2 * uv[2, 1]) % 1.0
            cu, cv = np.floor(u * 8), np.floor(v * 8)
            fu, fv = u * 8 - cu, v * 8 - cv
            base = np.where((cu + cv) % 2 < 1, 212.0, 158.0)
            mark = (((fu > 0.22) & (fu < 0.38) & (fv > 0.2) & (fv < 0.8))
                    | ((fu > 0.22) & (fu < 0.7) & (fv > 0.2) & (fv < 0.36)))
            rgb = np.stack([base, base, base + 8.0], axis=-1)
            rgb[mark] = (74.0, 84.0, 128.0)
            rgb = rgb * shade[f]
        else:
            rgb = np.broadcast_to(
                np.asarray(face_rgb[f], dtype=float) * shade[f],
                upd.shape + (3,)).copy()
        tile = img[y0:y1 + 1, x0:x1 + 1]
        tile[upd] = np.clip(rgb[upd], 0, 255).astype(np.uint8)
        img[y0:y1 + 1, x0:x1 + 1] = tile
    return img


def render_correspondence(mesh, uv_root: np.ndarray, path: Path,
                          size: int = 760) -> None:
    """Left: the 3D mesh with every UV island tinted its own colour.
    Right: the UV square in the SAME colours. This is the picture that
    explains what a UV layout is: same colour = same piece of surface,
    and the flat shapes are the 3D faces peeled onto the texture."""
    roots = {r: i for i, r in enumerate(sorted(set(uv_root.tolist())))}
    img, d, top = _setup(
        size, f"{mesh.source} - which shape is which piece",
        "same colour = same piece of surface: left = the 3D mesh, right = "
        "where each piece lands on the texture (#N = report island ids)")
    face_rgb = np.array([ISLAND[roots[r] % len(ISLAND)] for r in uv_root],
                        dtype=float)
    half = size // 2
    d.rectangle([(0, top), (half - 1, top + size)], fill=BG)
    pix2d, depth = _iso_transform(mesh.verts, half, half)
    left = _raster(mesh, half, half, pix2d, depth, face_rgb=face_rgb)
    img.paste(Image.fromarray(left), (0, top + (size - half) // 2))

    for f in range(mesh.n_faces):
        pts = [(half + float(u) * half, top + (1.0 - float(v)) * half)
               for u, v in mesh.uvs[mesh.tri_uv[f]]]
        c = ISLAND[roots[uv_root[f]] % len(ISLAND)]
        d.polygon(pts, fill=tuple(min(255, int(v * 0.85 + 44)) for v in c))
        d.line(pts + [pts[0]], fill=c, width=1)
    for r, i in roots.items():
        faces = [f for f in range(mesh.n_faces) if uv_root[f] == r]
        pts = mesh.uvs[mesh.tri_uv[faces]].reshape(-1, 2)
        cx = half + float(pts[:, 0].mean()) * half
        cy = top + (1.0 - float(pts[:, 1].mean())) * half
        d.text((cx - 8, cy - 7), f"#{i}", fill=(30, 30, 34),
               font=_font(12))
    d.line([(half, top), (half, top + size)], fill=GRID, width=2)
    img.save(path)


def render_checker_preview(mesh, path: Path, size: int = 760) -> None:
    """The mesh with a checker applied through its UVs, front AND back
    view (one viewpoint hides half the surface — and half the defects).
    A mirrored L mark = flipped face, squashed cells = stretch,
    bigger/smaller cells = texel density."""
    half = size // 2
    h = int(half * 0.94)
    canvas = Image.new("RGB", (size, h + 62), BG)
    d = ImageDraw.Draw(canvas)
    d.text((10, 8), f"{mesh.source} - checker through the UVs "
           "(front / back)", fill=INK, font=_font(13))
    d.text((10, 25), "every cell holds an L mark: a MIRRORED L (rotated is "
           "fine) = flipped face, squashed cells = stretch, cell size = "
           "texel density", fill=(120, 124, 128), font=_font(11))
    for i, azim in enumerate((-35.0, 145.0)):
        pix2d, depth = _iso_transform(mesh.verts, half, h, azim=azim)
        panel = _raster(mesh, half, h, pix2d, depth, checker=True)
        canvas.paste(Image.fromarray(panel), (i * half, 44))
        d.text((i * half + 8, 46), "front" if i == 0 else "back",
               fill=(120, 124, 128), font=_font(11))
    d.line([(half, 44), (half, 44 + h)], fill=GRID, width=2)
    canvas.save(path)
