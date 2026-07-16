"""Enclosures, containers, standoffs and panels with uniform walls."""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import (Sketch, Solid, box, circle, cone, cylinder, ngon,
                    rect, rounded_box, union)


def box_with_lid(inner_x: float, inner_y: float, inner_z: float,
                 wall: float = 2.0, lid_h: float = 8.0, lip_h: float = 4.0,
                 fit_clearance: float = 0.2, r: float = 2.0,
                 position: str = "beside") -> dict[str, Solid]:
    """Rounded box + friction-fit lid with an inner lip.

    inner_*: usable cavity size. wall: uniform wall thickness. lid_h: outer
    height of the lid. lip_h: how far the lid's lip reaches into the box.
    fit_clearance: gap per side between lip and box wall (0.15-0.25 prints
    as a good friction fit). position: "beside" (default, printable as-is)
    or "assembled" (lid mounted on the box, for checking the fit visually).
    Returns {"box", "lid"}.
    """
    if r < wall / 2:
        r = wall / 2
    ox, oy = inner_x + 2 * wall, inner_y + 2 * wall
    oz = inner_z + wall  # closed floor, open top
    body = rounded_box(ox, oy, oz, r, vertical_only=True)
    cavity = rounded_box(inner_x, inner_y, inner_z + 1, max(0.5, r - wall),
                         vertical_only=True).translate(0, 0, wall)
    b = body - cavity

    lid_top = rounded_box(ox, oy, lid_h - lip_h, r, vertical_only=True)
    lip_x = inner_x - 2 * fit_clearance
    lip_y = inner_y - 2 * fit_clearance
    lip = rounded_box(lip_x, lip_y, lip_h, max(0.5, r - wall),
                      vertical_only=True)
    lip_hollow = rounded_box(lip_x - 2 * wall, lip_y - 2 * wall, lip_h + 1,
                             max(0.3, r - 2 * wall), vertical_only=True)
    lip = lip - lip_hollow.translate(0, 0, -1)  # ring, not a plug
    lid = lid_top + lip.translate(0, 0, lid_h - lip_h)
    # built lip-up (printable); flip so the lip points down when assembled
    if position == "assembled":
        lid = lid.rotate(x=180).on_ground().translate(0, 0, oz - lip_h)
    elif position == "beside":
        lid = lid.translate(ox / 2 + lip_x / 2 + 10, 0, 0)
    else:
        raise BadArgumentError(
            f'box_with_lid() position must be "beside" or "assembled", '
            f"got {position!r}")
    b.desc = f"box_with_lid box ({fmt_num(ox)}x{fmt_num(oy)}x{fmt_num(oz)})"
    lid.desc = f"box_with_lid lid ({fmt_num(ox)}x{fmt_num(oy)}x{fmt_num(lid_h)})"
    return {"box": b, "lid": lid}


def container(profile: Sketch, height: float, wall: float = 2.0,
              floor: float | None = None) -> Solid:
    """Uniform-wall open container from ANY 2D profile: the outside is
    extrude(profile), the cavity is the profile offset inward by `wall`.
    floor defaults to wall."""
    fl = wall if floor is None else float(floor)
    if fl >= height:
        raise BadArgumentError(
            f"container() floor {fmt_num(fl)} must be below the height "
            f"{fmt_num(height)}")
    outer = profile.extrude(height)
    inner = profile.offset(-wall).extrude(height - fl + 1).translate(0, 0, fl)
    out = outer - inner
    out.desc = f"container(h={fmt_num(height)}, wall={fmt_num(wall)})"
    return out


def standoff(h: float, od: float = 6.0, id_: float = 2.5,
             base_od: float = 0.0, base_h: float = 0.0) -> Solid:
    """Mounting boss: cylinder with a screw hole, optional conical base
    flare for strength. Base on Z=0."""
    if id_ >= od:
        raise BadArgumentError(
            f"standoff() hole d={fmt_num(id_)} must be smaller than the "
            f"outer d={fmt_num(od)}")
    body = cylinder(h=h, d=od)
    if base_od > od and base_h > 0:
        body = body + cone(h=min(base_h, h), d1=base_od, d2=od)
    out = body - cylinder(h=h + 2, d=id_).translate(0, 0, -1)
    out.desc = f"standoff(h={fmt_num(h)}, od={fmt_num(od)}, id={fmt_num(id_)})"
    return out


def honeycomb_panel(x: float, y: float, t: float, cell: float = 8.0,
                    wall: float = 1.6, border: float = 4.0) -> Solid:
    """Flat panel with a hexagonal ventilation/lightening pattern.
    cell: hex hole size across flats. wall: rib width between holes.
    border: solid margin kept around the edges. Centered on XY, base Z=0."""
    if cell <= 0 or wall <= 0:
        raise BadArgumentError("honeycomb_panel() cell and wall must be positive")
    inner_x, inner_y = x - 2 * border, y - 2 * border
    if inner_x < cell or inner_y < cell:
        raise BadArgumentError(
            f"honeycomb_panel() {fmt_num(x)}x{fmt_num(y)} with border "
            f"{fmt_num(border)} leaves no room for {fmt_num(cell)} cells",
            suggestion="shrink the border or the cell size")
    hex_r = (cell / 2) / math.cos(math.pi / 6)  # across-flats -> circumradius
    pitch_x = cell + wall
    pitch_y = (cell + wall) * math.sqrt(3) / 2
    holes = []
    ny = int(inner_y / pitch_y) + 2
    nx = int(inner_x / pitch_x) + 2
    for j in range(-ny // 2 - 1, ny // 2 + 2):
        for i in range(-nx // 2 - 1, nx // 2 + 2):
            cx = i * pitch_x + (pitch_x / 2 if j % 2 else 0)
            cy = j * pitch_y
            if abs(cx) + hex_r <= inner_x / 2 and abs(cy) + hex_r <= inner_y / 2:
                holes.append(ngon(6, r=hex_r).rotate(30).translate(cx, cy))
    plate = rect(x, y)
    for h in holes:
        plate = plate - h
    out = plate.extrude(t)
    out.desc = (f"honeycomb_panel({fmt_num(x)}x{fmt_num(y)}x{fmt_num(t)}, "
                f"cell={fmt_num(cell)})")
    return out
