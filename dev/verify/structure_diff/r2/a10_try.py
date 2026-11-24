import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from shapely.geometry import Polygon, LineString
from ezdxf import path as ezpath
sys.path.insert(0, '.')
from segs import segs
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    dash = [LineString([a, b]) for a, b, h, t in segs(n, "DASH")]
    print("==", fl.label)
    seen = []
    for e in floor_entities(fl, layers="try"):
        t = e.dxftype()
        if t == "LWPOLYLINE":
            pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
            P = Polygon(pts).buffer(0) if len(pts) >= 3 else None
        elif t == "HATCH":
            p = ezpath.from_hatch_boundary_path(e.paths[0]); pts = [fl.to_local(v.x, v.y) for v in p.flattening(0.01)]
            P = Polygon(pts).buffer(0)
        else:
            print("  other", t, e.dxf.handle); continue
        b = [round(v, 3) for v in P.bounds]
        # diagonals inside
        nd = 0
        for d in dash:
            if d.length > 0.3 and P.buffer(0.02).contains(d):
                (x0, y0), (x1, y1) = d.coords
                if abs(x1-x0) > 0.1 and abs(y1-y0) > 0.1: nd += 1
        print(f"  {t:10s} {e.dxf.handle:5s} closed={getattr(e,'closed',None)} bbox={b} size={b[2]-b[0]:.2f}x{b[3]-b[1]:.2f} area={P.area:.3f} diag={nd}")
