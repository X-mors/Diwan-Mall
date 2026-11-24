# Verifier scratch: independent cross-checks of output/walls/<F>.json against raw DXF entities.
import sys, math, json, re
from collections import Counter, defaultdict
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import all_floors, floor_entities, get_floor
from shapely.geometry import LineString, Polygon, Point, box
from shapely.ops import unary_union

OUT = r"D:\حصر المباني\Diwan-Mall\output"
DOOR_RE = re.compile(r"^D(\d+)W(\d+)$", re.I)


def rect(ang, t0, t1, d0, d1):
    a = math.radians(ang)
    u = (math.cos(a), math.sin(a)); n = (-u[1], u[0])
    xy = lambda t, d: (t * u[0] + d * n[0], t * u[1] + d * n[1])
    return Polygon([xy(t0, d0), xy(t1, d0), xy(t1, d1), xy(t0, d1)])


def td(ang, x, y):
    a = math.radians(ang)
    u = (math.cos(a), math.sin(a)); n = (-u[1], u[0])
    return (x * u[0] + y * u[1], x * n[0] + y * n[1])


def wall_geoms(w):
    ang = w["angle"]; d0, d1 = w["_band"]; t0, t1 = w["_t"]
    g = rect(ang, t0, t1, d0, d1)
    # net: subtract openings
    net_ivs = [(t0, t1)]
    for o in w["openings"]:
        tc = td(ang, *o["at"])[0]
        a, b = tc - o["width"] / 2, tc + o["width"] / 2
        new = []
        for s, e in net_ivs:
            if b <= s or a >= e:
                new.append((s, e)); continue
            if a > s: new.append((s, a))
            if b < e: new.append((b, e))
        net_ivs = new
    net = [rect(ang, s, e, d0, d1) for s, e in net_ivs if e - s > 1e-3]
    return g, net, net_ivs


def load(fl):
    L = fl.to_local
    raw = {"W": [], "WIN": [], "cols": [], "doors": [], "try": [], "other": []}
    for e in floor_entities(fl, layers="W", types="LINE LWPOLYLINE"):
        if e.dxftype() == "LINE":
            a = L(e.dxf.start.x, e.dxf.start.y); b = L(e.dxf.end.x, e.dxf.end.y)
            raw["W"].append((a, b, e.dxf.handle))
        else:
            pts = [L(p[0], p[1]) for p in e.get_points("xy")]
            xs = [p[0] for p in pts]
            if max(xs) - min(xs) > 60: continue
            n = len(pts)
            for i in range(n if e.closed else n - 1):
                raw["W"].append((pts[i], pts[(i + 1) % n], e.dxf.handle))
    for e in floor_entities(fl, layers="WIN", types="LINE LWPOLYLINE"):
        if e.dxftype() == "LINE":
            raw["WIN"].append((L(e.dxf.start.x, e.dxf.start.y), L(e.dxf.end.x, e.dxf.end.y), e.dxf.handle))
        else:
            pts = [L(p[0], p[1]) for p in e.get_points("xy")]
            for i in range(len(pts) - 1):
                raw["WIN"].append((pts[i], pts[i + 1], e.dxf.handle))
    for e in floor_entities(fl, layers=("Etabs-col", "COL"), types="LWPOLYLINE"):
        pts = [L(p[0], p[1]) for p in e.get_points("xy")]
        if len(pts) >= 3:
            p = Polygon(pts)
            if not p.is_valid: p = p.buffer(0)
            raw["cols"].append((p, e.dxf.handle, e.dxf.layer))
    for e in floor_entities(fl, layers="try", types="LWPOLYLINE"):
        pts = [L(p[0], p[1]) for p in e.get_points("xy")]
        if len(pts) >= 3:
            raw["try"].append((Polygon(pts).buffer(0), e.dxf.handle))
    for e in floor_entities(fl, types="INSERT"):
        m = DOOR_RE.match(e.dxf.name)
        if m:
            raw["doors"].append((L(e.dxf.insert.x, e.dxf.insert.y), e.dxf.name, e.dxf.handle, e.dxf.layer))
    return raw


def main(nums):
    for n in nums:
        fl = get_floor(n)
        res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
        walls = res["walls"]
        raw = load(fl)
        print("=" * 30, fl.label, "walls", len(walls))
        # 1. internal consistency
        bad = []
        sg = sn = 0
        for w in walls:
            g, net, ivs = wall_geoms(w)
            Lc = math.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"])
            span = w["_t"][1] - w["_t"][0]
            netl = sum(e - s for s, e in ivs)
            ow = sum(o["width"] for o in w["openings"])
            sg += w["length_gross"]; sn += w["length_net"]
            if abs(Lc - w["length_gross"]) > 0.01 or abs(span - w["length_gross"]) > 0.01 \
                    or abs(w["length_gross"] - w["length_net"] - ow) > 0.01 or abs(netl - w["length_net"]) > 0.02:
                bad.append((w["id"], round(Lc, 3), round(span, 3), w["length_gross"], w["length_net"], round(ow, 3), round(netl, 3)))
            th = w["_band"][1] - w["_band"][0]
            if abs(th - w["thickness"]) > 0.003:
                bad.append((w["id"], "thk", th, w["thickness"]))
        print("sum gross/net", round(sg, 2), round(sn, 2), "inconsistent records:", bad[:10], len(bad))
        # 2. door blocks reported?
        ops = [(o, w["id"]) for w in walls for o in w["openings"]]
        miss = []
        for (p, name, h, lay) in raw["doors"]:
            hit = [wid for o, wid in ops if o.get("type") == "door" and o.get("block") == name and
                   math.hypot(o["at"][0] - p[0], o["at"][1] - p[1]) < 1.5]
            if not hit:
                miss.append((name, h, lay, (round(p[0], 2), round(p[1], 2))))
        nd = sum(1 for o, _ in ops if o.get("type") == "door")
        print("door blocks raw", len(raw["doors"]), "door openings", nd, "unmatched:", miss)
        # 3. overlap with concrete
        CU = unary_union([c[0] for c in raw["cols"]])
        cbad = []
        for w in walls:
            g, net, _ = wall_geoms(w)
            for r in net:
                a = r.intersection(CU).area
                if a > 0.003:
                    cbad.append((w["id"], round(a, 4), w["thickness"], w["length_net"]))
        print("net wall area inside concrete >0.003 m2:", cbad)
        # 4. WIN glazing lines lying inside NET solid parts
        wb = []
        for w in walls:
            g, net, _ = wall_geoms(w)
            NU = unary_union(net).buffer(-0.005) if net else None
            if NU is None or NU.is_empty: continue
            tot = 0
            for a, b, h in raw["WIN"]:
                ln = LineString([a, b])
                if ln.length < 0.05: continue
                tot += ln.intersection(NU).length
            if tot > 0.2:
                wb.append((w["id"], w["kind"], w["thickness"], round(tot, 2)))
        print("WIN lines inside net solid walls (>0.2 m):", wb)
        # 5. walls in shafts (try boxes) -- only flag big area
        TU = unary_union([t[0] for t in raw["try"]])
        sb = []
        for w in walls:
            g, net, _ = wall_geoms(w)
            for r in net:
                a = r.intersection(TU).area
                if a > 0.5 * r.area and r.area > 0.01:
                    sb.append((w["id"], w["kind"], round(a, 3), round(r.area, 3)))
        print("net walls mostly inside try boxes:", sb)


if __name__ == "__main__":
    main([int(a) for a in sys.argv[1:]] or [2, 3, 4, 5, 6, 7, 8])
