"""
Per-floor comparison boards: architectural floor N laid on the STRUCTURAL slab that carries it.

The slab a floor stands on is the structural sheet "سقف الدور N-1" (ceiling of the floor below);
the sheet "سقف الدور N" (ceiling of N, above its walls) is drawn dashed for reference.
Planters / terraces = faces outside the facade closed by MASS / try lines (F02 terraces, F09-F11
planters).  Each face is split into the part ON the slab below (green) and the part with NO slab
under it (red, hatched) = no extra concrete for it in the structural.

    python tools/slab_boards.py            # every floor -> output/compare/slab_board_Fnn.png + slab_boards.json
    python tools/slab_boards.py 9 10 11
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import str_slabs as ss  # noqa: E402
from diwan_common import OUT_DIR, all_floors  # noqa: E402

OUT = OUT_DIR / "compare"


def _r(v, n=2):
    return round(float(v), n)


def planter_faces(n, b):
    from diwan_common import floor_entities, get_floor
    from render_floor import _segments
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import polygonize, unary_union
    fl = get_floor(n)
    fp = b["footprint"]
    lines = [LineString(p) for e in floor_entities(fl, layers=("MASS", "try")) for p in _segments(e, fl) if len(p) >= 2]
    lines = [ln for ln in lines if ln.distance(fp) < 3.5 and ln.length < 200]
    faces = [f for f in polygonize(unary_union(lines + [fp.exterior])) if f.area > 0.05]
    out = [f for f in faces if fp.buffer(-0.05).intersection(f).area < 0.05 * f.area and f.distance(fp) < 0.5]
    # + the strip between each planter parapet (walls.planter_parapets, F09-F11) and the facade:
    # some planter boxes are not closed by MASS/try lines, so polygonize misses them
    import math
    for q in b["walls"].get("planter_parapets", []):
        x1, y1, x2, y2 = q["x1"], q["y1"], q["x2"], q["y2"]
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 0.1:
            continue
        nx, ny = -(y2 - y1) / L, (x2 - x1) / L
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        best = None
        for sg in (1, -1):
            ray = LineString([(mx, my), (mx + sg * nx * 3.0, my + sg * ny * 3.0)])
            X = ray.intersection(fp.exterior)
            if X.is_empty:
                continue
            d = min(Point(mx, my).distance(g) for g in getattr(X, "geoms", [X]))
            if best is None or d < best[0]:
                best = (d, sg)
        if best is None:
            continue
        d, sg = best
        half = q.get("thickness", 0.25) / 2
        quad = Polygon([(x1 - sg * nx * half, y1 - sg * ny * half), (x2 - sg * nx * half, y2 - sg * ny * half),
                        (x2 + sg * nx * d, y2 + sg * ny * d), (x1 + sg * nx * d, y1 + sg * ny * d)]).buffer(0)
        out.append(quad.difference(fp))
    return unary_union(out).buffer(0) if out else Polygon()


def board(n, S=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    import read_plan as rp
    import snap
    S = S or ss.read_structural()
    fl = next(f for f in all_floors() if f.floor_no == n)
    b = rp.read_floor(fl, use_cache=True, log=lambda *a, **k: None)
    under = ss.plan_for_ceiling(S, n - 1)
    above = ss.plan_for_ceiling(S, n)
    U, A = under["_outline"], above["_outline"]
    fp = b["footprint"]
    P = planter_faces(n, b)
    on = P.intersection(U.buffer(0.02))
    off = P.difference(U.buffer(0.02))
    slab_out = U.difference(fp.buffer(0.05))            # slab beyond the facade
    slab_out_free = slab_out.difference(P.buffer(0.05))  # ... with no planter / terrace drawn on it
    x0, y0, x1, y1 = U.union(fp).union(P if not P.is_empty else fp).bounds
    z = (x0 - 1.5, y0 - 1.5, x1 + 1.5, y1 + 1.5)
    fig, axs = snap.figure(1, z, k=0.62)
    ax = axs[0]
    from str_arch_compare import _patch
    _patch(ax, U, fc="#deebf7", ec="#08519c", lw=2.2, zorder=0)
    _patch(ax, A, fc="none", ec="#31a354", lw=1.2, ls="--", zorder=9)
    for c in under["columns"]:
        _patch(ax, c["_poly"], fc="#7b3294", ec="#3f007d", alpha=0.45, lw=0.6, zorder=3)
    snap.arch_draw(ax, n, z, layers=["W", "WIN", "Etabs-col", "MASS", "try", "ST"], texts=True, lw=0.6)
    _patch(ax, on, fc="#41ab5d", ec="#006d2c", alpha=0.45, lw=0.8, zorder=6)
    _patch(ax, off, fc="#ef3b2c", ec="#a50f15", alpha=0.6, lw=1.2, hatch="xxx", zorder=7)
    big_free = [g for g in getattr(slab_out_free, "geoms", [slab_out_free]) if g.area > 0.5]
    for g in big_free:
        _patch(ax, g, fc="#fdae6b", ec="#d94801", alpha=0.6, lw=1.0, hatch="///", zorder=5)
    ax.set_title(f"F{n:02d} {fl.level:+.2f}: architectural on the slab under it = structural sheet 'ceiling of floor {n - 1}'"
                 f"  (dashed green = slab above, ceiling of {n})", fontsize=10)
    ax.legend(handles=[Patch(fc="#deebf7", ec="#08519c", label=f"slab under F{n:02d} (ceiling of {n - 1})"),
                       Line2D([0], [0], color="#31a354", ls="--", label=f"slab above (ceiling of {n})"),
                       Patch(fc="#41ab5d", alpha=0.45, label="planter / terrace ON the slab"),
                       Patch(fc="#ef3b2c", hatch="xxx", label="planter / terrace with NO slab under it"),
                       Patch(fc="#fdae6b", hatch="///", label="slab beyond the facade, nothing drawn on it"),
                       Patch(fc="#7b3294", alpha=0.45, label="structural columns")],
              loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8, frameon=False)
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"slab_board_F{n:02d}.png"
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return {"floor": f"F{n:02d}", "slab_under": under["title"], "slab_under_ceiling_of": n - 1,
            "slab_under_area": _r(U.area), "facade_footprint_area": _r(fp.area),
            "slab_beyond_facade": _r(slab_out.area), "slab_beyond_facade_nothing_drawn": _r(sum(g.area for g in big_free)),
            "planter_terrace_area": _r(P.area), "planter_on_slab": _r(on.area), "planter_without_slab": _r(off.area),
            "planter_without_slab_parts": [[_r(v) for v in g.bounds] + [_r(g.area)]
                                           for g in getattr(off, "geoms", [off]) if not g.is_empty and g.area > 0.1],
            "png": f"output/compare/{png.name}"}


def main(argv=None):
    a = [int(x) for x in (argv or sys.argv[1:])] or [f.floor_no for f in all_floors() if f.floor_no]
    S = ss.read_structural()
    rows = []
    for n in a:
        r = board(n, S)
        rows.append(r)
        print(f"{r['floor']} on '{r['slab_under']}': slab {r['slab_under_area']} facade {r['facade_footprint_area']} | "
              f"planter/terrace {r['planter_terrace_area']} on slab {r['planter_on_slab']} WITHOUT slab {r['planter_without_slab']} | "
              f"slab beyond facade with nothing on it {r['slab_beyond_facade_nothing_drawn']}")
    (OUT / "slab_boards.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
