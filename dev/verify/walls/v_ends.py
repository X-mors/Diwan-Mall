# open-ended wall records (end not closed by a cap / other wall / concrete / void / glazing)
import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, OUT, rect, wall_geoms, td
from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    CU = unary_union([c[0] for c in raw["cols"]])
    TU = unary_union([t[0] for t in raw["try"]])
    WL = [LineString([a, b]) for a, b, h in raw["W"] if math.hypot(b[0]-a[0], b[1]-a[1]) > 0.01]
    WN = [LineString([a, b]) for a, b, h in raw["WIN"]]
    W = res["walls"]
    G = [wall_geoms(w)[0] for w in W]
    bad = []
    for i, w in enumerate(W):
        ang = w["angle"]; d0, d1 = w["_band"]; t0, t1 = w["_t"]
        for t, sgn in ((t0, -1), (t1, 1)):
            probe = rect(ang, t - 0.02, t + 0.02, d0 + 0.01, d1 - 0.01) if d1 - d0 > 0.03 else None
            if probe is None: continue
            # a line crossing the band near the end?
            crossing = any(l.intersects(probe) and abs(((math.degrees(math.atan2(l.coords[1][1]-l.coords[0][1], l.coords[1][0]-l.coords[0][0])) - ang + 90) % 180) - 90) > 30 for l in WL + WN)
            other = any(j != i and G[j].distance(probe) < 0.005 and abs(((W[j]['angle'] - ang + 90) % 180) - 90) > 30 for j in range(len(W)))
            col = probe.distance(CU) < 0.03
            void = probe.distance(TU) < 0.03
            if not (crossing or other or col or void):
                bad.append((w["id"], "start" if sgn < 0 else "end", w["thickness"], w["kind"], w["length_gross"], (round(w["x1"],2), round(w["y1"],2), round(w["x2"],2), round(w["y2"],2)), w["needs_check"]))
    print(fl.label, len(bad))
    for b in bad: print("   ", b)
