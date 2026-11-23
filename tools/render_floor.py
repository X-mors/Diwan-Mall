# -*- coding: utf-8 -*-
"""
Render one floor of the Diwan plans to PNG (matplotlib), in the LOCAL axis-aligned
frame (building rotation removed), coloured by layer.  Used for visual review.

    python tools/render_floor.py 3                       # whole building, F03
    python tools/render_floor.py 5 --zoom 0 0 10 10      # local-frame window (m)
    python tools/render_floor.py 2 --layers W WIN Etabs-col --out output/f2_walls.png

Overlay API (for other tools):  ax, fl = base_axes(floor_no, layers=...) then plot
in local coordinates and fig.savefig(...).
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import OUT_DIR, floor_entities, floor_texts, get_floor  # noqa: E402

plt.rcParams["font.family"] = "Tahoma"

LAYER_COLORS = {
    "W": "#d62728", "WIN": "#17becf", "Etabs-col": "#2ca02c", "COL": "#006400",
    "DASH": "#bcbd22", "ST": "#8c564b", "PR": "#9467bd", "try": "#ff7f0e",
    "X": "#ff9999", "MASS": "#7f7f7f", "HAT": "#aaaaaa", "FUR": "#c7c7c7",
    "DIM": "#98df8a", "TEXT": "#333333", "TEXT-D": "#555555",
}
DEFAULT_LAYERS = ["W", "WIN", "Etabs-col", "COL", "ST", "DASH", "PR", "try"]


def _segments(e, fl, depth=0):
    """Yield polylines (list of local points) approximating an entity (INSERTs exploded)."""
    t = e.dxftype()
    try:
        if t == "LINE":
            yield [fl.to_local(e.dxf.start.x, e.dxf.start.y), fl.to_local(e.dxf.end.x, e.dxf.end.y)]
        elif t == "LWPOLYLINE":
            pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
            if e.closed and pts:
                pts.append(pts[0])
            yield pts
        elif t in ("ARC", "CIRCLE"):
            c, r = e.dxf.center, e.dxf.radius
            a0, a1 = (e.dxf.start_angle, e.dxf.end_angle) if t == "ARC" else (0, 360)
            if a1 < a0:
                a1 += 360
            n = max(8, int((a1 - a0) / 6))
            yield [fl.to_local(c.x + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                               c.y + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
        elif t == "INSERT" and depth < 3:
            for v in e.virtual_entities():
                yield from _segments(v, fl, depth + 1)
        elif t == "HATCH":
            for path in e.paths:
                if hasattr(path, "vertices"):
                    pts = [fl.to_local(v[0], v[1]) for v in path.vertices]
                    if pts:
                        yield pts + [pts[0]]
    except Exception:
        return


def base_axes(floor_no, layers=None, zoom=None, figsize=(16, 30), texts=False, dpi_hint=None):
    fl = get_floor(floor_no)
    layers = layers or DEFAULT_LAYERS
    fig, ax = plt.subplots(figsize=figsize)
    for e in floor_entities(fl, layers=tuple(layers)):
        col = LAYER_COLORS.get(e.dxf.layer, "#000000")
        for pts in _segments(e, fl):
            if len(pts) >= 2:
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color=col, lw=0.6)
    if texts:
        for t in floor_texts(fl, layers=("TEXT", "-A-TEXT", "PR")):
            lx, ly = t["local"]
            ax.text(lx, ly, t["text"], fontsize=6, color="#222", clip_on=True)
    ax.set_aspect("equal")
    if zoom:
        ax.set_xlim(zoom[0], zoom[2])
        ax.set_ylim(zoom[1], zoom[3])
    else:
        # building region only (local frame of columns/windows +3 m)
        xs, ys = [], []
        for e in floor_entities(fl, layers=("Etabs-col", "WIN", "ST")):
            for pts in _segments(e, fl):
                for p in pts:
                    xs.append(p[0]); ys.append(p[1])
        if xs:
            ax.set_xlim(min(xs) - 3, max(xs) + 3)
            ax.set_ylim(min(ys) - 3, max(ys) + 3)
    ax.grid(True, lw=0.2)
    ax.set_title(f"{fl.label} {fl.name_ar} {fl.level:+.2f}  (local frame, m)")
    return fig, ax, fl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("floor", type=int)
    ap.add_argument("--layers", nargs="*")
    ap.add_argument("--zoom", nargs=4, type=float, help="local x0 y0 x1 y1")
    ap.add_argument("--texts", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--dpi", type=int, default=110)
    a = ap.parse_args()
    fig, ax, fl = base_axes(a.floor, a.layers, a.zoom, texts=a.texts)
    out = Path(a.out) if a.out else OUT_DIR / f"render_{fl.label}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=a.dpi, bbox_inches="tight")
    print("saved", out)


if __name__ == "__main__":
    main()
