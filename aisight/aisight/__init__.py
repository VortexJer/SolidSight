"""AISight: the family command.

The five tools are independent pip packages on purpose — install one,
some or all. What they do NOT have is a place that knows about all of
them at once, which is exactly what you want when you are leaving:
five skills, five packages, a plugin marketplace and maybe a checkout.
That is this package's whole job.
"""

__version__ = "0.1.0"

TOOLS = ("solidsight", "animationsight", "texturesight", "shadersight",
         "pcbsight")

__all__ = ["TOOLS", "__version__"]
