import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
fl=get_floor(2)
for e in floor_entities(fl, layers='WIN', types='ARC'):
    pts=[fl.to_local(v.x,v.y) for v in ezpath.make_path(e).flattening(0.005)]
    c=(3.47,36.15) if pts[0][1]>20 else (3.47,1.78)
    a0=math.degrees(math.atan2(pts[0][1]-c[1],pts[0][0]-c[0])); a1=math.degrees(math.atan2(pts[-1][1]-c[1],pts[-1][0]-c[0]))
    L=sum(math.dist(p,q) for p,q in zip(pts,pts[1:]))
    print(e.dxf.handle,'r',round(e.dxf.radius,3),'start',[round(float(v),3) for v in pts[0]],'end',[round(float(v),3) for v in pts[-1]],'len',round(L,3),'ang',round(a0,1),round(a1,1))
