"""solidsight.vision — deterministic image -> geometry.

The agent has eyes (it can look at a photo or a drawing); the geometry
kernel does not. These helpers convert the parts of an image that ARE
geometry — silhouettes, logos, gaskets, stencils, reliefs — into exact
sketches and solids, deterministically. The judgment stays with the
agent: real-world size, which contours matter, and whether the traced
shape actually matches the photo (build, render, compare side by side).

Both functions resolve relative paths against the model file that calls
them, like from_stl() does.
"""

from __future__ import annotations

import numpy as np

from .errors import BadArgumentError, EmptyGeometryError
from .geom import Sketch, Solid, _warn

__all__ = ["image_outline", "image_heightfield", "comparison_sheet"]

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif",
             ".tiff")


def _load_gray(path: str) -> tuple[np.ndarray, str]:
    """Load an image as a float64 grayscale array in [0, 1]."""
    from PIL import Image

    from .assembly import _resolve

    p = _resolve(path)
    if not p.exists():
        raise BadArgumentError(
            f"image file not found: {p}",
            suggestion="check the path (relative paths resolve against "
                       "the model file)")
    if p.suffix.lower() not in _IMG_EXTS:
        raise BadArgumentError(
            f"{p.name} does not look like an image "
            f"(expected one of {', '.join(_IMG_EXTS)})",
            suggestion="for meshes use from_mesh(); for images convert "
                       "to PNG first")
    try:
        with Image.open(p) as im:
            gray = im.convert("L")
            arr = np.asarray(gray, dtype=np.float64) / 255.0
    except Exception as e:  # pillow raises many types
        raise BadArgumentError(f"could not read {p.name}: {e}",
                               suggestion="re-save the image as PNG") from e
    if arr.size == 0:
        raise BadArgumentError(f"{p.name} is an empty image")
    return arr, p.name


def _rdp(points: np.ndarray, eps: float) -> np.ndarray:
    """Ramer-Douglas-Peucker polyline simplification (iterative)."""
    n = len(points)
    if n < 3 or eps <= 0:
        return points
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        seg = points[b] - points[a]
        length = np.hypot(*seg)
        rel = points[a + 1:b] - points[a]
        if length == 0.0:
            d = np.hypot(rel[:, 0], rel[:, 1])
        else:  # 2D cross product magnitude (numpy 2.x dropped 2D cross)
            d = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / length
        i = int(np.argmax(d))
        if d[i] > eps:
            keep[a + 1 + i] = True
            stack.append((a, a + 1 + i))
            stack.append((a + 1 + i, b))
    return points[keep]


def _ring_area(ring: np.ndarray) -> float:
    """Absolute shoelace area of a closed ring (no repeated endpoint)."""
    x, y = ring[:, 0], ring[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2.0


def image_outline(path: str, width: float | None = None,
                  height: float | None = None, threshold: float = 0.5,
                  invert: bool = False, simplify: float = 0.4,
                  min_area: float | None = None) -> Sketch:
    """Trace the dark shapes of an image into an exact 2D sketch.

    Dark pixels are material (ink on paper); pass invert=True for
    light-on-dark images. Give the real size with exactly one of
    width= or height= (mm) — the other follows the image aspect ratio.
    Holes (letter counters, gasket bores) are preserved via even-odd
    fill. The result is centered at the origin; extrude() it, or use it
    as an engraving cutter.

    simplify (mm) is the max deviation allowed when straightening the
    traced outline; min_area (mm^2, default (3*simplify)^2) drops
    specks and scanner noise.
    """
    from contourpy import contour_generator
    from manifold3d import CrossSection, FillRule

    arr, name = _load_gray(path)
    if (width is None) == (height is None):
        raise BadArgumentError(
            "image_outline() needs the real size: pass exactly one of "
            "width= or height= (mm)",
            suggestion="estimate the object's true size from the photo "
                       "and pass it, e.g. image_outline('logo.png', "
                       "width=60)")
    if not 0.0 < threshold < 1.0:
        raise BadArgumentError(
            f"threshold must be between 0 and 1, got {threshold}")

    # material = 1.0 field; pad with one background pixel all around so
    # shapes touching the border still produce closed rings
    field = (1.0 - arr) if not invert else arr
    field = np.pad(field, 1, constant_values=0.0)

    h_px, w_px = arr.shape
    scale = (width / w_px) if width is not None else (height / h_px)

    rings_px = contour_generator(z=field).lines(threshold)
    rings_mm: list[np.ndarray] = []
    dropped = 0
    default_min_area = (3.0 * simplify) ** 2 if simplify > 0 else 1.0
    area_floor = default_min_area if min_area is None else float(min_area)
    for ring in rings_px:
        pts = np.asarray(ring, dtype=np.float64)
        if len(pts) < 4 or not np.allclose(pts[0], pts[-1]):
            continue  # open fragment: cannot bound material
        # (x=col, y=row) -> mm, image up = +y, minus the 1px pad
        xy = np.column_stack(((pts[:, 0] - 1.0) * scale,
                              (h_px - 1.0 - (pts[:, 1] - 1.0)) * scale))
        xy = _rdp(xy[:-1], eps=simplify) if simplify > 0 else xy[:-1]
        if len(xy) < 3:
            dropped += 1
            continue
        if _ring_area(xy) < area_floor:
            dropped += 1
            continue
        rings_mm.append(xy)

    if not rings_mm:
        raise EmptyGeometryError(
            f"image_outline({name}): no contours found at "
            f"threshold={threshold}" + (" (invert=True)" if invert else ""),
            suggestion="if the image is light-on-dark pass invert=True; "
                       "otherwise adjust threshold (lower = stricter "
                       "about what counts as dark)")
    if dropped:
        _warn("image-specks-dropped",
              f"image_outline({name}): dropped {dropped} contour(s) "
              f"smaller than {area_floor:.2f} mm2 (noise/specks)",
              suggestion="pass min_area=0 to keep everything, or a "
                         "larger min_area to drop more")

    # center the sketch at the origin (predictable placement)
    allpts = np.vstack(rings_mm)
    cx = (allpts[:, 0].min() + allpts[:, 0].max()) / 2.0
    cy = (allpts[:, 1].min() + allpts[:, 1].max()) / 2.0
    contours = [[(float(x - cx), float(y - cy)) for x, y in ring]
                for ring in rings_mm]
    cs = CrossSection(contours, FillRule.EvenOdd)
    if cs.is_empty():
        raise EmptyGeometryError(
            f"image_outline({name}): traced contours enclose no area",
            suggestion="check threshold/invert; try simplify=0")
    return Sketch(cs, f"image_outline({name}, {len(contours)} contours)")


def comparison_sheet(ref_path, render_path, out_path,
                     panel_h: int = 700) -> None:
    """Compose the user's reference image and a render side by side into
    one PNG (used by `build --ref`). The sheet exists to be LOOKED at:
    same height panels, labels burned in, reference always on the left."""
    from PIL import Image, ImageDraw, ImageFont

    def _panel(src, label):
        with Image.open(src) as im:
            im = im.convert("RGB")
            w = max(1, round(im.width * panel_h / im.height))
            im = im.resize((w, panel_h), Image.LANCZOS)
        return im, label

    left, right = _panel(ref_path, "REFERENCE (input image)"), \
        _panel(render_path, "MODEL (solidsight render)")
    pad, band = 12, 34
    sheet = Image.new("RGB", (left[0].width + right[0].width + 3 * pad,
                              panel_h + band + 2 * pad), (248, 248, 246))
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:  # older pillow: fixed-size default font
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(sheet)
    x = pad
    for im, label in (left, right):
        sheet.paste(im, (x, band + pad))
        draw.text((x + 2, pad), label, fill=(40, 40, 40), font=font)
        x += im.width + pad
    sheet.save(out_path)


def image_heightfield(path: str, width: float, relief: float,
                      base: float = 0.6, invert: bool = False,
                      max_cells: int = 240) -> Solid:
    """Turn an image into a solid relief (heightmap / lithophane).

    Brightness becomes height: z runs from base (black) to
    base + relief (white) on top of a solid slab starting at z=0.
    For a lithophane pass invert=True (dark image areas = thick
    material) and hold it against the light. width is the real x size
    in mm; y follows the image aspect ratio.

    The image is resampled so its long side has at most max_cells
    columns (deterministic); more cells = finer relief and more
    triangles (~2*max_cells^2 on top).
    """
    from PIL import Image
    from manifold3d import Manifold, Mesh

    arr, name = _load_gray(path)
    if width <= 0 or relief <= 0 or base <= 0:
        raise BadArgumentError(
            f"width, relief and base must all be positive "
            f"(got width={width}, relief={relief}, base={base})")
    if max_cells < 2:
        raise BadArgumentError(f"max_cells must be >= 2, got {max_cells}")

    h_px, w_px = arr.shape
    if max(h_px, w_px) > max_cells:
        s = max_cells / max(h_px, w_px)
        nx, ny = max(2, round(w_px * s)), max(2, round(h_px * s))
        with Image.fromarray((arr * 255.0).astype(np.uint8)) as im:
            arr = np.asarray(im.resize((nx, ny), Image.LANCZOS),
                             dtype=np.float64) / 255.0
    ny, nx = arr.shape
    v = (1.0 - arr) if invert else arr
    heights = base + v * relief

    depth = width * ny / nx
    xs = np.linspace(-width / 2.0, width / 2.0, nx)
    ys = np.linspace(depth / 2.0, -depth / 2.0, ny)  # image up = +y
    gx, gy = np.meshgrid(xs, ys)

    top = np.column_stack((gx.ravel(), gy.ravel(), heights.ravel()))
    bot = np.column_stack((gx.ravel(), gy.ravel(), np.zeros(nx * ny)))
    verts = np.vstack((top, bot)).astype(np.float32)
    nb = nx * ny  # index offset of the bottom copy

    def vid(r, c):  # top-vertex index at grid row r, col c
        return r * nx + c

    faces: list[tuple[int, int, int]] = []
    for r in range(ny - 1):
        for c in range(nx - 1):
            a, b = vid(r, c), vid(r, c + 1)
            d, e = vid(r + 1, c), vid(r + 1, c + 1)
            faces += [(a, d, b), (b, d, e)]          # top (up, +z)
            faces += [(a + nb, b + nb, d + nb),      # bottom (down)
                      (b + nb, e + nb, d + nb)]
    for c in range(nx - 1):                          # north/south walls
        a, b = vid(0, c), vid(0, c + 1)
        faces += [(a, b, a + nb), (b, b + nb, a + nb)]
        a, b = vid(ny - 1, c), vid(ny - 1, c + 1)
        faces += [(a, a + nb, b), (b, a + nb, b + nb)]
    for r in range(ny - 1):                          # west/east walls
        a, b = vid(r, 0), vid(r + 1, 0)
        faces += [(a, a + nb, b), (b, a + nb, b + nb)]
        a, b = vid(r, nx - 1), vid(r + 1, nx - 1)
        faces += [(a, b, a + nb), (b, b + nb, a + nb)]

    tris = np.asarray(faces, dtype=np.uint32)
    m = Manifold(Mesh(vert_properties=verts, tri_verts=tris))
    if m.is_empty():
        raise EmptyGeometryError(
            f"image_heightfield({name}): mesh construction failed",
            suggestion="report this — a heightfield should always be "
                       "a valid solid")
    solid = Solid(m, f"image_heightfield({name}, {nx}x{ny})")
    if solid.volume < 0:
        solid = Solid(Manifold(Mesh(vert_properties=verts,
                                    tri_verts=tris[:, ::-1].copy())),
                      f"image_heightfield({name}, {nx}x{ny})")
    return solid
