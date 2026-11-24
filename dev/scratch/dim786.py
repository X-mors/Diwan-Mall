import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
fl = get_floor(3)
for e in floor_entities(fl, types="DIMENSION"):
    try: m = e.get_measurement()
    except Exception: continue
    if abs(m - 0.786) < 0.002 or abs(m-0.801)<0.002 or abs(m-0.815)<0.002:
        d = e.dxf
        p2 = fl.to_local(d.defpoint2.x, d.defpoint2.y); p3 = fl.to_local(d.defpoint3.x, d.defpoint3.y)
        print(round(m,3), "type", d.dimtype & 7, "angle", round(d.get("angle", 0),2), "local p2", [round(v,3) for v in p2], "p3", [round(v,3) for v in p3], "dist", round(math.dist(p2,p3),3), "text", d.get("text"))
