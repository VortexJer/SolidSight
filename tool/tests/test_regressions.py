"""Regression tests — every test here pins a real bug found while
dogfooding. Run with: pytest tool/tests"""

import math

import numpy as np
import pytest

from solidsight import box, cylinder, parts, polygon, stroke, union
from solidsight import scene as _scene_mod
from solidsight.scene import Scene
from solidsight.validate import ValidationOptions, analyze_scene


def make_scene():
    sc = Scene()
    _scene_mod.activate(sc)
    return sc


def teardown_function(_fn):
    _scene_mod.deactivate()


# --- threads: chamfer envelope must not split the thread into 2 shells ----

def test_thread_is_single_shell():
    t = parts.iso_thread(8, 20)
    shells = [s for s in t.manifold.decompose() if s.volume() > 1e-9]
    assert len(shells) == 1


# --- ray parity: shared triangle edges must count as ONE crossing ---------

def test_ray_through_shared_edge_counts_once():
    from solidsight.query import raycast
    b = box(10, 10, 10)
    # (0,0) is exactly on the cube's face diagonal -> edge-coincident hits
    res = raycast(b, (0, 0, -5), (0, 0, 1))
    assert res["crossings"] == 2
    assert len(res["material_segments"]) == 1
    assert res["material_segments"][0]["thickness_mm"] == pytest.approx(10)


# --- sealed cavities: decompose returns them as negative-volume pieces ----

def test_sealed_cavity_detected_and_shells_not_confused():
    sc = make_scene()
    block = box(20, 20, 20) - box(10, 10, 10).translate(0, 0, 5)
    sc.emit(block, name="block")
    metrics, checks, _pairs = analyze_scene(
        sc, ValidationOptions(mode="print-safe"))
    assert metrics["block"]["shells"] == 1          # NOT 2
    assert metrics["block"]["internal_voids"]["count"] == 1
    assert any(c["id"] == "internal-cavity" and c["level"] == "fail"
               for c in checks)


# --- union-touching: fires on coplanar contact, NOT on interleaved cutters -

def test_union_touching_warns_on_coplanar_stack():
    sc = make_scene()
    a = box(10, 10, 5)
    b = box(10, 10, 5).translate(0, 0, 5)   # exactly stacked, zero overlap
    _ = a + b
    assert any(w["code"] == "union-touching" for w in sc.warnings)


def test_union_interleaved_cutters_no_false_positive():
    sc = make_scene()
    outer = union(box(2, 10, 5).translate(-4, 0, 0),
                  box(2, 10, 5).translate(4, 0, 0))
    inner = box(2, 10, 5)                   # inside outer's bbox, not touching
    _ = outer + inner
    assert not any(w["code"] == "union-touching" for w in sc.warnings)


# --- wall thickness: no false 0 mm at concave V-grooves (thread roots) ----

def test_thread_thickness_no_false_zero():
    sc = make_scene()
    sc.emit(parts.iso_thread(8, 12), name="rod")
    metrics, _checks, _ = analyze_scene(sc, ValidationOptions(mode="free"))
    tmin = metrics["rod"]["wall_thickness"]["min_mm"]
    assert tmin is None or tmin > 0.5


# --- wall metric: real 0.5 mm cutter-skin must still be found -------------

def test_thin_skin_detected():
    sc = make_scene()
    skin = box(20, 20, 5) - cylinder(h=7, d=10).translate(0, -4.5, -1)
    sc.emit(skin, name="p")
    metrics, _c, _p = analyze_scene(sc, ValidationOptions(mode="free"))
    assert 0.4 < metrics["p"]["wall_thickness"]["min_mm"] < 0.6


# --- renderer: crease-split must not blend normals across 90-deg edges ----
# (trimesh removed Trimesh.smoothed(); a silent fallback averaged normals
# across creases and produced fan-shading artifacts on flat floors)

def test_crease_split_cube_normals_axis_aligned():
    from solidsight.render import _crease_split
    tm = box(10, 10, 10).to_trimesh()
    _verts, _faces, normals = _crease_split(tm, math.radians(30))
    assert np.abs(normals).max(axis=1).min() > 1 - 1e-6


# --- polygon: silent self-intersection must warn --------------------------

def test_self_intersecting_polygon_warns():
    sc = make_scene()
    _ = polygon([(0, 0), (10, 10), (10, 0), (0, 10)])   # bowtie
    assert any(w["code"] == "self-intersecting-polygon" for w in sc.warnings)


# --- collision report: oversized part -> patches + shrink suggestion ------

def test_multi_patch_collision_reports_oversized():
    from solidsight.assembly import pair_analysis
    sc = make_scene()
    walls = union(box(2, 30, 20).translate(-14, 0, 0),
                  box(2, 30, 20).translate(14, 0, 0))
    sc.emit(walls, name="walls")
    sc.emit(box(29, 20, 10, ).translate(0, 0, 5), name="bar")
    pairs, checks = pair_analysis(sc, mode="free")
    col = [p for p in pairs if p["status"] == "collision"][0]
    assert len(col["overlap_patches"]) == 2
    assert "oversized" in col["suggestion"]


# --- determinism: same construction, identical mesh ------------------------

def test_gear_deterministic():
    a = parts.spur_gear(2, 20, 8, bore=6)
    b = parts.spur_gear(2, 20, 8, bore=6)
    ma, mb = a.to_trimesh(), b.to_trimesh()
    assert np.array_equal(ma.vertices, mb.vertices)
    assert np.array_equal(ma.faces, mb.faces)


# --- new helpers stay sane --------------------------------------------------

def test_hex_grid_cuts_material():
    plate = box(60, 40, 3)
    vented = plate - parts.hex_grid(50, 30, 5, cell=7, wall=2).translate(0, 0, -1)
    assert vented.volume < plate.volume
    assert len([s for s in vented.manifold.decompose()
                if s.volume() > 1e-9]) == 1


def test_stroke_single_region():
    sk = stroke([(0, 0), (10, 0), (20, 6), (28, 14)], width=4)
    solid = sk.extrude(3)
    assert len([s for s in solid.manifold.decompose()
                if s.volume() > 1e-9]) == 1


def test_tube_path_single_shell():
    pts = [(0, 0, 0), (0, 0, 10), (5, 0, 15), (12, 0, 16)]
    t = parts.tube_path(pts, d=6)
    assert len([s for s in t.manifold.decompose() if s.volume() > 1e-9]) == 1
