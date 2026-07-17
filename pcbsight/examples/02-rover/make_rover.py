"""A 4-motor rover controller board — the complex pcbsight example.

Thirteen components (MCU, IMU, four motor connectors, battery, USB-C,
LED, three decoupling caps), 14 nets, real silkscreen bodies and values.
Written twice:

  rover_blind.kicad_pcb   routed the way a fresh agent would with only
                          the netlist and no way to SEE the copper: short
                          diagonals that cross other nets' pads, a USB
                          pair swapped and unmatched, half the motors
                          left unrouted. The defects of routing blind.
  rover_clean.kicad_pcb   the same board taken to zero findings.

The routing reads each pad's REAL world position from pcbsight (the tool
is how you see where the pads are), then lays copper on it: GND and the
motor signals on the bottom layer, power and USB on top, so cross-layer
crossings are never shorts. That is the honest workflow — and it is why
the clean board actually connects, while the blind one guesses.

Run: python make_rover.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from _kicad import edge_rect, footprint, header, header_pads, nets  # noqa: E402
from _router import Router  # noqa: E402

from pcbsight import parse_board  # noqa: E402

HERE = Path(__file__).parent

N = {1: "+3V3", 2: "GND", 3: "VBAT", 4: "M1_A", 5: "M1_B", 6: "M2_A",
     7: "M2_B", 8: "M3_A", 9: "M3_B", 10: "M4_A", 11: "M4_B",
     12: "USB_DP", 13: "USB_DM", 14: "LED"}
W, H = 80.0, 60.0


def components() -> list[str]:
    C: list[str] = []
    # U1: MCU, 8 pads/side. left = power + M1/M2, right = M3/M4 + USB + LED
    left = [(1, "+3V3"), (2, "GND"), (4, "M1_A"), (5, "M1_B"),
            (6, "M2_A"), (7, "M2_B"), (8, "M3_A"), (9, "M3_B")]
    right = [(10, "M4_A"), (11, "M4_B"), (12, "USB_DP"), (13, "USB_DM"),
             (14, "LED"), (3, "VBAT"), (2, "GND"), (1, "+3V3")]
    pads = []
    for k, (net, nn) in enumerate(left):
        pads.append((str(k + 1), -6.0, -10.5 + k * 3.0, 1.6, 1.0, "rect",
                     net, nn, "smd"))
    for k, (net, nn) in enumerate(right):
        pads.append((str(k + 9), 6.0, 10.5 - k * 3.0, 1.6, 1.0, "rect",
                     net, nn, "smd"))
    C.append(footprint("U1", "RP2040", 40, 30, 0, (11, 26), pads))

    C.append(footprint("U2", "MPU6050", 40, 50, 0, (7, 7), [
        ("1", -2.5, 1.5, 0.9, 0.7, "rect", 1, "+3V3", "smd"),
        ("2", -2.5, -1.5, 0.9, 0.7, "rect", 2, "GND", "smd"),
        ("3", 2.5, 1.5, 0.9, 0.7, "rect", 12, "USB_DP", "smd"),
        ("4", 2.5, -1.5, 0.9, 0.7, "rect", 13, "USB_DM", "smd")]))

    for ref, x, y, na, nna, nb, nnb in (
            ("J2", 12, 14, 4, "M1_A", 5, "M1_B"),
            ("J3", 12, 46, 6, "M2_A", 7, "M2_B"),
            ("J4", 68, 14, 8, "M3_A", 9, "M3_B"),
            ("J5", 68, 46, 10, "M4_A", 11, "M4_B")):
        pads = header_pads(3, 3.6, lambda k, na=na, nna=nna, nb=nb, nnb=nnb:
                           [(3, "VBAT"), (na, nna), (nb, nnb)][k], d=1.5)
        C.append(footprint(ref, "MOTOR", x, y, 0, (6, 13), pads))

    C.append(footprint("J1", "BATT", 6, 30, 0, (7, 9), [
        ("1", 0, -3, 2.0, 2.0, "circle", 3, "VBAT", "thru_hole"),
        ("2", 0, 3, 2.0, 2.0, "circle", 2, "GND", "thru_hole")]))
    C.append(footprint("J6", "USB-C", 40, 6, 0, (10, 4), [
        ("1", -1.2, 0, 0.6, 1.4, "rect", 12, "USB_DP", "smd"),
        ("2", 1.2, 0, 0.6, 1.4, "rect", 13, "USB_DM", "smd"),
        ("3", -4.0, 0, 0.9, 1.4, "rect", 3, "VBAT", "smd"),
        ("4", 4.0, 0, 0.9, 1.4, "rect", 2, "GND", "smd")]))
    C.append(footprint("D1", "LED", 58, 30, 0, (4, 2), [
        ("1", -1.4, 0, 1.0, 1.2, "rect", 14, "LED", "smd"),
        ("2", 1.4, 0, 1.0, 1.2, "rect", 2, "GND", "smd")]))
    for i, (cx, cy) in enumerate([(28, 20), (52, 20), (28, 42)], 1):
        C.append(footprint(f"C{i}", "100n", cx, cy, 0, (2.6, 1.5), [
            ("1", -1.0, 0, 0.9, 1.1, "rect", 1, "+3V3", "smd"),
            ("2", 1.0, 0, 0.9, 1.1, "rect", 2, "GND", "smd")]))
    return C


def _parse_pads(comp_strings):
    """Parse the footprint-only board so routing reads REAL pad
    positions/sizes/layers — the tool is how you see the pads."""
    tmp = "\n".join(header("rover") + nets(N) + edge_rect(0, 0, W, H)
                    + comp_strings + [")"]) + "\n"
    tp = HERE / "_scratch.kicad_pcb"
    tp.write_text(tmp, encoding="utf-8")
    board = parse_board(tp)
    tp.unlink()
    return board.pads


def seg(a, b, w, layer, net):
    return (f'  (segment (start {a[0]:.3f} {a[1]:.3f}) '
            f'(end {b[0]:.3f} {b[1]:.3f}) (width {w}) '
            f'(layer "{layer}") (net {net}))')


def via(p, net):
    return (f'  (via (at {p[0]:.3f} {p[1]:.3f}) (size 0.6) (drill 0.3) '
            f'(layers "F.Cu" "B.Cu") (net {net}))')


def build(blind: bool) -> str:
    comps = components()
    pads = _parse_pads(comps)
    at = {(p.ref, p.name): p.at for p in pads}
    L = header("rover") + nets(N) + edge_rect(0, 0, W, H) + comps

    if blind:
        def run(net, pts, w=0.4, layer="F.Cu"):
            for a, b in zip(pts, pts[1:]):
                L.append(seg(a, b, w, layer, net))

        # A blind pass with only the netlist: no view of where copper
        # already is. It shorts, necks, swaps and gives up.
        # GND: a diagonal spine that clips two cap pads
        run(2, [at[("J1", "2")], at[("C1", "2")], at[("D1", "2")],
                at[("U1", "2")]], w=0.8)
        # +3V3: straight through the caps' own pads
        run(1, [at[("U1", "1")], at[("C1", "1")], at[("C2", "1")]], w=0.4)
        # M1: short diagonals that cross each other and C1
        run(4, [at[("U1", "3")], at[("J2", "2")]], w=0.4)
        run(5, [at[("U1", "4")], at[("J2", "3")]], w=0.4)
        # VBAT necked to 0.25 mid-run: a current pinch on the motor rail
        b = at[("J1", "1")]
        run(3, [b, (22, b[1])], w=1.0)
        L.append(seg((22, b[1]), (34, 40), 0.25, "F.Cu", 3))
        run(3, [(34, 40), at[("U1", "14")]], w=1.0)
        # USB: DM too wide, DP stops short (open), no length match
        run(13, [at[("J6", "1")], (at[("J6", "1")][0], 30)], w=0.3)
        run(12, [at[("J6", "2")], (at[("J6", "2")][0], 24)], w=0.25)
        # M2/M3/M4, LED, IMU left unrouted by the blind pass
        L.append(")")
        return "\n".join(x for x in L if x) + "\n"

    # --- clean: a real 2-layer autoroute to zero findings ---------------
    r = Router(W, H)
    r.block_edge()
    for p in pads:
        r.block_pad(p.at[0], p.at[1], p.size[0], p.size[1], p.net,
                    through=p.through)
    by_net: dict[int, list] = {}
    for p in pads:
        by_net.setdefault(p.net, []).append(
            (p.at[0], p.at[1], p.through))
    # widths: power fat, signals thin; route power first (it wants room)
    widths = {1: 0.4, 2: 0.5, 3: 0.6, 12: 0.25, 13: 0.25, 14: 0.3}
    order = [3, 2, 1, 14, 12, 13, 4, 5, 6, 7, 8, 9, 10, 11]
    for net in order:
        pset = by_net.get(net, [])
        ok = r.route(net, pset, widths.get(net, 0.4))
        if not ok:
            raise SystemExit(f"autorouter failed on net {net} "
                             f"({N[net]}) - loosen the board")
    L += r.emit()
    L.append(")")
    return "\n".join(x for x in L if x) + "\n"


if __name__ == "__main__":
    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "rover_blind.kicad_pcb").write_text(build(True), encoding="utf-8")
    (HERE / "rover_clean.kicad_pcb").write_text(build(False), encoding="utf-8")
    print(f"rover board {W}x{H} mm, 14 nets, 13 components")
