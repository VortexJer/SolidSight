"""Texture images as measurement.

Tiling seams, repetition, normal-map validity, roughness/AO statistics
and compression artifacts — all exact properties of the pixels, all
normally judged by tiling a plane and squinting at it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .errors import BadTextureError

# thresholds, documented rather than magic
SEAM_RATIO_WARN = 2.0      # wrap-edge difference vs the interior's own
NORMAL_LEN_TOL = 0.06      # |n| must be ~1 after decoding
POWER_OF_TWO = {2 ** k for k in range(4, 15)}


def load_image(path: str | Path, srgb_to_linear: bool = False) -> np.ndarray:
    """(H, W, C) float array in 0..1. Kept as authored: no resizing, no
    guessing — a texture audit that resamples first is auditing its own
    resampler."""
    from PIL import Image
    p = Path(path)
    if not p.exists():
        raise BadTextureError(f"texture not found: {p}",
                              suggestion="check the path")
    try:
        with Image.open(p) as im:
            if im.mode not in ("RGB", "RGBA", "L"):
                im = im.convert("RGBA" if "A" in im.mode else "RGB")
            arr = np.asarray(im, dtype=np.float64) / 255.0
    except Exception as e:
        raise BadTextureError(f"could not read {p.name}: {e}",
                              suggestion="re-save as PNG") from e
    if arr.ndim == 2:
        arr = arr[:, :, None]
    if srgb_to_linear:
        arr = np.where(arr <= 0.04045, arr / 12.92,
                       ((arr + 0.055) / 1.055) ** 2.4)
    return arr


def basics(img: np.ndarray, name: str) -> dict:
    h, w = img.shape[:2]
    return {
        "name": name,
        "size_px": [int(w), int(h)],
        "channels": int(img.shape[2]),
        "power_of_two": bool(w in POWER_OF_TWO and h in POWER_OF_TWO),
        "square": bool(w == h),
        "megapixels": round(w * h / 1e6, 3),
    }


def tiling_seams(img: np.ndarray) -> dict:
    """Does this texture tile?

    The test is not 'do the edges look similar' — it is whether the jump
    ACROSS the wrap is bigger than the jumps the texture makes anyway.
    A noisy rock tiles fine with a large absolute edge difference; a
    smooth gradient does not tile with a small one. So every seam
    difference is normalised by the interior's own median row/column
    difference.
    """
    g = img[:, :, :3].mean(axis=2) if img.shape[2] >= 3 else img[:, :, 0]

    def score(a, b, interior):
        d = float(np.abs(a - b).mean())
        base = float(np.median(interior)) if interior.size else 0.0
        ratio = d / base if base > 1e-9 else (float("inf") if d > 1e-6
                                              else 0.0)
        return d, base, ratio

    col_diffs = np.abs(np.diff(g, axis=1)).mean(axis=0)
    row_diffs = np.abs(np.diff(g, axis=0)).mean(axis=1)
    h_d, h_base, h_ratio = score(g[:, 0], g[:, -1], col_diffs)
    v_d, v_base, v_ratio = score(g[0, :], g[-1, :], row_diffs)

    return {
        "horizontal": {"edge_diff": round(h_d, 5),
                       "interior_median_diff": round(h_base, 5),
                       "ratio": round(h_ratio, 2),
                       "tiles": bool(h_ratio <= SEAM_RATIO_WARN)},
        "vertical": {"edge_diff": round(v_d, 5),
                     "interior_median_diff": round(v_base, 5),
                     "ratio": round(v_ratio, 2),
                     "tiles": bool(v_ratio <= SEAM_RATIO_WARN)},
        "tiles": bool(h_ratio <= SEAM_RATIO_WARN
                      and v_ratio <= SEAM_RATIO_WARN),
        "note": ("the wrap difference is compared against the texture's "
                 "OWN median neighbouring-pixel difference: noisy images "
                 "are allowed a big edge jump, smooth ones are not"),
    }


def repetition(img: np.ndarray, max_size: int = 256) -> dict:
    """Visible repetition: the giveaway of a tiled material.

    Autocorrelation via FFT. A strong off-centre peak means the image
    repeats at that offset — which is a defect in a "seamless" texture
    (the eye finds the pattern) and expected in a deliberate one.
    """
    g = img[:, :, :3].mean(axis=2) if img.shape[2] >= 3 else img[:, :, 0]
    if max(g.shape) > max_size:                   # cost, not accuracy
        sy = max(1, g.shape[0] // max_size)
        sx = max(1, g.shape[1] // max_size)
        g = g[::sy, ::sx]
    g = g - g.mean()
    if not np.any(g):
        return {"periodic": False, "note": "flat image: nothing to correlate"}

    F = np.fft.rfft2(g)
    ac = np.fft.irfft2(F * np.conj(F), s=g.shape).real
    ac /= ac.flat[0]                              # normalise: ac[0,0] == 1
    ac = np.fft.fftshift(ac)
    cy, cx = np.array(ac.shape) // 2

    # ignore a neighbourhood of the centre (every image self-correlates)
    m = ac.copy()
    r = max(3, min(ac.shape) // 20)
    m[cy - r:cy + r + 1, cx - r:cx + r + 1] = -np.inf
    peak = float(m.max())
    py, px = np.unravel_index(int(np.argmax(m)), m.shape)

    return {
        "peak_correlation": round(peak, 4),
        "peak_offset_px": [int(px - cx), int(py - cy)],
        "periodic": bool(peak > 0.5),
        "analysis_size": [int(g.shape[1]), int(g.shape[0])],
        "note": ("off-centre autocorrelation peak; >0.5 means a clearly "
                 "repeating pattern at that offset. Expected in a "
                 "deliberate pattern, a defect in a 'random' material"),
    }


def normal_map(img: np.ndarray) -> dict:
    """Is this actually a valid tangent-space normal map?

    Three things go wrong constantly and all three are arithmetic:
    the vectors are not unit length (the map was resized/compressed in
    sRGB), the blue channel is wrong (Z should be near 1 for a flat
    surface), or the green channel is inverted (DirectX vs OpenGL — the
    single most common asset-pipeline bug there is, and invisible unless
    you know which convention the engine wants).
    """
    if img.shape[2] < 3:
        raise BadTextureError(
            "a normal map needs 3 channels, this image has "
            f"{img.shape[2]}",
            suggestion="pass the RGB normal map, not a grayscale height "
                       "map (those are a different thing)")
    n = img[:, :, :3] * 2.0 - 1.0
    length = np.linalg.norm(n, axis=2)
    bad = np.abs(length - 1.0) > NORMAL_LEN_TOL

    z = n[:, :, 2]
    y = n[:, :, 1]
    # A convex bump has +Y above centre in OpenGL and -Y in DirectX. The
    # honest test: correlate G against the height gradient implied by the
    # map itself. Simpler and reliable: the SIGN of the mean of G along
    # the vertical gradient of the reconstructed height.
    gy = np.gradient(z, axis=0)
    corr = float(np.mean(gy * y))

    return {
        "unit_length": {
            "mean": round(float(length.mean()), 4),
            "min": round(float(length.min()), 4),
            "max": round(float(length.max()), 4),
            "off_spec_fraction": round(float(bad.mean()), 4),
            "ok": bool(bad.mean() < 0.02),
        },
        "z_channel": {
            "mean": round(float(z.mean()), 4),
            "negative_fraction": round(float((z < 0).mean()), 4),
            "ok": bool(z.mean() > 0.5 and (z < 0).mean() < 0.001),
        },
        "green_convention": {
            "gradient_correlation": round(corr, 6),
            "likely": "OpenGL (+Y up)" if corr >= 0 else "DirectX (-Y up)",
            "note": ("a guess from the map's own statistics, not a fact "
                     "in the file: no format records the convention. "
                     "Confirm against what the engine expects"),
        },
        "flat_fraction": round(float(((np.abs(n[:, :, 0]) < 0.02)
                                      & (np.abs(y) < 0.02)).mean()), 4),
    }


def channel_stats(img: np.ndarray, kind: str) -> dict:
    """Statistics for a data map (roughness, metallic, AO, height).

    These are DATA, not pictures: a roughness map that never leaves
    0.4..0.6 wastes its whole range, and one with 3 unique values was
    quantised to death somewhere in the pipeline.
    """
    g = img[:, :, 0] if img.shape[2] == 1 else img[:, :, :3].mean(axis=2)
    hist, _ = np.histogram(g, bins=256, range=(0.0, 1.0))
    used = int((hist > 0).sum())
    q = np.percentile(g, [1, 25, 50, 75, 99])

    out = {
        "kind": kind,
        "mean": round(float(g.mean()), 4),
        "std": round(float(g.std()), 4),
        "min": round(float(g.min()), 4),
        "max": round(float(g.max()), 4),
        "percentiles": {"p1": round(float(q[0]), 4),
                        "p25": round(float(q[1]), 4),
                        "p50": round(float(q[2]), 4),
                        "p75": round(float(q[3]), 4),
                        "p99": round(float(q[4]), 4)},
        "distinct_levels_of_256": used,
        "range_used": round(float(q[4] - q[0]), 4),
        "is_constant": bool(g.std() < 1e-4),
    }
    if img.shape[2] >= 3:
        spread = float(np.abs(img[:, :, :3] - g[:, :, None]).max())
        out["is_grayscale"] = bool(spread < 0.02)
        out["channel_spread"] = round(spread, 4)
    return out


def compression_artifacts(img: np.ndarray) -> dict:
    """JPEG/DXT blocking: energy at the 8x8 (and 4x4) block boundaries
    that is not there in between.

    Compare the mean gradient ON block edges against the mean gradient
    elsewhere. A clean image has no reason to prefer multiples of 8.
    """
    g = img[:, :, :3].mean(axis=2) if img.shape[2] >= 3 else img[:, :, 0]
    h, w = g.shape
    out = {}
    for block in (8, 4):
        if w < block * 4 or h < block * 4:
            continue
        axes = {}
        for axis, name in ((1, "x"), (0, "y")):
            d = np.abs(np.diff(g, axis=axis))
            n = d.shape[axis]
            on = (np.arange(n) + 1) % block == 0
            if on.sum() == 0 or (~on).sum() == 0:
                continue
            edge = float(d[:, on].mean() if axis == 1 else d[on, :].mean())
            inter = float(d[:, ~on].mean() if axis == 1 else d[~on, :].mean())
            ratio = edge / inter if inter > 1e-9 else float("inf")
            axes[name] = {"edge_gradient": round(edge, 5),
                          "interior_gradient": round(inter, 5),
                          "ratio": round(ratio, 3) if np.isfinite(ratio)
                          else None}
        if len(axes) < 2:
            continue
        # A codec's grid is SQUARE: real blocking shows on both axes at
        # once. Testing columns alone calls a posterised gradient blocky
        # (its contour bands happen to correlate with x but not y), and a
        # near-flat image divides by ~0 — hence the visibility floor too.
        both = all(a["ratio"] is not None and a["ratio"] > 1.25
                   and a["edge_gradient"] > 1.0 / 255.0
                   for a in axes.values())
        ratios = [a["ratio"] for a in axes.values() if a["ratio"] is not None]
        out[f"block_{block}"] = {
            **{f"{k}_{kk}": vv for k, v in axes.items()
               for kk, vv in v.items()},
            # None when an axis has no gradient at all to compare against
            # (a flat image): that is "unmeasurable", not "clean" — and
            # it must not crash on an empty min() either.
            "ratio": min(ratios) if ratios else None,
            "blocking": bool(both),
        }
    out["note"] = ("gradient energy on block boundaries vs between them, "
                   "measured on BOTH axes: a codec's grid is square, so "
                   "blocking is only flagged when x and y both exceed "
                   "1.25x with a visible (>1/255) edge step")
    return out
