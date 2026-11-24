import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
for n in (2,3):
    fl = get_floor(n)
    for e in floor_entities(fl, layers=("W","WIN"), types="ARC HATCH"):
        if e.dxftype()=="ARC":
            c=e.dxf.center
            print(n, e.dxf.layer, "ARC", [round(v,2) for v in fl.to_local(c.x,c.y)], round(e.dxf.radius,3), round(e.dxf.start_angle-fl.angle,1), round(e.dxf.end_angle-fl.angle,1), tuple(e.dxf.extrusion))
        else:
            from diwan_common import entity_bbox
            b=entity_bbox(e); 
            print(n, e.dxf.layer, "HATCH", e.dxf.pattern_name, [round(v,2) for v in fl.to_local(b[0],b[1])], [round(v,2) for v in fl.to_local(b[2],b[3])])
