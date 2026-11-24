

# ============================================================================
# 7. review drawing
# ============================================================================
FAM_COLORS = {"0.10": "#ff7f0e", "0.12": "#d62728", "0.15": "#bcbd22", "0.20": "#9467bd",
              "0.25": "#1f77b4", "0.30": "#8c564b", "0.40": "#e377c2", "0.50": "#7f7f7f",
              "0.60": "#17becf", "other": "#000000"}
KIND_HATCH = {"exterior": "////", "shaft": "xxxx", "stair_lift": "....", "interior": None}


def render(res, ctx, out_png, zoom=None, dpi=110, show_ids=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, Patch
    plt.rcParams["font.family"] = "Tahoma"
    g = ctx.g
    if zoom:
        w, h = zoom[2] - zoom[0], zoom[3] - zoom[1]
        fs = (16 * w / max(w, h) + 1.5, 16 * h / max(w, h) + 1.0)
    else:
        fs = (13, 28)
    fig, ax = plt.subplots(figsize=fs)
    for s in g["wsegs"]:
        ax.plot([s[0], s[2]], [s[1], s[3]], color="#555", lw=0.35, zorder=3)
    for wv in ctx.win_segs:
        ax.plot([wv[0], wv[2]], [wv[1], wv[3]], color="#17becf", lw=0.5, zorder=3)
    for a in g["winarcs"] + g["warcs"]:
        pts = _arc_pts(a[0], a[1], a[2], a[3], a[4])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#17becf", lw=0.5, zorder=3)
    for c in ctx.conc:
        for gm in getattr(c["poly"], "geoms", [c["poly"]]):
            ax.add_patch(MPoly(list(gm.exterior.coords), closed=True, fc="#2ca02c", ec="#1a6b1a",
                               alpha=0.45, lw=0.6, zorder=2))
    for v in ctx.voids:
        ax.add_patch(MPoly(list(v["poly"].exterior.coords), closed=True, fc="#ffbb78", ec="#ff7f0e",
                           alpha=0.5, lw=0.5, zorder=2))
    for d in g["doors"]:
        x0, y0, x1, y1 = d["bbox"]
        ax.add_patch(MPoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True, fill=False,
                           ec="#9467bd", lw=0.4, ls=":", zorder=2))
    for w in res["walls"]:
        D = Dir(w["angle"])
        d0, d1 = w["_band"]
        s, e = w["_t"]
        col = FAM_COLORS.get(w["family"], "#000")
        poly = D.rect(s, e, d0, d1)
        ax.add_patch(MPoly(list(poly.exterior.coords), closed=True, fc=col, ec=col, alpha=0.75, lw=0.3,
                           hatch=KIND_HATCH.get(w["kind"]), zorder=4))
        for op in w["openings"]:
            ox, oy = op["at"]
            t0, _ = D.td(ox, oy)
            pr = D.rect(t0 - op["width"] / 2, t0 + op["width"] / 2, d0, d1)
            ax.add_patch(MPoly(list(pr.exterior.coords), closed=True, fc="white", ec=col, lw=0.6, ls="--",
                               zorder=5))
        if w["needs_check"]:
            ax.add_patch(MPoly(list(poly.buffer(0.06, join_style=2).exterior.coords), closed=True, fill=False,
                               ec="#ff00ff", lw=0.9, zorder=6))
        if show_ids:
            mx, my = (w["x1"] + w["x2"]) / 2, (w["y1"] + w["y2"]) / 2
            ax.text(mx, my, w["id"][1:], fontsize=(5.5 if not zoom else 8), ha="center", va="center",
                    color="black", zorder=7, clip_on=True,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec=col, lw=0.5, alpha=0.9))
    ax.set_aspect("equal")
    if zoom:
        ax.set_xlim(zoom[0], zoom[2])
        ax.set_ylim(zoom[1], zoom[3])
    else:
        ax.set_xlim(-2.5, 21.0)
        ax.set_ylim(-3.0, 41.5)
    ax.grid(True, lw=0.2, alpha=0.5)
    fams = sorted({w["family"] for w in res["walls"]})
    handles = [Patch(fc=FAM_COLORS.get(f, "#000"), label=f"t={f}") for f in fams]
    handles += [Patch(fc="white", ec="#333", hatch=h, label=k) for k, h in KIND_HATCH.items()]
    handles += [Patch(fc="#2ca02c", alpha=0.45, label="concrete (Etabs-col/COL)"),
                Patch(fc="#ffbb78", label="shaft/void"),
                Patch(fc="white", ec="#ff00ff", label="needs_check")]
    ax.legend(handles=handles, loc="upper right", fontsize=7, framealpha=0.9)
    T = res["totals"].get("ALL|ALL", {})
    ax.set_title(f"{res['floor']} {res['name_ar']} {res['level']:+.2f}  walls={T.get('n', 0)}  "
                 f"gross={T.get('length_gross', 0):.2f} m  net={T.get('length_net', 0):.2f} m  "
                 f"(local frame, centre-line)", fontsize=10)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ============================================================================
# 8. public API + CLI
# ============================================================================
def read_walls(floor, height=3.0, use_cache=True, with_ctx=False):
    """Run the wall reader on one floor (int floor_no or Floor). Returns a JSON-able dict."""
    fl = get_floor(floor) if isinstance(floor, int) else floor
    g = load_geometry(fl, use_cache=use_cache)
    ctx, runs, spaces, foot, diag = detect(g, height)
    recs = wall_records(ctx, runs, height)
    res = {
        "floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
        "source": {"file": fl.file.name, "sheet_index": fl.sheet_index},
        "frame": "local (diwan_common): rotation -10 deg, origin = min corner of Etabs-col",
        "method": "face pairing of layer W; centre-line lengths; T-junctions to through-wall; "
                  "L-corners to centre-line crossing; net excludes openings; split at concrete",
        "height_assumed": height,
        "walls": recs,
        "totals": totals(recs, height),
        "thickness_histogram_net": thickness_histogram(recs),
        "diagnostics": {**diag,
                        "w_segments": len(g["wsegs"]), "w_arcs": len(g["warcs"]),
                        "w_hatches": [{"pattern": h["pattern"], "handle": h["handle"]} for h in g["whatch"]],
                        "w_inserts": dict(Counter(i["name"] for i in g["w_inserts"])),
                        "w_ignored": g["w_ignored"],
                        "directions": [round(D.ang, 2) for D, _ in ctx.dirs],
                        "concrete_polys": len(ctx.conc), "voids": len(ctx.voids), "fins": len(ctx.fins),
                        "spaces": len(spaces),
                        "footprint_area": round(foot.area, 2) if foot is not None else None,
                        "doors_blocks": len(g["doors"]),
                        "doors_matched": sum(1 for w in recs for o in w["openings"] if o["type"] == "door"),
                        },
    }
    if with_ctx:
        return res, ctx
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diwan wall reader (masonry basis) -> output/walls/")
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (default: all 2..8)")
    ap.add_argument("--height", type=float, default=3.0, help="wall height for indicative areas (m)")
    ap.add_argument("--zoom", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                    help="also write a zoomed review PNG (local m)")
    ap.add_argument("--no-cache", action="store_true", help="re-read the DXF (ignore geometry cache)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--dpi", type=int, default=120)
    a = ap.parse_args(argv)
    floors = a.floors or [f.floor_no for f in all_floors()]
    WALL_OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for n in floors:
        res, ctx = read_walls(n, height=a.height, use_cache=not a.no_cache, with_ctx=True)
        js = WALL_OUT / f"{res['floor']}.json"
        js.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        if not a.no_png:
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls.png", dpi=a.dpi)
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls_south.png", zoom=(-1.5, -2.5, 20.5, 21.0), dpi=a.dpi)
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls_north.png", zoom=(-1.5, 19.0, 20.5, 41.0), dpi=a.dpi)
        if a.zoom:
            z = "_".join(f"{v:g}" for v in a.zoom)
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls_zoom_{z}.png", zoom=a.zoom, dpi=a.dpi)
        T = res["totals"]
        summary[res["floor"]] = {"level": res["level"], "totals": T,
                                 "thickness_histogram_net": res["thickness_histogram_net"],
                                 "needs_check": sum(1 for w in res["walls"] if w["needs_check"]),
                                 "diagnostics": {k: v for k, v in res["diagnostics"].items()
                                                 if k not in ("w_ignored", "w_hatches")}}
        A = T.get("ALL|ALL", {})
        print(f"{res['floor']}: walls={A.get('n')} gross={A.get('length_gross')} net={A.get('length_net')} "
              f"needs_check={summary[res['floor']]['needs_check']}  -> {js}")
        for k, v in T.items():
            if k.startswith("ALL|") or k.endswith("|ALL"):
                print(f"   {k:22s} n={v['n']:3d} gross={v['length_gross']:8.2f} net={v['length_net']:8.2f}")
    if not a.floors:
        (WALL_OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    main()
