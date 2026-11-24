import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import box, LineString
for fno in (2, 3, 5):
    fl = get_floor(fno)
    for bx in (box(1.2, 35.0, 2.6, 36.4), box(3.2, 37.4, 4.1, 38.4), box(1.0, 1.6, 2.2, 2.6)):
        hits = []
        for e in floor_entities(fl):
            t = e.dxftype()
            if t in ("TEXT","MTEXT","DIMENSION"): continue
            try:
                if t == "INSERT":
                    ents = list(e.virtual_entities())
                else:
                    ents = [e]
                for ee in ents:
                    if ee.dxftype() in ("TEXT","MTEXT","ATTRIB","HATCH"): continue
                    p = ezpath.make_path(ee)
                    pts = [fl.to_local(v.x, v.y) for v in p.flattening(0.02)]
                    if len(pts) >= 2 and LineString(pts).intersects(bx):
                        hits.append((e.dxf.layer if t!="INSERT" else e.dxf.layer+":"+e.dxf.name+"/"+ee.dxf.layer, ee.dxftype()))
            except Exception as ex:
                pass
        from collections import Counter
        print(f"F0{fno}", bx.bounds, Counter(hits))
