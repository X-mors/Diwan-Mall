import json, sys, math
import numpy as np
sys.path.insert(0, '.')
from segs import segs
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
LAY = ["W", "WIN", "Etabs-col", "COL", "try", "DASH", "X", "MASS", "ST", "PR"]
def tree(n, layers):
    gs = []
    for L in layers:
        for a, b, h, t in segs(n, L):
            if math.hypot(b[0]-a[0], b[1]-a[1]) > 1e-6:
                gs.append(LineString([a, b]))
    return STRtree(gs), gs
res = {}
T = {n: tree(n, LAY) for n in range(3, 9)}
TW = {n: tree(n, ["W"]) for n in range(3, 9)}
for n in range(3, 9):
    rows = json.load(open(f"dims_F{n:02d}.json"))
    t, gs = T[n]
    for r in rows:
        for p in (r[5], r[6]):
            P = Point(p)
            i = t.nearest(P); d = gs[i].distance(P)
            if d > 0.03:
                # does any other floor have a W line there?
                others = []
                for m in range(3, 9):
                    if m == n: continue
                    tw, gw = TW[m]; j = tw.nearest(P)
                    if gw[j].distance(P) < 0.01: others.append(m)
                print(f"F{n:02d} dim {r[2]} val {r[0]} end {p} nearest-any {d:.3f}  W-there-in-floors {others}")
