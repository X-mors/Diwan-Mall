import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, floor_entities, all_floors
for fl in all_floors()[:2]:
    rows=[]
    for e in floor_entities(fl, layers=None, types="DIMENSION"):
        d=e.dxf
        p2=fl.to_local(d.defpoint2.x,d.defpoint2.y); p3=fl.to_local(d.defpoint3.x,d.defpoint3.y)
        tm=fl.to_local(d.text_midpoint.x,d.text_midpoint.y)
        ins = lambda p: 0.9<p[0]<16.3 and -0.5<p[1]<38.3
        if ins(tm):
            rows.append((round(e.get_measurement(),3), [round(v,2) for v in p2], [round(v,2) for v in p3], [round(v,2) for v in tm], d.dimtype&7))
    print(fl.label, len(rows))
    for r in rows: print("  ", r)
