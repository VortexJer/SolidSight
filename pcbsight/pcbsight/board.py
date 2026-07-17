"""The board model: nets, tracks, vias, pads — positions in mm.

Reads .kicad_pcb (KiCad 6/7/8). Footprint pads are composed through the
footprint's placement (position + rotation), because a pad's (at ...) is
LOCAL — skipping that composition puts every pad of every rotated
footprint in the wrong place, silently.
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


@dataclass
class Board:
    source: str
    nets: dict[int, str] = field(default_factory=dict)
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)
    copper_thickness_mm: float = 0.035        # 1 oz, unless the file says
    layers_cu: tuple[str, ...] = ("F.Cu", "B.Cu")

    def net_name(self, n: int) -> str:
        return self.nets.get(n, f"net#{n}")

    def items_of_net(self, n: int):
        return ([t for t in self.tracks if t.net == n],
                [v for v in self.vias if v.net == n],
                [p for p in self.pads if p.net == n])


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

    for fp in (S.children(root, "footprint") + S.children(root, "module")):
        ref = "?"
        for prop in S.children(fp, "property"):
            if len(prop) >= 3 and prop[1] == "Reference":
                ref = str(prop[2])
        for txt in S.children(fp, "fp_text"):
            if len(txt) >= 3 and txt[1] == "reference":
                ref = str(txt[2])
        fat = S.child(fp, "at")
        fx, fy = (float(fat[1]), float(fat[2])) if fat else (0.0, 0.0)
        frot = float(fat[3]) if fat and len(fat) >= 4 else 0.0

        for pad in S.children(fp, "pad"):
            if len(pad) < 3:
                continue
            pname = str(pad[1])
            ptype = str(pad[2])                  # smd | thru_hole | np_...
            pat = S.child(pad, "at")
            px, py = (float(pat[1]), float(pat[2])) if pat else (0.0, 0.0)
            # compose: rotate the LOCAL pad offset by the footprint angle.
            # KiCad rotates counter-clockwise with y DOWN, so the matrix
            # uses -angle in the conventional frame.
            a = math.radians(frot)
            wx = fx + px * math.cos(a) + py * math.sin(a)
            wy = fy - px * math.sin(a) + py * math.cos(a)
            size = S.child(pad, "size")
            shape = str(pad[3]) if len(pad) >= 4 else "circle"
            netc = S.child(pad, "net")
            b.pads.append(Pad(
                ref=ref, name=pname, at=(wx, wy),
                size=(float(size[1]), float(size[2])) if size else (1.0, 1.0),
                shape=shape,
                net=int(netc[1]) if netc else 0,
                layers=tuple(str(v) for v in S.values(pad, "layers")),
                through=ptype == "thru_hole"))

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
