# list raw entities (from indep pickle) whose geometry touches a local box
import sys, pickle
from pathlib import Path
from shapely.geometry import LineString, box, Polygon
OUT = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\v1")
n = int(sys.argv[1]); x0, y0, x1, y1 = map(float, sys.argv[2:6])
layers = sys.argv[6].split(",") if len(sys.argv) > 6 else None
d = pickle.load(open(OUT / f"indep_F0{n}.pkl", "rb"))
g = d["g"]
B = box(x0, y0, x1, y1)
for k, recs in g.items():
    if k == "texts" or (layers and k not in layers):
        continue
    for r in recs:
        pts = r["pts"]
        if len(pts) < 2:
            continue
        geom = LineString(pts)
        if geom.intersects(B):
            L = geom.length
            s = " ".join(f"({p[0]:.3f},{p[1]:.3f})" for p in pts[:6])
            print(f"{k:9s} {r.get('handle','?'):6s} {r.get('type', r.get('name','')):10s} len={L:6.3f} {s}{' ...' if len(pts)>6 else ''}")
for t in g["texts"]:
    if x0 <= t["x"] <= x1 and y0 <= t["y"] <= y1:
        print("TEXT", t["handle"], t["layer"], t["text"], round(t["x"], 3), round(t["y"], 3))
