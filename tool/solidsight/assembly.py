"""Assembly helpers: bring several parts into one shared coordinate space.

An assembly file is a normal model file that uses place() instead of raw
emit(), pulling parts from other model files (from_model) or external meshes
(from_stl). Every build with 2+ parts automatically gets pairwise collision /
clearance analysis in report.json.

    from solidsight import *

    bracket = from_model("../bracket/model.py", "body")
    lid     = from_model("lid.py")            # single-part model
    motor   = from_stl("nema17.stl")

    place(bracket, name="bracket")
    place(motor, name="motor", at=(0, 0, 8), rotate=(0, 0, 90))
    place(lid, name="lid", at=(0, 0, 40))
"""

from __future__ import annotations

from pathlib import Path

from .errors import BadArgumentError, SceneError, fmt_num
from .geom import Solid
from .scene import emit


def place(solid: Solid, name: str, at: tuple = (0, 0, 0),
          rotate: tuple = (0, 0, 0), color: str | None = None) -> Solid:
    """Position a part in the assembly: rotate (degrees, X then Y then Z,
    around the origin), THEN translate by `at`. Registers it under `name`
    like emit() does, and returns the placed solid."""
    if not isinstance(solid, Solid):
        raise BadArgumentError(
            f"place() got a {type(solid).__name__}, not a Solid",
            suggestion="from_model()/from_stl() return Solids; dicts from the "
                       'parts catalog need one entry picked, e.g. h["leaf_a"]')
    rx, ry, rz = rotate
    x, y, z = at
    placed = solid.rotate(rx, ry, rz).translate(x, y, z)
    return emit(placed, name=name, color=color)


def _resolve(path: str) -> Path:
    """Relative paths resolve against the model file that is executing."""
    from .scene import current_model_dir
    p = Path(path)
    base = current_model_dir()
    if not p.is_absolute() and base is not None:
        return base / p
    return p


def from_model(path: str, part: str | None = None) -> Solid:
    """Load a named part from another solidsight model file. Relative paths
    resolve against the calling model file's directory. With part=None the
    model must emit exactly one part."""
    from .runner import run_model
    p = _resolve(path)
    scene = run_model(p)
    if part is None:
        if len(scene.parts) != 1:
            names = ", ".join(pp.name for pp in scene.parts)
            raise SceneError(
                f"{p.name} emits {len(scene.parts)} parts; say which one",
                where=f"available: {names}",
                suggestion=f'from_model("{path}", "{scene.parts[0].name}")')
        return scene.parts[0].solid
    return scene.get(part).solid


def from_stl(path: str) -> Solid:
    """Import an external STL/OBJ/3MF/PLY mesh as a Solid. The mesh must be
    watertight — solidsight will not guess at holes."""
    import numpy as np
    import trimesh
    from manifold3d import Manifold, Mesh

    p = _resolve(path)
    if not p.exists():
        raise BadArgumentError(f"mesh file not found: {p}",
                               suggestion="check the path (relative paths "
                                          "resolve against the model file)")
    try:
        tm = trimesh.load(str(p), force="mesh")
    except Exception as e:
        raise BadArgumentError(
            f"could not read {p.name}: {e}",
            suggestion="supported formats: STL, OBJ, PLY, 3MF, GLB") from e
    if tm.is_empty or len(tm.faces) == 0:
        raise BadArgumentError(f"{p.name} contains no triangles")
    tm.merge_vertices()
    if not tm.is_watertight:
        broken = tm.edges_sorted[trimesh.grouping.group_rows(
            tm.edges_sorted, require_count=1)] if len(tm.edges_sorted) else []
        raise BadArgumentError(
            f"{p.name} is not watertight ({len(broken)} boundary edges) — "
            "it cannot become a solid",
            suggestion="repair it first (e.g. Meshmixer/Blender 'make "
                       "manifold'), or re-export with merged vertices")
    mesh = Mesh(
        vert_properties=np.asarray(tm.vertices, dtype=np.float32),
        tri_verts=np.asarray(tm.faces, dtype=np.uint32))
    m = Manifold(mesh)
    if m.is_empty():
        raise BadArgumentError(
            f"{p.name} could not be converted into a solid "
            f"(status: {m.status()})",
            suggestion="the mesh may self-intersect or have inverted "
                       "normals; repair and re-export")
    solid = Solid(m, f"from_stl({p.name})")
    if solid.volume < 0:
        solid = Solid(Manifold(Mesh(
            vert_properties=np.asarray(tm.vertices, dtype=np.float32),
            tri_verts=np.asarray(tm.faces[:, ::-1], dtype=np.uint32))),
            f"from_stl({p.name})")
    return solid


# ---------------------------------------------------------------------------
# pairwise analysis (used by the report on every multi-part build)
# ---------------------------------------------------------------------------

def pair_analysis(scene, mode: str = "free",
                  touch_tol: float = 0.05) -> tuple[list[dict], list[dict]]:
    """For every pair of named parts: collision (overlap bbox + volume + a
    concrete move suggestion) or minimum clearance between their surfaces.
    Returns (pairs, checks)."""
    from .validate import check

    pairs: list[dict] = []
    checks: list[dict] = []
    parts = scene.parts
    ps = mode == "print-safe"
    if len(parts) < 2:
        return pairs, checks

    diag = max(scene.combined().size) * 2 + 1

    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = parts[i], parts[j]
            inter = a.solid.manifold ^ b.solid.manifold
            vol = float(inter.volume())
            if vol > 1e-3:
                bb = inter.bounding_box()
                size = [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]
                axis = int(min(range(3), key=lambda k: size[k]))
                axis_name = "xyz"[axis]
                move = size[axis]
                pairs.append({
                    "a": a.name, "b": b.name, "status": "collision",
                    "overlap_volume_mm3": round(vol, 3),
                    "overlap_bbox": {
                        "min": [round(float(v), 3) for v in bb[:3]],
                        "max": [round(float(v), 3) for v in bb[3:]]},
                    "min_clearance_mm": None,
                    "suggestion": f"move '{b.name}' {fmt_num(move + 0.1)} mm "
                                  f"along {axis_name} (the thinnest overlap "
                                  f"axis), or shrink one part there",
                })
                checks.append(check(
                    "fail" if ps else "warn", "parts-overlap",
                    f'parts "{a.name}" and "{b.name}" occupy the same space '
                    f"({fmt_num(vol)} mm3 of overlap)",
                    where=f"overlap bbox x {fmt_num(bb[0])}..{fmt_num(bb[3])}, "
                          f"y {fmt_num(bb[1])}..{fmt_num(bb[4])}, "
                          f"z {fmt_num(bb[2])}..{fmt_num(bb[5])}",
                    suggestion=f"move '{b.name}' {fmt_num(move + 0.1)} mm "
                               f"along {axis_name}, or rework the joint; "
                               "separate parts must never intersect"))
            else:
                gap = float(a.solid.manifold.min_gap(b.solid.manifold, diag))
                gap = round(gap, 3)
                touching = gap <= touch_tol
                pairs.append({
                    "a": a.name, "b": b.name,
                    "status": "touching" if touching else "clear",
                    "overlap_volume_mm3": 0.0,
                    "overlap_bbox": None,
                    "min_clearance_mm": gap,
                    "suggestion": None if not touching else
                        f"surfaces are {fmt_num(gap)} mm apart — parts that "
                        "must slide or snap need real clearance (0.15-0.3 mm "
                        "printed); if they should be one rigid piece, union "
                        "them into a single part",
                })
    return pairs, checks
