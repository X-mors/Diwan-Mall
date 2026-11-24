import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import ezdxf
from collections import Counter
from diwan_common import get_floor, floor_entities
doc = ezdxf.readfile(r"D:\حصر المباني\tools\raw_template_reference.dxf")
msp = doc.modelspace()
c = Counter((e.dxftype(), e.dxf.layer) for e in msp)
print(sorted(c.items(), key=lambda kv: -kv[1])[:25])
def key(s, t): 
    a=(round(s[0],2),round(s[1],2)); b=(round(t[0],2),round(t[1],2)); return tuple(sorted([a,b]))
T = {key(e.dxf.start, e.dxf.end) for e in msp.query('LINE[layer=="W"]')}
fl = get_floor(3)
F = {key(e.dxf.start, e.dxf.end) for e in floor_entities(fl, layers="W", types="LINE")}
print("template W", len(T), "F03 W", len(F), "common exact", len(T & F))
import math
for e in floor_entities(fl, layers="W", types="LINE"):
    k = key(e.dxf.start, e.dxf.end)
    if k not in T:
        a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
        print(f"  extra W ({a[0]:.3f},{a[1]:.3f})-({b[0]:.3f},{b[1]:.3f}) L={math.dist(a,b):.3f}")
