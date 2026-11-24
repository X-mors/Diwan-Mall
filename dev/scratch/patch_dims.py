p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()

# 1. extraction: axis lines (layer X / x1)
old = '''    # ---- room labels ----'''
new = '''    # ---- axis grid (layer X / x1) ----
    g["axes"] = []
    for e in floor_entities(fl, layers=("X", "x1"), types="LINE"):
        a = L(e.dxf.start.x, e.dxf.start.y)
        b = L(e.dxf.end.x, e.dxf.end.y)
        g["axes"].append((a[0], a[1], b[0], b[1]))

    # ---- room labels ----'''
assert old in s
s = s.replace(old, new)
s = s.replace('_v5.pkl"', '_v6.pkl"')

# 2. cross-check function
anchor = "# ============================================================================\n# 7. review drawing"
fn = r'''def dim_crosscheck(ctx, recs):
    """Compare the architect's DIMENSIONs (layer DIM) with the wall reading.
    Each dimension end is snapped to (a) a W face line, (b) an axis line (layer X), or nothing.
    Dimensions <= GAP_MAX with both ends on faces are wall-THICKNESS dimensions: they must
    match the band of a wall record nearby."""
    g = ctx.g
    face_d = {}
    for di, (D, _) in enumerate(ctx.dirs):
        face_d[di] = (D, [f["d"] for f in ctx.faces[di]])
    axes = []
    for a in g.get("axes", []):
        L = math.hypot(a[2] - a[0], a[3] - a[1])
        if L > 1:
            axes.append(a)
    stats = Counter()
    thick = []
    for dm in g["dims"]:
        if dm["type"] not in (0, 1):
            continue
        p2, p3 = dm["p2"], dm["p3"]
        if dm["type"] == 0:
            ang = dm["angle"]
        else:
            ang = math.degrees(math.atan2(p3[1] - p2[1], p3[0] - p2[0])) % 180.0
        # faces perpendicular to the measuring direction have normal // measuring direction
        cand = [(di, D, ds) for di, (D, ds) in face_d.items() if _angdiff(D.ang + 90.0, ang) < 1.0]
        if not cand:
            stats["no_face_direction"] += 1
            continue
        di, D, ds = cand[0]
        c2 = D.td(*p2)[1]
        c3 = D.td(*p3)[1]
        on2 = min((abs(c2 - d) for d in ds), default=9) <= 0.012
        on3 = min((abs(c3 - d) for d in ds), default=9) <= 0.012

        def on_axis(c):
            for a in axes:
                if _angdiff(math.degrees(math.atan2(a[3] - a[1], a[2] - a[0])), D.ang) < 1.0:
                    if abs(D.td(a[0], a[1])[1] - c) <= 0.012:
                        return True
            return False
        ax2, ax3 = on_axis(c2), on_axis(c3)
        key = ("F" if on2 else ("A" if ax2 else "-")) + ("F" if on3 else ("A" if ax3 else "-"))
        stats["ends_" + "".join(sorted(key))] += 1
        val = dm["value"]
        if on2 and on3 and val <= GAP_MAX + 0.01:
            lo, hi = min(c2, c3), max(c2, c3)
            tpos = D.td(*p2)[0]
            hit = None
            for w in recs:
                if _angdiff(w["angle"], D.ang) > 1.0:
                    continue
                b0, b1 = w["_band"]
                if abs(b0 - lo) <= 0.012 and abs(b1 - hi) <= 0.012:
                    t0, t1 = w["_t"]
                    if t0 - 1.5 <= tpos <= t1 + 1.5:
                        hit = w["id"]
                        break
            thick.append({"value": round(val, 3), "at": [round(v, 2) for v in p2], "wall": hit})
            stats["thickness_dims"] += 1
            stats["thickness_dims_matched" if hit else "thickness_dims_unmatched"] += 1
    return {"n_dims": len(g["dims"]), "stats": dict(stats), "thickness_dims": thick}


def overlap_check(recs):
    """Sum of plan overlaps between wall bodies (should be ~0: no double counting)."""
    from shapely.strtree import STRtree
    polys = [Dir(w["angle"]).rect(w["_t"][0], w["_t"][1], *w["_band"]) for w in recs]
    tree = STRtree(polys)
    tot, pairs = 0.0, []
    for i, p in enumerate(polys):
        for j in tree.query(p):
            j = int(j)
            if j <= i:
                continue
            a = p.intersection(polys[j]).area
            if a > 1e-4:
                tot += a
                pairs.append((recs[i]["id"], recs[j]["id"], round(a, 4)))
    return {"overlap_area_m2": round(tot, 4), "pairs": pairs[:40]}


'''
i = s.index(anchor)
s = s[:i] + fn + s[i:]

old = '''    if with_ctx:
        return res, ctx
    return res'''
new = '''    res["dim_crosscheck"] = dim_crosscheck(ctx, recs)
    res["overlap_check"] = overlap_check(recs)
    if with_ctx:
        return res, ctx
    return res'''
assert old in s
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("ok")
