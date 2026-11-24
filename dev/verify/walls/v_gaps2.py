# adjacent-only unbridged gaps between collinear wall records
import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, OUT, rect
from shapely.ops import unary_union
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    CU = unary_union([c[0] for c in raw["cols"]]).buffer(0.02)
    TU = unary_union([t[0] for t in raw["try"]]).buffer(0.02)
    W = res["walls"]
    groups = {}
    for w in W:
        k = (round(w["angle"], 1), round(w["_band"][0], 2), round(w["_band"][1], 2))
        groups.setdefault(k, []).append(w)
    out = []
    for k, ws in groups.items():
        ws.sort(key=lambda w: w["_t"][0])
        for a, b in zip(ws, ws[1:]):
            g = b["_t"][0] - a["_t"][1]
            if 0.05 < g <= 2.0:
                R = rect(a["angle"], a["_t"][1] + 0.01, b["_t"][0] - 0.01, *a["_band"])
                if R.intersection(CU).area / R.area < 0.3 and R.intersection(TU).area / R.area < 0.3:
                    c = R.centroid
                    out.append((a["id"], b["id"], round(g, 3), a["thickness"], a["kind"], (round(c.x, 2), round(c.y, 2))))
    print(fl.label, len(out))
    for o in out: print("   ", o)
