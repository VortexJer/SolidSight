"""Assemble the deterministic board report."""

from __future__ import annotations

import json
from pathlib import Path

from . import checks as C
from .board import parse_board


def _check(id_, level, message, where=None, suggestion=None) -> dict:
    c = {"id": id_, "level": level, "message": message}
    if where:
        c["where"] = where
    if suggestion:
        c["try"] = suggestion
    return c


def analyze(board, min_clearance: float = C.CLEARANCE_DEFAULT,
            dt_c: float = C.DT_DEFAULT) -> dict:
    conn = C.connectivity(board)
    clr = C.clearance(board, min_clearance)
    cur = C.current_capacity(board, dt_c)
    pairs = C.diff_pairs(board)

    checks: list[dict] = []
    for n in conn:
        if not n["routed"]:
            lonely = (", unconnected pad(s): "
                      + ", ".join(n["unconnected_pads"])
                      if n["unconnected_pads"] else "")
            checks.append(_check(
                "net-open", "fail",
                f"net '{n['net']}' is {n['islands']} separate island(s) - "
                f"it is not routed{lonely}",
                where=f"{n['pads']} pad(s), {n['tracks']} track(s)",
                suggestion="route the missing connection(s); an open net "
                           "is a board that does not work, not a style "
                           "issue"))
    for f in clr[:40]:
        checks.append(_check(
            "clearance", "fail" if f["clearance_mm"] < f["required_mm"] * 0.5
            else "warn",
            f"{f['kind']}: '{f['a']}' to '{f['b']}' at "
            f"{f['clearance_mm']} mm (required {f['required_mm']})",
            where=f"{f['layer']} near ({f['near'][0]}, {f['near'][1]})",
            suggestion="move the copper apart or drop the fab's clearance "
                       "class; below ~50% of spec this risks shorts after "
                       "etch, hence FAIL"))
    for p in pairs:
        if not p["width_matched"]:
            checks.append(_check(
                "diff-pair-width", "warn",
                f"pair {p['pair']} mixes widths {p['widths_mm']} mm",
                suggestion="a differential pair needs one width for a "
                           "constant differential impedance"))
        if p["skew_mm"] > 0.5:
            checks.append(_check(
                "diff-pair-skew", "warn",
                f"pair {p['pair']} is skewed {p['skew_mm']} mm "
                f"(~{p['skew_ps_fr4']} ps on FR4)",
                suggestion="length-match the pair (serpentine the short "
                           "side); relevant above ~100 MHz signals"))

    fails = [c for c in checks if c["level"] == "fail"]
    return {
        "status": ("failed" if fails else
                   ("warnings" if checks else "ok")),
        "board": {
            "source": board.source,
            "nets": len([n for n in board.nets if n != 0]),
            "tracks": len(board.tracks),
            "vias": len(board.vias),
            "pads": len(board.pads),
            "copper_um": round(board.copper_thickness_mm * 1000, 1),
        },
        "rules": {"min_clearance_mm": min_clearance, "delta_t_c": dt_c},
        "connectivity": conn,
        "clearance_findings": clr,
        "current_capacity": cur,
        "diff_pairs": pairs,
        "checks": checks,
    }


def inspect(path: str | Path, out_dir: Path,
            min_clearance: float = C.CLEARANCE_DEFAULT,
            dt_c: float = C.DT_DEFAULT) -> dict:
    from .render import render_board
    board = parse_board(path)
    rep = analyze(board, min_clearance, dt_c)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    render_board(board, out / "board.png",
                 marks=rep["clearance_findings"][:20])
    rep["files"] = {"report": "report.json", "renders": ["board.png"]}
    (out / "report.json").write_text(json.dumps(rep, indent=2) + "\n",
                                     encoding="utf-8")
    rep["_out_dir"] = str(out)
    return rep
