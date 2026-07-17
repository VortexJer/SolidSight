"""Deterministic board render — copper as drawn, findings marked."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .board import Board, pad_on_layer

BG = (247, 247, 245)
INK = (46, 48, 51)
GRID = (225, 225, 220)
LAYER_C = {"F.Cu": (94, 122, 106), "B.Cu": (108, 116, 148)}
PAD_C = (140, 112, 76)
VIA_C = (100, 100, 104)
MARK = (183, 62, 62)


def _font(sz=12):
    try:
        return ImageFont.load_default(size=sz)
    except TypeError:
        return ImageFont.load_default()


def render_board(board: Board, path: Path, marks: list[dict] | None = None,
                 size: int = 900) -> None:
    """Top-down view, both copper layers (back dashed-ish by colour),
    pads, vias, and a red circle at every clearance finding."""
    xs, ys = [], []
    for t in board.tracks:
        xs += [t.start[0], t.end[0]]
        ys += [t.start[1], t.end[1]]
    for p in board.pads:
        xs.append(p.at[0])
        ys.append(p.at[1])
    for v in board.vias:
        xs.append(v.at[0])
        ys.append(v.at[1])
    if not xs:
        xs, ys = [0, 10], [0, 10]
    lo = (min(xs), min(ys))
    hi = (max(xs), max(ys))
    span = max(hi[0] - lo[0], hi[1] - lo[1], 1.0) * 1.12
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    top = 40
    s = (size - 30) / span

    def px(pt):
        # KiCad y grows DOWN the sheet; keep that so the render matches
        # the editor the user sees
        return (size / 2 + (pt[0] - cx) * s, top + (size - 30) / 2
                + (pt[1] - cy) * s)

    img = Image.new("RGB", (size, size + top), BG)
    d = ImageDraw.Draw(img)
    d.text((10, 8), f"{board.source} - top view - grid 10 mm",
           fill=INK, font=_font(13))

    # 10 mm grid
    gx = lo[0] - (lo[0] % 10)
    while gx < hi[0] + 10:
        d.line([px((gx, lo[1] - 20)), px((gx, hi[1] + 20))], fill=GRID)
        gx += 10
    gy = lo[1] - (lo[1] % 10)
    while gy < hi[1] + 10:
        d.line([px((lo[0] - 20, gy)), px((hi[0] + 20, gy))], fill=GRID)
        gy += 10

    for layer in ("B.Cu", "F.Cu"):            # back first, front on top
        col = LAYER_C.get(layer, INK)
        for t in board.tracks:
            if t.layer != layer:
                continue
            d.line([px(t.start), px(t.end)], fill=col,
                   width=max(1, int(t.width * s)))
        for p in board.pads:
            if not pad_on_layer(p, layer) or layer == "B.Cu" and \
                    pad_on_layer(p, "F.Cu"):
                continue
            w, h = p.size[0] * s / 2, p.size[1] * s / 2
            X, Y = px(p.at)
            if p.shape in ("circle", "oval"):
                d.ellipse([X - w, Y - h, X + w, Y + h], fill=PAD_C)
            else:
                d.rectangle([X - w, Y - h, X + w, Y + h], fill=PAD_C)

    for v in board.vias:
        X, Y = px(v.at)
        r = v.size * s / 2
        d.ellipse([X - r, Y - r, X + r, Y + r], fill=VIA_C)
        rd = v.drill * s / 2
        d.ellipse([X - rd, Y - rd, X + rd, Y + rd], fill=BG)

    for m in (marks or []):
        X, Y = px(tuple(m["near"]))
        d.ellipse([X - 12, Y - 12, X + 12, Y + 12], outline=MARK, width=2)
        d.text((X + 14, Y - 8),
               f"{m['clearance_mm']}mm", fill=MARK, font=_font(11))

    # legend
    lx = 10
    for name, col in (("F.Cu", LAYER_C["F.Cu"]), ("B.Cu", LAYER_C["B.Cu"]),
                      ("pad", PAD_C), ("via", VIA_C), ("finding", MARK)):
        d.rectangle([lx, size + top - 18, lx + 10, size + top - 8], fill=col)
        d.text((lx + 14, size + top - 20), name, fill=INK, font=_font(11))
        lx += 60 + 10 * len(name)
    img.save(path)
