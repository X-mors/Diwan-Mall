"""Independent room polygons: node all face lines (W, 0, WIN continuous, column/try outlines,
MASS outside stairs) + door rectangles built from the D<w>W<t> block definitions + door-less
openings from openings.json, polygonize, then pick the face containing each label."""
import sys, re, json, math, pickle
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import all_floors, floor_entities, floor_texts, get_floor
from ezdxf import path as ezpath
from ezdxf.math import Vec3
from shapely.geometry import LineString, Polygon, Point, box
from shapely.ops import unary_union, polygonize
DOOR_RECT = {"D10W12": [(-0.12, 0), (0, 0), (0, 1.0), (-0.12, 1.0)],
             "D80W12": [(0, 0), (0.8, 0), (0.8, 0.12), (0, 0.12)],
             "D90W12": [(0, 0), (0.9, 0), (0.9, 0.12), (0, 0.12)],
             "D90W25": [(0, 0), (0.9, 0), (0.9, 0.25), (0, 0.25)]}
def ext(ls, d=0.02):
    cs = list(ls.coords)
    if len(cs) < 2: return ls
    def mv(a, b):
        L = math.hypot(a[0]-b[0], a[1]-b[1])
        if L < 1e-9: return a
        return (a[0] + (a[0]-b[0])/L*d, a[1] + (a[1]-b[1])/L*d)
    cs[0] = mv(cs[0], cs[1]); cs[-1] = mv(cs[-1], cs[-2])
    return LineString(cs)
def run(n):
    fl = get_floor(n); L = fl.to_local
    lines = []; info = {"doors": 0}
    st = []
    for e in floor_entities(fl, layers=("W", "0", "WIN", "Etabs-col", "COL", "try", "MASS", "ST")):
        t = e.dxftype()
        if t in ("TEXT", "MTEXT", "INSERT", "DIMENSION", "HATCH", "POINT"): continue
        try:
            pts = [L(v.x, v.y) for v in ezpath.make_path(e).flattening(0.01)]
        except Exception: continue
        if len(pts) < 2: continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        if max(xs)-min(xs) > 40 or max(ys)-min(ys) > 60: continue
        if not (-4 < sum(xs)/len(xs) < 25 and -5 < sum(ys)/len(ys) < 45): continue
        lay = e.dxf.layer
        if lay == "WIN":
            lt = e.dxf.get("linetype", "BYLAYER")
            if lt.upper() == "BYLAYER": lt = fl.doc.layers.get(lay).dxf.linetype
            if lt.upper() not in ("CONTINUOUS", "BYBLOCK"): continue
        if lay == "ST": st.append(LineString(pts)); continue
        if lay == "0" and t == "LWPOLYLINE" and (e.closed or len(e) > 4): continue
        lines.append((LineString(pts), lay))
    # stair hulls to drop MASS stair well
    sh = unary_union([s.buffer(0.6) for s in st])
    shp = list(sh.geoms) if hasattr(sh, "geoms") else [sh]
    hulls = [unary_union([s for s in st if p.intersects(s)]).convex_hull.buffer(0.05) for p in shp]
    lines = [(g, lay) for g, lay in lines if not (lay == "MASS" and any(h.contains(g) for h in hulls))]
    geoms = [ext(g) if lay in ("W", "0", "MASS", "WIN") else g for g, lay in lines]
    for e in floor_entities(fl, types="INSERT"):
        nm = e.dxf.name.upper()
        if nm in DOOR_RECT:
            m = e.matrix44()
            pts = [m.transform(Vec3(x, y, 0)) for x, y in DOOR_RECT[nm]]
            pts = [L(p.x, p.y) for p in pts]
            geoms.append(LineString(pts + [pts[0]])); info["doors"] += 1
    op = json.load(open(rf"D:\حصر المباني\Diwan-Mall\output\openings\{fl.label}.json", encoding="utf-8"))
    for o in op.get("openings", []):
        e1, e2 = map(tuple, o["ends"]); t = o.get("wall_t") or 0.12
        geoms.append(LineString([e1, e2]).buffer(t/2, cap_style=2).exterior)
    for d in op.get("doors", []):
        if d.get("source") != "block" and d.get("jamb_a") and d.get("jamb_b"):
            a0, a1 = map(tuple, d["jamb_a"]); b0, b1 = map(tuple, d["jamb_b"])
            if math.dist(a0, b0) + math.dist(a1, b1) > math.dist(a0, b1) + math.dist(a1, b0): b0, b1 = b1, b0
            geoms.append(LineString([a0, a1, b1, b0, a0]))
    U = unary_union(geoms)
    faces = list(polygonize(U))
    texts = [t for t in floor_texts(fl, layers=("TEXT", "-A-TEXT")) if -4 < t["local"][0] < 25 and -5 < t["local"][1] < 45]
    out = []
    for t in texts:
        x, y = t["local"]
        cands = [Point(x - 0.05, y + 0.05), Point(x + 0.05, y + 0.05), Point(x, y)]
        hit = None
        for p in cands:
            fs = [f for f in faces if f.contains(p) and f.area > 0.15]
            if fs:
                hit = min(fs, key=lambda f: f.area); break
        out.append({"text": t["text"], "xy": (round(x, 3), round(y, 3)), "area": round(hit.area, 3) if hit else None,
                    "perim": round(hit.length, 3) if hit else None, "bounds": [round(v, 3) for v in hit.bounds] if hit else None,
                    "poly": hit})
    return faces, out, info
if __name__ == "__main__":
    res = {}
    for n in map(int, sys.argv[1:]):
        faces, out, info = run(n)
        res[n] = (faces, out)
        print("F%02d faces=%d doors=%d" % (n, len(faces), info["doors"]))
    pickle.dump(res, open(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\indep.pkl", "wb"))
