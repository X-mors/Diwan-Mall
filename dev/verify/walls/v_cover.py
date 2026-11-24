# Verifier scratch: which raw W lines are NOT on the boundary of any wall record / concrete / void?
import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, wall_geoms, OUT
from shapely.geometry import LineString
from shapely.ops import unary_union


def run(n, show=80):
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    WB = unary_union([wall_geoms(w)[0].boundary for w in res["walls"]]).buffer(0.015)
    WI = unary_union([wall_geoms(w)[0] for w in res["walls"]]).buffer(-0.01)
    CU = unary_union([c[0] for c in raw["cols"]]).buffer(0.02)
    TU = unary_union([t[0] for t in raw["try"]]).buffer(0.02)
    EX = unary_union([WB, CU, TU])
    tot = 0; un = []; inside = 0
    for a, b, h in raw["W"]:
        ln = LineString([a, b])
        if ln.length < 0.01: continue
        tot += ln.length
        inside += ln.intersection(WI).length
        r = ln.difference(EX)
        if r.length > 0.02:
            un.append((round(r.length, 2), h, (round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))))
    un.sort(key=lambda x: -x[0])
    print(fl.label, "W len", round(tot, 1), "unexplained", round(sum(u[0] for u in un), 1), "W inside wall bodies", round(inside, 2))
    for u in un[:show]:
        print("   ", u)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        run(int(a))
