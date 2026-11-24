import sys, math, collections
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
fl = get_floor(3)
c = collections.Counter()
n=0
for e in floor_entities(fl, layers="DIM"):
    t = e.dxftype(); c[t]+=1
    if t == "DIMENSION" and n < 15:
        n+=1
        d = e.dxf
        p2 = fl.to_local(d.defpoint2.x, d.defpoint2.y); p3 = fl.to_local(d.defpoint3.x, d.defpoint3.y)
        print(d.dimtype, round(d.get("actual_measurement",-1),3), repr(d.get("text","")), tuple(round(v,3) for v in p2), tuple(round(v,3) for v in p3), round(d.get("angle",0)-fl.angle,2), d.dimstyle)
print(c)
types = collections.Counter(e.dxf.dimtype & 7 for e in floor_entities(fl, layers="DIM", types="DIMENSION"))
print(types)
