import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import openings as O
from collections import Counter
for fno in (3, 5):
    res = O.analyze_floor(fno)
    G = res["_G"]
    print(res["floor"], "dims", len(G.dims), Counter(d["layer"] for d in G.dims))
    vals = Counter(round(d["value"],3) for d in G.dims if d["value"] is not None)
    print("  dim values in 0.7..1.3:", sorted((v,c) for v,c in vals.items() if 0.7<=v<=1.3))
    for d in res["doors"]:
        if "jamb_a" not in d: continue
        pts = [p for j in (d["jamb_a"], d["jamb_b"]) for p in j] + [O._mid(*d["jamb_a"]), O._mid(*d["jamb_b"])]
        near = []
        for dm in G.dims:
            for q in (dm["p2"], dm["p3"]):
                if min(math.dist(q, p) for p in pts) < 0.06:
                    near.append((round(dm["value"],3) if dm["value"] else None, dm["layer"]))
        # any dim with value == width within 1.5 m of door center
        same = [round(dm["value"],3) for dm in G.dims if dm["value"] and abs(dm["value"]-d["width"])<0.011 and math.dist(O._mid(dm["p2"],dm["p3"]), d["center"])<1.5]
        if near or same:
            print("  ", d["id"], d["block"], d["width"], "dims touching jambs:", near, "same-value dims nearby:", same)
