import sys, pickle
from pathlib import Path
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import rooms
from shapely.ops import unary_union

OUT = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\v1")
floors = [int(a) for a in sys.argv[1:]] or [2, 3, 4, 5, 6, 7, 8]
for n in floors:
    d = pickle.load(open(OUT / f"indep_F0{n}.pkl", "rb"))
    F = [f.buffer(0) for f in d["faces"]]
    res = rooms.analyze_floor(n)
    R = res["rooms"]
    with open(OUT / f"tool_F0{n}.pkl", "wb") as f:
        pickle.dump([{k: v for k, v in r.items()} for r in R], f)
    print(f"===== F0{n}: tool rooms {len(R)}  indep faces {len(F)}")
    toolU = unary_union([r["_poly"].buffer(0) for r in R])
    # 1) tool rooms vs my faces
    for r in R:
        P = r["_poly"].buffer(0)
        ov = [(f, f.intersection(P, grid_size=1e-5).area) for f in F]
        ov = [(f, a) for f, a in ov if a > 0.01]
        myU = unary_union([f for f, a in ov]) if ov else None
        mine = sum(f.area for f, a in ov)
        diff = abs(P.area - mine)
        if diff > 0.05 or len(ov) != 1:
            print(f"  {r['id']:8s} {r['name']:22s} {r['category']:9s} tool={P.area:8.3f}  mine={mine:8.3f} "
                  f"n_my={len(ov)} parts={[round(a,2) for f,a in ov]} myfaces_full={[round(f.area,2) for f,a in ov]} "
                  f"c=({P.centroid.x:.2f},{P.centroid.y:.2f})")
    # 2) my faces not covered by tool rooms
    for f in F:
        cov = f.intersection(toolU).area
        if f.area - cov > 0.1:
            c = f.representative_point()
            print(f"  UNCOVERED my face area={f.area:.3f} uncovered={f.area-cov:.3f} at ({c.x:.2f},{c.y:.2f}) "
                  f"bounds={tuple(round(v,2) for v in f.bounds)}")
