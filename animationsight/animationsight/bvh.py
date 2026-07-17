"""BVH parsing and forward kinematics.

BVH is the lingua franca of mocap: a joint hierarchy with per-joint
offsets and channels, then one row of channel values per frame. Nothing
here is approximate — the parser reads what the file says and the FK
composes the exact transforms the format defines.

Everything is deterministic: same file in, same arrays out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .errors import BadClipError

_ROT = {"Xrotation": 0, "Yrotation": 1, "Zrotation": 2}
_POS = {"Xposition": 0, "Yposition": 1, "Zposition": 2}

# BVH files carry no unit. These are the conventions actually in the
# wild; the caller must pick one and the report states it.
UNITS_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}


@dataclass
class Joint:
    name: str
    offset: np.ndarray                      # (3,) in file units
    channels: list[str] = field(default_factory=list)
    children: list["Joint"] = field(default_factory=list)
    parent: "Joint | None" = None
    is_end: bool = False
    chan_start: int = 0                     # index into a motion row


@dataclass
class Clip:
    root: Joint
    joints: list[Joint]                     # depth-first, incl. end sites
    frames: np.ndarray                      # (F, C) raw channel values
    frame_time: float                       # seconds
    unit: str
    source: str

    @property
    def n_frames(self) -> int:
        return int(self.frames.shape[0])

    @property
    def fps(self) -> float:
        return 1.0 / self.frame_time if self.frame_time > 0 else 0.0

    @property
    def duration_s(self) -> float:
        return self.n_frames * self.frame_time

    @property
    def names(self) -> list[str]:
        return [j.name for j in self.joints]


def _tokens(text: str) -> list[str]:
    return text.replace("\t", " ").split()


def parse_bvh(path: str | Path, unit: str = "cm") -> Clip:
    """Read a .bvh file into a Clip. `unit` declares what the file's
    numbers mean (BVH does not say); everything downstream is mm."""
    p = Path(path)
    if not p.exists():
        raise BadClipError(f"clip not found: {p}",
                           suggestion="check the path")
    if unit not in UNITS_MM:
        raise BadClipError(
            f"unknown unit {unit!r}",
            suggestion="one of: " + ", ".join(UNITS_MM))
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise BadClipError(f"could not read {p.name}: {e}") from e

    up = text.upper()
    if "HIERARCHY" not in up or "MOTION" not in up:
        raise BadClipError(
            f"{p.name} is not a BVH file (no HIERARCHY/MOTION sections)",
            suggestion="animationsight reads .bvh mocap clips")
    h_txt, m_txt = re.split(r"\bMOTION\b", text, maxsplit=1,
                            flags=re.IGNORECASE)

    root, joints = _parse_hierarchy(h_txt, p.name)
    frames, frame_time = _parse_motion(m_txt, p.name)

    n_chan = sum(len(j.channels) for j in joints)
    if frames.shape[1] != n_chan:
        raise BadClipError(
            f"{p.name}: the hierarchy declares {n_chan} channels but the "
            f"motion rows carry {frames.shape[1]}",
            suggestion="the file is inconsistent or truncated; re-export it")
    return Clip(root=root, joints=joints, frames=frames,
                frame_time=frame_time, unit=unit, source=p.name)


def _parse_hierarchy(text: str, fname: str) -> tuple[Joint, list[Joint]]:
    toks = _tokens(text)
    i = 0
    if not toks or toks[0].upper() != "HIERARCHY":
        raise BadClipError(f"{fname}: expected HIERARCHY first")
    i += 1

    joints: list[Joint] = []
    stack: list[Joint] = []
    root: Joint | None = None
    chan_cursor = 0

    while i < len(toks):
        t = toks[i]
        tu = t.upper()
        if tu in ("ROOT", "JOINT"):
            name = toks[i + 1]
            j = Joint(name=name, offset=np.zeros(3),
                      parent=stack[-1] if stack else None)
            if stack:
                stack[-1].children.append(j)
            else:
                if root is not None:
                    raise BadClipError(
                        f"{fname}: a second ROOT ({name}) — one skeleton "
                        "per file",
                        suggestion="split multi-character files")
                root = j
            joints.append(j)
            stack.append(j)
            i += 2
        elif tu == "END":                       # "End Site"
            j = Joint(name=f"{stack[-1].name}_end", offset=np.zeros(3),
                      parent=stack[-1], is_end=True)
            stack[-1].children.append(j)
            joints.append(j)
            stack.append(j)
            i += 2
        elif t == "{":
            i += 1
        elif t == "}":
            if not stack:
                raise BadClipError(f"{fname}: unbalanced '}}' in HIERARCHY")
            stack.pop()
            i += 1
        elif tu == "OFFSET":
            try:
                stack[-1].offset = np.array(
                    [float(v) for v in toks[i + 1:i + 4]], dtype=float)
            except (ValueError, IndexError) as e:
                raise BadClipError(
                    f"{fname}: bad OFFSET for joint "
                    f"{stack[-1].name if stack else '?'}") from e
            i += 4
        elif tu == "CHANNELS":
            n = int(toks[i + 1])
            chans = toks[i + 2:i + 2 + n]
            unknown = [c for c in chans if c not in _ROT and c not in _POS]
            if unknown:
                raise BadClipError(
                    f"{fname}: joint {stack[-1].name} has unsupported "
                    f"channel(s) {unknown}",
                    suggestion="only X/Y/Zposition and X/Y/Zrotation "
                               "channels are defined by BVH")
            stack[-1].channels = chans
            stack[-1].chan_start = chan_cursor
            chan_cursor += n
            i += 2 + n
        else:
            i += 1

    if root is None:
        raise BadClipError(f"{fname}: no ROOT joint in HIERARCHY")
    if stack:
        raise BadClipError(f"{fname}: unbalanced braces in HIERARCHY")
    return root, joints


def _parse_motion(text: str, fname: str) -> tuple[np.ndarray, float]:
    m_frames = re.search(r"Frames:\s*(\d+)", text, re.IGNORECASE)
    m_time = re.search(r"Frame\s+Time:\s*([0-9.eE+-]+)", text, re.IGNORECASE)
    if not m_frames or not m_time:
        raise BadClipError(
            f"{fname}: MOTION needs 'Frames:' and 'Frame Time:' lines")
    n = int(m_frames.group(1))
    ft = float(m_time.group(1))
    if n < 2:
        raise BadClipError(
            f"{fname}: {n} frame(s) — motion needs at least 2",
            suggestion="a single pose has no velocity to measure")
    if ft <= 0:
        raise BadClipError(f"{fname}: Frame Time must be positive, got {ft}")

    body = text[m_time.end():]
    rows = [r for r in (line.strip() for line in body.splitlines()) if r]
    if len(rows) < n:
        raise BadClipError(
            f"{fname}: header says {n} frames but only {len(rows)} rows "
            "follow", suggestion="the file is truncated")
    try:
        data = np.array([[float(v) for v in r.split()] for r in rows[:n]],
                        dtype=float)
    except ValueError as e:
        raise BadClipError(f"{fname}: non-numeric value in the motion "
                           f"data: {e}") from e
    return data, ft


# ---------------------------------------------------------------------------
# forward kinematics
# ---------------------------------------------------------------------------

def _rot_matrix(axis: str, deg: np.ndarray) -> np.ndarray:
    """(F,3,3) rotation matrices about one axis for F angles."""
    r = np.radians(deg)
    c, s = np.cos(r), np.sin(r)
    one, zero = np.ones_like(c), np.zeros_like(c)
    if axis == "Xrotation":
        m = [[one, zero, zero], [zero, c, -s], [zero, s, c]]
    elif axis == "Yrotation":
        m = [[c, zero, s], [zero, one, zero], [-s, zero, c]]
    else:                                        # Zrotation
        m = [[c, -s, zero], [s, c, zero], [zero, zero, one]]
    return np.stack([np.stack(row, axis=-1) for row in m], axis=-2)


def forward_kinematics(clip: Clip) -> tuple[np.ndarray, np.ndarray]:
    """World positions and rotations for every joint, every frame.

    Returns (positions (F, J, 3) in mm, rotations (F, J, 3, 3)).
    Channels are applied in the order the file declares them — that
    order is part of the data, not a convention we get to choose.
    """
    scale = UNITS_MM[clip.unit]
    F = clip.n_frames
    J = len(clip.joints)
    pos = np.zeros((F, J, 3))
    rot = np.zeros((F, J, 3, 3))
    index = {id(j): k for k, j in enumerate(clip.joints)}

    for k, j in enumerate(clip.joints):
        local_t = np.tile(j.offset * scale, (F, 1))
        local_r = np.tile(np.eye(3), (F, 1, 1))

        for ci, ch in enumerate(j.channels):
            col = clip.frames[:, j.chan_start + ci]
            if ch in _POS:
                local_t[:, _POS[ch]] += col * scale
            else:
                local_r = local_r @ _rot_matrix(ch, col)

        if j.parent is None:
            pos[:, k] = local_t
            rot[:, k] = local_r
        else:
            pk = index[id(j.parent)]
            pos[:, k] = pos[:, pk] + np.einsum("fij,fj->fi",
                                               rot[:, pk], local_t)
            rot[:, k] = rot[:, pk] @ local_r
    return pos, rot
