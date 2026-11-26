"""
Structural vs architectural comparison / overlay (reusable; "مطابقة الإنشائي مع المعماري").

All geometry is brought to the architectural LOCAL frame (diwan_common: -10 deg, origin = min corner
of Etabs-col), so any floor can be laid over any structural sheet or over another floor.

Modes
    python tools/str_arch_compare.py 6
        architectural floor 6 under its CEILING sheet ("سقف الدور 6"): slab zones 20/35, beams with
        labels, structural columns; walls coloured by masonry height (3.20 - concrete above).
        -> output/compare/F06_vs_str.png + F06_vs_str.json (column match, walls under beams, ...)
    python tools/str_arch_compare.py 6 --sheet 7
        the same floor against another ceiling sheet (e.g. to see what changes)
    python tools/str_arch_compare.py --arch 8 9
        two architectural floors laid one on the other (walls / columns that do not stack)
        -> output/compare/F08_over_F09.png + .json
    python tools/str_arch_compare.py --str 7 8
        two structural ceiling sheets laid one on the other (zones / beams / columns that differ)
    python tools/str_arch_compare.py --all          every floor vs its ceiling sheet

Rules kept here (see CLAUDE.md): structural sheet names above the 7th are shifted
("السابع متكرر"=8, "الثامن"=9, "التاسع"=10, "العاشر"=11, handled in str_slabs.TITLE_CEILING_OF);
"سقف الدور N" = slab ABOVE floor N; executed storey 3.20 (the structural +3.30 marks are wrong).
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import str_slabs as ss  # noqa: E402
from diwan_common import OUT_DIR, all_floors  # noqa: E402

OUT = OUT_DIR / "compare"
H_COLORS = {3.00: "#1a9850", 2.85: "#fdae61", 2.50: "#d73027", 2.30: "#7b3294"}


def _r(v, n=3):
    return None if v is None else round(float(v), n)


def _bundle(n):
    import read_plan as rp
    fl = next(f for f in all_floors() if f.floor_no == n)
    return rp.read_floor(fl, use_cache=True, log=lambda *a, **k: None)


def _arch_concrete(b):
    from shapely.geometry import Polygon
    out = []
    for e in b["structure"]["elements"]:
        if e.get("outline") and not e.get("only_in_tr_block"):
            try:
                out.append((e, Polygon(e["outline"]).buffer(0)))
            except Exception:
                pass
    return out


def match_columns(plan, b, shift=(0.0, 0.0)):
    """Structural columns of `plan` vs the concrete (columns / shear walls / core) of floor bundle b,
    matched by overlap (>= 50 % of the smaller one)."""
    from shapely.affinity import translate
    sc = [c["_poly"] for c in plan["columns"]]
    pairs, used = [], set()
    for e, P in _arch_concrete(b):
        P = translate(P, *shift)
        best, fr = None, 0.0
        for i, Q in enumerate(sc):
            a = P.intersection(Q).area
            f = a / max(min(P.area, Q.area), 1e-9)
            if f > fr:
                best, fr = i, f
        if best is not None and fr >= 0.5:
            Q = sc[best]
            pairs.append({"arch": e["id"], "kind": e["kind"], "size_arch": e.get("size_txt"),
                          "str_bbox": [_r(v, 2) for v in Q.bounds], "overlap": _r(fr, 2),
                          "offset": _r(P.centroid.distance(Q.centroid), 3),
                          "area_arch": _r(P.area, 3), "area_str": _r(Q.area, 3),
                          "same_size": abs(P.area - Q.area) <= 0.05 * max(P.area, Q.area)})
            used.add(best)
        else:
            pairs.append({"arch": e["id"], "kind": e["kind"], "size_arch": e.get("size_txt"), "str_bbox": None,
                          "offset": None, "overlap": _r(fr, 2), "note": "no structural column under it"})
    only_str = [{"str_bbox": [_r(v, 2) for v in sc[i].bounds], "area": _r(sc[i].area, 3)}
                for i in range(len(sc)) if i not in used]
    return pairs, only_str


def walls_under_beams(plan, walls, shift=(0.0, 0.0)):
    from shapely.geometry import LineString
    out = []
    for bm in plan["beams"]:
        B = bm["_poly"].buffer(0.03)
        for w in walls:
            L = LineString([(w["x1"] + shift[0], w["y1"] + shift[1]), (w["x2"] + shift[0], w["y2"] + shift[1])])
            ln = L.intersection(B).length
            if ln > 0.2:
                out.append({"wall": w["id"], "family": w["family"], "len_under_beam": _r(ln, 2),
                            "beam": bm.get("name"), "beam_size": f"{int(round(bm.get('b', 0) * 100))}x{int(round(bm['depth'] * 100))}" if bm.get("depth") else None,
                            "assumed": bm.get("assumed", False)})
    return out


# ----------------------------------------------------------------------------- drawing
def _ax(extent, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "DejaVu Sans"
    x0, y0, x1, y1 = extent
    k = 0.55
    fig, ax = plt.subplots(figsize=((x1 - x0) * k + 2, (y1 - y0) * k + 1.5))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=11)
    ax.grid(True, lw=0.2, color="#cccccc")
    return fig, ax


def _patch(ax, P, **kw):
    from matplotlib.patches import Polygon as MPoly
    geoms = [P] if P.geom_type == "Polygon" else list(getattr(P, "geoms", []))
    for g in geoms:
        if g.geom_type != "Polygon" or g.is_empty:
            continue
        ax.add_patch(MPoly(list(g.exterior.coords), closed=True, **kw))


def _draw_str(ax, plan, alpha=1.0, color_zones=True, edge="#2166ac", tag=""):
    if color_zones:
        for z in plan["zones"]:
            fc = "#c6dbef" if z["thickness"] < 0.3 else "#6baed6"
            _patch(ax, z["_poly"], fc=fc, ec="#4292c6", lw=0.4, alpha=0.55 * alpha,
                   hatch="..." if z["assumed"] else None, zorder=1)
            if z["area"] > 3:
                c = z["_poly"].representative_point()
                ax.text(c.x, c.y, f"{int(round(z['thickness'] * 100))}{'?' if z['assumed'] else ''}", fontsize=7,
                        color="#08306b", ha="center", va="center", zorder=9)
    _patch(ax, plan["_outline"], fc="none", ec=edge, lw=1.0, zorder=2)
    for bm in plan["beams"]:
        _patch(ax, bm["_poly"], fc="#fb9a99" if not bm.get("assumed") else "#fdbf6f", ec="#e31a1c", lw=0.4,
               alpha=0.8 * alpha, zorder=3)
        c = bm["_poly"].centroid
        if bm.get("depth"):
            ax.text(c.x, c.y, f"B{(bm.get('name') or '?')[1:]} {int(round(bm.get('b', 0) * 100))}x{int(round(bm['depth'] * 100))}",
                    fontsize=5, color="#99000d", ha="center", va="center", zorder=9)
    for c in plan["columns"]:
        _patch(ax, c["_poly"], fc="none", ec=edge, lw=0.9, zorder=8)


def _draw_walls(ax, walls, HW=None, color="#333333", lw_k=40, zorder=5, shift=(0, 0)):
    for w in walls:
        if HW and w["id"] in HW:
            r = HW[w["id"]]
            Lw = math.dist((w["x1"], w["y1"]), (w["x2"], w["y2"])) or 1e-9
            for a, b_, d, h, s in r["runs"]:
                f0, f1 = a / Lw, b_ / Lw
                xs = [w["x1"] + (w["x2"] - w["x1"]) * f for f in (f0, f1)]
                ys = [w["y1"] + (w["y2"] - w["y1"]) * f for f in (f0, f1)]
                ax.plot(xs, ys, color=H_COLORS.get(round(h, 2), "#000000"), lw=max(1.0, w["thickness"] * lw_k),
                        solid_capstyle="butt", zorder=zorder)
        else:
            ax.plot([w["x1"] + shift[0], w["x2"] + shift[0]], [w["y1"] + shift[1], w["y2"] + shift[1]], color=color,
                    lw=max(0.8, w["thickness"] * lw_k * 0.6), solid_capstyle="butt", zorder=zorder, alpha=0.85)


def _draw_arch_concrete(ax, b, color="#252525", fill=True, shift=(0, 0)):
    from shapely.affinity import translate
    for e, P in _arch_concrete(b):
        _patch(ax, translate(P, *shift), fc=color if fill else "none", ec=color, lw=0.6, alpha=0.7 if fill else 1, zorder=6)


def _extent(*polys, pad=1.5):
    xs = [p.bounds for p in polys]
    return (min(b[0] for b in xs) - pad, min(b[1] for b in xs) - pad, max(b[2] for b in xs) + pad, max(b[3] for b in xs) + pad)


def _legend(ax, items):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    h = []
    for kind, col, lab in items:
        h.append(Line2D([0], [0], color=col, lw=3, label=lab) if kind == "line" else Patch(fc=col, ec="#555555", label=lab))
    ax.legend(handles=h, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7, frameon=False)


# ----------------------------------------------------------------------------- modes
def floor_vs_sheet(n, sheet_of=None, S=None):
    import masonry_heights as mh
    from shapely.geometry import box
    S = S or ss.read_structural()
    plan = ss.plan_for_ceiling(S, sheet_of or n)
    b = _bundle(n)
    walls = b["walls"]["walls"]
    HW = mh.wall_heights(sheet_of or n, walls, b["structure"]["elements"], S=S)
    shift = HW["_shift"]
    pairs, only_str = match_columns(plan, b, shift)
    wub = walls_under_beams(plan, walls, shift)
    fb = b["rooms"]["totals"]["footprint_bbox"]
    ext = _extent(plan["_outline"], box(*fb))
    tag = f"F{n:02d}_vs_str" + (f"_sheet{sheet_of}" if sheet_of else "")
    fig, ax = _ax(ext, f"F{n:02d} architectural (walls by masonry height) over structural ceiling sheet "
                       f"of floor {sheet_of or n} [{'/'.join(str(c) for c in plan['ceiling_of'])}]  storey 3.20")
    _draw_str(ax, plan)
    _draw_arch_concrete(ax, b)
    _draw_walls(ax, walls, HW)
    _legend(ax, [("patch", "#c6dbef", "slab 20"), ("patch", "#6baed6", "slab 35 ('?' = no label, assumed)"),
                 ("patch", "#fb9a99", "beam (label read)"), ("patch", "#fdbf6f", "beam (depth assumed)"),
                 ("line", "#2166ac", "structural outline / columns"), ("patch", "#252525", "arch. concrete")]
            + [("line", c, f"masonry H {h:.2f}") for h, c in H_COLORS.items()])
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{tag}.png"
    fig.savefig(png, dpi=130, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    rep = {"floor": f"F{n:02d}", "structural_sheet": plan["title"], "sheet_ceiling_of": plan["ceiling_of"],
           "shift_applied": shift, "masonry_heights": mh.floor_summary(HW, walls),
           "columns": {"matched": sum(1 for p in pairs if p["offset"] is not None),
                       "arch_without_structural": [p for p in pairs if p["offset"] is None],
                       "structural_without_arch": only_str,
                       "max_offset": max([p["offset"] for p in pairs if p["offset"] is not None] or [None]),
                       "size_differs": [p for p in pairs if p["offset"] is not None and not p["same_size"]]},
           "walls_under_beams": wub,
           "areas": {"structural_outline": _r(plan["_outline"].area, 2),
                     "arch_footprint": b["rooms"]["totals"].get("gross_floor_area")},
           "png": str(png.relative_to(OUT_DIR.parent))}
    (OUT / f"{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def _not_stacked(wa, wb, tol=0.05, frac_min=0.8):
    """walls of list wa whose centre line is < frac_min on any wall of wb (same line within tol)."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    U = unary_union([LineString([(w["x1"], w["y1"]), (w["x2"], w["y2"])]).buffer(tol) for w in wb])
    out = []
    for w in wa:
        L = LineString([(w["x1"], w["y1"]), (w["x2"], w["y2"])])
        if L.length < 1e-6:
            continue
        f = L.intersection(U).length / L.length
        if f < frac_min:
            out.append({"wall": w["id"], "family": w["family"], "length": _r(L.length, 2), "on_other": _r(f, 2),
                        "_xy": (w["x1"], w["y1"], w["x2"], w["y2"])})
    return out


def arch_over_arch(n1, n2):
    """Floor n1 over floor n2: grey = same in both, RED = only in F{n1}, BLUE = only in F{n2}."""
    from shapely.geometry import box
    b1, b2 = _bundle(n1), _bundle(n2)
    w1, w2 = b1["walls"]["walls"], b2["walls"]["walls"]
    only1, only2 = _not_stacked(w1, w2), _not_stacked(w2, w1)
    ext = _extent(box(*b1["rooms"]["totals"]["footprint_bbox"]), box(*b2["rooms"]["totals"]["footprint_bbox"]))
    fig, ax = _ax(ext, f"F{n1:02d} over F{n2:02d}: grey = same, RED = only in F{n1:02d}, BLUE = only in F{n2:02d}")
    _draw_arch_concrete(ax, b2, color="#9e9e9e", fill=True)
    _draw_walls(ax, w2, color="#9e9e9e", zorder=4)
    for lst, col in ((only1, "#e31a1c"), (only2, "#1f78b4")):
        for o in lst:
            x1, y1, x2, y2 = o["_xy"]
            ax.plot([x1, x2], [y1, y2], color=col, lw=4.5, solid_capstyle="butt", zorder=7)
            ax.text((x1 + x2) / 2, (y1 + y2) / 2, o["wall"], color=col, fontsize=6, zorder=8)
    _legend(ax, [("line", "#9e9e9e", "same in both"), ("line", "#e31a1c", f"only F{n1:02d}"), ("line", "#1f78b4", f"only F{n2:02d}")])
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"F{n1:02d}_over_F{n2:02d}"
    fig.savefig(OUT / f"{tag}.png", dpi=130, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)
    strip = lambda L: [{k: v for k, v in o.items() if k != "_xy"} for o in L]  # noqa: E731
    rep = {"upper": f"F{n1:02d}", "lower": f"F{n2:02d}", "walls_upper": len(w1),
           "walls_not_on_lower": strip(only1), "length_not_on_lower": _r(sum(o["length"] for o in only1), 2),
           "walls_only_on_lower": strip(only2), "length_only_on_lower": _r(sum(o["length"] for o in only2), 2),
           "png": f"output/compare/{tag}.png"}
    (OUT / f"{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def str_over_str(n1, n2, S=None):
    S = S or ss.read_structural()
    p1, p2 = ss.plan_for_ceiling(S, n1), ss.plan_for_ceiling(S, n2)
    ext = _extent(p1["_outline"], p2["_outline"])
    fig, ax = _ax(ext, f"structural ceiling of {n1} (red, zones shaded) over ceiling of {n2} (blue)")
    _draw_str(ax, p1, edge="#b2182b")
    _draw_str(ax, p2, color_zones=False, edge="#2166ac", alpha=0.5)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"STR{n1:02d}_over_STR{n2:02d}"
    fig.savefig(OUT / f"{tag}.png", dpi=130, bbox_inches="tight")
    import matplotlib.pyplot as plt
    plt.close(fig)

    def z35(p):
        from shapely.ops import unary_union
        return unary_union([z["_poly"] for z in p["zones"] if z["thickness"] >= 0.3])
    a, b = z35(p1), z35(p2)
    rep = {"sheet_1": p1["title"], "sheet_2": p2["title"],
           "outline_area": [_r(p1["_outline"].area, 2), _r(p2["_outline"].area, 2)],
           "outline_xor_area": _r(p1["_outline"].symmetric_difference(p2["_outline"]).area, 2),
           "slab35_area": [_r(a.area, 2), _r(b.area, 2)], "slab35_xor_area": _r(a.symmetric_difference(b).area, 2),
           "beams": [sorted({f"{bm.get('name')} {bm.get('b')}x{bm.get('depth')}" for bm in p["beams"]}) for p in (p1, p2)],
           "columns": [len(p1["columns"]), len(p2["columns"])], "png": f"output/compare/{tag}.png"}
    (OUT / f"{tag}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("floors", nargs="*", type=int)
    ap.add_argument("--sheet", type=int, help="use the ceiling sheet of this floor instead of the floor's own")
    ap.add_argument("--arch", nargs=2, type=int, metavar=("UPPER", "LOWER"))
    ap.add_argument("--str", nargs=2, type=int, metavar=("A", "B"), dest="str_")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    if a.arch:
        r = arch_over_arch(*a.arch)
        print(f"{r['upper']} over {r['lower']}: only in {r['upper']} {r['length_not_on_lower']} m "
              f"({len(r['walls_not_on_lower'])} walls), only in {r['lower']} {r['length_only_on_lower']} m "
              f"({len(r['walls_only_on_lower'])} walls) -> {r['png']}")
        return
    if a.str_:
        print(json.dumps(str_over_str(*a.str_), ensure_ascii=False, indent=1))
        return
    S = ss.read_structural()
    fls = [f.floor_no for f in all_floors() if f.floor_no] if a.all or not a.floors else a.floors
    for n in fls:
        r = floor_vs_sheet(n, a.sheet, S=S)
        c = r["columns"]
        print(f"{r['floor']} vs '{r['structural_sheet']}': columns matched {c['matched']} (max offset {c['max_offset']}), "
              f"size differs {len(c['size_differs'])}, arch-only {len(c['arch_without_structural'])}, str-only {len(c['structural_without_arch'])} | "
              f"walls under beams {len(r['walls_under_beams'])} | H {r['masonry_heights']['length_by_height']} -> {r['png']}")


if __name__ == "__main__":
    main()
