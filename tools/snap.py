"""
Screenshots of the drawings for questions / reports, in the common architectural LOCAL frame.

    arch_draw(ax, floor_no, zoom)        architectural floor (layers W, WIN, Etabs-col, COL, ST, DASH, MASS, TEXT ...)
    str_draw(ax, ceiling_of, zoom)       structural ceiling sheet of that floor (Slab edge, Etabs-Slab, BEAMS,
                                         Etabs-col, slab thickness, beam / thickness texts)
    Both draw with the drawing's own Arabic text (decoded + shaped), so a crop reads like the sheet.

    python tools/snap.py arch 6 0 26 18 40 out.png
    python tools/snap.py str 6 0 26 18 40 out.png
    python tools/snap.py both 6 0 26 18 40 out.png        side by side
"""
import math
import sys
from functools import lru_cache
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

plt.rcParams["font.family"] = "DejaVu Sans"

ARCH_COLORS = {"W": "#d62728", "WIN": "#17becf", "Etabs-col": "#2ca02c", "COL": "#006400", "DASH": "#bcbd22",
               "ST": "#8c564b", "MASS": "#7f7f7f", "PR": "#9467bd", "try": "#ff7f0e", "HAT": "#aaaaaa"}
STR_COLORS = {"Slab edge": "#000000", "Etabs-Slab": "#1f4fd6", "slab thickness": "#d62728", "BEAMS": "#2ca02c",
              "Etabs-col": "#7b3294", "GLOB-SLAB-HIDDEN": "#17becf"}


def ar(s):
    """Shape Arabic for matplotlib (needs arabic-reshaper + python-bidi; falls back to raw)."""
    if not s or not any("؀" <= c <= "ۿ" for c in s):
        return s
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        R = arabic_reshaper.ArabicReshaper(configuration={"support_ligatures": False})
        return get_display(R.reshape(s))
    except Exception:
        return s


def _in(pts, z, pad=0.5):
    return any(z[0] - pad <= x <= z[2] + pad and z[1] - pad <= y <= z[3] + pad for x, y in pts)


# ----------------------------------------------------------------------------- architectural
def arch_draw(ax, floor_no, zoom, layers=None, texts=True, lw=0.7):
    from diwan_common import floor_entities, floor_texts, get_floor
    from render_floor import _segments
    fl = get_floor(floor_no)
    layers = layers or list(ARCH_COLORS)
    for e in floor_entities(fl, layers=tuple(layers)):
        col = ARCH_COLORS.get(e.dxf.layer, "#000000")
        for pts in _segments(e, fl):
            if len(pts) >= 2 and _in(pts, zoom):
                xs, ys = zip(*pts)
                ax.plot(xs, ys, color=col, lw=lw)
    if texts:
        for t in floor_texts(fl):
            lx, ly = t["local"]
            if zoom[0] <= lx <= zoom[2] and zoom[1] <= ly <= zoom[3] and t["text"].strip():
                ax.text(lx, ly, ar(t["text"]), fontsize=7, color="#222222", clip_on=True)
    _frame(ax, zoom, f"{fl.label} architectural plan  {fl.level:+.2f}")


# ----------------------------------------------------------------------------- structural
@lru_cache(maxsize=1)
def _str_doc():
    import ezdxf
    import str_slabs as ss
    return ezdxf.readfile(str(ss.STR_DXF))


def _to_world(plan, x, y):
    import str_slabs as ss
    from diwan_common import rot
    off = plan["_cal"]["offset"]
    a = rot(plan["anchor"], -ss.ANGLE)
    q = (x - off[0] + a[0], y - off[1] + a[1])
    return rot(q, ss.ANGLE)


def str_draw(ax, ceiling_of, zoom, texts=True, lw=0.7):
    import str_slabs as ss
    from ezdxf import bbox
    from ezdxf import path as P
    S = ss.read_structural()
    plan = ss.plan_for_ceiling(S, ceiling_of)
    cs = [_to_world(plan, x, y) for x in (zoom[0] - 1, zoom[2] + 1) for y in (zoom[1] - 1, zoom[3] + 1)]
    wx0, wy0 = min(c[0] for c in cs), min(c[1] for c in cs)
    wx1, wy1 = max(c[0] for c in cs), max(c[1] for c in cs)
    L = lambda x, y: ss.to_arch_local(plan, x, y)  # noqa: E731

    def draw(e, col, depth=0):
        t = e.dxftype()
        try:
            if t == "INSERT" and depth < 3:
                for v in e.virtual_entities():
                    draw(v, col, depth + 1)
            elif t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE"):
                pts = [L(p.x, p.y) for p in P.make_path(e).flattening(0.02)]
                if len(pts) >= 2 and _in(pts, zoom):
                    ax.plot(*zip(*pts), color=col, lw=lw)
            elif t == "HATCH":
                for pp in P.from_hatch(e):
                    pts = [L(p.x, p.y) for p in pp.flattening(0.02)]
                    if len(pts) >= 3 and _in(pts, zoom):
                        ax.fill(*zip(*pts), color=col, alpha=0.25, lw=0)
        except Exception:
            pass

    for e in _str_doc().modelspace():
        lay = e.dxf.layer
        if lay not in STR_COLORS:
            continue
        b = bbox.extents([e], fast=True)
        if not b.has_data or b.extmax.x < wx0 or b.extmin.x > wx1 or b.extmax.y < wy0 or b.extmin.y > wy1:
            continue
        draw(e, STR_COLORS[lay])
    # columns / shear walls as read by str_slabs (they sit in blocks whose INSERT layer is not Etabs-col)
    from matplotlib.patches import Polygon as MPoly
    for c in plan["columns"]:
        P = c["_poly"]
        for gm in ([P] if P.geom_type == "Polygon" else list(P.geoms)):
            if _in(list(gm.exterior.coords), zoom):
                ax.add_patch(MPoly(list(gm.exterior.coords), closed=True, fc="#7b3294", ec="#3f007d", alpha=0.55, lw=0.8, zorder=4))
    if texts:
        g = ss.extract()
        for t in g["texts"]:
            if not (wx0 <= t["x"] <= wx1 and wy0 <= t["y"] <= wy1):
                continue
            lx, ly = L(t["x"], t["y"])
            if zoom[0] <= lx <= zoom[2] and zoom[1] <= ly <= zoom[3] and t["text"].strip():
                big = t["layer"] == "slab thickness" or ss.BEAM_RE.search(t["text"] or "")
                if not big and not ss.LEVEL_RE.match(t.get("raw") or ""):
                    continue          # rebar / notes clutter
                ax.text(lx, ly, ar(t["text"]), fontsize=9 if big else 6,
                        color="#d62728" if t["layer"] == "slab thickness" else ("#1b7837" if big else "#333333"),
                        fontweight="bold" if big else None, clip_on=True)
    _frame(ax, zoom, f"structural slab sheet = ceiling of floor {ceiling_of}")
    return plan


def _frame(ax, zoom, title):
    ax.set_xlim(zoom[0], zoom[2])
    ax.set_ylim(zoom[1], zoom[3])
    ax.set_aspect("equal")
    ax.grid(True, lw=0.2, color="#cccccc")
    ax.set_title(title, fontsize=10)


def figure(n=1, zoom=None, k=0.9, max_w=20):
    w = (zoom[2] - zoom[0]) * k
    h = (zoom[3] - zoom[1]) * k
    s = min(1.0, max_w / (w * n))
    fig, axs = plt.subplots(1, n, figsize=(w * n * s + 1, h * s + 1.2))
    return fig, (axs if n > 1 else [axs])


def main(argv=None):
    a = argv or sys.argv[1:]
    mode, fno = a[0], int(a[1])
    z = tuple(map(float, a[2:6]))
    out = a[6]
    fig, axs = figure(2 if mode == "both" else 1, z)
    if mode in ("arch", "both"):
        arch_draw(axs[0], fno, z)
    if mode in ("str", "both"):
        str_draw(axs[-1], fno, z)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main()
