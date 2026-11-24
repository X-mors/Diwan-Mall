import sys, pickle, glob
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from rooms import *
fl = get_floor(int(sys.argv[1]))
g = load_geometry(fl)
for t in g["texts"]:
    print("TXT", t["layer"], repr(t["text"]), round(t["x"],2), round(t["y"],2), t["height"])
for t in g["notes"]:
    print("NOTE", t["layer"], repr(t["text"]), round(t["x"],2), round(t["y"],2))
def bb(pts):
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    return tuple(round(v,2) for v in (min(xs),min(ys),max(xs),max(ys)))
for k in ("cols","try_polys","mass","w_hatch","zero"):
    for r in g[k]:
        print(k, r.get("layer",""), r["type"] if "type" in r else r.get("pattern"), len(r["pts"]), bb(r["pts"]))
