import sys, json, pickle
sys.path.insert(0, '.')
from a6_diff import geoms, uncovered
S = json.load(open(r"D:\حصر المباني\Diwan-Mall\output\floor_compare\summary.json", encoding="utf-8"))
R = S["regions"]
def inreg(g, fl, m=0.15):
    c = g.centroid
    hits = []
    for r in R:
        x0, y0, x1, y1 = r["bbox"]
        if x0 - m <= c.x <= x1 + m and y0 - m <= c.y <= y1 + m and (fl in r["floors_unlike_ref"] or fl in r["floors_differing_from_ref"]):
            hits.append(r["id"])
    return hits
for L in sys.argv[1:] or ["W"]:
    G = {n: geoms(n, L) for n in range(2, 9)}
    for n in range(2, 9):
        if n == 6: continue
        fl = f"F{n:02d}"
        for sign, pcs in (("+", uncovered(G[n], G[6])), ("-", uncovered(G[6], G[n]))):
            for g, h in pcs:
                for p in getattr(g, "geoms", [g]):
                    if p.length < 0.05: continue
                    hits = inreg(p, fl)
                    if not hits:
                        c = p.centroid
                        print(f"MISS {L} {fl} {sign} h={h} len={p.length:.2f} at ({c.x:.2f},{c.y:.2f}) bbox={[round(v,2) for v in p.bounds]}")
