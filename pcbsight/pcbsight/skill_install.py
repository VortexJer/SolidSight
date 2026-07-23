"""Self-hosting of the Claude Code skill (same contract as solidsight)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from . import __version__

MARKER = ".installed-version"
SUBDIRS = ()


def default_skill_dir() -> Path:
    return Path.home() / ".claude" / "skills" / "pcbsight"


def _source() -> Path:
    return Path(str(resources.files("pcbsight") / "skill_data"))


def install_skill(target: Path | None = None, quiet: bool = False) -> Path:
    dst = Path(target) if target else default_skill_dir()
    src = _source()
    if not (src / "SKILL.md").exists():
        raise RuntimeError(
            f"packaged skill data missing at {src} — reinstall "
            "pcbsight")
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "SKILL.md", dst / "SKILL.md")
    for sub in SUBDIRS:
        sub_dst = dst / sub
        if sub_dst.exists():
            shutil.rmtree(sub_dst)
        if (src / sub).is_dir():
            shutil.copytree(src / sub, sub_dst)
    (dst / MARKER).write_text(__version__, encoding="utf-8")
    if not quiet:
        print(f"pcbsight skill v{__version__} installed at {dst}")
    return dst


def _installed(name: str) -> bool:
    """Is this distribution installed right now?"""
    from importlib.metadata import PackageNotFoundError, version
    try:
        version(name)
    except PackageNotFoundError:
        return False
    return True


def _drop_umbrella() -> int:
    """`pip install aisight` pulls the five tools in as dependencies, so
    removing one of them leaves the umbrella behind requiring a package
    that is gone — a broken install pip will complain about. The umbrella
    goes with it. The other four tools are untouched: pip does not
    cascade, and they were never aisight's to remove."""
    if not _installed("aisight"):
        return 0
    print("also removing the aisight umbrella (it requires pcbsight) — "
          "the other tools stay")
    return subprocess.call([sys.executable, "-m", "pip", "uninstall",
                            "-y", "aisight"])


def uninstall(remove_package: bool = True) -> int:
    dst = default_skill_dir()
    if dst.exists():
        shutil.rmtree(dst)
        print(f"removed skill: {dst}")
    else:
        print(f"skill was not installed (nothing at {dst})")
    if remove_package:
        print("removing the pcbsight package...")
        code = subprocess.call([sys.executable, "-m", "pip", "uninstall",
                                "-y", "pcbsight"])
        return _drop_umbrella() or code
    return 0


def maybe_autoinstall() -> None:
    """Silent self-hosting; never raises — a failure here must not break
    an inspection."""
    try:
        if not (Path.home() / ".claude").is_dir():
            return
        dst = default_skill_dir()
        marker = dst / MARKER
        if dst.exists() and marker.exists() and \
                marker.read_text(encoding="utf-8").strip() == __version__:
            return
        fresh = not dst.exists()
        install_skill(dst, quiet=True)
        print(("pcbsight: Claude Code skill installed at "
               if fresh else
               "pcbsight: Claude Code skill updated at ") + str(dst),
              file=sys.stderr)
    except Exception:
        pass
