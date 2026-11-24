import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter, defaultdict
from diwan_common import all_floors, floor_entities, DXF_FILES, floors_in_file, entity_bbox, _entity_anchor
for p in DXF_FILES:
    fls = floors_in_file(str(p))
    msp = fls[0].msp
    un = Counter(); ex=defaultdict(list)
    for e in msp:
        a = _entity_anchor(e)
        if a is None or not any(f.contains(*a, pad=0.5) for f in fls):
            un[(e.dxf.layer, e.dxftype())] += 1
            if len(ex[(e.dxf.layer, e.dxftype())])<3:
                b = entity_bbox(e)
                ex[(e.dxf.layer, e.dxftype())].append((e.dxf.get('name','') if e.dxftype()=='INSERT' else '', tuple(round(v,1) for v in a) if a else None, tuple(round(v,1) for v in b) if b else None))
    print("==", p.name, [f.label for f in fls])
    for k,v in sorted(un.items()):
        print("  ", k, v, ex[k])
