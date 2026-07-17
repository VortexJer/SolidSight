"""Generate the example boards, defects known by construction.

A small 2-layer board: a regulator-ish footprint (3 pads), a connector
(2 pads), a USB differential pair, a power trace.

  board_clean.kicad_pcb    everything routed, clearances honoured,
                           the pair length-matched
  board_broken.kicad_pcb   the same board with, exactly:
                             * GND left unrouted between U1.2 and J1.2
                               (an open net: 2 islands)
                             * a signal track passing 0.08 mm from the
                               5V trace (clearance violation)
                             * the USB pair skewed by ~3 mm and with
                               mismatched widths
                             * the 5V trace necked down to 0.2 mm
                               (current pinch: ~0.6 A at dT=10)

Run: python make_boards.py
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent / "01-board"


def seg(x1, y1, x2, y2, w, layer, net):
    return (f"  (segment (start {x1} {y1}) (end {x2} {y2}) "
            f"(width {w}) (layer \"{layer}\") (net {net}))")


def via(x, y, net, size=0.6, drill=0.3):
    return (f"  (via (at {x} {y}) (size {size}) (drill {drill}) "
            f"(layers \"F.Cu\" \"B.Cu\") (net {net}))")


def footprint(ref, x, y, rot, pads, value="", body=(6.0, 4.0)):
    bw, bh = body
    out = [f'  (footprint "generic:{ref}" (at {x} {y} {rot}) (layer "F.Cu")',
           f'    (property "Reference" "{ref}" (at 0 {-bh / 2 - 1.2}))',
           f'    (property "Value" "{value}" (at 0 {bh / 2 + 1.2}))']
    hw, hh = bw / 2, bh / 2
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    for (ax, ay), (bx, by) in zip(corners, corners[1:]):
        out.append(f'    (fp_line (start {ax} {ay}) (end {bx} {by}) '
                   f'(layer "F.SilkS") (width 0.12))')
    for name, px, py, sx, sy, shape, net, netname, ptype in pads:
        layers = '"*.Cu" "*.Mask"' if ptype == "thru_hole" \
            else '"F.Cu" "F.Mask"'
        out.append(
            f'    (pad "{name}" {ptype} {shape} (at {px} {py}) '
            f'(size {sx} {sy}) (layers {layers}) '
            f'(net {net} "{netname}"))')
    out.append("  )")
    return "\n".join(out)


def edge_rect(x1, y1, x2, y2):
    c = [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]
    return [f'  (gr_line (start {ax} {ay}) (end {bx} {by}) '
            f'(layer "Edge.Cuts") (width 0.15))'
            for (ax, ay), (bx, by) in zip(c, c[1:])]


NETS = {1: "+5V", 2: "GND", 3: "USB_P", 4: "USB_N", 5: "SIG"}


def build(broken: bool) -> str:
    L: list[str] = ["(kicad_pcb (version 20240108) (generator pcbsight)"]
    for nid, name in NETS.items():
        L.append(f"  (net {nid} \"{name}\")")
    L += edge_rect(13, 10, 67, 53)      # the substrate

    # U1: a 3-pad regulator at (20, 20); J1: a 2-pad connector at (60, 20)
    L.append(footprint("U1", 20, 20, 0, [
        ("1", -2.5, 0, 1.5, 1.5, "rect", 1, "+5V", "smd"),
        ("2", 0, 0, 1.5, 1.5, "rect", 2, "GND", "smd"),
        ("3", 2.5, 0, 1.5, 1.5, "rect", 5, "SIG", "smd"),
    ], value="AP2112", body=(7.0, 4.0)))
    L.append(footprint("J1", 60, 20, 180, [
        ("1", -1.5, 0, 1.7, 1.7, "circle", 1, "+5V", "thru_hole"),
        ("2", 1.5, 0, 1.7, 1.7, "circle", 2, "GND", "thru_hole"),
    ], value="PWR", body=(6.0, 5.0)))
    # J2: USB pads at (40, 40)
    L.append(footprint("J2", 40, 40, 0, [
        ("1", -1.0, 0, 0.8, 1.2, "rect", 3, "USB_P", "smd"),
        ("2", 1.0, 0, 0.8, 1.2, "rect", 4, "USB_N", "smd"),
    ], value="USB", body=(6.0, 4.0)))

    # +5V: U1.1 (17.5,20) -> J1.1 (61.5,20), routed via y=16 — NOT along
    # y=20, where the first version of this generator drove it straight
    # through the GND and SIG pads and pcbsight flagged its own "clean"
    # board at 0.0 mm clearance. The example was wrong; the check was not.
    if broken:
        # neck the middle down to 0.2 mm: a current pinch
        L.append(seg(17.5, 20, 17.5, 16, 1.0, "F.Cu", 1))
        L.append(seg(17.5, 16, 30, 16, 1.0, "F.Cu", 1))
        L.append(seg(30, 16, 45, 16, 0.2, "F.Cu", 1))
        L.append(seg(45, 16, 61.5, 16, 1.0, "F.Cu", 1))
        L.append(seg(61.5, 16, 61.5, 20, 1.0, "F.Cu", 1))
    else:
        L.append(seg(17.5, 20, 17.5, 16, 1.0, "F.Cu", 1))
        L.append(seg(17.5, 16, 61.5, 16, 1.0, "F.Cu", 1))
        L.append(seg(61.5, 16, 61.5, 20, 1.0, "F.Cu", 1))

    # GND: U1.2 (20,20) -> J1.2 (58.5,20) via the bottom layer
    L.append(seg(20, 20, 20, 26, 0.5, "F.Cu", 2))
    L.append(via(20, 26, 2))
    if broken:
        # the bottom run STOPS short: 2 islands -> an open net
        L.append(seg(20, 26, 40, 26, 0.5, "B.Cu", 2))
    else:
        L.append(seg(20, 26, 58.5, 26, 0.5, "B.Cu", 2))
        L.append(via(58.5, 26, 2))
        L.append(seg(58.5, 26, 58.5, 20, 0.5, "F.Cu", 2))

    # SIG: U1.3 (22.5,20) down and to the right
    if broken:
        # runs parallel to the +5V trace at y=16 with an 0.08 mm gap:
        # +5V edge at 16.5, SIG (w=0.3) centre at 16.73 -> edge 16.58
        L.append(seg(22.5, 20, 22.5, 16.73, 0.3, "F.Cu", 5))
        L.append(seg(22.5, 16.73, 35, 16.73, 0.3, "F.Cu", 5))
        L.append(seg(35, 16.73, 35, 34, 0.3, "F.Cu", 5))
    else:
        L.append(seg(22.5, 20, 22.5, 24, 0.3, "F.Cu", 5))
        L.append(seg(22.5, 24, 35, 24, 0.3, "F.Cu", 5))
        L.append(seg(35, 24, 35, 34, 0.3, "F.Cu", 5))

    # USB pair: J2.1 (39,40) and J2.2 (41,40) up to (39,50)/(41,50)
    if broken:
        L.append(seg(39, 40, 39, 50, 0.25, "F.Cu", 3))       # short, 0.25
        L.append(seg(41, 40, 41, 47, 0.3, "F.Cu", 4))        # width mixed
        L.append(seg(41, 47, 44, 47, 0.3, "F.Cu", 4))        # + detour
        L.append(seg(44, 47, 44, 50, 0.3, "F.Cu", 4))
    else:
        L.append(seg(39, 40, 39, 50, 0.25, "F.Cu", 3))
        L.append(seg(41, 40, 41, 50, 0.25, "F.Cu", 4))

    L.append(")")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "board_clean.kicad_pcb").write_text(build(False),
                                               encoding="utf-8")
    (HERE / "board_broken.kicad_pcb").write_text(build(True),
                                                encoding="utf-8")
    print(f"wrote 2 boards to {HERE}")
