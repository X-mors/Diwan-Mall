import sys, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, OUT, wall_geoms
from shapely.ops import unary_union
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    CU = unary_union([c[0] for c in raw["cols"]])
    TU = unary_union([t[0] for t in raw["try"]])
    out = []
    for w in res["walls"]:
        g = wall_geoms(w)[0]
        a = g.intersection(CU).area; v = g.intersection(TU).area
        if a > 0.005 or (v > 0.01 and v > 0.3 * g.area):
            out.append((w["id"], w["kind"], w["thickness"], w["length_gross"], round(a, 3), round(v, 3), [o["type"] for o in w["openings"]]))
    print(fl.label, out)
