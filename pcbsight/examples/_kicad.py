"""Tiny deterministic .kicad_pcb emitter shared by the examples.

Enough of the format to make a board that LOOKS like a board: an
Edge.Cuts outline, footprints with a silkscreen body, a reference and a
value, real pads and nets. Not a CAD tool — just enough that pcbsight
has a substrate, components and names to draw.
"""

from __future__ import annotations


def header(gen: str = "vigia") -> list[str]:
    return [f"(kicad_pcb (version 20240108) (generator {gen})"]


def nets(net_map: dict[int, str]) -> list[str]:
    return [f'  (net {nid} "{name}")' for nid, name in net_map.items()]


def edge_rect(x1: float, y1: float, x2: float, y2: float) -> list[str]:
    """A rectangular board outline on Edge.Cuts."""
    c = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    out = []
    for (ax, ay), (bx, by) in zip(c, c[1:]):
        out.append(f'  (gr_line (start {ax} {ay}) (end {bx} {by}) '
                   f'(layer "Edge.Cuts") (width 0.15))')
    return out


def seg(x1, y1, x2, y2, w, layer, net) -> str:
    return (f'  (segment (start {x1} {y1}) (end {x2} {y2}) '
            f'(width {w}) (layer "{layer}") (net {net}))')


def via(x, y, net, size=0.6, drill=0.3) -> str:
    return (f'  (via (at {x} {y}) (size {size}) (drill {drill}) '
            f'(layers "F.Cu" "B.Cu") (net {net}))')


def footprint(ref: str, value: str, x: float, y: float, rot: float,
              body: tuple[float, float], pads: list) -> str:
    """A footprint with a silkscreen body rectangle (body = w,h in mm),
    a reference and a value, and its pads. pads: list of
    (name, px, py, sx, sy, shape, net, netname, ptype)."""
    bw, bh = body
    L = [f'  (footprint "ex:{ref}" (at {x} {y} {rot}) (layer "F.Cu")',
         f'    (property "Reference" "{ref}" (at 0 {-bh / 2 - 1.2}))',
         f'    (property "Value" "{value}" (at 0 {bh / 2 + 1.2}))']
    # silk body outline (a rectangle in LOCAL coords)
    hw, hh = bw / 2, bh / 2
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    for (ax, ay), (bx, by) in zip(corners, corners[1:]):
        L.append(f'    (fp_line (start {ax} {ay}) (end {bx} {by}) '
                 f'(layer "F.SilkS") (width 0.12))')
    for name, px, py, sx, sy, shape, net, netname, ptype in pads:
        layers = '"*.Cu" "*.Mask"' if ptype == "thru_hole" \
            else '"F.Cu" "F.Mask"'
        netpart = f' (net {net} "{netname}")' if net else ""
        L.append(f'    (pad "{name}" {ptype} {shape} (at {px} {py}) '
                 f'(size {sx} {sy}) (layers {layers}){netpart})')
    L.append("  )")
    return "\n".join(L)


def dip_pads(count_per_side: int, pitch: float, span: float,
             net_of, size=(1.4, 1.0)) -> list:
    """Two rows of SMD pads (a chip). net_of(i) -> (net, name)."""
    pads = []
    n = count_per_side
    for k in range(n):
        py = -(n - 1) * pitch / 2 + k * pitch
        net, nn = net_of(k)
        pads.append((str(k + 1), -span / 2, py, size[0], size[1], "rect",
                     net, nn, "smd"))
    for k in range(n):
        py = (n - 1) * pitch / 2 - k * pitch
        net, nn = net_of(n + k)
        pads.append((str(n + k + 1), span / 2, py, size[0], size[1], "rect",
                     net, nn, "smd"))
    return pads


def header_pads(count: int, pitch: float, net_of, d=1.7) -> list:
    """A single row of through-hole header pins along y."""
    pads = []
    for k in range(count):
        py = -(count - 1) * pitch / 2 + k * pitch
        net, nn = net_of(k)
        pads.append((str(k + 1), 0.0, py, d, d, "circle", net, nn,
                     "thru_hole"))
    return pads
