"""Regression tests for solidsight.vision (image -> geometry)."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from solidsight.errors import BadArgumentError, EmptyGeometryError
from solidsight.vision import (image_heightfield, image_outline,
                               profile_read)


@pytest.fixture()
def car_side_png(tmp_path):
    """A toy car side silhouette: a bulged body on two ground-touching
    wheels, dark on white, 800x400 px."""
    im = Image.new("L", (800, 400), 255)
    d = ImageDraw.Draw(im)
    d.polygon([(80, 300), (180, 300), (230, 180), (520, 150), (600, 220),
               (720, 240), (720, 300), (80, 300)], fill=20)
    for cx in (220, 600):                      # wheels touch ground at y=340
        d.ellipse([cx - 45, 250, cx + 45, 340], fill=20)
    p = tmp_path / "car_side.png"
    im.save(p)
    return p


@pytest.fixture()
def annulus_png(tmp_path):
    """Black disc (r=80px) with a white hole (r=30px) on a 200px canvas."""
    im = Image.new("L", (200, 200), 255)
    d = ImageDraw.Draw(im)
    d.ellipse([20, 20, 180, 180], fill=0)
    d.ellipse([70, 70, 130, 130], fill=255)
    p = tmp_path / "annulus.png"
    im.save(p)
    return p


def test_outline_traces_area_with_hole(annulus_png):
    # 80 mm wide -> outer r 32 mm, hole r 12 mm; the hole must survive
    sk = image_outline(str(annulus_png), width=80)
    vol = sk.extrude(5.0).volume
    expected = np.pi * (32.0**2 - 12.0**2) * 5.0
    assert abs(vol / expected - 1.0) < 0.02  # trace within 2 % of ideal


def test_outline_is_deterministic(annulus_png):
    a = image_outline(str(annulus_png), width=80).extrude(3.0)
    b = image_outline(str(annulus_png), width=80).extrude(3.0)
    assert a.volume == b.volume
    assert a.bbox == b.bbox


def test_outline_requires_exactly_one_size(annulus_png):
    with pytest.raises(BadArgumentError):
        image_outline(str(annulus_png))
    with pytest.raises(BadArgumentError):
        image_outline(str(annulus_png), width=50, height=50)


def test_outline_invert_flips_material(annulus_png, tmp_path):
    # inverted: material = the white hole disc + the white border frame
    sk = image_outline(str(annulus_png), invert=True, width=80)
    inv_vol = sk.extrude(1.0).volume
    plain_vol = image_outline(str(annulus_png), width=80).extrude(1.0).volume
    total = 80.0 * 80.0  # whole 200px canvas at scale 0.4 mm/px
    assert abs((inv_vol + plain_vol) - total) / total < 0.03


def test_outline_blank_image_says_what_to_try(tmp_path):
    p = tmp_path / "blank.png"
    Image.new("L", (50, 50), 255).save(p)
    with pytest.raises(EmptyGeometryError) as ei:
        image_outline(str(p), width=10)
    assert "invert" in str(ei.value)


def test_outline_shape_touching_border_still_closes(tmp_path):
    im = Image.new("L", (100, 100), 255)
    ImageDraw.Draw(im).rectangle([0, 0, 99, 49], fill=0)  # top half black
    p = tmp_path / "half.png"
    im.save(p)
    vol = image_outline(str(p), width=100).extrude(1.0).volume
    assert abs(vol - 100.0 * 50.0) / (100.0 * 50.0) < 0.03


def test_heightfield_ramp_volume_and_bbox(tmp_path):
    ramp = np.tile(np.linspace(0, 255, 100, dtype=np.uint8), (50, 1))
    p = tmp_path / "ramp.png"
    Image.fromarray(ramp).save(p)
    s = image_heightfield(str(p), width=100, relief=10, base=1)
    lo, hi = s.bbox
    assert hi[2] == pytest.approx(11.0, abs=0.2)   # base + full relief
    assert lo[2] == 0.0
    # mean brightness 0.5 -> ~ (1 + 5) mm * 100 x 50 mm
    assert s.volume == pytest.approx(30000.0, rel=0.02)
    assert s.manifold.decompose() and s.volume > 0


def test_heightfield_invert_is_complementary(tmp_path):
    rng = np.random.default_rng(7)
    img = (rng.random((40, 60)) * 255).astype(np.uint8)
    p = tmp_path / "noise.png"
    Image.fromarray(img).save(p)
    a = image_heightfield(str(p), width=60, relief=8, base=1)
    b = image_heightfield(str(p), width=60, relief=8, base=1, invert=True)
    footprint = 60.0 * 40.0
    both = a.volume + b.volume
    # a + b = footprint * (2*base + relief) exactly, up to resampling
    assert both == pytest.approx(footprint * (2 * 1 + 8), rel=0.02)


def test_profile_read_measures_length_height_and_axles(car_side_png):
    r = profile_read(str(car_side_png), length=4465, stations=12)
    # length is the anchor, so it is exact
    assert r["length_mm"] == pytest.approx(4465.0, rel=1e-4)
    # body spans rows 150..340 px at 4465/640 mm/px -> ~1325 mm tall
    assert r["height_mm"] == pytest.approx(1325.0, rel=0.03)
    # both wheels (drawn at cx 220 and 600 px) are found and ordered
    assert len(r["axles"]) == 2
    assert r["axles"][0]["x"] < r["axles"][1]["x"]
    # drawn wheelbase 380 px * 6.977 mm/px ~ 2651 mm
    assert r["wheelbase_measured_mm"] == pytest.approx(2651.0, rel=0.04)
    assert len(r["stations"]) == 12
    # the roof crown (mid) sits well above the front stub
    tops = [s["top_z"] for s in r["stations"]]
    assert max(tops) > tops[0] + 500


def test_profile_read_is_deterministic(car_side_png):
    a = profile_read(str(car_side_png), length=4465, stations=9)
    b = profile_read(str(car_side_png), length=4465, stations=9)
    assert a["stations"] == b["stations"]
    assert a["axles"] == b["axles"]


def test_profile_read_writes_verification_overlay(car_side_png, tmp_path):
    out = tmp_path / "check.png"
    r = profile_read(str(car_side_png), length=4465, overlay=str(out))
    assert out.exists()
    assert r["overlay"] == str(out)
    # overlay keeps the source dimensions
    with Image.open(out) as im:
        assert im.size == (800, 400)


def test_profile_read_wheelbase_anchor(car_side_png):
    # anchor on the known wheelbase + the two axle pixel columns instead
    r = profile_read(str(car_side_png), wheelbase=2704,
                     axle_px=(220, 600), stations=6)
    # scale set so those columns are exactly 2704 mm apart -> length scales up
    assert r["length_mm"] == pytest.approx(640 * 2704 / 380, rel=0.02)


def test_profile_read_needs_an_anchor(car_side_png):
    with pytest.raises(BadArgumentError):
        profile_read(str(car_side_png))


def test_profile_read_blank_image_says_what_to_try(tmp_path):
    p = tmp_path / "blank.png"
    Image.new("L", (60, 60), 255).save(p)
    with pytest.raises(EmptyGeometryError) as ei:
        profile_read(str(p), length=1000)
    assert "invert" in str(ei.value)


def test_heightfield_is_watertight_single_shell(tmp_path):
    img = np.zeros((30, 30), dtype=np.uint8)
    img[10:20, 10:20] = 255
    p = tmp_path / "plateau.png"
    Image.fromarray(img).save(p)
    s = image_heightfield(str(p), width=30, relief=5, base=1)
    comps = s.manifold.decompose()
    assert len(comps) == 1
    assert s.volume > 30.0 * 30.0 * 1.0 * 0.9
