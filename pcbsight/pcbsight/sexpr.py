"""A small s-expression reader/writer for KiCad files.

KiCad's .kicad_pcb is a lisp-style tree: (kicad_pcb (net 1 "GND")
(segment (start 10 20) ...)). `parse` reads it into nested Python
lists with atoms as str/int/float; `dumps`/`save` write a tree back,
which is what makes EDITING a board possible: load -> modify the tree
-> save -> inspect again.

One honest caveat: parsing loses the quoted-vs-bare distinction on
strings, so the writer quotes every string except each node's tag.
That is legal s-expression syntax and KiCad's reader unquotes tokens
generically, but the re-written file is not byte-identical to the
original — run `pcbsight inspect` on the result to prove the edit
did what it meant.
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


# --- writing (the edit loop's other half) ----------------------------------

def _fmt_atom(a, is_tag: bool = False) -> str:
    if isinstance(a, float):
        return repr(a)                      # repr round-trips exactly
    if isinstance(a, int):
        return str(a)
    s = str(a)
    if is_tag and s and not any(c in s for c in ' \t\r\n()"\\'):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _fmt(node, indent: int) -> str:
    if not isinstance(node, list):
        return _fmt_atom(node)
    parts = [_fmt_atom(node[0], is_tag=True) if node else ""]
    flat = all(not isinstance(c, list) for c in node[1:])
    body = [_fmt_atom(c) for c in node[1:]] if flat else None
    if flat and sum(len(b) for b in body) + len(parts[0]) < 76 - indent:
        return "(" + " ".join(parts + body) + ")"
    ind = "  " * (indent // 2 + 1)
    lines = ["(" + parts[0]]
    for c in node[1:]:
        lines.append(ind + _fmt(c, indent + 2))
    lines.append("  " * (indent // 2) + ")")
    return "\n".join(lines)


def dumps(node: list) -> str:
    """Serialise a tree from `parse` back to s-expression text."""
    return _fmt(node, 0) + "\n"


def load(path) -> list:
    from pathlib import Path
    p = Path(path)
    return parse(p.read_text(encoding="utf-8", errors="replace"), p.name)


def save(node: list, path) -> None:
    from pathlib import Path
    Path(path).write_text(dumps(node), encoding="utf-8")
