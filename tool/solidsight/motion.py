"""Motion inspection: sweep a declared joint through its range and
measure, exactly, what its child link hits.

    solidsight motion model.py                       # every moving joint
    solidsight motion model.py --joint base_to_arm --steps 24

For each sampled position the child link is transformed rigidly and
intersected against every other part: the output is the exact collision
map over the range (which positions hit what, with overlap volumes) plus
the free arc/travel. v1 limitation, stated honestly: joint axes must be
principal (+-X/+-Y/+-Z) — arbitrary axes need a general rotation the
Solid API does not expose yet.
"""

from __future__ import annotations

from .errors import BadArgumentError


def _axis_index(axis) -> tuple[int, float]:
    ax = [round(float(v), 6) for v in axis]
    nonzero = [i for i, v in enumerate(ax) if abs(v) > 1e-9]
    if len(nonzero) != 1:
        raise BadArgumentError(
            "motion inspection v1 needs a principal joint axis "
            f"(+-X/+-Y/+-Z), got {tuple(axis)}",
            suggestion="align the joint axis with a coordinate axis, or "
                       "rotate the whole model so it is")
    i = nonzero[0]
    return i, (1.0 if ax[i] > 0 else -1.0)


def _pose(solid, joint: dict, value: float):
    """Child link posed at `value` (degrees or mm) along the joint."""
    i, sign = _axis_index(joint["axis"])
    ox, oy, oz = joint["origin"]
    if joint["type"] == "prismatic":
        d = [0.0, 0.0, 0.0]
        d[i] = sign * value
        return solid.translate(*d)
    rot = [0.0, 0.0, 0.0]
    rot[i] = sign * value
    return solid.translate(-ox, -oy, -oz).rotate(*rot).translate(ox, oy, oz)


def _jname(j: dict) -> str:
    """A joint's name: as declared, else the parent_to_child default."""
    return j.get("name") or f"{j['parent']}_to_{j['child']}"


def inspect_motion(scene, joint_name: str | None = None,
                   steps: int = 12) -> list[dict]:
    moving = [j for j in scene.joints
              if j["type"] in ("revolute", "prismatic", "continuous")]
    if joint_name:
        moving = [j for j in moving if _jname(j) == joint_name]
        if not moving:
            names = ", ".join(_jname(j) for j in scene.joints) or "(none)"
            raise BadArgumentError(
                f"no moving joint named {joint_name!r}",
                where=f"declared joints: {names}",
                suggestion="use a name from that list (joints are named by "
                           "joint(..., name=...), else parent_to_child)")
    if not moving:
        raise BadArgumentError(
            "the model declares no moving joints",
            suggestion="add joint(parent, child, type='revolute', ...) "
                       "declarations to the model")

    reports = []
    for j in moving:
        child = scene.get(j["child"]).solid
        limits = j["limits"] or ((0.0, 360.0)
                                 if j["type"] == "continuous" else None)
        lo, hi = limits
        others = [p for p in scene.parts if p.name != j["child"]]
        samples = []
        for k in range(steps + 1):
            v = lo + (hi - lo) * k / steps
            posed = _pose(child, j, v)
            hits = []
            for other in others:
                inter = posed.manifold ^ other.solid.manifold
                vol = float(inter.volume())
                if vol > 1e-3:
                    hits.append({"part": other.name,
                                 "overlap_mm3": round(vol, 3)})
            samples.append({"value": round(v, 3), "hits": hits})
        free = [s["value"] for s in samples if not s["hits"]]
        blocked = [s for s in samples if s["hits"]]
        unit = "deg" if j["type"] != "prismatic" else "mm"
        reports.append({
            "joint": _jname(j),
            "type": j["type"], "unit": unit,
            "range": [lo, hi], "steps": steps,
            "free_positions": free,
            "collisions": blocked,
            "verdict": ("FREE over the whole range" if not blocked else
                        f"COLLIDES at {len(blocked)}/{len(samples)} "
                        f"sampled positions"),
        })
    return reports
