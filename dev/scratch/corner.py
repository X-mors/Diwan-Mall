import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
for fno in (3, 5):
    fl = get_floor(fno)
    for box in ((0.2, 35.2, 2.8, 36.3), (0.2, 1.6, 2.0, 2.6)):
        print(f"F0{fno} box {box}")
        for e in floor_entities(fl, layers=("W","0","WIN","PR","Etabs-col","COL")):
            if e.dxftype() in ("TEXT","MTEXT","INSERT","HATCH","DIMENSION"): continue
            try:
                p = ezpath.make_path(e)
                pts = [fl.to_local(v.x, v.y) for v in p.flattening(0.01)]
            except Exception: continue
            segs = list(zip(pts, pts[1:]))
            for a,b in segs:
                inb = lambda q: box[0]<=q[0]<=box[2] and box[1]<=q[1]<=box[3]
                if inb(a) or inb(b):
                    print("  ", e.dxf.layer, e.dxftype(), f"({a[0]:.3f},{a[1]:.3f})-({b[0]:.3f},{b[1]:.3f})")
