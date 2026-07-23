"""AISight: the family command.

The five tools are independent pip packages on purpose — install one,
some or all, none depends on another. This one depends on all five, so
it is both ends of the family in a single command: `pip install aisight`
brings the whole thing in, `aisight uninstall` takes it all back off —
five skills, five packages, a plugin marketplace and, if you point at
one, a checkout.
"""

__version__ = "0.2.0"

TOOLS = ("solidsight", "animationsight", "texturesight", "shadersight",
         "pcbsight")

__all__ = ["TOOLS", "__version__"]
