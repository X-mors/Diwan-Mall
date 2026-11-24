"""cache local-frame segments per floor/layer (my own, independent of structure.py)"""
import sys, pickle, math
from pathlib import Path
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
CACHE = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_structure_diff\r2\cache")
CACHE.mkdir(exist_ok=True)
def segs(n, layer):
    f = CACHE / f"F{n:02d}_{layer}.pkl"
    if f.exists():
        return pickle.load(open(f, "rb"))
    fl = get_floor(n)
    out = []
    for e in floor_entities(fl, layers=layer):
        t = e.dxftype()
        h = e.dxf.handle
        try:
            if t == "LINE":
                a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
                out.append((a, b, h, t))
            elif t in ("LWPOLYLINE", "ARC", "CIRCLE", "POLYLINE", "SPLINE", "ELLIPSE"):
                p = ezpath.make_path(e)
                vs = [fl.to_local(v.x, v.y) for v in p.flattening(0.01)]
                for a, b in zip(vs, vs[1:]):
                    out.append((a, b, h, t))
        except Exception as ex:
            pass
    pickle.dump(out, open(f, "wb"))
    return out
if __name__ == "__main__":
    for n in range(2, 9):
        for L in sys.argv[1:]:
            print(n, L, len(segs(n, L)))
