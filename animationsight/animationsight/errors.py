"""Errors written for a model to read: what failed, where, what to try."""

from __future__ import annotations


class AnimationSightError(Exception):
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


class BadClipError(AnimationSightError):
    """The clip file is missing, malformed, or not what it claims."""


class BadArgumentError(AnimationSightError):
    """A caller passed something the API cannot honour."""
