"""Robot description export: declared joints -> URDF / SDF with real
inertials and simplified collision meshes.

In a model file, after emitting the links as parts:

    joint("base", "arm", type="revolute", axis=(0, 0, 1),
          origin=(0, 0, 40), limits=(-90, 90))
    joint("arm", "gripper", type="prismatic", axis=(1, 0, 0),
          origin=(60, 0, 0), limits=(0, 25))

    solidsight robot model.py            # -> out/robot/<model>.urdf + meshes
    solidsight robot model.py --sdf      # -> also <model>.sdf

Masses and inertia tensors are computed from the exact geometry (density
in g/cm3, default 1.24 = solid PLA; override per part with
joint-independent `density=` on the robot command). Collision meshes are
simplified copies (1 mm tolerance). URDF is in meters/kilograms as the
spec requires; STLs stay in mm and are scaled 0.001 in the reference.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import BadArgumentError, SceneError, fmt_num

JOINT_TYPES = ("fixed", "revolute", "continuous", "prismatic")


def joint(parent: str, child: str, type: str = "fixed",
          axis: tuple = (0, 0, 1), origin: tuple = (0, 0, 0),
          limits: tuple | None = None, damping: float = 0.0) -> None:
    """Declare a robot joint between two emitted parts (they become URDF
    links). origin: the joint anchor point in scene mm coordinates,
    relative to the scene origin — the child's frame attaches there.
    limits: (lo, hi) in degrees for revolute, mm for prismatic."""
    from . import scene as scene_mod
    sc = scene_mod.current()
    if sc is None:
        raise SceneError("joint() called outside a solidsight build",
                         suggestion="declare joints inside the model file, "
                                    "after the emits")
    if type not in JOINT_TYPES:
        raise BadArgumentError(
            f"joint() type {type!r} is not supported",
            suggestion="use one of: " + ", ".join(JOINT_TYPES))
    if type in ("revolute", "prismatic") and limits is None:
        raise BadArgumentError(
            f"a {type} joint needs limits=(lo, hi)",
            suggestion="degrees for revolute, mm for prismatic; use "
                       "type='continuous' for an unlimited spin axis")
    if limits is not None and not limits[0] < limits[1]:
        raise BadArgumentError(
            f"joint() limits {limits} must be (lo, hi) with lo < hi")
    a = tuple(float(v) for v in axis)
    if abs(a[0]) + abs(a[1]) + abs(a[2]) < 1e-9:
        raise BadArgumentError("joint() axis must be a non-zero vector",
                               suggestion="e.g. axis=(0, 0, 1) for Z")
    sc.joints.append({
        "parent": parent, "child": child, "type": type, "axis": a,
        "origin": tuple(float(v) for v in origin),
        "limits": (tuple(float(v) for v in limits) if limits else None),
        "damping": float(damping),
    })


# ---------------------------------------------------------------------------

def _link_data(part, density_g_cm3: float) -> dict:
    tm = part.solid.to_trimesh()
    tm.density = density_g_cm3 * 1e-3            # g/cm3 -> g/mm3; mass in g
    com = tm.center_mass                          # mm
    inertia_g_mm2 = tm.moment_inertia             # about COM, g*mm^2
    mass_kg = float(tm.mass) * 1e-3
    inertia = inertia_g_mm2 * 1e-3 * 1e-6         # -> kg*m^2
    return {"name": part.name, "mass_kg": mass_kg,
            "com_m": [float(c) * 1e-3 for c in com],
            "inertia_kg_m2": inertia, "tm": tm}


def validate_robot(scene) -> tuple[dict, list[str]]:
    """Check the joint graph is a proper tree over emitted parts.
    Returns ({child: joint}, ordered link names root-first)."""
    names = [p.name for p in scene.parts]
    problems = []
    for j in scene.joints:
        for end in ("parent", "child"):
            if j[end] not in names:
                raise BadArgumentError(
                    f"joint references unknown part {j[end]!r}",
                    where=f"emitted parts: {', '.join(names)}",
                    suggestion="joint() names must match emit()/place() "
                               "names")
    children = {}
    for j in scene.joints:
        if j["child"] in children:
            raise BadArgumentError(
                f"part {j['child']!r} is the child of two joints — a robot "
                "is a tree, every link has at most one parent")
        children[j["child"]] = j
    roots = [n for n in names if n not in children]
    if len(roots) != 1:
        raise BadArgumentError(
            f"the robot needs exactly ONE root link, found "
            f"{len(roots)}: {', '.join(roots) or '(none — joint cycle)'}",
            suggestion="chain every part to the base with joint(); "
                       "use type='fixed' for rigid attachments")
    # walk the tree to detect cycles / unreachable links
    order, stack = [], [roots[0]]
    kids = {}
    for j in scene.joints:
        kids.setdefault(j["parent"], []).append(j["child"])
    while stack:
        n = stack.pop()
        if n in order:
            raise BadArgumentError(f"joint cycle through {n!r}")
        order.append(n)
        stack.extend(sorted(kids.get(n, []), reverse=True))
    missing = [n for n in names if n not in order]
    if missing:
        raise BadArgumentError(
            "part(s) not connected to the robot tree: "
            + ", ".join(missing),
            suggestion="add joint(parent, child) declarations (fixed is "
                       "fine) so every link hangs off the root")
    return children, order


def export_urdf(scene, out_dir: Path, model_name: str,
                density: float = 1.24, sdf: bool = False,
                say=print) -> list[str]:
    from .events import BUS
    _children, order = validate_robot(scene)
    robot_name = model_name.replace(".py", "")
    rdir = out_dir / "robot"
    mesh_dir = rdir / "meshes"
    mesh_dir.mkdir(parents=True, exist_ok=True)

    solid_parts = {p.name: p for p in scene.parts}
    links = {}
    files: list[str] = []
    with BUS.stage("robot", total=len(order)) as st:
        for name in order:
            data = _link_data(solid_parts[name], density)
            links[name] = data
            data["tm"].export(mesh_dir / f"{name}.stl")
            files.append(f"robot/meshes/{name}.stl")
            from .geom import Solid as _S
            coll = _S(solid_parts[name].solid.manifold.simplify(1.0)
                      ).to_trimesh()
            coll.export(mesh_dir / f"{name}_collision.stl")
            files.append(f"robot/meshes/{name}_collision.stl")
            if data["mass_kg"] <= 0:
                raise BadArgumentError(f"link {name!r} has zero mass")
            st.tick(f"link '{name}' ({fmt_num(data['mass_kg'])} kg)")

    root = ET.Element("robot", name=robot_name)
    for name in order:
        d = links[name]
        link = ET.SubElement(root, "link", name=name)
        inertial = ET.SubElement(link, "inertial")
        ET.SubElement(inertial, "origin",
                      xyz=_v(d["com_m"]), rpy="0 0 0")
        ET.SubElement(inertial, "mass", value=_f(d["mass_kg"]))
        ix = d["inertia_kg_m2"]
        ET.SubElement(inertial, "inertia",
                      ixx=_f(ix[0][0]), ixy=_f(ix[0][1]), ixz=_f(ix[0][2]),
                      iyy=_f(ix[1][1]), iyz=_f(ix[1][2]), izz=_f(ix[2][2]))
        for tag, mesh in (("visual", f"meshes/{name}.stl"),
                          ("collision", f"meshes/{name}_collision.stl")):
            el = ET.SubElement(link, tag)
            ET.SubElement(el, "origin", xyz="0 0 0", rpy="0 0 0")
            geo = ET.SubElement(el, "geometry")
            ET.SubElement(geo, "mesh", filename=mesh,
                          scale="0.001 0.001 0.001")

    for j in sorted(scene.joints, key=lambda x: x["child"]):
        je = ET.SubElement(root, "joint",
                           name=f"{j['parent']}_to_{j['child']}",
                           type=j["type"])
        ET.SubElement(je, "parent", link=j["parent"])
        ET.SubElement(je, "child", link=j["child"])
        ET.SubElement(je, "origin",
                      xyz=_v([v * 1e-3 for v in j["origin"]]), rpy="0 0 0")
        if j["type"] != "fixed":
            ET.SubElement(je, "axis", xyz=_v(_norm(j["axis"])))
        if j["limits"]:
            import math
            lo, hi = j["limits"]
            if j["type"] == "revolute":
                lo, hi = math.radians(lo), math.radians(hi)
            else:                                   # prismatic: mm -> m
                lo, hi = lo * 1e-3, hi * 1e-3
            ET.SubElement(je, "limit", lower=_f(lo), upper=_f(hi),
                          effort="10", velocity="1")
        if j["damping"]:
            ET.SubElement(je, "dynamics", damping=_f(j["damping"]))

    ET.indent(root)
    urdf_path = rdir / f"{robot_name}.urdf"
    ET.ElementTree(root).write(urdf_path, encoding="unicode",
                               xml_declaration=False)
    files.insert(0, f"robot/{robot_name}.urdf")
    say(f"  robot: {urdf_path}  ({len(order)} links, "
        f"{len(scene.joints)} joints, density {density} g/cm3)")

    if sdf:
        sdf_path = rdir / f"{robot_name}.sdf"
        _write_sdf(root, robot_name, sdf_path)
        files.append(f"robot/{robot_name}.sdf")
        say(f"  robot: {sdf_path}")
    return files


def _write_sdf(urdf_root, robot_name: str, path: Path) -> None:
    """Minimal SDF 1.7 wrapper of the same links/joints (Gazebo accepts
    URDF directly too; this is for SDF-only consumers)."""
    sdf = ET.Element("sdf", version="1.7")
    model = ET.SubElement(sdf, "model", name=robot_name)
    for link in urdf_root.findall("link"):
        le = ET.SubElement(model, "link", name=link.get("name"))
        inertial = link.find("inertial")
        li = ET.SubElement(le, "inertial")
        ET.SubElement(li, "pose").text = \
            inertial.find("origin").get("xyz") + " 0 0 0"
        ET.SubElement(li, "mass").text = inertial.find("mass").get("value")
        im = inertial.find("inertia")
        ie = ET.SubElement(li, "inertia")
        for k in ("ixx", "ixy", "ixz", "iyy", "iyz", "izz"):
            ET.SubElement(ie, k).text = im.get(k)
        for tag in ("visual", "collision"):
            src = link.find(tag)
            el = ET.SubElement(le, tag, name=f"{link.get('name')}_{tag}")
            geo = ET.SubElement(el, "geometry")
            me = ET.SubElement(geo, "mesh")
            ET.SubElement(me, "uri").text = src.find(
                "geometry/mesh").get("filename")
            ET.SubElement(me, "scale").text = "0.001 0.001 0.001"
    for jo in urdf_root.findall("joint"):
        jt = jo.get("type")
        je = ET.SubElement(model, "joint", name=jo.get("name"),
                           type="revolute" if jt == "continuous" else jt)
        ET.SubElement(je, "parent").text = jo.find("parent").get("link")
        ET.SubElement(je, "child").text = jo.find("child").get("link")
        ET.SubElement(je, "pose").text = jo.find("origin").get("xyz") + \
            " 0 0 0"
        ax = jo.find("axis")
        if ax is not None:
            axe = ET.SubElement(je, "axis")
            ET.SubElement(axe, "xyz").text = ax.get("xyz")
            lim = jo.find("limit")
            if lim is not None:
                le2 = ET.SubElement(axe, "limit")
                ET.SubElement(le2, "lower").text = lim.get("lower")
                ET.SubElement(le2, "upper").text = lim.get("upper")
    ET.indent(sdf)
    ET.ElementTree(sdf).write(path, encoding="unicode",
                              xml_declaration=False)


def _f(x: float) -> str:
    return f"{x:.9g}"


def _v(xyz) -> str:
    return " ".join(_f(float(v)) for v in xyz)


def _norm(a):
    n = (a[0] ** 2 + a[1] ** 2 + a[2] ** 2) ** 0.5
    return (a[0] / n, a[1] / n, a[2] / n)
