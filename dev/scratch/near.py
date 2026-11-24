import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities, entity_bbox
fl=get_floor(int(sys.argv[1])); x0,y0,x1,y1=map(float,sys.argv[2:6])
for e in floor_entities(fl):
    b=entity_bbox(e)
    if not b: continue
    pts=[fl.to_local(b[0],b[1]),fl.to_local(b[2],b[3]),fl.to_local(b[0],b[3]),fl.to_local(b[2],b[1])]
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    if max(xs)<x0 or min(xs)>x1 or max(ys)<y0 or min(ys)>y1: continue
    t=e.dxftype()
    if t=="LINE":
        s,u=e.dxf.start,e.dxf.end
        print(e.dxf.layer,t,[round(v,3) for v in fl.to_local(s.x,s.y)],[round(v,3) for v in fl.to_local(u.x,u.y)])
    elif t=="LWPOLYLINE":
        print(e.dxf.layer,t,[[round(v,3) for v in fl.to_local(p[0],p[1])] for p in e.get_points('xy')], e.closed)
    else:
        print(e.dxf.layer,t,e.dxf.get('name',''), [round(min(xs),2),round(min(ys),2),round(max(xs),2),round(max(ys),2)])
