import sys, math, json
from collections import Counter
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
fl = get_floor(n)
rows = []
for e in floor_entities(fl, layers="DIM"):
    if e.dxftype() != "DIMENSION": continue
    p1 = e.dxf.get("defpoint2"); p2 = e.dxf.get("defpoint3")
    if p1 is None or p2 is None: continue
    a = fl.to_local(p1.x, p1.y); b = fl.to_local(p2.x, p2.y)
    dt = e.dimtype & 7
    # measurement along dim line direction
    if dt == 0:  # linear/rotated: angle
        ang = math.radians(e.dxf.get("angle", 0.0))
        d = abs((p2.x - p1.x) * math.cos(ang) + (p2.y - p1.y) * math.sin(ang))
    else:
        d = math.hypot(p2.x - p1.x, p2.y - p1.y)
    txt = e.dxf.get("text", "")
    rows.append((round(d, 3), txt, e.dxf.handle, dt, e.dxf.get("dimstyle"), [round(c, 3) for c in a], [round(c, 3) for c in b]))
print("n", len(rows), Counter(r[4] for r in rows), Counter(r[3] for r in rows))
for r in sorted(rows):
    if r[0] <= 0.31: print(r)
print(Counter(r[1] for r in rows).most_common(5))
json.dump(rows, open(f"dims_F{n:02d}.json", "w"), default=float)
