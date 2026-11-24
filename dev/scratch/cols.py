import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, entity_bbox, floor_entities
from shapely.geometry import Polygon
fl = get_floor(int(sys.argv[1]) if len(sys.argv)>1 else 3)
for lay in ("Etabs-col","COL","try"):
    print("==", lay)
    for e in floor_entities(fl, layers=lay, types="LWPOLYLINE"):
        pts = [fl.to_local(e.ocs().to_wcs((p[0],p[1],e.dxf.elevation)).x, e.ocs().to_wcs((p[0],p[1],e.dxf.elevation)).y) for p in e.get_points("xy")]
        bul = [p[4] for p in e.get_points("xyseb")]
        P = Polygon(pts) if len(pts)>=3 else None
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        print(f"  n={len(pts)} closed={e.closed} bbox=({min(xs):.3f},{min(ys):.3f})-({max(xs):.3f},{max(ys):.3f}) w={max(xs)-min(xs):.3f} h={max(ys)-min(ys):.3f} area={P.area if P else 0:.3f} perim={P.length if P else 0:.3f} bulge={any(bul)} ext={tuple(e.dxf.extrusion)} col={e.dxf.get('color')} cw={e.dxf.get('const_width',0)}")
        if len(pts)>4: print("     ", [(round(x,3),round(y,3)) for x,y in pts])
    for e in floor_entities(fl, layers=lay, types="HATCH"):
        b = entity_bbox(e)
        a = fl.to_local(b[0],b[1]); 
        paths=[]
        for p in e.paths:
            if hasattr(p,'vertices'):
                paths.append([fl.to_local(v[0],v[1]) for v in p.vertices])
            else:
                paths.append(('edges', len(p.edges)))
        print(f"  HATCH pat={e.dxf.pattern_name} solid={e.dxf.solid_fill} npaths={len(e.paths)} assoc={e.dxf.associative}", [ (len(p), round(min(q[0] for q in p),3), round(min(q[1] for q in p),3), round(max(q[0] for q in p),3), round(max(q[1] for q in p),3)) if isinstance(p,list) else p for p in paths])
