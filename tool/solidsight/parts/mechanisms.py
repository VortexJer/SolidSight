"""Hinges and snap-fit clips."""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Solid, box, cylinder, polygon, union


def hinge(length: float = 40.0, leaf: float = 15.0, t: float = 3.0,
          knuckles: int = 5, pin_d: float = 3.0,
          clearance: float = 0.4) -> dict[str, Solid]:
    """Print-in-place barrel hinge. Returns {"leaf_a", "leaf_b"}, assembled
    and interleaved, pin axis along X at Z = barrel radius.

    leaf_a carries the pin fused to its knuckles; leaf_b's knuckles are bored
    out with `clearance` around the pin, so the printed assembly rotates.
    knuckles must be odd (leaf_a gets the outer ones). Leaves lie flat on
    Z=0 with thickness t; total footprint is length x (2*leaf).
    """
    if knuckles < 3 or knuckles % 2 == 0:
        raise BadArgumentError(
            f"hinge() knuckles must be an odd number >= 3, got {knuckles}",
            suggestion="use 3, 5 or 7")
    if pin_d + 2 * clearance >= pin_d * 2.4:
        raise BadArgumentError(
            f"hinge() clearance {fmt_num(clearance)} is huge next to "
            f"pin_d {fmt_num(pin_d)} — the pin would rattle out")

    barrel_od = pin_d + 2 * max(1.6, t * 0.8)
    zc = barrel_od / 2.0  # pin axis height

    seg_len = (length - (knuckles - 1) * clearance) / knuckles
    if seg_len < pin_d:
        raise BadArgumentError(
            f"hinge() knuckle segments came out {fmt_num(seg_len)} long — "
            f"too short next to pin_d {fmt_num(pin_d)}",
            suggestion="use fewer knuckles or a longer hinge")

    def knuckle(x0: float) -> Solid:
        k = cylinder(h=seg_len, d=barrel_od).rotate(y=90).translate(
            x0, 0, zc)
        return k

    def plate(side: int) -> Solid:
        # side +1 -> +Y leaf, -1 -> -Y leaf
        p = box(length, leaf - barrel_od * 0.25, t)
        y_mid = barrel_od * 0.25 + (leaf - barrel_od * 0.25) / 2
        return p.translate(0, side * y_mid, 0)

    starts = [-length / 2 + i * (seg_len + clearance) for i in range(knuckles)]
    a_idx = [i for i in range(knuckles) if i % 2 == 0]
    b_idx = [i for i in range(knuckles) if i % 2 == 1]

    pin = cylinder(h=length, d=pin_d).rotate(y=90).translate(-length / 2, 0, zc)
    pin_hole = cylinder(h=length + 2, d=pin_d + 2 * clearance
                        ).rotate(y=90).translate(-length / 2 - 1, 0, zc)

    def leaf_solid(side: int, own: list[int], other: list[int]) -> Solid:
        s = plate(side)
        for i in own:
            s = s + knuckle(starts[i])
        # carve back the plate wherever the other leaf's knuckles turn
        for i in other:
            cut = box(seg_len + 2 * clearance, barrel_od + 2 * clearance,
                      barrel_od + 2 * clearance, center=True).translate(
                starts[i] + seg_len / 2, 0, zc)
            s = s - cut
        return s

    leaf_a = leaf_solid(+1, a_idx, b_idx) + pin
    leaf_b = leaf_solid(-1, b_idx, a_idx) - pin_hole

    leaf_a.desc = f"hinge leaf_a (l={fmt_num(length)}, {knuckles} knuckles)"
    leaf_b.desc = f"hinge leaf_b (l={fmt_num(length)}, {knuckles} knuckles)"
    return {"leaf_a": leaf_a, "leaf_b": leaf_b}


def snap_clip(length: float = 12.0, width: float = 6.0, t: float = 1.6,
              hook: float = 1.2, hook_len: float = 3.0) -> Solid:
    """Cantilever snap-fit clip. Base on Z=0, arm rising in +Z, hook pointing
    +Y at the top. Insert along -Z into a snap_slot() window; the retention
    face is the flat underside of the hook.

    length: total arm height. t: arm thickness (flex direction is Y).
    hook: how far the hook sticks out. hook_len: vertical size of the hook
    (40% retention rise + 60% insertion ramp).
    """
    if hook_len >= length:
        raise BadArgumentError(
            f"snap_clip() hook_len {fmt_num(hook_len)} must be shorter than "
            f"the arm length {fmt_num(length)}")
    z_hb = length - hook_len          # hook base height
    rise = hook_len * 0.4             # retention face rise
    pts = [(0, 0), (t, 0), (t, z_hb),
           (t + hook, z_hb + rise),   # hook tip (retention edge below)
           (t, length), (0, length)]
    profile = polygon(pts)
    clip = profile.extrude(width)     # extruded along Z of the sketch...
    # re-orient: sketch was (Y-profile, Z-profile); extrusion becomes X width
    clip = Solid(clip.manifold.rotate([90, 0, 0]).rotate([0, 0, 90]),
                 "snap_clip")
    clip = clip.translate(-width / 2, -t / 2, 0).on_ground()
    clip.desc = (f"snap_clip(l={fmt_num(length)}, w={fmt_num(width)}, "
                 f"hook={fmt_num(hook)})")
    return clip


def snap_slot(width: float = 6.0, t: float = 1.6, hook: float = 1.2,
              hook_len: float = 3.0, wall: float = 2.0,
              clearance: float = 0.25, height: float | None = None) -> Solid:
    """Cutter for the window a snap_clip() latches into. Subtract it from a
    wall of thickness `wall`; the window's TOP edge is the ledge the hook
    grabs. Centered on X, wall assumed to lie in the XZ plane (thickness in
    Y, from y=0 to y=wall); the window bottom sits at Z=0.

    Match width/t/hook/hook_len to the clip and keep the same clearance on
    both parts. `height` overrides the window height (use hook_len * 0.6 +
    2 * clearance when the clip is mounted upside-down, e.g. hanging from a
    lid, so the insertion ramp clears the window too).
    """
    win_w = width + 2 * clearance
    win_h = (float(height) if height is not None
             else hook_len * 0.4 + 2 * clearance)
    cutter = box(win_w, wall + 2, win_h).translate(0, wall / 2, 0)
    cutter.desc = f"snap_slot(w={fmt_num(width)})"
    return cutter
