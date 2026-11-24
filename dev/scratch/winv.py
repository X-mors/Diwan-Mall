import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import all_floors, floor_entities
for fl in all_floors():
    c=Counter()
    for e in floor_entities(fl, layers=("W","WIN","PR","DASH","0","PR1","HAT","MASS","try","COL","Etabs-col")):
        c[(e.dxf.layer,e.dxftype())]+=1
    print(fl.label, sorted(c.items()))
