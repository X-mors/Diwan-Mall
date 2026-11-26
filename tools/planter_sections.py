"""
Vertical sections through the facade / planters for one floor ("as if standing in floor N").

Actual floor numbers only (the structural sheet names are mapped in str_slabs):
    slab of floor N = structural ceiling of floor N-1;  slab top = finish level - 0.10;  storey 3.20.
For each floor the section line crosses the facade (architectural footprint), the planter
(slab_boards.planter_faces) and the slab edge of the structural sheet under it.

    python tools/planter_sections.py 8 9 10 11            # north side, x = 8
    python tools/planter_sections.py 10 --side south --x 8
    -> output/compare/section_Fnn_<side>.png
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


def floor_cut(S, n, x, side):
    """(facade y, slab edge y, planter (y0, y1) or None, slab depth at edge, slab top) along x."""
    from shapely.geometry import LineString
    import slab_boards as sb
    fl, b = _bundle(n)
    cut = LineString([(x, -10), (x, 50)])
    fb = b["footprint"].intersection(cut).bounds
    plan = ss.plan_for_ceiling(S, n - 1)
    ub = plan["_outline"].intersection(cut).bounds
    k = 3 if side == "north" else 1
    fac, edge = fb[k], ub[k]
    P = sb.planter_faces(n, b).intersection(cut)
    pl = None
    for g in getattr(P, "geoms", [P]):
        if g.is_empty:
            continue
        y0, y1 = g.bounds[1], g.bounds[3]
        if (side == "north" and y0 >= fac - 0.05) or (side == "south" and y1 <= fac + 0.05):
            pl = (y0, y1)
    d, _ = ss.soffit_at(plan, x, edge - 0.3 if side == "north" else edge + 0.3)
    return {"floor": n, "facade": fac, "edge": edge, "planter": pl, "depth": d, "top": fl.level - FIN}


def section(focus, x=8.0, side="north", S=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    S = S or ss.read_structural()
    floors = [n for n in (focus - 1, focus, focus + 1) if 2 <= n <= 11]
    cuts = {n: floor_cut(S, n, x, side) for n in floors}
    top_n = max(floors)
    # slab above the top floor drawn (ceiling of top_n): from the structural sheet
    from shapely.geometry import LineString
    plan_up = ss.plan_for_ceiling(S, top_n)
    ub = plan_up["_outline"].intersection(LineString([(x, -10), (x, 50)])).bounds
    up_edge = ub[3] if side == "north" else ub[1]
    up_top = cuts[top_n]["top"] + 3.20
    d_up, _ = ss.soffit_at(plan_up, x, up_edge - 0.3 if side == "north" else up_edge + 0.3)
    sg = 1 if side == "north" else -1
    inner = min(c["facade"] for c in cuts.values()) - 4.5 if side == "north" else max(c["facade"] for c in cuts.values()) + 4.5
    outer = max([c["edge"] for c in cuts.values()] + [up_edge]) + 1.2 if side == "north" else \
        min([c["edge"] for c in cuts.values()] + [up_edge]) - 1.2
    fig, ax = plt.subplots(figsize=(10, 3.4 * len(floors) + 1.5))

    def slab(edge, top, d, lab, hl):
        a, b_ = sorted((inner, edge))
        ax.add_patch(Rectangle((a, top - d), b_ - a, d, fc="#4292c6" if hl else "#9e9e9e", ec="k", hatch="//", zorder=3))
        ax.text(inner + sg * 0.1, top - d - 0.3, lab + f"  ({d:.2f} m)", fontsize=9, ha="left" if sg > 0 else "right",
                color="#08519c" if hl else "k", fontweight="bold" if hl else None)

    for n in floors:
        c = cuts[n]
        hl = n == focus
        slab(c["edge"], c["top"], c["depth"], f"slab of floor {n} = ceiling of floor {n - 1}", hl)
        nxt = cuts.get(n + 1)
        ceil_d = nxt["depth"] if nxt else d_up
        ax.plot([c["facade"]] * 2, [c["top"], c["top"] + 3.20 - ceil_d], color="#17becf", lw=3, zorder=4)
        if c["planter"]:
            y0, y1 = c["planter"]
            a, b_ = sorted((c["facade"], y1 if side == "north" else y0))
            ax.add_patch(Rectangle((a, c["top"]), b_ - a, 0.45, fc="#74c476", ec="#238b45", zorder=4))
            pe = (y1 - 0.25) if side == "north" else y0
            ax.add_patch(Rectangle((pe, c["top"]), 0.25, 0.6, fc="#fdd0a2", ec="#d94801", zorder=4))
            over = (b_ - c["edge"]) if side == "north" else (c["edge"] - a)
            note = f"planter of floor {n}: {abs(b_ - a):.2f} m wide, on its slab" + \
                   (f" (parapet {over:.2f} m past the slab edge)" if over > 0.03 else "")
        else:
            out = abs(c["edge"] - c["facade"])
            note = f"floor {n}: no planter; slab edge {out:.2f} m outside the glass"
        ax.text(inner + sg * 0.3, c["top"] + 2.3, f"FLOOR {n} (inside)", fontsize=12, ha="left" if sg > 0 else "right",
                fontweight="bold" if hl else None, color="#08519c" if hl else "k")
        ax.text(inner + sg * 0.3, c["top"] + 1.6, note, fontsize=8.5, ha="left" if sg > 0 else "right",
                color="#00441b" if c["planter"] else "#7f2704")
    slab(up_edge, up_top, d_up, f"ceiling of floor {top_n}" + (" (roof)" if top_n == 11 else f" = slab of floor {top_n + 1}"), False)
    # person on the focus floor
    c = cuts[focus]
    px = inner + sg * 2.2
    py = c["top"]
    ax.plot([px, px], [py + 0.5, py + 1.1], "k", lw=2)
    ax.add_patch(plt.Circle((px, py + 1.3), 0.18, fc="none", ec="k", lw=2))
    ax.plot([px - 0.25, px, px + 0.25], [py, py + 0.5, py], "k", lw=2)
    ax.text(px + sg * 0.4, py + 0.25, "you stand here", fontsize=10, color="#08519c", ha="left" if sg > 0 else "right")
    lo = min(c["top"] for c in cuts.values()) - 0.9
    ax.set_ylim(lo, up_top + 0.7)
    ax.set_xlim(*sorted((inner, outer)))
    if sg < 0:
        ax.invert_xaxis()
    ax.set_aspect("equal")
    ax.set_xlabel(f"{side} ->   (m, vertical section on the {side} side at x = {x})")
    ax.set_ylabel("level (m)")
    ax.set_title(f"Standing in floor {focus}: section on the {side} side (blue = the slab under your feet)\n"
                 "green = planter soil, orange = planter parapet, cyan = glass facade", fontsize=11)
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"section_F{focus:02d}_{side}.png"
    fig.savefig(png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return png, cuts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("floors", nargs="+", type=int)
    ap.add_argument("--x", type=float, default=8.0)
    ap.add_argument("--side", choices=["north", "south"], default="north")
    a = ap.parse_args(argv)
    S = ss.read_structural()
    for n in a.floors:
        png, cuts = section(n, a.x, a.side, S)
        print(png, {k: {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in cuts.items()})


if __name__ == "__main__":
    main()
