"""Progress and event streaming: every subsystem reports what it is doing.

Agents drive long builds (a 30-part assembly renders and cross-checks for
minutes); this bus makes the wait observable. Events are live telemetry —
they carry wall-clock times — so they are NEVER written into the
deterministic artifacts (report.json, renders, exports). They go to a side
channel the caller opts into: a console progress line (--progress, stderr)
and/or an NDJSON stream (--events PATH).

Usage inside subsystems::

    from .events import BUS
    with BUS.stage("render", total=len(views)) as st:
        for v in views:
            ...
            st.tick(f"view {v}")

With no sinks attached (the default) emitting is a no-op dict build — cheap
enough to leave permanently instrumented.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


class _Stage:
    """Handle for one running stage; created by EventBus.stage()."""

    def __init__(self, bus: "EventBus", name: str, detail: str,
                 total: int | None):
        self.bus, self.name, self.total = bus, name, total
        self.detail = detail
        self.done = 0
        self.t0 = time.monotonic()

    def tick(self, detail: str = "", n: int = 1) -> None:
        """One unit of work finished inside this stage."""
        self.done += n
        pct = eta = None
        if self.total:
            pct = round(100.0 * self.done / self.total, 1)
            elapsed = time.monotonic() - self.t0
            if self.done > 0:
                eta = round(elapsed * (self.total - self.done) / self.done, 1)
        self.bus.emit(self.name, "progress", detail or self.detail,
                      pct=pct, eta_s=eta,
                      count=[self.done, self.total] if self.total else None)

    def __enter__(self) -> "_Stage":
        self.bus.emit(self.name, "start", self.detail,
                      pct=0.0 if self.total else None)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        dur = round(time.monotonic() - self.t0, 3)
        if exc_type is None:
            self.bus.emit(self.name, "done", self.detail, duration_s=dur,
                          pct=100.0 if self.total else None)
        else:
            self.bus.emit(self.name, "error", f"{exc_type.__name__}: {exc}",
                          duration_s=dur)


class EventBus:
    def __init__(self):
        self._sinks: list = []
        self._t0 = time.monotonic()
        self._seq = 0

    # -- sinks --------------------------------------------------------------
    def add_sink(self, fn) -> None:
        self._sinks.append(fn)

    def clear_sinks(self) -> None:
        self._sinks = []
        self._seq = 0
        self._t0 = time.monotonic()

    @property
    def active(self) -> bool:
        return bool(self._sinks)

    # -- emitting -----------------------------------------------------------
    def emit(self, stage: str, status: str, detail: str = "", **extra) -> None:
        if not self._sinks:
            return
        ev = {"seq": self._seq, "t_s": round(time.monotonic() - self._t0, 3),
              "stage": stage, "status": status, "detail": detail}
        ev.update({k: v for k, v in extra.items() if v is not None})
        self._seq += 1
        for sink in self._sinks:
            try:
                sink(ev)
            except Exception:
                pass  # a broken sink must never break a build

    def warn(self, stage: str, message: str) -> None:
        self.emit(stage, "warning", message)

    def stage(self, name: str, detail: str = "",
              total: int | None = None) -> _Stage:
        return _Stage(self, name, detail, total)


BUS = EventBus()


# ---------------------------------------------------------------------------

def console_sink(stream=None):
    """Human/agent-readable one-line-per-event progress on stderr."""
    out = stream or sys.stderr

    def sink(ev: dict) -> None:
        pct = f" {ev['pct']:5.1f}%" if ev.get("pct") is not None else ""
        cnt = ""
        if ev.get("count"):
            cnt = f" ({ev['count'][0]}/{ev['count'][1]})"
        eta = f" eta {ev['eta_s']}s" if ev.get("eta_s") is not None else ""
        dur = (f" [{ev['duration_s']}s]"
               if ev.get("duration_s") is not None else "")
        line = (f"[{ev['t_s']:7.1f}s] {ev['stage']}: {ev['status']}"
                f"{pct}{cnt}{eta}{dur}"
                + (f" - {ev['detail']}" if ev["detail"] else ""))
        print(line.encode("ascii", "replace").decode("ascii"),
              file=out, flush=True)

    return sink


def ndjson_sink(path: str | Path):
    """Structured machine stream: one JSON object per line, appended live."""
    f = open(path, "w", encoding="utf-8")

    def sink(ev: dict) -> None:
        f.write(json.dumps(ev) + "\n")
        f.flush()

    sink.close = f.close  # type: ignore[attr-defined]
    return sink
