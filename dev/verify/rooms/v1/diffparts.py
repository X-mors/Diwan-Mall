# parts of my face (containing point x,y) that no tool room covers
import sys, pickle
from pathlib import Path
from shapely.geometry import Point
from shapely.ops import unary_union
OUT = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\v1")
n = int(sys.argv[1]); x, y = float(sys.argv[2]), float(sys.argv[3])
d = pickle.load(open(OUT / f"indep_F0{n}.pkl", "rb"))
R = pickle.load(open(OUT / f"tool_F0{n}.pkl", "rb"))
F = [f.buffer(0) for f in d["faces"]]
toolU = unary_union([r["_poly"].buffer(0) for r in R])
p = Point(x, y)
f = min(F, key=lambda f: f.distance(p))
print("my face area", round(f.area, 3), "bounds", [round(v, 2) for v in f.bounds])
for r in R:
    a = r["_poly"].buffer(0).intersection(f).area
    if a > 0.01:
        print("  tool", r["id"], r["name"], round(r["_poly"].area, 3), "overlap", round(a, 3))
diff = f.difference(toolU.buffer(0.001))
for g in sorted(getattr(diff, "geoms", [diff]), key=lambda g: -g.area):
    if g.area < 0.005:
        continue
    mrr = g.minimum_rotated_rectangle
    xs, ys = mrr.exterior.coords.xy
    e = sorted([((xs[i+1]-xs[i])**2 + (ys[i+1]-ys[i])**2) ** 0.5 for i in range(2)])
    print(f"  uncovered part area={g.area:.3f} bounds={[round(v,2) for v in g.bounds]} mrr={e[0]:.2f}x{e[1]:.2f} "
          f"inscribed~{2*g.area/max(g.length,1e-6):.3f}")
