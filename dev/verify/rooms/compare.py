import pickle, json, sys
from shapely.geometry import Point, shape
res = pickle.load(open(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\indep.pkl", "rb"))
for n, (faces, out) in res.items():
    F = "F%02d" % n
    d = json.load(open(rf"D:\حصر المباني\Diwan-Mall\output\rooms\{F}.json", encoding="utf-8"))
    # map each tool room by label handles
    byh = {}
    for r in d["rooms"]:
        for l in r["labels"]:
            byh[(round(l["x"], 3), round(l["y"], 3))] = r
    print("=====", F)
    seen = set()
    for o in out:
        r = byh.get(o["xy"])
        key = (o["bounds"] and tuple(o["bounds"]), r and r["id"])
        if key in seen: continue
        seen.add(key)
        ta = r["area"] if r else None
        diff = (o["area"] - ta) if (o["area"] is not None and ta is not None) else None
        flag = "" if diff is not None and abs(diff) < 0.25 else "  <<<"
        print(f"{o['text'][:18]:18s} {str(o['xy']):20s} indep={o['area']} tool={ta} ({r['id'] if r else None} {r['name'] if r else ''}) diff={None if diff is None else round(diff,3)}{flag}  ib={o['bounds']}")
