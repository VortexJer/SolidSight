"""Live development mode: rebuild on every source change.

`solidsight watch model.py [build flags]` polls the model file and its
sibling .py files (shared params.py etc.), rebuilds when they change, and
skips work it can prove unnecessary:

* identical scene fingerprint -> the edit was cosmetic (comments, prints):
  renders, report and exports are all left untouched and the loop says so;
* per-part mesh fingerprints -> exports of unchanged parts are reused.

The fingerprint is exact (hash of every part's mesh bytes + name + color +
ghost flag + the build options that shape the output), so a "skipped" build
is byte-for-byte what a full rebuild would have produced.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .errors import SolidsightError
from .events import BUS
from .runner import run_model


def part_fingerprint(part) -> str:
    """Exact content hash of one part as it affects any build artifact."""
    tm = part.solid.to_trimesh()
    h = hashlib.sha1()
    h.update(tm.vertices.tobytes())
    h.update(tm.faces.tobytes())
    h.update(f"{part.name}|{part.color}|{part.ghost}".encode())
    return h.hexdigest()


def scene_fingerprint(scene, build_opts: dict) -> tuple[str, dict[str, str]]:
    """(whole-scene hash incl. build options, per-part hashes)."""
    parts = {p.name: part_fingerprint(p) for p in scene.parts}
    h = hashlib.sha1()
    for name in sorted(parts):
        h.update(f"{name}={parts[name]}".encode())
    for e in scene.expectations:
        h.update(repr(sorted(e.items())).encode())
    for w in scene.warnings:
        h.update(repr(sorted(w.items())).encode())
    h.update(repr(sorted(build_opts.items(), key=str)).encode())
    return h.hexdigest(), parts


def watched_files(model_path: Path) -> dict[Path, tuple[float, int]]:
    """The model + every sibling .py (models import shared params files)."""
    files = {}
    for p in sorted(model_path.resolve().parent.glob("*.py")):
        try:
            st = p.stat()
            files[p] = (st.st_mtime, st.st_size)
        except OSError:
            pass
    return files


def run_watch(model_path: Path, build_kwargs: dict, say,
              poll_s: float = 0.5, on_build=None,
              max_builds: int | None = None) -> int:
    """The watch loop. `say` is the CLI printer; `on_build(report|None,
    error|None)` notifies integrations (the browser viewer); `max_builds`
    exists for tests."""
    from .report import build_model

    opts_key = {k: str(v) for k, v in build_kwargs.items()
                if k not in ("out_dir",)}
    last_fp: str | None = None
    last_parts: dict[str, str] = {}
    builds = 0

    def build_once(reason: str) -> None:
        nonlocal last_fp, last_parts, builds
        builds += 1
        t0 = time.monotonic()
        try:
            with BUS.stage("model", f"executing {model_path.name}"):
                scene = run_model(model_path)
            fp, parts = scene_fingerprint(scene, opts_key)
            if fp == last_fp:
                say(f"build #{builds}: no geometric change ({reason}) — "
                    f"outputs untouched "
                    f"[{time.monotonic() - t0:.1f}s]")
                if on_build:
                    on_build(None, None, None)
                return
            unchanged = {n for n, h in parts.items()
                         if last_parts.get(n) == h}
            report = build_model(model_path, scene=scene,
                                 unchanged_parts=unchanged, **build_kwargs)
            last_fp, last_parts = fp, parts
            n_fail = sum(1 for c in report["checks"] if c["level"] == "fail")
            n_warn = sum(1 for c in report["checks"] if c["level"] == "warn")
            say(f"build #{builds}: {report['status'].upper()} "
                f"({n_fail} fail, {n_warn} warn) "
                f"[{time.monotonic() - t0:.1f}s] — {reason}")
            if on_build:
                on_build(report, None, scene)
        except SolidsightError as e:
            say(f"build #{builds}: BUILD FAILED [{time.monotonic() - t0:.1f}s]"
                f" — {reason}")
            say(e.render())
            if on_build:
                on_build(None, e, None)

    build_once("initial build")
    say(f"watching {model_path.parent} for .py changes "
        f"(ctrl-c to stop) ...")

    state = watched_files(model_path)
    try:
        while max_builds is None or builds < max_builds:
            time.sleep(poll_s)
            now = watched_files(model_path)
            if now != state:
                changed = sorted(
                    p.name for p in (now.keys() | state.keys())
                    if now.get(p) != state.get(p))
                # debounce: wait for the files to stop moving (editors write
                # in bursts), then rebuild once
                while True:
                    time.sleep(0.2)
                    settled = watched_files(model_path)
                    if settled == now:
                        break
                    now = settled
                state = now
                build_once("changed: " + ", ".join(changed))
    except KeyboardInterrupt:
        say("watch stopped.")
    return 0
