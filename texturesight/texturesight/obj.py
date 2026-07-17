"""Minimal OBJ reader — geometry + UVs only.

texturesight needs exactly two things from a mesh: the triangles in 3D
and the same triangles in UV space. Everything else in the format is
someone else's problem, so this reads what it needs and says clearly
when what it needs is not there (an OBJ with no `vt` lines cannot be
texture-audited, and pretending otherwise would be the whole failure
mode of this tool).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .errors import BadMeshError


class Mesh:
    """Triangles in 3D and in UV space, plus their material groups."""

    def __init__(self, verts: np.ndarray, uvs: np.ndarray,
                 tri_v: np.ndarray, tri_uv: np.ndarray,
                 groups: dict[str, np.ndarray], source: str):
        self.verts = verts            # (V, 3)
        self.uvs = uvs                # (T, 2)
        self.tri_v = tri_v            # (F, 3) indices into verts
        self.tri_uv = tri_uv          # (F, 3) indices into uvs
        self.groups = groups          # material -> face index array
        self.source = source

    @property
    def n_faces(self) -> int:
        return int(len(self.tri_v))

    def face_area_3d(self) -> np.ndarray:
        p = self.verts[self.tri_v]                       # (F, 3, 3)
        return 0.5 * np.linalg.norm(
            np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)

    def face_area_uv(self) -> np.ndarray:
        """Signed UV area: the sign is the winding, and a flipped face
        (negative area where its neighbours are positive) is a real
        defect — mirrored normal maps, wrong-way anisotropy."""
        q = self.uvs[self.tri_uv]                        # (F, 3, 2)
        e1, e2 = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]
        return 0.5 * (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])


def parse_obj(path: str | Path) -> Mesh:
    p = Path(path)
    if not p.exists():
        raise BadMeshError(f"mesh not found: {p}", suggestion="check the path")
    verts: list[tuple[float, float, float]] = []
    uvs: list[tuple[float, float]] = []
    tri_v: list[tuple[int, int, int]] = []
    tri_uv: list[tuple[int, int, int]] = []
    groups: dict[str, list[int]] = {}
    current = "default"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise BadMeshError(f"could not read {p.name}: {e}") from e

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        tag = parts[0]
        if tag == "v":
            verts.append(tuple(float(x) for x in parts[1:4]))
        elif tag == "vt":
            uvs.append(tuple(float(x) for x in parts[1:3]))
        elif tag == "usemtl":
            current = parts[1] if len(parts) > 1 else "default"
        elif tag == "f":
            idx_v, idx_t = [], []
            for token in parts[1:]:
                bits = token.split("/")
                try:
                    vi = int(bits[0])
                except ValueError as e:
                    raise BadMeshError(
                        f"{p.name}:{lineno}: bad face index {token!r}") from e
                ti = int(bits[1]) if len(bits) > 1 and bits[1] else 0
                idx_v.append(vi - 1 if vi > 0 else len(verts) + vi)
                idx_t.append((ti - 1 if ti > 0 else len(uvs) + ti)
                             if ti else -1)
            if len(idx_v) < 3:
                raise BadMeshError(f"{p.name}:{lineno}: face with "
                                   f"{len(idx_v)} vertices")
            # fan-triangulate polygons; the winding is preserved
            for k in range(1, len(idx_v) - 1):
                groups.setdefault(current, []).append(len(tri_v))
                tri_v.append((idx_v[0], idx_v[k], idx_v[k + 1]))
                tri_uv.append((idx_t[0], idx_t[k], idx_t[k + 1]))

    if not verts or not tri_v:
        raise BadMeshError(f"{p.name} contains no triangles")
    tri_uv_arr = np.array(tri_uv, dtype=np.int64)
    if (tri_uv_arr < 0).any() or not uvs:
        raise BadMeshError(
            f"{p.name} has no UV coordinates on some or all faces",
            where=f"{int((tri_uv_arr < 0).any(axis=1).sum())} of "
                  f"{len(tri_uv_arr)} faces lack UVs",
            suggestion="texturesight audits UV/texture work, so the mesh "
                       "must be unwrapped: export from your DCC tool with "
                       "'include UVs' / 'texture coordinates' enabled")
    return Mesh(np.array(verts, dtype=float), np.array(uvs, dtype=float),
                np.array(tri_v, dtype=np.int64), tri_uv_arr,
                {k: np.array(v, dtype=np.int64) for k, v in groups.items()},
                p.name)
