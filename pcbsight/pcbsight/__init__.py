"""pcbsight — PCB review built exclusively for AI agents.

A layout is judged by eyeballing the copper. But an open net is a
union-find question, a clearance is a segment distance, current capacity
is IPC-2221 arithmetic, and pair skew is a subtraction. So compute them.

    from pcbsight import parse_board, analyze
"""

__version__ = "0.5.1"

from .board import Board, Pad, Track, Via, parse_board
from .sexpr import dumps as sexpr_dumps
from .sexpr import load as load_sexpr
from .sexpr import save as save_sexpr
from .checks import (clearance, connectivity, current_capacity, diff_pairs,
                     microstrip_z0)
from .errors import BadArgumentError, BadBoardError, PCBSightError
from .report import analyze, inspect

__all__ = [
    "parse_board", "Board", "Track", "Via", "Pad",
    "load_sexpr", "save_sexpr", "sexpr_dumps",
    "analyze", "inspect", "connectivity", "clearance",
    "current_capacity", "diff_pairs", "microstrip_z0",
    "PCBSightError", "BadBoardError", "BadArgumentError",
]
