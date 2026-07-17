"""Errors written for a model to read: what failed, where, what to try."""

from __future__ import annotations


class TextureSightError(Exception):
    def __init__(self, message: str, where: str | None = None,
                 suggestion: str | None = None):
        super().__init__(message)
        self.message = message
        self.where = where
        self.suggestion = suggestion

    def render(self) -> str:
        kind = type(self).__name__.replace("Error", "").lower()
        out = [f"{kind}-error: {self.message}"]
        if self.where:
            out.append(f"  where: {self.where}")
        if self.suggestion:
            out.append(f"  try:   {self.suggestion}")
        return "\n".join(out)


class BadMeshError(TextureSightError):
    """The mesh is missing, malformed, or has no UVs to audit."""


class BadTextureError(TextureSightError):
    """The image is missing, unreadable, or the wrong kind of map."""


class BadArgumentError(TextureSightError):
    """A caller passed something the API cannot honour."""
