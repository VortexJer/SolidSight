"""ISO-style metric threads, bolts and nuts.

The thread is built by twist-extruding the horizontal cross-section of a
single-start V-thread (radius varies with angle in a sawtooth), which
reproduces the helix exactly and is manifold by construction — no hand-built
meshes involved.
"""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import (Sketch, Solid, circle, cone, cylinder, intersection,
                    polygon, prism, union)

# Coarse-pitch lookup for common metric sizes (ISO 261).
ISO_COARSE_PITCH = {2: 0.4, 2.5: 0.45, 3: 0.5, 4: 0.7, 5: 0.8, 6: 1.0,
                    8: 1.25, 10: 1.5, 12: 1.75, 16: 2.0, 20: 2.5}


def iso_thread(d: float, length: float, pitch: float | None = None,
               internal: bool = False, clearance: float = 0.15,
               chamfer: bool = True, segments: int = 32,
               left_hand: bool = False) -> Solid:
    """Threaded cylinder (external) or thread cutter (internal).

    d: nominal major diameter (e.g. 8 for M8). pitch: defaults to the ISO
    coarse pitch when d is a standard size.
    internal=True returns a slightly OVERSIZED thread meant to be SUBTRACTED
    from a body to produce a working nut/tapped hole (clearance is applied
    on the radius). External threads get clearance removed so printed pairs
    actually screw together.
    Base sits on Z=0, axis is +Z.
    """
    if pitch is None:
        pitch = ISO_COARSE_PITCH.get(round(float(d), 2))
        if pitch is None:
            raise BadArgumentError(
                f"iso_thread() has no default pitch for d={fmt_num(d)}",
                suggestion="pass pitch= explicitly (e.g. M8 coarse is 1.25); "
                           "standard sizes: " + ", ".join(
                               f"M{k}={v}" for k, v in ISO_COARSE_PITCH.items()))
    p = float(pitch)
    if length < 2 * p:
        raise BadArgumentError(
            f"iso_thread() length {fmt_num(length)} is under two pitches "
            f"({fmt_num(2 * p)}) — not enough for a usable thread",
            suggestion="lengthen the thread or reduce the pitch")

    grow = float(clearance) if internal else -float(clearance)
    r_major = d / 2.0 + grow
    depth = 0.6134 * p                       # ISO thread depth (external)
    r_minor = r_major - depth
    if r_minor <= 0.3:
        raise BadArgumentError(
            f"iso_thread() minor radius came out {fmt_num(r_minor)} — pitch "
            f"{fmt_num(p)} is too coarse for d={fmt_num(d)}")

    # Horizontal slice of a single-start V-thread: radius as a function of
    # angle. Fractions of one pitch (ISO): crest flat 1/8, root flat 1/4,
    # flanks 5/16 each.
    n = max(24, int(segments))
    pts = []
    for i in range(n):
        f = i / n  # fraction of one turn
        if f < 5 / 16:                       # rising flank
            r = r_minor + depth * (f / (5 / 16))
        elif f < 5 / 16 + 1 / 8:             # crest
            r = r_major
        elif f < 5 / 16 + 1 / 8 + 5 / 16:    # falling flank
            r = r_major - depth * ((f - 5 / 16 - 1 / 8) / (5 / 16))
        else:                                # root
            r = r_minor
        a = 2 * math.pi * f
        pts.append((r * math.cos(a), r * math.sin(a)))
    profile: Sketch = polygon(pts)

    turns = length / p
    sign = 1.0 if left_hand else -1.0
    thread = profile.extrude(length, twist=sign * 360.0 * turns,
                             divisions=max(8, int(turns * n)))

    if chamfer and not internal:
        # Taper both ends so the thread starts cleanly (also print-friendlier).
        # Envelope = cylinder clipped by two 45-degree cones; the three solids
        # OVERLAP (never just touch) so the result stays a single shell.
        ch = min(depth, length / 4)
        rise = length + r_major  # tall enough to clear the whole thread
        bottom_cone = cone(h=rise, r1=r_major - ch, r2=r_major - ch + rise,
                           segments=segments)
        top_cone = cone(h=rise, r1=r_major - ch + rise, r2=r_major - ch,
                        segments=segments).translate(0, 0, length - rise)
        envelope = intersection(
            cylinder(h=length, r=r_major + 0.01, segments=segments),
            bottom_cone, top_cone)
        thread = intersection(thread, envelope)
    if internal:
        # Guarantee the cutter has no paper-thin core: fill to the minor radius.
        thread = thread + cylinder(h=length, r=r_minor + 0.01, segments=segments)

    kind = "internal" if internal else "external"
    thread.desc = (f"iso_thread(M{fmt_num(d)}x{fmt_num(p)}, "
                   f"l={fmt_num(length)}, {kind})")
    return thread


def bolt(d: float, length: float, pitch: float | None = None,
         head_af: float | None = None, head_h: float | None = None,
         segments: int = 32) -> Solid:
    """Hex-head bolt. length is the threaded shank below the head; the head
    sits on top (base of the shank on Z=0). head_af is the across-flats size
    (wrench size, default 1.6*d), head_h defaults to 0.65*d."""
    af = float(head_af) if head_af else 1.6 * float(d)
    hh = float(head_h) if head_h else 0.65 * float(d)
    shank = iso_thread(d, length, pitch, segments=segments)
    head = prism(6, h=hh, across_flats=af).translate(0, 0, length)
    # 30-degree washer-face chamfer on the head top
    head = intersection(
        head,
        cone(h=af, r1=af, r2=0.0, segments=segments
             ).translate(0, 0, length + hh - af * 0.55) +
        cylinder(h=hh - 0.001, r=af, segments=segments).translate(0, 0, length))
    out = shank + head
    out.desc = f"bolt(M{fmt_num(d)}, l={fmt_num(length)})"
    return out


def nut(d: float, pitch: float | None = None, af: float | None = None,
        h: float | None = None, segments: int = 32) -> Solid:
    """Hex nut for a bolt of nominal diameter d. af defaults to 1.6*d,
    height to 0.8*d. Printed pairs need the default clearance to run."""
    aff = float(af) if af else 1.6 * float(d)
    hh = float(h) if h else 0.8 * float(d)
    body = prism(6, h=hh, across_flats=aff, )
    cutter = iso_thread(d, hh + 2, pitch, internal=True,
                        segments=segments).translate(0, 0, -1)
    out = body - cutter
    out.desc = f"nut(M{fmt_num(d)})"
    return out
