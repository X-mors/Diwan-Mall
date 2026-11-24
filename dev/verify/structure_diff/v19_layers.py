import sys
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
from collections import Counter
LL = {"W", "WIN", "ST", "DASH", "PR", "MASS", "X", "COL", "try", "Etabs-col", "HAT", "0", "FUR"}
for fl in all_floors():
    c=Counter((e.dxf.layer, e.dxftype()) for e in floor_entities(fl) if e.dxftype() not in ('INSERT','TEXT','MTEXT','DIMENSION') and e.dxf.layer not in LL)
    print(fl.label, dict(c))
