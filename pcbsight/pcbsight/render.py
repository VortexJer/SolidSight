"""Deterministic board render — it should look like a board.

Substrate (soldermask green), copper traces (gold, front bright / back
dim), pads and vias, silkscreen component bodies with their reference
designators and values, and every clearance finding circled in red at
its coordinates. Software rasterizer via Pillow: no GPU, byte-identical.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .board import Board

# a board-shop palette
BG = (238, 238, 234)
MASK = (26, 74, 58)          # soldermask green substrate
MASK_EDGE = (14, 44, 34)
F_CU = (208, 158, 92)        # front copper (gold)
B_CU = (150, 120, 92)        # back copper (dimmer)
PAD = (222, 196, 128)        # tin-plated pad
PAD_TH = (208, 176, 108)     # through-hole annulus
DRILL = (30, 42, 38)
SILK = (232, 232, 226)       # silkscreen white
SILK_DIM = (150, 168, 160)   # inferred body (we are guessing its size)
VIA_C = (196, 176, 120)
MARK = (240, 84, 84)
INK = (40, 44, 42)


def _font(sz=12):
    try:
        return ImageFont.load_default(size=sz)
    except TypeError:
        return ImageFont.load_default()


def render_board(board: Board, path: Path, marks: list[dict] | None = None,
                 size: int = 1000) -> None:
    ox1, oy1, ox2, oy2 = board.outline_rect()
    bw, bh = ox2 - ox1, oy2 - oy1
    span = max(bw, bh, 1.0)
    top = 46
    pad_px = 30
    s = (size - 2 * pad_px) / (span * 1.06)
    cx, cy = (ox1 + ox2) / 2, (oy1 + oy2) / 2
    plot = size - 2 * pad_px

    def px(pt):
        # KiCad y grows DOWN; keep it so the render matches the editor
        return (size / 2 + (pt[0] - cx) * s,
                top + plot / 2 + (pt[1] - cy) * s)

    img = Image.new("RGB", (size, size + top), BG)
    d = ImageDraw.Draw(img)
    f_ref, f_val, f_pad = _font(13), _font(11), _font(10)

    # --- substrate -------------------------------------------------------
    a, b = px((ox1, oy1)), px((ox2, oy2))
    d.rounded_rectangle([min(a[0], b[0]), min(a[1], b[1]),
                         max(a[0], b[0]), max(a[1], b[1])],
                        radius=max(6, 2 * s), fill=MASK, outline=MASK_EDGE,
                        width=3)

    # a faint 10 mm grid on the mask, for scale
    gx = math.ceil(ox1 / 10) * 10
    grid_c = (34, 84, 66)
    while gx < ox2:
        x = px((gx, 0))[0]
        d.line([(x, min(a[1], b[1])), (x, max(a[1], b[1]))], fill=grid_c)
        gx += 10
    gy = math.ceil(oy1 / 10) * 10
    while gy < oy2:
        y = px((0, gy))[1]
        d.line([(min(a[0], b[0]), y), (max(a[0], b[0]), y)], fill=grid_c)
        gy += 10

    # --- copper (back first, front on top) -------------------------------
    for layer, col in (("B.Cu", B_CU), ("F.Cu", F_CU)):
        for t in board.tracks:
            if t.layer != layer:
                continue
            d.line([px(t.start), px(t.end)], fill=col,
                   width=max(1, int(t.width * s)))

    # --- pads ------------------------------------------------------------
    for p in board.pads:
        X, Y = px(p.at)
        w = max(1.5, p.size[0] * s / 2)
        h = max(1.5, p.size[1] * s / 2)
        col = PAD_TH if p.through else PAD
        if p.shape in ("circle", "oval"):
            d.ellipse([X - w, Y - h, X + w, Y + h], fill=col)
        else:
            d.rectangle([X - w, Y - h, X + w, Y + h], fill=col)
        if p.through:                        # drill
            r = min(w, h) * 0.45
            d.ellipse([X - r, Y - r, X + r, Y + r], fill=DRILL)

    # --- vias ------------------------------------------------------------
    for v in board.vias:
        X, Y = px(v.at)
        r = max(1.5, v.size * s / 2)
        d.ellipse([X - r, Y - r, X + r, Y + r], fill=VIA_C)
        rd = max(0.8, v.drill * s / 2)
        d.ellipse([X - rd, Y - rd, X + rd, Y + rd], fill=DRILL)

    # --- silkscreen: component bodies + references -----------------------
    for fp in board.footprints:
        col = SILK_DIM if fp.body_inferred else SILK
        for poly in fp.body:
            if len(poly) >= 2:
                d.line([px(q) for q in poly], fill=col, width=2)
        # reference designator + value at the footprint centre
        cxp, cyp = px(fp.at)
        label = fp.ref
        d.text((cxp, cyp), label, fill=SILK, font=f_ref, anchor="mm")
        if fp.value and fp.value not in ("", "~", fp.ref):
            d.text((cxp, cyp + 12), fp.value[:14], fill=SILK_DIM,
                   font=f_val, anchor="mm")

    # --- findings --------------------------------------------------------
    for m in (marks or []):
        X, Y = px(tuple(m["near"]))
        d.ellipse([X - 13, Y - 13, X + 13, Y + 13], outline=MARK, width=3)
        d.text((X + 15, Y - 8), f"{m['clearance_mm']}mm", fill=MARK,
               font=f_pad)

    # --- title + legend --------------------------------------------------
    d.text((12, 8), f"{board.source}  -  {bw:.0f} x {bh:.0f} mm  -  "
                    f"{len(board.footprints)} components, "
                    f"{len([n for n in board.nets if n])} nets",
           fill=INK, font=_font(14))
    d.text((12, 27), "soldermask green substrate  -  gold = F.Cu, "
                     "dim = B.Cu  -  white silk = component outlines + "
                     "refs  -  red = finding",
           fill=(110, 114, 112), font=_font(11))
    img.save(path)
