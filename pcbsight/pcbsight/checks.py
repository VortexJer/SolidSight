"""Board electrical checks: connectivity, clearance, current, pairs.

Everything a layout reviewer eyeballs, computed:

  * connectivity - union-find over copper that actually touches, so an
    open net is N islands, not a feeling;
  * clearance - exact segment-to-segment distances minus copper widths;
  * current capacity - IPC-2221 external-layer formula per net;
  * differential pairs - found by net NAME (_P/_N and +/-), then width
    and length symmetry measured.

Geometry is treated as segments-with-width and pads-as-discs/rects;
that is exact for clearance between tracks and conservative for pads.
"""

from __future__ import annotations

import math

from .board import Board, Pad, Track, pad_on_layer

CLEARANCE_DEFAULT = 0.2      # mm — a common fab minimum; overridable
DT_DEFAULT = 10.0            # deg C rise for the IPC current table


def _seg_seg_dist(a1, a2, b1, b2) -> float:
    """Min distance between two 2D segments."""
    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1]

    def pt_seg(p, s1, s2):
        d = (s2[0] - s1[0], s2[1] - s1[1])
        L2 = dot(d, d)
        if L2 <= 1e-18:
            return math.dist(p, s1)
        t = max(0.0, min(1.0, dot((p[0] - s1[0], p[1] - s1[1]), d) / L2))
        return math.dist(p, (s1[0] + t * d[0], s1[1] + t * d[1]))

    # if they intersect, distance is 0
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])

    if (ccw(a1, a2, b1) * ccw(a1, a2, b2) < 0
            and ccw(b1, b2, a1) * ccw(b1, b2, a2) < 0):
        return 0.0
    return min(pt_seg(a1, b1, b2), pt_seg(a2, b1, b2),
               pt_seg(b1, a1, a2), pt_seg(b2, a1, a2))


def _pad_radius(p: Pad) -> float:
    """Conservative pad extent (half the max dimension)."""
    return max(p.size) / 2.0


# ---------------------------------------------------------------------------
# connectivity
# ---------------------------------------------------------------------------

def connectivity(board: Board) -> list[dict]:
    """Per net: how many electrically continuous islands the copper
    forms. 1 island = routed; 2+ = an open. Pads with no copper at all
    are the classic 'forgot to route it' case."""
    out = []
    for net_id, net_name in sorted(board.nets.items()):
        if net_id == 0:
            continue                          # KiCad's "no net"
        tracks, vias, pads = board.items_of_net(net_id)
        items: list[tuple[str, object]] = (
            [("t", t) for t in tracks] + [("v", v) for v in vias]
            + [("p", p) for p in pads])
        if not items:
            continue
        parent = list(range(len(items)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

        def touches(ka, a, kb, b) -> bool:
            if ka == "t" and kb == "t":
                if a.layer != b.layer:
                    return False
                lim = (a.width + b.width) / 2 + 1e-6
                return _seg_seg_dist(a.start, a.end, b.start, b.end) <= lim
            if ka == "t" and kb == "v":
                lim = a.width / 2 + b.size / 2 + 1e-6
                return _pt_seg(b.at, a) <= lim
            if ka == "t" and kb == "p":
                if not pad_on_layer(b, a.layer):
                    return False
                lim = a.width / 2 + _pad_radius(b) + 1e-6
                return _pt_seg(b.at, a) <= lim
            if ka == "v" and kb == "p":
                lim = a.size / 2 + _pad_radius(b) + 1e-6
                return math.dist(a.at, b.at) <= lim
            if ka == "v" and kb == "v":
                lim = (a.size + b.size) / 2 + 1e-6
                return math.dist(a.at, b.at) <= lim
            if ka == "p" and kb == "p":
                shared = any(pad_on_layer(a, L) and pad_on_layer(b, L)
                             for L in board.layers_cu)
                lim = _pad_radius(a) + _pad_radius(b) + 1e-6
                return shared and math.dist(a.at, b.at) <= lim
            return False

        def _pt_seg(p, t: Track) -> float:
            return _seg_seg_dist(p, p, t.start, t.end)

        n = len(items)
        for i in range(n):
            for j in range(i + 1, n):
                ka, a = items[i]
                kb, b = items[j]
                if touches(ka, a, kb, b) or touches(kb, b, ka, a):
                    union(i, j)

        roots = {find(i) for i in range(n)}
        islands = len(roots)
        # which pads sit alone (no track touches them)?
        island_of = [find(i) for i in range(n)]
        pads_idx = [i for i, (k, _o) in enumerate(items) if k == "p"]
        lonely = []
        for i in pads_idx:
            mates = [j for j in range(n) if island_of[j] == island_of[i]]
            if all(items[j][0] == "p" and j == i for j in mates):
                p = items[i][1]
                lonely.append(f"{p.ref}.{p.name}")
        out.append({
            "net": net_name, "net_id": net_id,
            "tracks": len(tracks), "vias": len(vias), "pads": len(pads),
            "islands": islands,
            "routed": islands == 1,
            "unconnected_pads": lonely,
            "total_track_mm": round(sum(t.length for t in tracks), 3),
        })
    return out


# ---------------------------------------------------------------------------
# clearance
# ---------------------------------------------------------------------------

def clearance(board: Board, min_clearance: float = CLEARANCE_DEFAULT
              ) -> list[dict]:
    """Copper-to-copper spacing between DIFFERENT nets, per layer.
    Exact for track pairs; pads enter with their conservative radius."""
    findings = []

    tracks = board.tracks
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            a, b = tracks[i], tracks[j]
            if a.net == b.net or a.layer != b.layer:
                continue
            d = _seg_seg_dist(a.start, a.end, b.start, b.end) \
                - a.width / 2 - b.width / 2
            if d < min_clearance:
                mid = ((a.start[0] + a.end[0] + b.start[0] + b.end[0]) / 4,
                       (a.start[1] + a.end[1] + b.start[1] + b.end[1]) / 4)
                findings.append({
                    "kind": "track-track",
                    "a": board.net_name(a.net), "b": board.net_name(b.net),
                    "layer": a.layer,
                    "clearance_mm": round(max(d, 0.0), 4),
                    "required_mm": min_clearance,
                    "near": [round(mid[0], 2), round(mid[1], 2)],
                })

    for t in tracks:
        for p in board.pads:
            if p.net == t.net or not pad_on_layer(p, t.layer):
                continue
            d = _seg_seg_dist(p.at, p.at, t.start, t.end) \
                - t.width / 2 - _pad_radius(p)
            if d < min_clearance:
                findings.append({
                    "kind": "track-pad",
                    "a": board.net_name(t.net),
                    "b": f"{board.net_name(p.net)} (pad {p.ref}.{p.name})",
                    "layer": t.layer,
                    "clearance_mm": round(max(d, 0.0), 4),
                    "required_mm": min_clearance,
                    "near": [round(p.at[0], 2), round(p.at[1], 2)],
                })
    findings.sort(key=lambda f: f["clearance_mm"])
    return findings


# ---------------------------------------------------------------------------
# current capacity (IPC-2221)
# ---------------------------------------------------------------------------

def current_capacity(board: Board, dt_c: float = DT_DEFAULT) -> list[dict]:
    """Max continuous current per net at a given temperature rise,
    from IPC-2221's external-layer curve:

        I = 0.048 * dT^0.44 * A^0.725      (A in mil^2)

    Computed at the net's NARROWEST track, because that is where it
    heats. The formula is the standard for external layers; internal
    layers halve it (k=0.024) and the report says which was used.
    """
    out = []
    mil = 0.0254                              # mm per mil
    for net_id, net_name in sorted(board.nets.items()):
        if net_id == 0:
            continue
        tracks, _v, _p = board.items_of_net(net_id)
        if not tracks:
            continue
        wmin = min(t.width for t in tracks)
        internal = all(t.layer not in ("F.Cu", "B.Cu") for t in tracks)
        k = 0.024 if internal else 0.048
        area_mil2 = (wmin / mil) * (board.copper_thickness_mm / mil)
        i_max = k * (dt_c ** 0.44) * (area_mil2 ** 0.725)
        out.append({
            "net": net_name,
            "min_width_mm": round(wmin, 3),
            "copper_um": round(board.copper_thickness_mm * 1000, 1),
            "layer_model": "internal" if internal else "external",
            "dt_c": dt_c,
            "i_max_a": round(i_max, 3),
            "note": "IPC-2221, at the net's narrowest track",
        })
    return out


# ---------------------------------------------------------------------------
# differential pairs
# ---------------------------------------------------------------------------

_PAIR_SUFFIXES = [("_P", "_N"), ("_p", "_n"), ("+", "-"), ("P", "N")]


def diff_pairs(board: Board) -> list[dict]:
    """Pairs found by net name; then width equality and length skew
    measured. Length skew converts to time as ~6.6 ps/mm (FR4)."""
    names = {name: nid for nid, name in board.nets.items()}
    seen: set[frozenset] = set()
    out = []
    for name, nid in sorted(names.items()):
        for sp, sn in _PAIR_SUFFIXES:
            if name.endswith(sp):
                base = name[: -len(sp)]
                mate = base + sn
                # dedupe by the PAIR, not the suffix rule: "USB_P" ends
                # with both "_P" and "P", and reporting the same two nets
                # twice is a bug, not thoroughness
                key = frozenset((name, mate))
                if mate in names and mate != name and key not in seen:
                    seen.add(key)
                    tp, _vp, _pp = board.items_of_net(nid)
                    tn, _vn, _pn = board.items_of_net(names[mate])
                    if not tp or not tn:
                        continue
                    lp = sum(t.length for t in tp)
                    ln = sum(t.length for t in tn)
                    wp = {round(t.width, 3) for t in tp}
                    wn = {round(t.width, 3) for t in tn}
                    skew = abs(lp - ln)
                    out.append({
                        "pair": f"{name} / {mate}",
                        "length_mm": [round(lp, 3), round(ln, 3)],
                        "skew_mm": round(skew, 3),
                        "skew_ps_fr4": round(skew * 6.6, 1),
                        "widths_mm": sorted(wp | wn),
                        "width_matched": wp == wn and len(wp) == 1,
                    })
    return out


# ---------------------------------------------------------------------------
# impedance (single-ended microstrip estimate)
# ---------------------------------------------------------------------------

def microstrip_z0(width_mm: float, height_mm: float, er: float = 4.5,
                  t_mm: float = 0.035) -> float:
    """IPC-2141 microstrip estimate. An ESTIMATE: field solvers exist
    for a reason, and the stackup must be the real one."""
    w, h, t = width_mm, height_mm, t_mm
    if w <= 0 or h <= 0:
        raise ValueError("width and height must be positive")
    return (87.0 / math.sqrt(er + 1.41)) * math.log(
        5.98 * h / (0.8 * w + t))
