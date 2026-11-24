# Verifier scratch: hunt for W face pairs (raw) not explained by any wall record / concrete / void.
import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, wall_geoms, OUT
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union


def ang(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def adiff(a, b):
    return abs((a - b + 90) % 180 - 90)


def run(n, min_len=0.15, show=40):
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    W = [(a, b, h) for a, b, h in raw["W"] if math.hypot(b[0] - a[0], b[1] - a[1]) > 0.05]
    WU = unary_union([wall_geoms(w)[0] for w in res["walls"]]).buffer(0.015)
    CU = unary_union([c[0] for c in raw["cols"]]).buffer(0.015)
    TU = unary_union([t[0] for t in raw["try"]]).buffer(0.015)
    EXPL = unary_union([WU, CU, TU])
    segs = []
    for a, b, h in W:
        A = ang(a, b)
        r = math.radians(A)
        u = (math.cos(r), math.sin(r)); nv = (-u[1], u[0])
        t1 = a[0] * u[0] + a[1] * u[1]; t2 = b[0] * u[0] + b[1] * u[1]
        d = (a[0] * nv[0] + a[1] * nv[1] + b[0] * nv[0] + b[1] * nv[1]) / 2
        segs.append(dict(A=A, u=u, nv=nv, t0=min(t1, t2), t1=max(t1, t2), d=d, h=h, a=a, b=b))
    miss = []
    for i, s in enumerate(segs):
        for j, q in enumerate(segs):
            if j <= i or adiff(s["A"], q["A"]) > 1.0:
                continue
            # project q into s frame
            u, nv = s["u"], s["nv"]
            qt = sorted([q["a"][0] * u[0] + q["a"][1] * u[1], q["b"][0] * u[0] + q["b"][1] * u[1]])
            qd = (q["a"][0] * nv[0] + q["a"][1] * nv[1] + q["b"][0] * nv[0] + q["b"][1] * nv[1]) / 2
            off = qd - s["d"]
            if not (0.06 <= abs(off) <= 0.62):
                continue
            t0, t1 = max(s["t0"], qt[0]), min(s["t1"], qt[1])
            if t1 - t0 < min_len:
                continue
            d0, d1 = sorted([s["d"], qd])
            # consecutive: no other parallel seg strictly between on the overlap
            blocked = False
            for k, o in enumerate(segs):
                if k in (i, j) or adiff(o["A"], s["A"]) > 1.0:
                    continue
                od = (o["a"][0] * nv[0] + o["a"][1] * nv[1] + o["b"][0] * nv[0] + o["b"][1] * nv[1]) / 2
                if d0 + 0.015 < od < d1 - 0.015:
                    ot = sorted([o["a"][0] * u[0] + o["a"][1] * u[1], o["b"][0] * u[0] + o["b"][1] * u[1]])
                    if min(ot[1], t1) - max(ot[0], t0) > 0.5 * (t1 - t0):
                        blocked = True
                        break
            if blocked:
                continue
            xy = lambda t, d: (t * u[0] + d * nv[0], t * u[1] + d * nv[1])
            R = Polygon([xy(t0, d0), xy(t1, d0), xy(t1, d1), xy(t0, d1)])
            un = R.difference(EXPL)
            if un.area / (d1 - d0) > min_len:
                c = R.centroid
                miss.append((round(un.area / (d1 - d0), 2), round(d1 - d0, 3), (round(c.x, 2), round(c.y, 2)),
                             round(s["A"], 1), s["h"], q["h"], round(t1 - t0, 2)))
    miss.sort(key=lambda m: -m[0])
    tot = sum(m[0] for m in miss)
    print(fl.label, "unexplained W pair bands:", len(miss), "sum len", round(tot, 2))
    for m in miss[:show]:
        print("   len_unexpl=%s thk=%s at=%s ang=%s handles=%s/%s overlap=%s" % m)


if __name__ == "__main__":
    for a in (sys.argv[1:] or ["3"]):
        run(int(a))
