import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter, defaultdict
from diwan_common import all_floors, floor_entities
from sosa_decode import decode
fls = all_floors()
for fl in fls:
    c = Counter()
    for e in floor_entities(fl, types="INSERT"):
        c[(e.dxf.layer, e.dxf.name)] += 1
    print(fl.label, sorted(c.items(), key=lambda kv: (kv[0][0], kv[0][1])))
