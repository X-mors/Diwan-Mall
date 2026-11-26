"""
Vertical sections through the facade / planters for one floor ("as if standing in floor N").

Actual floor numbers only (the structural sheet names are mapped in str_slabs):
    slab of floor N = structural ceiling of floor N-1;  slab top = finish level - 0.10;  storey 3.20.
For each floor the section line crosses the facade (architectural footprint), the planter
(slab_boards.planter_faces) and the slab edge of the structural sheet under it.

    python tools/planter_sections.py 8 9 10 11            # plan + sections AA (north), BB (west), CC (south)
    python tools/planter_sections.py 10 --cuts BB
    -> output/compare/plan_Fnn_slab_planters.png, section_Fnn_AA.png / _BB / _CC
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import str_slabs as ss  # noqa: E402
from diwan_common import OUT_DIR, all_floors  # noqa: E402

OUT = OUT_DIR / "compare"
FIN = 0.10


def _bundle(n):
    import read_plan as rp
    fl = next(f for f in all_floors() if f.floor_no == n)
    return fl, rp.read_floor(fl, use_cache=True, log=lambda *a, **k: None)


# the three cuts asked by the owner (local frame): (axis held constant, value, outward sign, side name)
CUTS = {
    "AA": ("x", 8.0, +1, "north"),     # north planters
    "BB": ("y", 7.5, -1, "west"),      # west planters between the SW curve and the stair
    "CC": ("x", 8.0, -1, "south"),     # south planters
}


def _line(cut):
    from shapely.geometry import LineString
    ax_, v, _, _ = cut
    return LineString([(v, -10), (v, 50)]) if ax_ == "x" else LineString([(-10, v), (50, v)])


def _u(cut, g):
    """(u_min, u_max) of a geometry along the cut."""
    x0, y0, x1, y1 = g.bounds
    return (y0, y1) if cut[0] == "x" else (x0, x1)


def _pt(cut, u):
    return (cut[1], u) if cut[0] == "x" else (u, cut[1])


def floor_cut(S, n, cut):
    """facade u, slab edge u, planter (u0, u1) or None, slab depth at the edge, slab top -- along the cut."""
    import slab_boards as sb
    fl, b = _bundle(n)
    L = _line(cut)
    sg = cut[2]
    pick = (lambda t: t[1]) if sg > 0 else (lambda t: t[0])
    fac = pick(_u(cut, b["footprint"].intersection(L)))
    plan = ss.plan_for_ceiling(S, n - 1)
    edge = pick(_u(cut, plan["_outline"].intersection(L)))
    P = sb.planter_faces(n, b).intersection(L)
    pl = None
    for g in getattr(P, "geoms", [P]):
        if g.is_empty:
            continue
        u0, u1 = _u(cut, g)
        if (sg > 0 and u0 >= fac - 0.05) or (sg < 0 and u1 <= fac + 0.05):
            pl = (u0, u1)
    d, _ = ss.soffit_at(plan, *_pt(cut, edge - sg * 0.3))
    return {"floor": n, "facade": fac, "edge": edge, "planter": pl, "depth": d, "top": fl.level - FIN}


def section(focus, name="AA", S=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    S = S or ss.read_structural()
    cut = CUTS[name]
    side = cut[3]
    sg = cut[2]
    floors = [n for n in (focus - 1, focus, focus + 1) if 2 <= n <= 11]
    cuts = {n: floor_cut(S, n, cut) for n in floors}
    top_n = max(floors)
    plan_up = ss.plan_for_ceiling(S, top_n)
    ub = _u(cut, plan_up["_outline"].intersection(_line(cut)))
    up_edge = ub[1] if sg > 0 else ub[0]
    up_top = cuts[top_n]["top"] + 3.20
    d_up, _ = ss.soffit_at(plan_up, *_pt(cut, up_edge - sg * 0.3))
    if sg > 0:
        inner = min(c["facade"] for c in cuts.values()) - 4.5
        outer = max([c["edge"] for c in cuts.values()] + [up_edge] + [c["planter"][1] for c in cuts.values() if c["planter"]]) + 1.2
    else:
        inner = max(c["facade"] for c in cuts.values()) + 4.5
        outer = min([c["edge"] for c in cuts.values()] + [up_edge] + [c["planter"][0] for c in cuts.values() if c["planter"]]) - 1.2
    fig, ax = plt.subplots(figsize=(10, 3.4 * len(floors) + 1.5))
    # text anchor: x axis is inverted for sg < 0, so "inner" is always on the left of the picture
    ha = "left"

    def slab(edge, top, d, lab, hl):
        a, b_ = sorted((inner, edge))
        ax.add_patch(Rectangle((a, top - d), b_ - a, d, fc="#4292c6" if hl else "#9e9e9e", ec="k", hatch="//", zorder=3))
        ax.text(inner + sg * 0.1, top - d - 0.3, lab + f"  ({d:.2f} m)", fontsize=9, ha=ha,
                color="#08519c" if hl else "k", fontweight="bold" if hl else None)

    for n in floors:
        c = cuts[n]
        hl = n == focus
        slab(c["edge"], c["top"], c["depth"], f"slab of floor {n} = ceiling of floor {n - 1}", hl)
        nxt = cuts.get(n + 1)
        ceil_d = nxt["depth"] if nxt else d_up
        ax.plot([c["facade"]] * 2, [c["top"], c["top"] + 3.20 - ceil_d], color="#17becf", lw=3, zorder=4)
        if c["planter"]:
            u0, u1 = c["planter"]
            pin, pout = (c["facade"], u1) if sg > 0 else (c["facade"], u0)     # inner / outer end of the planter
            a, b_ = sorted((pin, pout))
            ax.add_patch(Rectangle((a, c["top"]), b_ - a, 0.45, fc="#74c476", ec="#238b45", zorder=4))
            ax.add_patch(Rectangle((pout - 0.25 if sg > 0 else pout, c["top"]), 0.25, 0.6, fc="#fdd0a2", ec="#d94801", zorder=4))
            over = sg * (pout - c["edge"])
            width = abs(b_ - a)
            if over > 0.03:     # MISMATCH: architectural planter / parapet outside the structural slab edge
                ra, rb = sorted((c["edge"], pout))
                ax.add_patch(Rectangle((ra, c["top"] - 0.6), rb - ra, 1.4, fc="none", ec="red", lw=2.2, zorder=11))
                txt = (f"PROBLEM: the whole planter ({over:.2f} m) has NO slab under it" if over >= width - 0.05 else
                       f"PROBLEM: parapet {over * 100:.0f} cm outside\nthe structural slab edge (no concrete under it)")
                ax.annotate(txt, (pout, c["top"] + 0.3), (pout + sg * 0.3, c["top"] - 1.6), fontsize=9, color="red",
                            fontweight="bold", ha=ha, zorder=12, arrowprops=dict(arrowstyle="->", color="red", lw=1.5))
                note = (f"planter of floor {n}: {width:.2f} m wide, NOT on the structural slab" if over >= width - 0.05 else
                        f"planter of floor {n}: {width:.2f} m wide, parapet {over:.2f} m past the slab edge")
            else:
                note = f"planter of floor {n}: {width:.2f} m wide, on its slab"
        else:
            out = sg * (c["edge"] - c["facade"])
            note = (f"floor {n}: no planter; slab edge {out:.2f} m outside the glass" if out > 0.03 else
                    f"floor {n}: no planter; slab edge at the glass")
        ax.text(inner + sg * 0.3, c["top"] + 2.3, f"FLOOR {n} (inside)", fontsize=12, ha=ha,
                fontweight="bold" if hl else None, color="#08519c" if hl else "k")
        ax.text(inner + sg * 0.3, c["top"] + 1.6, note, fontsize=8.5, ha=ha,
                color="#00441b" if c["planter"] else "#7f2704")
    slab(up_edge, up_top, d_up, f"ceiling of floor {top_n}" + (" (roof)" if top_n == 11 else f" = slab of floor {top_n + 1}"), False)
    c = cuts[focus]
    px = inner + sg * 2.2
    py = c["top"]
    ax.plot([px, px], [py + 0.5, py + 1.1], "k", lw=2)
    ax.add_patch(plt.Circle((px, py + 1.3), 0.18, fc="none", ec="k", lw=2))
    ax.plot([px - 0.25, px, px + 0.25], [py, py + 0.5, py], "k", lw=2)
    ax.text(px + sg * 0.4, py + 0.25, "you stand here", fontsize=10, color="#08519c", ha=ha)
    lo = min(c["top"] for c in cuts.values()) - 0.9
    ax.set_ylim(lo, up_top + 0.7)
    ax.set_xlim(*sorted((inner, outer)))
    if sg < 0:
        ax.invert_xaxis()
    ax.set_aspect("equal")
    other = "y" if cut[0] == "x" else "x"
    ax.set_xlabel(f"{side} ->   (m along {other}; section {name[0]}-{name[1]} at {cut[0]} = {cut[1]})")
    ax.set_ylabel("level (m)")
    ax.set_title(f"FLOOR {focus} - SECTION {name[0]}-{name[1]} ({side} side)   blue = the slab under your feet\n"
                 "green = planter soil, orange = planter parapet, cyan = glass facade, red box = problem", fontsize=11)
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"section_F{focus:02d}_{name}.png"
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return png, cuts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("floors", nargs="+", type=int)
    ap.add_argument("--cuts", nargs="+", default=list(CUTS), choices=list(CUTS))
    a = ap.parse_args(argv)
    S = ss.read_structural()
    for n in a.floors:
        print(plan_view(n, S=S))
        for name in a.cuts:
            png, cuts = section(n, name, S)
            print(png, {k: {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in cuts.items()})


def plan_view(n, S=None):
    """Plan of floor n in the colours of the sections: blue = slab under floor n (structural),
    cyan = facade (architectural), green = planters on the slab, red = planter without slab,
    orange = planter parapets, dashed = slab above (ceiling of n), magenta lines = sections A-A, B-B, C-C (CUTS)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    import slab_boards as sb
    import snap
    from str_arch_compare import _patch
    S = S or ss.read_structural()
    fl, b = _bundle(n)
    under, above = ss.plan_for_ceiling(S, n - 1), ss.plan_for_ceiling(S, n)
    U, A, fp = under["_outline"], above["_outline"], b["footprint"]
    P = sb.planter_faces(n, b)
    on, off = P.intersection(U.buffer(0.02)), P.difference(U.buffer(0.02))
    x0, y0, x1, y1 = U.union(fp).union(A).bounds
    z = (x0 - 1.0, y0 - 1.2, x1 + 1.0, y1 + 1.2)
    fig, axs = snap.figure(1, z, k=0.62)
    ax = axs[0]
    _patch(ax, U, fc="#c6dbef", ec="#08519c", lw=2.4, zorder=0)
    _patch(ax, A, fc="none", ec="#525252", lw=1.3, ls="--", zorder=9)
    snap.arch_draw(ax, n, z, layers=["W", "Etabs-col", "ST"], texts=False, lw=0.5)
    _patch(ax, fp, fc="none", ec="#17becf", lw=2.2, zorder=8)
    _patch(ax, on, fc="#74c476", ec="#238b45", lw=0.6, zorder=6)
    _patch(ax, off, fc="#ef3b2c", ec="#a50f15", lw=1.0, hatch="xxx", zorder=7)
    for q in b["walls"].get("planter_parapets", []):
        ax.plot([q["x1"], q["x2"]], [q["y1"], q["y2"]], color="#fd8d3c", lw=3.0, solid_capstyle="butt", zorder=8)
    # MISMATCH callouts: parapet outer face outside the structural slab edge
    from shapely.geometry import LineString
    probs = []
    for q in b["walls"].get("planter_parapets", []):
        L = LineString([(q["x1"], q["y1"]), (q["x2"], q["y2"])])
        o = max((L.parallel_offset(q["thickness"] / 2, "left"), L.parallel_offset(q["thickness"] / 2, "right")),
                key=lambda g: g.distance(fp))
        bad = o.difference(U.buffer(0.02))
        if bad.length > 0.3:
            pts = [o.interpolate(t, normalized=True) for t in [i / 20 for i in range(21)]]
            d = max((U.exterior.distance(p_) for p_ in pts if not U.contains(p_)), default=0)
            probs.append((q["id"], bad, d))
    # planter edge (not a parapet line) outside the slab, e.g. F09 west strips
    from shapely.ops import unary_union as _uu
    done = _uu([p_[1] for p_ in probs]).buffer(0.3) if probs else None
    for g in getattr(off, "geoms", [off]):
        if g.is_empty or g.area < 0.3 or (done is not None and g.difference(done).area < 0.5 * g.area):
            continue
        bx0, by0, bx1, by1 = g.bounds
        w, ln = sorted((bx1 - bx0, by1 - by0))
        mid = LineString([((bx0 + bx1) / 2, by0), ((bx0 + bx1) / 2, by1)]) if by1 - by0 > bx1 - bx0 else \
            LineString([(bx0, (by0 + by1) / 2), (bx1, (by0 + by1) / 2)])
        probs.append(("edge", mid, w))
    for i, (qid, bad, d) in enumerate(probs, 1):
        for g in getattr(bad, "geoms", [bad]):
            ax.plot(*g.xy, color="red", lw=6, alpha=0.8, zorder=11)
        c = bad.centroid
        what = "planter edge" if qid == "edge" else "parapet"
        ax.annotate(f"({i}) {what} {d * 100:.0f} cm outside slab, {bad.length:.1f} m",
                    (c.x, c.y), (c.x + (2.5 if c.x < 8 else -1.5), c.y + (-2.2 if c.y > 20 else 2.2)),
                    fontsize=10, color="red", fontweight="bold", zorder=12,
                    arrowprops=dict(arrowstyle="->", color="red", lw=1.5))
    # section line A-A (north) at x
    for name, cut in CUTS.items():
        lo_, hi_ = _u(cut, U.union(fp).union(P).intersection(_line(cut)))
        far = hi_ + 0.8 if cut[2] > 0 else lo_ - 0.8
        near = far - cut[2] * 5.3
        (ax0, ay0), (ax1, ay1) = _pt(cut, near), _pt(cut, far)
        ax.plot([ax0, ax1], [ay0, ay1], color="#e7298a", lw=2.2, ls="-.", zorder=10)
        tx, ty = _pt(cut, far - cut[2] * 0.25)
        ax.text(tx + (0.15 if cut[0] == "x" else 0), ty + (0.15 if cut[0] == "y" else 0), f"{name[0]}-{name[1]}",
                color="#e7298a", fontsize=12, fontweight="bold", zorder=10,
                ha="right" if cut[0] == "y" and cut[2] < 0 else "left")
    ax.set_title(f"FLOOR {n} - plan  (blue = the slab under your feet, ceiling of floor {n - 1};  "
                 f"dashed = slab above, ceiling of floor {n})", fontsize=11)
    ax.legend(handles=[Patch(fc="#c6dbef", ec="#08519c", label=f"slab of floor {n} (structural)"),
                       Line2D([0], [0], color="#17becf", lw=2.2, label=f"facade of floor {n} (architectural)"),
                       Patch(fc="#74c476", label="planter on the slab"),
                       Patch(fc="#ef3b2c", hatch="xxx", label="planter with NO slab under it"),
                       Line2D([0], [0], color="#fd8d3c", lw=3, label="planter parapet"),
                       Line2D([0], [0], color="#525252", ls="--", label=f"slab above (ceiling of floor {n})"),
                       Line2D([0], [0], color="#e7298a", ls="-.", label="sections A-A, B-B, C-C")],
              loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=9, frameon=False)
    if not probs:
        ax.text(0.02, 0.01, "OK: every planter parapet is on the structural slab", transform=ax.transAxes,
                fontsize=11, color="#006d2c", fontweight="bold")
    png = OUT / f"plan_F{n:02d}_slab_planters.png"
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return png


if __name__ == "__main__":
    main()
