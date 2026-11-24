"""print every segment (lines + polyline pieces) that intersects a local box"""
import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, box
F=int(sys.argv[1]); x0,y0,x1,y1=map(float,sys.argv[2:6])
layers=tuple(sys.argv[6].split(',')) if len(sys.argv)>6 else ('W','Etabs-col','COL','WIN','try')
B=box(x0,y0,x1,y1)
fl=get_floor(F)
for e in floor_entities(fl, layers=layers):
    t=e.dxftype()
    try:
        if t=='LINE':
            pts=[fl.to_local(e.dxf.start.x,e.dxf.start.y), fl.to_local(e.dxf.end.x,e.dxf.end.y)]
        elif t in ('LWPOLYLINE','ARC','CIRCLE','POLYLINE'):
            pts=[fl.to_local(v.x,v.y) for v in ezpath.make_path(e).flattening(0.01)]
        else: continue
    except Exception: continue
    for p,q in zip(pts,pts[1:]):
        if math.dist(p,q)<1e-6: continue
        if LineString([p,q]).intersects(B):
            print(e.dxf.layer,t,e.dxf.handle,'(%.3f,%.3f)-(%.3f,%.3f) L=%.3f'%(p[0],p[1],q[0],q[1],math.dist(p,q)))
