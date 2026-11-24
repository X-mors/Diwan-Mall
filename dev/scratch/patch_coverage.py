p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()
anchor = "def overlap_check(recs):"
fn = r'''def face_coverage(ctx, recs):
    """How much of the W linework is explained by the wall records.  A W segment is 'used' where
    it lies on a band edge of a wall record (within its length) or on a jamb/cap across a band.
    Unused W length (outside concrete / shaft boxes) points at walls the reader may have missed,
    single-line elements (terrace outline) or architectural details."""
    from shapely.strtree import STRtree
    edges = []
    for w in recs:
        D = Dir(w["angle"])
        t0, t1 = w["_t"]
        b0, b1 = w["_band"]
        rect = D.rect(t0, t1, b0, b1)
        edges.append(rect.boundary.buffer(0.015))
    tree = STRtree(edges) if edges else None
    mask = []
    if ctx.CU is not None:
        mask.append(ctx.CU.buffer(0.02))
    if ctx.VU is not None:
        mask.append(ctx.VU.buffer(0.02))
    if getattr(ctx, "PU", None) is not None:
        mask.append(ctx.PU.buffer(0.02))
    M = unary_union(mask) if mask else None
    total = used = masked = 0.0
    unused = []
    for sg, ln in zip(ctx.wsegs, ctx.wlines):
        L = ln.length
        total += L
        if M is not None:
            inside = ln.intersection(M).length
            if inside >= L - 1e-6:
                masked += L
                continue
        cov = 0.0
        if tree is not None:
            parts = [edges[int(k)] for k in tree.query(ln)]
            if parts:
                cov = ln.intersection(unary_union(parts)).length
        used += min(cov, L)
        rest = L - min(cov, L)
        if rest > 0.25:
            unused.append({"handle": sg[4], "len": round(rest, 2),
                           "from": [round(sg[0], 2), round(sg[1], 2)], "to": [round(sg[2], 2), round(sg[3], 2)]})
    unused.sort(key=lambda u: -u["len"])
    return {"w_length": round(total, 2), "on_wall_records": round(used, 2),
            "on_concrete_shaft_planter": round(masked, 2),
            "unexplained": round(total - used - masked, 2), "largest_unexplained": unused[:25]}


'''
i = s.index(anchor)
s = s[:i] + fn + s[i:]
old = '''    res["overlap_check"] = overlap_check(recs)'''
new = '''    res["overlap_check"] = overlap_check(recs)
    res["face_coverage"] = face_coverage(ctx, recs)'''
assert old in s
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("ok")
