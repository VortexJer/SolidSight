"""A human-facing preview: one HTML page with the verdict and every
evidence render in an out directory, opened in the default browser.

The agent never needs this — report.json and the renders are its
interface. This is for the person the agent works for: end the last
run with `--show` (or run `preview out/`) and a page pops up with
everything worth looking at.
"""

from __future__ import annotations

import html
import json
import webbrowser
from pathlib import Path

TOOL = __name__.split(".")[0]

_COLORS = {"ok": "#2e7d32", "warnings": "#b26a00", "failed": "#b71c1c"}


def _check_line(c: dict) -> str:
    lvl = str(c.get("level", ""))
    main = ""
    for key in ("what", "summary", "message", "msg", "text", "id"):
        if c.get(key):
            main = str(c[key])
            break
    where = str(c.get("where", "") or "")
    out = f"<li><b>[{html.escape(lvl.upper())}]</b> {html.escape(main)}"
    if where:
        out += f"<br><small>{html.escape(where)}</small>"
    return out + "</li>"


def build_preview(out_dir: str | Path) -> Path:
    """Write out_dir/index.html collecting verdict + renders. Returns
    the page path; separate from show() so tests never open a browser."""
    out = Path(out_dir)
    if not out.is_dir():
        raise SystemExit(f"{TOOL} preview: {out} is not a directory "
                         "(pass the --out directory of a previous run)")
    status, checks = "", []
    rep = out / "report.json"
    if rep.exists():
        try:
            data = json.loads(rep.read_text(encoding="utf-8"))
            status = str(data.get("status", ""))
            checks = list(data.get("checks", []) or [])
        except (OSError, ValueError):
            pass
    imgs = sorted(p.name for p in out.iterdir()
                  if p.suffix.lower() in (".png", ".gif"))
    # animated evidence first: a person clicks play before reading curves
    imgs.sort(key=lambda n: (not n.endswith(".gif"), n))
    color = _COLORS.get(status, "#444")
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>{TOOL} - {html.escape(out.name)}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:2rem auto;"
        "max-width:960px;padding:0 1rem;color:#222;background:#fafaf8}"
        "img{max-width:100%;border:1px solid #ddd;border-radius:4px;"
        "margin:.5rem 0;background:#fff}h1{font-size:1.25rem}"
        "h3{margin:1.2rem 0 0;font-size:.95rem;color:#555}"
        "code{background:#f0f0ee;padding:.1em .3em;border-radius:3px}"
        ".st{font-weight:700}li{margin:.35em 0}</style>",
        f"<h1>{TOOL} · <code>{html.escape(str(out))}</code></h1>",
    ]
    if status:
        parts.append(f"<p class='st' style='color:{color}'>verdict: "
                     f"{html.escape(status.upper())}</p>")
    if checks:
        parts.append("<ul>" + "".join(_check_line(c) for c in checks)
                     + "</ul>")
    for name in imgs:
        parts.append(f"<h3>{html.escape(name)}</h3>"
                     f"<img src='{html.escape(name)}' alt=''>")
    if rep.exists():
        parts.append("<p><a href='report.json'>report.json</a></p>")
    page = out / "index.html"
    page.write_text("\n".join(parts), encoding="utf-8")
    return page


def show(out_dir: str | Path) -> Path:
    page = build_preview(out_dir)
    webbrowser.open(page.resolve().as_uri())
    return page
