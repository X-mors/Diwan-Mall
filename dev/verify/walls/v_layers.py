import sys, math
from collections import Counter
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    c = Counter(); L = Counter()
    for e in floor_entities(fl, types="LINE LWPOLYLINE ARC"):
        lay = e.dxf.layer
        try:
            if e.dxftype() == "LINE":
                a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
                pts = [a, b]
            elif e.dxftype() == "LWPOLYLINE":
                pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
            else:
                pts = [fl.to_local(e.dxf.center.x, e.dxf.center.y)]
        except Exception:
            continue
        if all(-1.5 <= p[0] <= 21 and -2.5 <= p[1] <= 41 for p in pts):
            c[(lay, e.dxftype())] += 1
            if e.dxftype() == "LINE":
                L[lay] += math.hypot(b[0]-a[0], b[1]-a[1])
    print(fl.label)
    for k, v in sorted(c.items()):
        print("   ", k, v, round(L.get(k[0], 0), 1) if k[1] == "LINE" else "")
