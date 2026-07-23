"""`aisight` — the one command that knows about all five tools."""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import TOOLS, __version__
from .clean import (Plan, installed_version, is_checkout, make_plan,
                    marketplace_dir, run, skill_dir)


def _status() -> int:
    print(f"aisight {__version__}\n")
    width = max(len(t) for t in TOOLS)
    for t in TOOLS:
        v = installed_version(t)
        skill = "skill" if skill_dir(t).is_dir() else "     "
        print(f"  {t:<{width}}  {v or '-':<10} {skill}")
    mk = marketplace_dir()
    print(f"\n  plugin marketplace: {mk if mk.exists() else 'not installed'}")
    return 0


def _uninstall(args) -> int:
    tools = args.only or list(TOOLS)
    bad = [t for t in tools if t not in TOOLS]
    if bad:
        print(f"aisight: not an AISight tool: {', '.join(bad)}",
              file=sys.stderr)
        return 2

    checkout = None
    if args.repo:
        if not is_checkout(args.repo):
            print(f"aisight: {args.repo} is not an AISight checkout — "
                  "refusing to delete it.\n"
                  "         (expected .claude-plugin/marketplace.json plus "
                  "the five tool folders)", file=sys.stderr)
            return 2
        checkout = args.repo

    # the plugin and the checkout belong to the family, not to one tool:
    # only touch them when the whole family is going
    whole = set(tools) == set(TOOLS)
    plan = make_plan(tools, packages=not args.keep_packages,
                     plugin=whole, checkout=checkout)
    if plan.empty:
        print("nothing to remove — AISight is not installed here")
        return 0

    print("this will remove:")
    for line in plan.lines():
        print(line)
    if args.dry_run:
        print("\n(dry run — nothing was touched)")
        return 0
    if not args.yes:
        try:
            if input("\nproceed? [y/N] ").strip().lower() not in ("y", "yes"):
                print("cancelled")
                return 1
        except EOFError:
            print("cancelled (no answer)")
            return 1

    code = run(plan)
    # this package goes last: pip cannot remove it while it is the one
    # doing the removing on every platform, so it is its own step
    if whole and not args.keep_packages and installed_version("aisight"):
        print("removing packages: aisight")
        code = subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                "-y", "aisight"]) or code
    print("\ndone." if not code else "\ndone, with pip errors above.")
    return code


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="aisight",
        description="The AISight family: solidsight, animationsight, "
                    "texturesight, shadersight, pcbsight.")
    p.add_argument("--version", action="version",
                   version=f"aisight {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("status", help="what is installed on this machine")

    u = sub.add_parser(
        "uninstall",
        help="remove the skills, the packages and the plugin marketplace")
    u.add_argument("--only", nargs="+", metavar="TOOL",
                   help="uninstall just these tools (default: all five)")
    u.add_argument("--repo", metavar="PATH",
                   help="also delete a git checkout of the repo — verified "
                        "to be an AISight working copy first")
    u.add_argument("--keep-packages", action="store_true",
                   help="remove the skills and the plugin, keep pip")
    u.add_argument("--dry-run", action="store_true",
                   help="print what would go, touch nothing")
    u.add_argument("-y", "--yes", action="store_true",
                   help="do not ask for confirmation")

    args = p.parse_args(argv)
    if args.command == "uninstall":
        return _uninstall(args)
    if args.command == "status":
        return _status()
    p.print_help()
    return 0


__all__ = ["main", "Plan"]

if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
