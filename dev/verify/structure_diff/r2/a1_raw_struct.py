import sys, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ezdxf import path as ezpath

def lpoly(fl, pts):
    return [fl.to_local(x, y) for x, y in pts]

for n in [int(a) for a in sys.argv[1:]] or [3]:
    fl = get_floor(n)
    print("=====", fl.label)
    polys = []
    for e in floor_entities(fl, layers=("Etabs-col", "COL")):
        t = e.dxftype()
        if t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            lp = lpoly(fl, pts)
            closed = e.closed
            P = Polygon(lp) if len(lp) >= 3 else None
            bx = P.bounds if P is not None else None
            print(f" {e.dxf.layer:9s} LWPOLY h={e.dxf.handle} n={len(pts)} closed={closed} bbox={[round(v,3) for v in bx]} area={P.area:.3f} per={P.length:.3f}")
        elif t == "HATCH":
            for bp in e.paths:
                try:
                    p = ezpath.from_hatch_boundary_path(bp)
                    vs = [(v.x, v.y) for v in p.flattening(0.01)]
                except Exception as ex:
                    vs = []
                lp = lpoly(fl, vs)
                if len(lp) >= 3:
                    P = Polygon(lp).buffer(0)
                    print(f" {e.dxf.layer:9s} HATCH h={e.dxf.handle} pat={e.dxf.pattern_name} bbox={[round(v,3) for v in P.bounds]} area={P.area:.3f}")
        else:
            print(f" {e.dxf.layer:9s} {t} h={e.dxf.handle}")
