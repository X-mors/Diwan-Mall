import sys, math, collections
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities, floor_texts
fl = get_floor(3)
for lay in ["try","COL","Etabs-col","PR","DASH","MASS","ST","HAT","Etabs-Slab","-MASS","sidewalk","0","PR1"]:
    c = collections.Counter(e.dxftype() for e in floor_entities(fl, layers=lay))
    print(lay, dict(c))
print("--- try polylines")
for e in floor_entities(fl, layers="try"):
    if e.dxftype()=="LWPOLYLINE":
        pts=[fl.to_local(p[0],p[1]) for p in e.get_points("xy")]
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        print("  ", len(pts), e.closed, round(min(xs),2), round(min(ys),2), round(max(xs),2), round(max(ys),2))
    else:
        print("  ", e.dxftype(), e.dxf.get("pattern_name",""))
print("--- texts TEXT/-A-TEXT")
for t in floor_texts(fl, layers=("TEXT","-A-TEXT")):
    print("  ", t["layer"], repr(t["text"]), tuple(round(v,2) for v in t["local"]))
print("--- MASS")
for e in floor_entities(fl, layers=("MASS","-MASS","sidewalk","HAT")):
    b=None
    try:
        from diwan_common import entity_bbox
        b = entity_bbox(e)
        lb = fl.to_local(b[0],b[1]); ub = fl.to_local(b[2],b[3])
    except Exception: pass
    print("  ", e.dxf.layer, e.dxftype(), [round(v,2) for v in (lb+ub)] if b else None)
