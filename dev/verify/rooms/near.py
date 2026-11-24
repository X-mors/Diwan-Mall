import sys, pickle
from shapely.geometry import LineString, Point, box, Polygon
raw = pickle.load(open(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\raw.pkl", "rb"))
F = sys.argv[1]; x0, y0, x1, y1 = map(float, sys.argv[2:6])
layers = sys.argv[6].split(",") if len(sys.argv) > 6 else None
B = box(x0, y0, x1, y1)
d = raw[F]
for k in ("W", "WIN", "cols", "try", "mass", "st", "pr", "dash", "zero"):
    if layers and k not in layers: continue
    for r in d[k]:
        if len(r["pts"]) < 2: continue
        g = LineString(r["pts"])
        if g.intersects(B):
            pts = r["pts"]
            s = " ".join(f"({p[0]:.3f},{p[1]:.3f})" for p in (pts if len(pts) <= 6 else pts[:3] + pts[-2:]))
            print(k, r["layer"], r["t"], r["h"], r["lt"], f"n={len(pts)} L={g.length:.3f}", s)
for r in d["inserts"]:
    if B.contains(Point(r["ins"])) and (not layers or "ins" in layers):
        print("INSERT", r["name"], r["layer"], r["h"], f"({r['ins'][0]:.3f},{r['ins'][1]:.3f})", r["xs"], r["ys"], round(r["rot"],1))
for r in d["texts"]:
    if B.contains(Point(r["local"])) and (not layers or "txt" in layers):
        print("TEXT", r["layer"], repr(r["text"]), r["h"], f"({r['local'][0]:.3f},{r['local'][1]:.3f})")
