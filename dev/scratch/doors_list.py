import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
fl = get_floor(int(sys.argv[1]) if len(sys.argv)>1 else 3)
rows=[]
for e in floor_entities(fl, types="INSERT"):
    n=e.dxf.name
    if not n.startswith("D"): continue
    p=e.dxf.insert
    lx,ly=fl.to_local(p.x,p.y)
    rows.append((round(ly,2),round(lx,2),n,e.dxf.layer,round(e.dxf.xscale,3),round(e.dxf.yscale,3),round((e.dxf.rotation-fl.angle)%360,2), e.dxf.handle, tuple(round(v,3) for v in e.dxf.extrusion)))
for r in sorted(rows, reverse=True): print(r)
print(len(rows))
