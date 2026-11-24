import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, OUT, wall_geoms
from shapely.geometry import LineString
from shapely.ops import unary_union
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    GU = unary_union([wall_geoms(w)[0] for w in res["walls"]]).buffer(0.02)
    tot_in = tot_out = 0; outs = []
    for a, b, h in raw["WIN"]:
        ln = LineString([a, b])
        if ln.length < 0.3: continue
        i = ln.intersection(GU).length
        tot_in += i; o = ln.length - i
        if o > 0.3:
            tot_out += o
            outs.append((h, round(o, 2), (round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))))
    print(fl.label, "WIN len inside wall gross:", round(tot_in, 2), " outside:", round(tot_out, 2))
    for o in sorted(outs, key=lambda x: (x[2][0], x[2][1])): print("   ", o)
