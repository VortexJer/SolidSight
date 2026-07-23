"""Everything AISight leaves on a machine, and how to take it back off.

Four kinds of leftovers, and they are NOT the same risk:

  skill      ~/.claude/skills/<tool>/          ours, generated, safe
  package    the pip distribution              ours, safe
  plugin     ~/.claude/plugins/marketplaces/   ours, only the aisight one
  checkout   a git clone of the repo           YOURS. never guessed.

The first three are found by name and removed. The fourth is only ever
removed when you point at it, and only after this module has checked
that the directory really is an AISight checkout — a wrong path here
would delete somebody's work, so "looks about right" is not enough.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import TOOLS

MARKETPLACE = "aisight"


def claude_home() -> Path:
    return Path.home() / ".claude"


def skill_dir(tool: str) -> Path:
    return claude_home() / "skills" / tool


def marketplace_dir() -> Path:
    return claude_home() / "plugins" / "marketplaces" / MARKETPLACE


def installed_version(tool: str) -> str | None:
    """The installed version of a tool, or None if it is not installed."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:                                  # pragma: no cover
        return None
    try:
        return version(tool)
    except PackageNotFoundError:
        return None


@dataclass
class Plan:
    """What a run would touch. Printed before anything is deleted."""
    skills: list[Path] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    plugin: list[Path] = field(default_factory=list)
    checkout: Path | None = None

    @property
    def empty(self) -> bool:
        return not (self.skills or self.packages or self.plugin
                    or self.checkout)

    def lines(self) -> list[str]:
        out = []
        for p in self.skills:
            out.append(f"  skill      {p}")
        for name in self.packages:
            v = installed_version(name)
            out.append(f"  package    {name} {v or ''}".rstrip())
        for p in self.plugin:
            out.append(f"  plugin     {p}")
        if self.checkout:
            out.append(f"  checkout   {self.checkout}   (a git clone)")
        return out


def is_checkout(path: Path) -> bool:
    """True only for a real AISight working copy.

    Checked hard on purpose: this is the one path the user hands us, and
    the one deletion that could destroy work that is not ours.
    """
    path = Path(path)
    mk = path / ".claude-plugin" / "marketplace.json"
    if not mk.is_file():
        return False
    try:
        data = json.loads(mk.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if data.get("name") != MARKETPLACE:
        return False
    # and the five tools must actually be there
    return all((path / t / "pyproject.toml").is_file() for t in TOOLS)


def make_plan(tools=TOOLS, packages: bool = True, plugin: bool = True,
              checkout: Path | None = None) -> Plan:
    plan = Plan()
    for t in tools:
        if skill_dir(t).is_dir():
            plan.skills.append(skill_dir(t))
        if packages and installed_version(t):
            plan.packages.append(t)
    if plugin:
        if marketplace_dir().exists():
            plan.plugin.append(marketplace_dir())
        reg = claude_home() / "plugins" / "known_marketplaces.json"
        if reg.is_file() and _registry_has_us(reg):
            plan.plugin.append(reg)
    if checkout is not None:
        plan.checkout = Path(checkout)
    return plan


def _registry_has_us(reg: Path) -> bool:
    try:
        return MARKETPLACE in json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False


def _drop_from_registry(reg: Path, say) -> None:
    """Take our marketplace out of the registry, leave everyone else's."""
    try:
        data = json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if MARKETPLACE not in data:
        return
    del data[MARKETPLACE]
    reg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    say(f"unregistered marketplace '{MARKETPLACE}' from {reg.name}")


def run(plan: Plan, say=print, pip: bool = True) -> int:
    """Carry out a plan. Returns a process exit code."""
    failed = 0
    for d in plan.skills:
        shutil.rmtree(d, ignore_errors=True)
        say(f"removed skill      {d}")
    for p in plan.plugin:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            say(f"removed plugin     {p}")
        elif p.name == "known_marketplaces.json":
            _drop_from_registry(p, say)
    if plan.checkout is not None:
        shutil.rmtree(plan.checkout, ignore_errors=True)
        say(f"removed checkout   {plan.checkout}")
    if plan.packages and pip:
        say(f"removing packages: {', '.join(plan.packages)}")
        failed = subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                  "-y", *plan.packages])
    return failed
