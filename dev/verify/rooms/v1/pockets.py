# my faces (or parts) not covered by any tool room, with a real inscribed radius -> possible missed spaces
import sys, pickle
from pathlib import Path
import shapely
from shapely.ops import unary_union
OUT = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\v1")
floors = [int(a) for a in sys.argv[1:]] or [2, 3, 4, 5, 6, 7, 8]
for n in floors:
    d = pickle.load(open(OUT / f"indep_F0{n}.pkl", "rb"))
    R = pickle.load(open(OUT / f"tool_F0{n}.pkl", "rb"))
    toolU = unary_union([r["_poly"].buffer(0) for r in R]).buffer(0.002)
    print(f"== F0{n}")
    for f in d["faces"]:
        f = f.buffer(0)
        diff = f.difference(toolU)
        for g in getattr(diff, "geoms", [diff]):
            if g.area < 0.08:
                continue
            mic = shapely.maximum_inscribed_circle(g, tolerance=0.005)
            rad = mic.length
            if rad >= 0.14:
                c = g.representative_point()
                print(f"  area={g.area:.3f} r_in={rad:.3f} at ({c.x:.2f},{c.y:.2f}) bounds={[round(v,2) for v in g.bounds]}")
