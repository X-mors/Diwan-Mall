import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, entity_bbox
from ezdxf import path as ezpath
from shapely.geometry import Polygon
fl = get_floor(3)
ins = [e for e in fl.msp.query('INSERT[layer=="Etabs-Slab"]') if (lambda b: b and fl.contains((b[0]+b[2])/2,(b[1]+b[3])/2))(entity_bbox(e))]
print(len(ins), [ (e.dxf.name, tuple(e.dxf.insert), e.dxf.xscale, e.dxf.rotation, e.dxf.handle) for e in ins])
e = ins[0]
for v in e.virtual_entities():
    t = v.dxftype()
    if t == 'HATCH':
        for p in v.paths:
            pass
        P = ezpath.from_hatch(v)
        for pp in P:
            pts = [fl.to_local(q.x,q.y) for q in pp.flattening(0.01)]
            poly = Polygon(pts)
            xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
            print(f"  HATCH {v.dxf.layer} pat={v.dxf.pattern_name} n={len(pts)} bbox=({min(xs):.3f},{min(ys):.3f})-({max(xs):.3f},{max(ys):.3f}) area={poly.area:.3f}")
            if len(pts) < 14: print("     ", [(round(x,3),round(y,3)) for x,y in pts])
    elif t == 'LWPOLYLINE':
        pp = ezpath.make_path(v)
        pts = [fl.to_local(q.x,q.y) for q in pp.flattening(0.01)]
        xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
        print(f"  LWPOLY {v.dxf.layer} n={len(pts)} closed={v.closed} bbox=({min(xs):.3f},{min(ys):.3f})-({max(xs):.3f},{max(ys):.3f}) w={max(xs)-min(xs):.3f} h={max(ys)-min(ys):.3f}")
    elif t == 'LINE':
        a = fl.to_local(v.dxf.start.x, v.dxf.start.y); b = fl.to_local(v.dxf.end.x, v.dxf.end.y)
        print(f"  LINE {v.dxf.layer} ({a[0]:.3f},{a[1]:.3f})-({b[0]:.3f},{b[1]:.3f})")
