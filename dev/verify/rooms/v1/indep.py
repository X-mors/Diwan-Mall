# Independent room polygonisation for verification (verifier scratch, not part of the tool)
import sys, math, pickle, json
from pathlib import Path
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities, floor_texts
from shapely.geometry import LineString, Polygon, box, Point, MultiPolygon
from shapely.ops import unary_union
import ezdxf

OUT = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\v1")
DOOR_RECT = {  # block-coord rectangle of the wall gap (jamb to jamb, through the wall)
    "D10W12": (-0.12, 0.0, 0.0, 1.0),
    "D80W12": (0.0, 0.0, 0.8, 0.12),
    "D90W12": (0.0, 0.0, 0.9, 0.12),
    "D90W25": (0.0, 0.0, 0.9, 0.25),
}


def is_dashed(e, doc):
    lt = e.dxf.get("linetype", "BYLAYER")
    if lt.upper() == "BYLAYER":
        try:
            lt = doc.layers.get(e.dxf.layer).dxf.linetype
        except Exception:
            lt = "CONTINUOUS"
    return "DASH" in lt.upper() or "HIDDEN" in lt.upper()


def flat(e, L):
    t = e.dxftype()
    if t == "LINE":
        return [[L(e.dxf.start.x, e.dxf.start.y), L(e.dxf.end.x, e.dxf.end.y)]]
    if t == "LWPOLYLINE":
        pts = [L(x, y) for x, y in e.get_points("xy")]
        if e.closed and pts:
            pts.append(pts[0])
        return [pts]
    if t in ("ARC", "CIRCLE"):
        c, r = e.dxf.center, e.dxf.radius
        a0, a1 = (e.dxf.start_angle, e.dxf.end_angle) if t == "ARC" else (0, 360)
        if a1 < a0:
            a1 += 360
        n = max(8, int((a1 - a0) / 3))
        return [[L(c.x + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                   c.y + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]]
    return []


def collect(n):
    fl = get_floor(n)
    L = fl.to_local
    doc = fl.doc
    g = {"w": [], "zero": [], "win": [], "win_d": [], "cols": [], "try": [], "try_hatch": [], "mass": [],
         "doors": [], "texts": [], "st": [], "pr": [], "dash": []}
    for e in floor_entities(fl):
        lay, t = e.dxf.layer, e.dxftype()
        if t == "INSERT":
            if e.dxf.name in DOOR_RECT:
                x0, y0, x1, y1 = DOOR_RECT[e.dxf.name]
                m = e.matrix44()
                pts = [m.transform((x, y, 0)) for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
                g["doors"].append({"name": e.dxf.name, "layer": lay, "handle": e.dxf.handle,
                                   "pts": [L(p.x, p.y) for p in pts]})
            continue
        if t == "HATCH":
            if lay in ("try", "Etabs-col"):
                for p in e.paths:
                    try:
                        vs = [L(v[0], v[1]) for v in p.vertices]
                    except AttributeError:
                        vs = []
                        for ed in p.edges:
                            try:
                                vs.append(L(ed.start[0], ed.start[1]))
                            except Exception:
                                pass
                    if len(vs) >= 3:
                        g["try_hatch" if lay == "try" else "cols"].append({"pts": vs, "handle": e.dxf.handle})
            continue
        if t not in ("LINE", "LWPOLYLINE", "ARC", "CIRCLE"):
            continue
        polys = flat(e, L)
        if not polys or not polys[0]:
            continue
        xs = [p[0] for p in polys[0]]
        ys = [p[1] for p in polys[0]]
        if max(xs) - min(xs) > 60 or max(ys) - min(ys) > 80:
            continue
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        if not (-6 < cx < 27 and -7 < cy < 47):
            continue
        rec = {"pts": polys[0], "handle": e.dxf.handle, "type": t}
        if lay == "W":
            g["w"].append(rec)
        elif lay == "0":
            g["zero"].append(rec)
        elif lay == "WIN":
            g["win_d" if is_dashed(e, doc) else "win"].append(rec)
        elif lay in ("Etabs-col", "COL") and t == "LWPOLYLINE":
            g["cols"].append(rec)
        elif lay == "try":
            g["try"].append(rec)
        elif lay in ("MASS",):
            g["mass"].append(rec)
        elif lay == "ST":
            g["st"].append(rec)
        elif lay == "PR":
            g["pr"].append(rec)
        elif lay == "DASH":
            g["dash"].append(rec)
    for t in floor_texts(fl, layers=("TEXT", "-A-TEXT")):
        g["texts"].append({"text": t["text"], "x": t["local"][0], "y": t["local"][1], "layer": t["layer"],
                           "handle": t["handle"]})
    return g


def faces(g, eps=0.015, use_mass=True, use_zero=True):
    geoms = []
    for k in ["w", "win"] + (["zero"] if use_zero else []) + (["mass"] if use_mass else []) + ["try"]:
        for r in g[k]:
            if len(r["pts"]) >= 2:
                geoms.append(LineString(r["pts"]).buffer(eps, cap_style=2, join_style=2))
    for r in g["cols"] + g["try_hatch"]:
        try:
            p = Polygon(r["pts"]).buffer(0)
            geoms.append(p.buffer(eps, join_style=2))
        except Exception:
            pass
    for d in g["doors"]:
        geoms.append(Polygon(d["pts"]).buffer(eps, join_style=2))
    U = unary_union(geoms)
    env = box(-6, -7, 27, 47)
    free = env.difference(U)
    out = []
    for f in getattr(free, "geoms", [free]):
        if f.area < 0.02:
            continue
        if f.exterior.distance(env.exterior) < 1e-6 or f.intersects(env.exterior):
            continue
        out.append(f.buffer(eps, join_style=2))
    return out, U


if __name__ == "__main__":
    floors = [int(a) for a in sys.argv[1:]] or [2, 3, 4, 5, 6, 7, 8]
    for n in floors:
        g = collect(n)
        F, U = faces(g)
        with open(OUT / f"indep_F0{n}.pkl", "wb") as f:
            pickle.dump({"g": g, "faces": F}, f)
        print(n, "doors", len(g["doors"]), "faces", len(F), "area>1", sum(1 for f in F if f.area > 1),
              "sum", round(sum(f.area for f in F), 2))
