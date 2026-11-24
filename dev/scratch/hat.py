import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import Polygon
for n in (2,3,5,8):
    fl = get_floor(n)
    print("==", fl.label)
    for lay in ("Etabs-col","try","W"):
        for v in floor_entities(fl, layers=lay, types="HATCH"):
            for pp in ezpath.from_hatch(v):
                pts = [fl.to_local(q.x,q.y) for q in pp.flattening(0.01)]
                if len(pts)<3: continue
                poly = Polygon(pts)
                xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
                print(f"  {lay} HATCH assoc={v.dxf.associative} pat={v.dxf.pattern_name} n={len(pts)} bbox=({min(xs):.3f},{min(ys):.3f})-({max(xs):.3f},{max(ys):.3f}) area={poly.area:.3f}")
