import sys, pickle, json
from pathlib import Path
from shapely.geometry import Point, Polygon
OUT = Path(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\v1")
floors = [int(a) for a in sys.argv[1:]] or [2, 3, 4, 5, 6, 7, 8]
for n in floors:
    d = pickle.load(open(OUT / f"indep_F0{n}.pkl", "rb"))
    g = d["g"]
    R = pickle.load(open(OUT / f"tool_F0{n}.pkl", "rb"))
    print(f"===== F0{n}")
    # labels
    byh = {}
    for r in R:
        for lb in r.get("labels", []) or []:
            byh[lb["handle"]] = r
    for t in g["texts"]:
        p = Point(t["x"], t["y"])
        r = byh.get(t["handle"])
        inside = [q for q in R if q["_poly"].buffer(0).contains(p)]
        ins = inside[0]["id"] + ":" + inside[0]["name"] if inside else "-"
        if r is None:
            print(f"  LABEL NOT USED {t['handle']} {t['text']!r} at ({t['x']:.2f},{t['y']:.2f}) inside={ins}")
        else:
            dist = r["_poly"].distance(p)
            if dist > 0.01 or not inside or inside[0]["id"] != r["id"]:
                print(f"  label {t['handle']} {t['text']!r} at ({t['x']:.2f},{t['y']:.2f}) -> {r['id']} {r['name']} dist={dist:.2f} pt-inside={ins}")
    # doors: rooms touching each of my door rectangles
    for dd in g["doors"]:
        P = Polygon(dd["pts"])
        touch = [r for r in R if r["_poly"].buffer(0).distance(P) < 0.03 and r["category"] not in ()]
        names = [f"{r['id'][4:]}:{r['name']}" for r in touch]
        c = P.centroid
        if len(touch) != 2:
            print(f"  DOOR {dd['name']} {dd['handle']} at ({c.x:.2f},{c.y:.2f}) touches {len(touch)}: {names}")
    # WC pans
    fur = []
    print("  WC rooms:", sum(1 for r in R if r['category'] == 'wc'))
