"""Error types designed to be read by an LLM agent, not a human at a console.

Every error carries: what failed, where (names / coordinates / bounding boxes),
and a concrete suggestion of what to try next. Generic messages like
"invalid geometry" are forbidden by design.
"""

from __future__ import annotations


def fmt_num(x: float) -> str:
    """Format a number compactly for messages: 12.0 -> '12', 12.345 -> '12.345'."""
    r = round(float(x), 3)
    if r == int(r):
        return str(int(r))
    return f"{r:g}"


def fmt_vec(v) -> str:
    return "(" + ", ".join(fmt_num(c) for c in v) + ")"


def fmt_bbox(bbox) -> str:
    """bbox: ((minx,miny,minz),(maxx,maxy,maxz)) -> 'x 0..10, y -5..5, z 0..3'."""
    lo, hi = bbox
    axes = "xyz"
    return ", ".join(
        f"{axes[i]} {fmt_num(lo[i])}..{fmt_num(hi[i])}" for i in range(3)
    )


class SolidsightError(Exception):
    """Base error. Renders as:  <code>: <message>\\n  where: ...\\n  try: ..."""

    code = "solidsight-error"

    def __init__(self, message: str, where: str | None = None,
                 suggestion: str | None = None):
        self.message = message
        self.where = where
        self.suggestion = suggestion
        super().__init__(self.render())

    def render(self) -> str:
        lines = [f"{self.code}: {self.message}"]
        if self.where:
            lines.append(f"  where: {self.where}")
        if self.suggestion:
            lines.append(f"  try: {self.suggestion}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "where": self.where,
            "suggestion": self.suggestion,
        }


class EmptyGeometryError(SolidsightError):
    code = "empty-geometry"


class BadArgumentError(SolidsightError):
    code = "bad-argument"


class SceneError(SolidsightError):
    code = "scene-error"


class ModelRuntimeError(SolidsightError):
    """A Python error inside the user's model file, re-packaged with the
    offending source line and a suggestion."""

    code = "model-error"
