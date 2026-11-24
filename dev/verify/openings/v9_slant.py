import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
F=int(sys.argv[1])
fl=get_floor(F)
segs=[]
for e in floor_entities(fl, layers=('W','WIN','Etabs-col','COL','try')):
    t=e.dxftype()
    try:
        if t=='LINE': pts=[fl.to_local(e.dxf.start.x,e.dxf.start.y), fl.to_local(e.dxf.end.x,e.dxf.end.y)]
        elif t in ('LWPOLYLINE','ARC','CIRCLE'): pts=[fl.to_local(v.x,v.y) for v in ezpath.make_path(e).flattening(0.01)]
        else: continue
    except Exception: continue
    for p,q in zip(pts,pts[1:]):
        L=math.dist(p,q)
        if L<1e-4: continue
        ang=math.degrees(math.atan2(q[1]-p[1],q[0]-p[0]))%180
        if 2<ang<88 or 92<ang<178:
            segs.append((e.dxf.layer,e.dxf.handle,round(ang,2),[round(v,3) for v in p],[round(v,3) for v in q],round(L,3)))
for s in sorted(segs,key=lambda s:(s[2],min(s[3][1],s[4][1]))): print(s)
