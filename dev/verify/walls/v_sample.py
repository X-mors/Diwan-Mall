# Verifier scratch: dump raw evidence around specific wall records.
import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, wall_geoms, OUT, td
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

_cache = {}


def raw_for(n):
    if n not in _cache:
        fl = get_floor(n)
        _cache[n] = (fl, load(fl), json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8")))
    return _cache[n]


def show(n, wid, pad=0.6):
    fl, raw, res = raw_for(n)
    w = next(x for x in res["walls"] if x["id"] == wid)
    ang = w["angle"]; d0, d1 = w["_band"]; t0, t1 = w["_t"]
    print(f"--- {fl.label} {wid} ang={ang} band={w['_band']} t={w['_t']} thk={w['thickness']} kind={w['kind']} "
          f"gross={w['length_gross']} net={w['length_net']} nc={w['needs_check']} reason={w['reason']}")
    print("    sides:", [(s['share'], s['labels']) for s in w['sides']], "junctions", w.get('junctions'), "corner_ext", w.get('corner_ext'), "end_reason", w.get('end_reason'))
    for o in w["openings"]:
        print("    opening:", {k: o[k] for k in o if k in ('type', 'width', 'at', 'block', 'door_width', 'to_concrete')})
    # raw W segs parallel and within band +-pad
    rows = []
    for a, b, h in raw["W"]:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 0.02: continue
        A = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
        ta, da = td(ang, *a); tb, db = td(ang, *b)
        par = abs((A - ang + 90) % 180 - 90) < 1.0
        tmin, tmax = min(ta, tb), max(ta, tb)
        if par and d0 - 0.3 <= (da + db) / 2 <= d1 + 0.3 and tmax >= t0 - pad and tmin <= t1 + pad:
            rows.append(("PAR", round((da + db) / 2, 3), round(tmin, 3), round(tmax, 3), h))
        elif not par and min(da, db) <= d1 + 0.02 and max(da, db) >= d0 - 0.02 and t0 - pad <= (ta + tb) / 2 <= t1 + pad:
            rows.append(("X  ", round(min(da, db), 3), round(max(da, db), 3), round((ta + tb) / 2, 3), h))
    for r in sorted(rows):
        print("   ", r)
    pass
    g, net, ivs = wall_geoms(w)
    for c, h, lay in raw["cols"]:
        if c.distance(g) < 0.05:
            ts = [td(ang, x, y)[0] for x, y in c.exterior.coords]
            ds = [td(ang, x, y)[1] for x, y in c.exterior.coords]
            print(f"    col {lay} {h}: t {min(ts):.3f}..{max(ts):.3f} d {min(ds):.3f}..{max(ds):.3f}")
    for (p, name, h, lay) in raw["doors"]:
        if g.buffer(0.3).contains(__import__('shapely.geometry', fromlist=['Point']).Point(p)):
            print(f"    door {name} {h} on {lay} at t={td(ang, *p)[0]:.3f} d={td(ang, *p)[1]:.3f}")
    wl = 0
    for a, b, h in raw["WIN"]:
        ln = LineString([a, b])
        x = ln.intersection(g.buffer(0.01)).length
        if x > 0.05:
            ta, da = td(ang, *a); tb, db = td(ang, *b)
            print(f"    WIN {h}: t {min(ta, tb):.3f}..{max(ta, tb):.3f} d {(da + db) / 2:.3f} inside {x:.2f}")


if __name__ == "__main__":
    n = int(sys.argv[1])
    for wid in sys.argv[2:]:
        show(n, wid)
