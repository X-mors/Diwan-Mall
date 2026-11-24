import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, box, Point
n = int(sys.argv[1]); x0, y0, x1, y1 = map(float, sys.argv[2:6])
skip = set(sys.argv[6].split(",")) if len(sys.argv) > 6 else set()
fl = get_floor(n); L = fl.to_local; B = box(x0, y0, x1, y1)
for e in floor_entities(fl):
    if e.dxf.layer in skip: continue
    t = e.dxftype()
    if t == "INSERT":
        p = L(e.dxf.insert.x, e.dxf.insert.y)
        if B.contains(Point(p)): print("INSERT", e.dxf.layer, e.dxf.name, e.dxf.handle, [round(v,3) for v in p])
        continue
    if t in ("TEXT", "MTEXT"):
        p = L(e.dxf.insert.x, e.dxf.insert.y)
        if B.contains(Point(p)): print(t, e.dxf.layer, e.dxf.handle, [round(v,3) for v in p], repr(e.dxf.get("text", "")[:30]))
        continue
    if t in ("DIMENSION", "HATCH"): continue
    try: pts = [L(v.x, v.y) for v in ezpath.make_path(e).flattening(0.01)]
    except Exception: continue
    if len(pts) < 2: continue
    g = LineString(pts)
    if g.intersects(B) and g.length < 30:
        print(t, e.dxf.layer, e.dxf.handle, f"L={g.length:.3f}", [(round(a,3), round(b,3)) for a, b in (pts if len(pts) < 6 else pts[:2] + pts[-2:])])
