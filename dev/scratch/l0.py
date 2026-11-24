import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import all_floors, floor_entities, floor_texts
for fl in all_floors():
    for e in floor_entities(fl, layers=("0",), types="LWPOLYLINE"):
        pts=[tuple(round(v,2) for v in fl.to_local(p[0],p[1])) for p in e.get_points('xy')]
        print(fl.label, "L0 LWP", len(pts), pts[:5], e.closed)
    for t in floor_texts(fl, layers=("0","-A-TEXT")):
        print(fl.label, t['layer'], repr(t['raw']), t['text'], [round(v,1) for v in t['local']])
