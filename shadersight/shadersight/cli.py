"""shadersight CLI — shaders as mathematical systems."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .errors import ShaderSightError

_ASCII_FOLD = {ord(a): b for a, b in
               [("—", "-"), ("–", "-"), ("°", " deg"), ("·", "-"),
                ("…", "..."), ("×", "x"), ("→", "->"), ("≤", "<="),
                ("≥", ">=")]}


def _say(text: str, err: bool = False) -> None:
    print(text.translate(_ASCII_FOLD), file=sys.stderr if err else sys.stdout,
          flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="shadersight",
        description="Shader review for AI agents: a material or a node "
                    "graph in, exact physics + cost + preview out.")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("material",
                       help="test a PBR material's physics (energy, "
                            "reciprocity, positivity)")
    m.add_argument("--preset", default=None,
                   help="start from a MEASURED material: gold, silver, "
                        "copper, aluminum, iron, titanium, chromium, "
                        "plastic, rubber, wood, skin, snow. Explicit "
                        "flags override the preset")
    m.add_argument("--base-color", default=None,
                   help="R,G,B in 0..1 (default 0.8,0.8,0.8, or the "
                        "preset's measured value)")
    m.add_argument("--roughness", type=float, default=None)
    m.add_argument("--metallic", type=float, default=None)
    m.add_argument("--specular", type=float, default=None)
    m.add_argument("--boost", type=float, default=None,
                   help="the 'intensity' slider real engines expose "
                        "(multiplies the whole BRDF). 1.0 is physics; "
                        "above it manufactures energy - pass your "
                        "engine's value to MEASURE what it costs")
    m.add_argument("--from-json", default=None, metavar="FILE[:NAME]",
                   help="EDIT an existing material: load it from a .json "
                        "(a flat params dict, or a {\"materials\": {...}} "
                        "set with :NAME picking one). Explicit flags "
                        "override the loaded values")
    m.add_argument("--quality", default="normal",
                   choices=["fast", "normal", "high"],
                   help="hemisphere integration resolution (default normal)")
    m.add_argument("--out", default="out")
    m.add_argument("--json", action="store_true")
    m.add_argument("--show", action="store_true",
                   help="when done, open an HTML preview of the out dir "
                        "in the browser (for the human you work for)")

    g = sub.add_parser("graph",
                       help="analyse a shader node graph (cycles, dead "
                            "nodes, cost)")
    g.add_argument("graph", help="a graph .json file")
    g.add_argument("--out", default="out")
    g.add_argument("--json", action="store_true")
    g.add_argument("--show", action="store_true",
                   help="when done, open an HTML preview of the out dir")

    pv = sub.add_parser("preview",
                        help="build out/index.html (verdict + every "
                             "render) and open it in the browser")
    pv.add_argument("out", nargs="?", default="out",
                    help="an --out directory from a previous run")

    df = sub.add_parser("diff",
                        help="what changed between two material/graph runs")
    df.add_argument("a", help="the 'before' out dir (with report.json)")
    df.add_argument("b", help="the 'after' out dir")

    sub.add_parser("install-skill", help="(re)install the Claude Code skill")
    sub.add_parser("uninstall", help="remove the skill AND the package")
    sub.add_parser("version")

    args = p.parse_args(argv)
    if args.cmd not in ("install-skill", "uninstall"):
        from .skill_install import maybe_autoinstall
        maybe_autoinstall()

    try:
        if args.cmd == "version":
            _say(f"shadersight {__version__}")
            return 0
        if args.cmd == "install-skill":
            from .skill_install import install_skill
            install_skill()
            return 0
        if args.cmd == "uninstall":
            from .skill_install import uninstall
            return uninstall()
        if args.cmd == "preview":
            from .preview import show
            _say(f"preview: {show(args.out)}")
            return 0
        if args.cmd == "material":
            rc = _material(args)
        elif args.cmd == "diff":
            return _diff(args)
        else:
            rc = _graph(args)
        if getattr(args, "show", False):
            from .preview import show
            _say(f"  preview: {show(args.out or 'out')}")
        return rc
    except ShaderSightError as e:
        _say(f"FAILED\n{e.render()}", err=True)
        return 1


def _diff(args) -> int:
    import json as _json
    from pathlib import Path

    from .report import diff_reports
    reps = []
    for d in (args.a, args.b):
        p = Path(d) / "report.json"
        if not p.exists():
            _say(f"FAILED\ndiff-error: no report.json in {d}\n"
                 f"  try:   run `shadersight material/graph ... --out {d}` "
                 f"first", err=True)
            return 1
        reps.append(_json.loads(p.read_text(encoding="utf-8")))
    for line in diff_reports(*reps):
        _say(line)

    # two material runs -> also a side-by-side sphere sheet: the numbers
    # are the verdict, but "which of these is the real gold" is a
    # question a pair of images answers in one look
    pa, pb = Path(args.a) / "preview.png", Path(args.b) / "preview.png"
    if pa.exists() and pb.exists():
        from .render import compare_sheet
        out = Path(args.b) / "compare.png"
        # short labels: a full path overflows the title band unread
        compare_sheet(pa, pb, out, label_a=Path(args.a).name,
                      label_b=Path(args.b).name)
        _say(f"  compare: {out}  (before | after - LOOK at it)")
    return 0


def _material(args) -> int:
    from pathlib import Path

    from .brdf import PRESETS, Material
    from .errors import BadModelError
    from .report import inspect_material

    params = {"base_color": (0.8, 0.8, 0.8), "roughness": 0.5,
              "metallic": 0.0, "specular": 0.5}
    name = "material"
    if args.preset:
        if args.preset not in PRESETS:
            raise BadModelError(
                f"unknown preset {args.preset!r}",
                suggestion="one of: " + ", ".join(sorted(PRESETS)))
        params.update(PRESETS[args.preset])
        name = args.preset
    if args.from_json:
        import json as _json
        # FILE[:NAME] — but a Windows path starts with "C:", so only
        # treat the last ":" as a name separator when FILE alone does
        # not exist as a file
        spec = args.from_json
        fpath, mname = Path(spec), ""
        if not fpath.exists():
            head, sep, tail = spec.rpartition(":")
            if sep and head and Path(head).exists():
                fpath, mname = Path(head), tail
        fname = str(fpath)
        if not fpath.exists():
            raise BadModelError(f"material file not found: {spec}",
                                suggestion="check the path (or "
                                           "FILE:NAME to pick from a set)")
        data = _json.loads(fpath.read_text(encoding="utf-8"))
        mats = data.get("materials") if isinstance(data, dict) else None
        if mats is not None:
            if not mname:
                if len(mats) == 1:
                    mname = next(iter(mats))
                else:
                    raise BadModelError(
                        f"{fname} holds {len(mats)} materials",
                        suggestion="pick one: --from-json "
                                   f"{fname}:<{'|'.join(sorted(mats))}>")
            if mname not in mats:
                raise BadModelError(
                    f"no material {mname!r} in {fname}",
                    suggestion="one of: " + ", ".join(sorted(mats)))
            entry, name = dict(mats[mname]), mname
        else:
            entry = dict(data)
            name = mname or fpath.stem
        allowed = {"base_color", "roughness", "metallic", "specular",
                   "boost"}
        for k in list(entry):
            if k not in allowed:
                entry.pop(k)
        if "base_color" in entry:
            entry["base_color"] = tuple(entry["base_color"])
        params.update(entry)
    if args.base_color is not None:
        try:
            params["base_color"] = tuple(float(v)
                                         for v in args.base_color.split(","))
        except ValueError:
            raise BadModelError(f"bad --base-color {args.base_color!r}",
                                suggestion="three numbers, e.g. 0.8,0.1,0.1")
    for k in ("roughness", "metallic", "specular", "boost"):
        v = getattr(args, k)
        if v is not None:
            params[k] = v
    mat = Material(name=name, **params)
    rep = inspect_material(mat, Path(args.out), quality=args.quality)
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    mt = rep["material"]
    _say(f"shadersight material: {rep['status'].upper()}")
    _say(f"  material '{mt.get('name', mat.name)}': base {mt['base_color']}, "
         f"roughness {mt['roughness']}, "
         f"metallic {mt['metallic']} -> F0 {mt['f0']}, alpha {mt['alpha_ggx']}")
    e = rep["energy_conservation"]
    _say(f"  energy: max albedo {e['max_albedo']} at "
         f"{e['max_at_theta_deg']} deg -> "
         f"{'CONSERVES' if e['conserves_energy'] else 'VIOLATES'} "
         f"(grid {e['grid']['n_theta']}x{e['grid']['n_phi']}, "
         f"{e['grid']['n_views']} views"
         + (", over-limit views re-measured at 128x256"
            if e.get("remeasured") else "") + ")")
    r = rep["reciprocity"]
    _say(f"  reciprocity: max rel error {r['max_relative_error']} -> "
         f"{'OK' if r['reciprocal'] else 'BROKEN'}")
    _say(f"  positivity: min value {rep['positivity']['min_value']} -> "
         f"{'OK' if rep['positivity']['non_negative'] else 'NEGATIVE LOBE'}")
    _say(f"  furnace: loses {rep['furnace']['energy_lost'] * 100:.0f}% at "
         f"normal incidence (single-scatter GGX)")

    for c in [c for c in rep["checks"] if c["level"] == "fail"] + \
             [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{c['level'].upper()}] {c['message']}")
        if c.get("where"):
            _say(f"         where: {c['where']}")
        if c.get("try"):
            _say(f"         try:   {c['try']}")

    _say(f"  report: {out}/report.json")
    for f in rep["files"]["renders"]:
        _say(f"  render: {out}/{f}")
    _say("  NEXT: read the checks, then LOOK at albedo_curve.png (does it "
         "stay under the energy ceiling?) and preview.png.")
    return 2 if rep["status"] == "failed" else 0


def _graph(args) -> int:
    from pathlib import Path

    from .report import inspect_graph
    rep = inspect_graph(args.graph, Path(args.out))
    out = rep.pop("_out_dir")
    if args.json:
        print(json.dumps(rep, indent=2))
        return 2 if rep["status"] == "failed" else 0

    _say(f"shadersight graph: {rep['status'].upper()}")
    _say(f"  graph: {rep['name']} - {rep['nodes']} node(s), output "
         f"'{rep['output']}'")
    _say(f"  reachable: {rep['reachable_nodes']}/{rep['nodes']} nodes; "
         f"{len(rep['dead_nodes'])} dead, {len(rep['cycle_nodes'])} in cycles")
    c = rep["cost"]
    _say(f"  cost: ~{c['alu_equivalents']} ALU-equiv/pixel, "
         f"{c['texture_fetches']} texture fetch(es)"
         + (f" (top: {', '.join(list(c['by_type'])[:3])})"
            if c["by_type"] else ""))
    for chk in [c for c in rep["checks"] if c["level"] == "fail"] + \
               [c for c in rep["checks"] if c["level"] == "warn"]:
        _say(f"  [{chk['level'].upper()}] {chk['message']}")
        if chk.get("where"):
            _say(f"         where: {chk['where']}")
        if chk.get("try"):
            _say(f"         try:   {chk['try']}")
    _say(f"  report: {out}/report.json")
    return 2 if rep["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
