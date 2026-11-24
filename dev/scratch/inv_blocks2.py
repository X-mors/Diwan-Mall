import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter, defaultdict
from diwan_common import all_floors, floor_entities, DXF_FILES, open_doc, floors_in_file, entity_bbox
for p in DXF_FILES:
    doc = open_doc(str(p)); msp = doc.modelspace()
    fls = floors_in_file(str(p))
    c = Counter(); outside = Counter()
    for e in msp.query("INSERT"):
        ins = e.dxf.insert
        inf = [f.label for f in fls if f.contains(ins.x, ins.y, pad=0.5)]
        key = (e.dxf.layer, e.dxf.name)
        c[key] += 1
        if not inf:
            bb = entity_bbox(e)
            outside[key] += 1
            if outside[key] <= 2:
                print("  OUT", p.name, key, (round(ins.x,1), round(ins.y,1)), bb and tuple(round(v,1) for v in bb), e.dxf.xscale, e.dxf.rotation)
    print(p.name, "total", sum(c.values()), "outside", sum(outside.values()))
    print("   outside:", dict(outside))
