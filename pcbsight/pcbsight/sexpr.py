"""A small s-expression reader for KiCad files.

KiCad's .kicad_pcb is a lisp-style tree: (kicad_pcb (net 1 "GND")
(segment (start 10 20) ...)). This reads it into nested Python lists,
with atoms as str/int/float. It reads what it needs and nothing more —
no writing, no round-tripping.
"""

from __future__ import annotations

from .errors import BadBoardError


def parse(text: str, source: str = "board") -> list:
    """Parse ONE toplevel s-expression into nested lists."""
    tokens = _tokenize(text)
    if not tokens:
        raise BadBoardError(f"{source}: empty file")
    pos = 0

    def read():
        nonlocal pos
        if pos >= len(tokens):
            raise BadBoardError(f"{source}: unexpected end of file "
                                "(unbalanced parentheses)")
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            out = []
            while True:
                if pos >= len(tokens):
                    raise BadBoardError(f"{source}: unbalanced '('")
                if tokens[pos] == ")":
                    pos += 1
                    return out
                out.append(read())
        if tok == ")":
            raise BadBoardError(f"{source}: stray ')'")
        return _atom(tok)

    expr = read()
    return expr


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
        elif c in "()":
            out.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            out.append('"' + "".join(buf))       # keep a marker for strings
            i = j + 1
        else:
            j = i
            while j < n and text[j] not in ' \t\r\n()"':
                j += 1
            out.append(text[i:j])
            i = j
    return out


def _atom(tok: str):
    if tok.startswith('"'):
        return tok[1:]
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


# --- tree helpers ----------------------------------------------------------

def children(node: list, tag: str) -> list[list]:
    """All child lists whose first atom is `tag`."""
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def child(node: list, tag: str) -> list | None:
    cs = children(node, tag)
    return cs[0] if cs else None


def value(node: list, tag: str, default=None):
    """The single value of (tag value)."""
    c = child(node, tag)
    if c is None or len(c) < 2:
        return default
    return c[1]


def values(node: list, tag: str) -> list:
    """All values of (tag v1 v2 ...)."""
    c = child(node, tag)
    return c[1:] if c else []
