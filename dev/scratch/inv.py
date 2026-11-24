import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter, defaultdict
from diwan_common import all_floors, floor_entities
fls = all_floors()
allc = {}
for fl in fls:
    c = Counter()
    for e in floor_entities(fl):
        c[(e.dxf.layer, e.dxftype())] += 1
    allc[fl.label] = c
keys = sorted(set(k for c in allc.values() for k in c))
print("layer/type".ljust(34), " ".join(f.label for f in fls))
for k in keys:
    print(f"{k[0]+'/'+k[1]:34}", " ".join(f"{allc[f.label].get(k,0):3d}" for f in fls))
