p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()
i = s.index("def dim_crosscheck(ctx, recs):")
j = s.index("def overlap_check(recs):")
fn = r'''def dim_crosscheck(ctx, recs):
    """Compare the architect's DIMENSIONs (layer DIM) with the wall reading.

    Every linear dimension has two measured points (defpoint2/3).  Each point is classified:
      wall      - lies on a face of a wall record (band edge, within the record's length)
      concrete  - on the outline of a column / core (Etabs-col, COL)
      window    - on a WIN line
      face      - on a W face line that is not part of any wall record (pier step, cap, ...)
      axis      - on an axis line (layer X)
      none      - on nothing (e.g. the end of a chain on the dimension line itself)
    Dimensions <= 0.62 m whose two points bound one wall record are THICKNESS dimensions and
    are compared with the record's thickness."""
    g = ctx.g
    axes = [a for a in g.get("axes", []) if math.hypot(a[2] - a[0], a[3] - a[1]) > 1]
    conc_edges = unary_union([c["poly"].boundary for c in ctx.conc]) if ctx.conc else None
    win_lines = [LineString([(w[0], w[1]), (w[2], w[3])]) for w in ctx.win_segs
                 if math.hypot(w[2] - w[0], w[3] - w[1]) > 1e-4]
    stats = Counter()
    thick, unmatched_pts = [], []
    for dm in g["dims"]:
        if dm["type"] not in (0, 1):
            continue
        p2, p3 = dm["p2"], dm["p3"]
        ang = dm["angle"] if dm["type"] == 0 else math.degrees(math.atan2(p3[1] - p2[1], p3[0] - p2[0])) % 180.0
        Dm = Dir(ang)              # measuring direction
        Df = Dir(ang + 90.0)       # faces measured by this dimension run along Df
        kinds, recs_at = [], []
        for P in (p2, p3):
            tP, dP = Df.td(*P)
            hit = None
            for w in recs:
                if _angdiff(w["angle"], Df.ang) > 1.0:
                    continue
                Dw = Dir(w["angle"])
                tw, dw = Dw.td(*P)
                b0, b1 = w["_band"]
                t0, t1 = w["_t"]
                if (abs(dw - b0) <= 0.012 or abs(dw - b1) <= 0.012) and t0 - 0.05 <= tw <= t1 + 0.05:
                    hit = w
                    break
            if hit is not None:
                kinds.append("wall")
                recs_at.append(hit)
                continue
            recs_at.append(None)
            Pt = Point(P)
            if conc_edges is not None and conc_edges.distance(Pt) <= 0.015:
                kinds.append("concrete")
            elif any(ln.distance(Pt) <= 0.015 for ln in win_lines):
                kinds.append("window")
            elif any(ln.distance(Pt) <= 0.015 for ln in ctx.wlines):
                kinds.append("face")
            elif any(_angdiff(math.degrees(math.atan2(a[3] - a[1], a[2] - a[0])), Df.ang) < 1.0
                     and abs(Df.td(a[0], a[1])[1] - dP) <= 0.015 for a in axes):
                kinds.append("axis")
            else:
                kinds.append("none")
        for k in kinds:
            stats["end_" + k] += 1
        for k, P in zip(kinds, (p2, p3)):
            if k == "face":
                unmatched_pts.append({"at": [round(P[0], 3), round(P[1], 3)], "dim": round(dm["value"], 3)})
        val = dm["value"]
        if val <= GAP_MAX + 0.01 and recs_at[0] is not None and recs_at[0] is recs_at[1]:
            w = recs_at[0]
            ok = abs(w["thickness"] - val) <= 0.012
            thick.append({"value": round(val, 3), "wall": w["id"], "wall_thickness": w["thickness"], "ok": ok})
            stats["thickness_dims"] += 1
            stats["thickness_dims_ok" if ok else "thickness_dims_mismatch"] += 1
    return {"n_dims": len(g["dims"]), "stats": dict(stats), "thickness_dims": thick,
            "points_on_unused_W_faces": unmatched_pts[:60]}


'''
s = s[:i] + fn + s[j:]

i = s.index("def overlap_check(recs):")
j = s.index("\n\n\n", i)
s = s[:i] + r'''def overlap_check(recs):
    """Plan overlaps between wall bodies.  The centre-line L-corner rule makes the two walls
    of a corner overlap by a (tA/2 x tB/2) square while leaving the outer quarter empty (the
    volume is still exact); those are reported separately from real double counting."""
    from shapely.strtree import STRtree
    polys = [Dir(w["angle"]).rect(w["_t"][0], w["_t"][1], *w["_band"]) for w in recs]
    tree = STRtree(polys)
    tot, corner, pairs = 0.0, 0.0, []
    for i, p in enumerate(polys):
        for j in tree.query(p):
            j = int(j)
            if j <= i:
                continue
            a = p.intersection(polys[j]).area
            if a <= 1e-4:
                continue
            A, B = recs[i], recs[j]
            sin = max(abs(math.sin(math.radians(A["angle"] - B["angle"]))), 0.05)
            if (max(A["corner_ext"]) > 0 and max(B["corner_ext"]) > 0
                    and a <= (A["thickness"] / 2 + 0.01) * (B["thickness"] / 2 + 0.01) / sin):
                corner += a
                continue
            tot += a
            pairs.append((A["id"], B["id"], round(a, 4)))
    return {"overlap_area_m2": round(tot, 4), "corner_quarter_overlap_m2": round(corner, 4),
            "pairs": pairs[:60]}''' + s[j:]
open(p, "w", encoding="utf-8").write(s)
print("ok")
