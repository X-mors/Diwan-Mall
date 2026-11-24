"""independent layer diff: portion of each segment of floor A not within 2 cm (collinear-ish) of floor B's segments"""
import sys, math, pickle
import numpy as np
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_structure_diff\r2")
from segs import segs
from shapely.geometry import LineString, MultiLineString
from shapely.strtree import STRtree
from shapely.ops import unary_union
TOL = 0.02
def geoms(n, L, maxlen=50):
    out = []
    for a, b, h, t in segs(n, L):
        if math.hypot(b[0]-a[0], b[1]-a[1]) < 1e-6: continue
        out.append((LineString([a, b]), h))
    # drop entities whose total length > maxlen (frame / long outline polylines)
    tot = {}
    for g, h in out: tot[h] = tot.get(h, 0) + g.length
    return [(g, h) for g, h in out if tot[h] <= maxlen]
def uncovered(A, B):
    """pieces of A not inside buffer(TOL) of B ; returns list of (LineString, handle)"""
    if not B:
        return [(g, h) for g, h in A]
    tree = STRtree([g for g, _ in B])
    Bg = [g for g, _ in B]
    res = []
    for g, h in A:
        idx = tree.query(g.buffer(TOL))
        if len(idx) == 0:
            res.append((g, h)); continue
        cov = unary_union([Bg[i].buffer(TOL, cap_style=2) for i in idx])
        d = g.difference(cov)
        if not d.is_empty and d.length > 0.0:
            res.append((d, h))
    return res
def total(pcs, minlen=0.05):
    s = 0
    for g, h in pcs:
        parts = getattr(g, "geoms", [g])
        s += sum(p.length for p in parts if p.length >= minlen)
    return s
if __name__ == "__main__":
    L = sys.argv[1] if len(sys.argv) > 1 else "W"
    ref = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    G = {n: geoms(n, L) for n in range(2, 9)}
    print("layer", L)
    print("     " + "".join(f"F{m:02d}    " for m in range(2, 9)))
    for n in range(2, 9):
        row = []
        for m in range(2, 9):
            row.append("  —    " if n == m else f"{total(uncovered(G[n], G[m])):7.2f}")
        print(f"F{n:02d} " + " ".join(row))
    pickle.dump(G, open(f"G_{L}.pkl", "wb"))
