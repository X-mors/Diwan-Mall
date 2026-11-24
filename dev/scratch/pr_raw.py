import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, floor_entities, floor_texts
fl = get_floor(int(sys.argv[1]) if len(sys.argv)>1 else 3)
def L(p): return tuple(round(v,2) for v in fl.to_local(p.x,p.y))
for lay in ("PR","WIN"):
    print("=== layer", lay)
    for e in floor_entities(fl, layers=lay):
        t=e.dxftype()
        if t=="LINE":
            s,u=e.dxf.start,e.dxf.end
            print(t, L(s), L(u), round(math.dist((s.x,s.y),(u.x,u.y)),3), e.dxf.get('linetype','BYLAYER'))
        elif t=="LWPOLYLINE":
            pts=[tuple(round(v,2) for v in fl.to_local(p[0],p[1])) for p in e.get_points('xy')]
            print(t, len(pts), pts[:6], e.closed)
        elif t=="ARC":
            c=e.dxf.center
            print(t, L(c), round(e.dxf.radius,3), round(e.dxf.start_angle-fl.angle,1), round(e.dxf.end_angle-fl.angle,1))
        elif t in ("TEXT","MTEXT"):
            pass
        elif t=="INSERT":
            pass
        else:
            print(t)
for t in floor_texts(fl, layers=("PR",)):
    print("PRTEXT", repr(t['raw']), t['text'], tuple(round(v,2) for v in t['local']), t['height'])
