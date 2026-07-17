"""The board model: substrate, footprints, nets, tracks, vias, pads —
positions in mm.

Reads .kicad_pcb (KiCad 6/7/8). Footprint pads AND graphics are composed
through the footprint's placement (position + rotation), because their
coordinates are LOCAL — skipping that composition puts every pad and
every silkscreen line of a rotated footprint in the wrong place,
silently.

A board is not just copper: it is a substrate with parts on it. The
model carries the board outline (Edge.Cuts, or the copper bbox as a
fallback) and each footprint's reference, value and body outline, so a
render can look like a board instead of like loose wires.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr as S
from .errors import BadBoardError


@dataclass
class Track:
    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: int

    @property
    def length(self) -> float:
        return math.dist(self.start, self.end)


@dataclass
class Via:
    at: tuple[float, float]
    size: float
    drill: float
    net: int
    layers: tuple[str, str] = ("F.Cu", "B.Cu")


@dataclass
class Pad:
    ref: str                     # footprint reference, e.g. "R1"
    name: str                    # pad number/name, e.g. "1"
    at: tuple[float, float]      # WORLD position, composed
    size: tuple[float, float]
    shape: str                   # circle | rect | roundrect | oval ...
    net: int
    layers: tuple[str, ...]
    through: bool
    rot: float = 0.0             # WORLD rotation (footprint + local), deg


@dataclass
class Footprint:
    ref: str                     # U1, J1, R3 ...
    value: str                   # "STM32", "100nF", "" ...
    at: tuple[float, float]      # WORLD placement
    rot: float                   # degrees
    layer: str                   # F.Cu (top) or B.Cu (bottom)
    pads: list[Pad] = field(default_factory=list)
    # body outline(s): world-space polylines from silkscreen / fab /
    # courtyard graphics, or a single rectangle inferred from the pads
    body: list[list[tuple[float, float]]] = field(default_factory=list)
    body_inferred: bool = False

    def pad_bbox(self) -> tuple[float, float, float, float]:
        xs = [p.at[0] for p in self.pads] or [self.at[0]]
        ys = [p.at[1] for p in self.pads] or [self.at[1]]
        exs = [p.size[0] / 2 for p in self.pads] or [0.5]
        return (min(x - e for x, e in zip(xs, exs)),
                min(y - e for y, e in zip(ys, exs)),
                max(x + e for x, e in zip(xs, exs)),
                max(y + e for y, e in zip(ys, exs)))


@dataclass
class Board:
    source: str
    nets: dict[int, str] = field(default_factory=dict)
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)
    footprints: list[Footprint] = field(default_factory=list)
    outline: list[tuple[tuple[float, float], tuple[float, float]]] = \
        field(default_factory=list)   # Edge.Cuts segments
    copper_thickness_mm: float = 0.035        # 1 oz, unless the file says
    layers_cu: tuple[str, ...] = ("F.Cu", "B.Cu")

    def net_name(self, n: int) -> str:
        return self.nets.get(n, f"net#{n}")

    def items_of_net(self, n: int):
        return ([t for t in self.tracks if t.net == n],
                [v for v in self.vias if v.net == n],
                [p for p in self.pads if p.net == n])

    def extent(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) of everything — the drawing box."""
        xs, ys = [], []
        if self.outline:
            for (x1, y1), (x2, y2) in self.outline:
                xs += [x1, x2]
                ys += [y1, y2]
        for t in self.tracks:
            xs += [t.start[0], t.end[0]]
            ys += [t.start[1], t.end[1]]
        for p in self.pads:
            xs.append(p.at[0])
            ys.append(p.at[1])
        for v in self.vias:
            xs.append(v.at[0])
            ys.append(v.at[1])
        if not xs:
            return (0.0, 0.0, 10.0, 10.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def outline_rect(self) -> tuple[float, float, float, float]:
        """The substrate rectangle: Edge.Cuts bbox if present, else the
        copper bbox grown by a 2 mm margin (a board always has a border)."""
        if self.outline:
            xs, ys = [], []
            for (x1, y1), (x2, y2) in self.outline:
                xs += [x1, x2]
                ys += [y1, y2]
            return (min(xs), min(ys), max(xs), max(ys))
        lo_x, lo_y, hi_x, hi_y = self.extent()
        m = 2.0
        return (lo_x - m, lo_y - m, hi_x + m, hi_y + m)


def _compose(fx, fy, a_rad):
    def w(px, py):
        return (fx + px * math.cos(a_rad) + py * math.sin(a_rad),
                fy - px * math.sin(a_rad) + py * math.cos(a_rad))
    return w


def _is_body_layer(layer: str) -> bool:
    return any(k in layer for k in ("SilkS", "Fab", "CrtYd"))


def parse_board(path: str | Path) -> Board:
    p = Path(path)
    if not p.exists():
        raise BadBoardError(f"board not found: {p}",
                            suggestion="check the path")
    text = p.read_text(encoding="utf-8", errors="replace")
    root = S.parse(text, p.name)
    if not root or root[0] != "kicad_pcb":
        raise BadBoardError(
            f"{p.name} is not a kicad_pcb file (toplevel is "
            f"{root[0] if root else 'empty'})",
            suggestion="pcbsight reads KiCad .kicad_pcb boards")

    b = Board(source=p.name)

    for net in S.children(root, "net"):
        if len(net) >= 3:
            b.nets[int(net[1])] = str(net[2])
        elif len(net) == 2:
            b.nets[int(net[1])] = f"net#{net[1]}"

    for seg in S.children(root, "segment"):
        st, en = S.child(seg, "start"), S.child(seg, "end")
        if not st or not en:
            continue
        b.tracks.append(Track(
            start=(float(st[1]), float(st[2])),
            end=(float(en[1]), float(en[2])),
            width=float(S.value(seg, "width", 0.0)),
            layer=str(S.value(seg, "layer", "F.Cu")),
            net=int(S.value(seg, "net", 0))))

    for via in S.children(root, "via"):
        at = S.child(via, "at")
        if not at:
            continue
        lay = S.values(via, "layers")
        b.vias.append(Via(
            at=(float(at[1]), float(at[2])),
            size=float(S.value(via, "size", 0.6)),
            drill=float(S.value(via, "drill", 0.3)),
            net=int(S.value(via, "net", 0)),
            layers=(str(lay[0]), str(lay[1])) if len(lay) >= 2
            else ("F.Cu", "B.Cu")))

    # board outline: Edge.Cuts graphics on the root
    for gr in (S.children(root, "gr_line") + S.children(root, "gr_rect")):
        if str(S.value(gr, "layer", "")) != "Edge.Cuts":
            continue
        st, en = S.child(gr, "start"), S.child(gr, "end")
        if not st or not en:
            continue
        s = (float(st[1]), float(st[2]))
        e = (float(en[1]), float(en[2]))
        if gr[0] == "gr_rect":
            x1, y1, x2, y2 = s[0], s[1], e[0], e[1]
            b.outline += [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
                          ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]
        else:
            b.outline.append((s, e))

    for fp in (S.children(root, "footprint") + S.children(root, "module")):
        ref, value = "?", ""
        for prop in S.children(fp, "property"):
            if len(prop) >= 3 and prop[1] == "Reference":
                ref = str(prop[2])
            if len(prop) >= 3 and prop[1] == "Value":
                value = str(prop[2])
        for txt in S.children(fp, "fp_text"):
            if len(txt) >= 3 and txt[1] == "reference":
                ref = str(txt[2])
            if len(txt) >= 3 and txt[1] == "value":
                value = str(txt[2])
        fat = S.child(fp, "at")
        fx, fy = (float(fat[1]), float(fat[2])) if fat else (0.0, 0.0)
        frot = float(fat[3]) if fat and len(fat) >= 4 else 0.0
        flayer = str(S.value(fp, "layer", "F.Cu"))
        a = math.radians(frot)
        w = _compose(fx, fy, a)

        fpobj = Footprint(ref=ref, value=value, at=(fx, fy), rot=frot,
                          layer=flayer)

        for pad in S.children(fp, "pad"):
            if len(pad) < 3:
                continue
            pname = str(pad[1])
            ptype = str(pad[2])                  # smd | thru_hole | np_...
            pat = S.child(pad, "at")
            px, py = (float(pat[1]), float(pat[2])) if pat else (0.0, 0.0)
            prot = float(pat[3]) if pat and len(pat) >= 4 else 0.0
            wx, wy = w(px, py)
            size = S.child(pad, "size")
            shape = str(pad[3]) if len(pad) >= 4 else "circle"
            netc = S.child(pad, "net")
            pobj = Pad(
                ref=ref, name=pname, at=(wx, wy),
                size=(float(size[1]), float(size[2])) if size else (1.0, 1.0),
                shape=shape,
                net=int(netc[1]) if netc else 0,
                layers=tuple(str(v) for v in S.values(pad, "layers")),
                through=ptype == "thru_hole",
                rot=(frot + prot) % 360.0)
            b.pads.append(pobj)
            fpobj.pads.append(pobj)

        # body outline: silk / fab / courtyard graphics, composed to world
        for g in (S.children(fp, "fp_line") + S.children(fp, "fp_rect")):
            if not _is_body_layer(str(S.value(g, "layer", ""))):
                continue
            st, en = S.child(g, "start"), S.child(g, "end")
            if not st or not en:
                continue
            s = w(float(st[1]), float(st[2]))
            e = w(float(en[1]), float(en[2]))
            if g[0] == "fp_rect":
                c = [w(float(st[1]), float(st[2])),
                     w(float(en[1]), float(st[2])),
                     w(float(en[1]), float(en[2])),
                     w(float(st[1]), float(en[2])),
                     w(float(st[1]), float(st[2]))]
                fpobj.body.append(c)
            else:
                fpobj.body.append([s, e])
        for g in S.children(fp, "fp_poly"):
            if not _is_body_layer(str(S.value(g, "layer", ""))):
                continue
            pts = S.child(g, "pts")
            if not pts:
                continue
            poly = [w(float(xy[1]), float(xy[2]))
                    for xy in S.children(pts, "xy")]
            if poly:
                fpobj.body.append(poly + [poly[0]])

        # no graphics? infer the body from the pad bbox (+0.3 mm) so a
        # part is never invisible — a courtyard is better than nothing
        if not fpobj.body and fpobj.pads:
            x1, y1, x2, y2 = fpobj.pad_bbox()
            m = 0.4
            fpobj.body = [[(x1 - m, y1 - m), (x2 + m, y1 - m),
                           (x2 + m, y2 + m), (x1 - m, y2 + m),
                           (x1 - m, y1 - m)]]
            fpobj.body_inferred = True

        b.footprints.append(fpobj)

    if not b.tracks and not b.pads:
        raise BadBoardError(
            f"{p.name} has no copper (no segments, no pads)",
            suggestion="is this a project file (.kicad_pro) instead of "
                       "the board (.kicad_pcb)?")
    return b


def pad_on_layer(pad: Pad, layer: str) -> bool:
    if pad.through:
        return True
    for pl in pad.layers:
        if pl == layer or pl.startswith("*"):
            return True
    return False
