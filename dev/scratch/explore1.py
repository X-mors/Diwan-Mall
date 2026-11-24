import sys, math, collections, pickle
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import all_floors, floor_entities
out = {}
for fl in all_floors():
    c = collections.Counter()
    angs = collections.Counter()
    data = {"lines": [], "lw": [], "arcs": [], "hatch": [], "inserts": [], "cols": [], "win": [], "winarc": []}
    for e in floor_entities(fl, layers="W"):
        t = e.dxftype(); c[t] += 1
        if t == "LINE":
            a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
            data["lines"].append((a, b, e.dxf.handle, e.dxf.get("linetype","BYLAYER")))
            ang = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 180
            angs[round(ang)] += 1
        elif t == "LWPOLYLINE":
            pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
            bul = [p[4] for p in e.get_points("xyseb")]
            data["lw"].append((pts, e.closed, bul, e.dxf.handle))
        elif t == "ARC":
            cc = fl.to_local(e.dxf.center.x, e.dxf.center.y)
            data["arcs"].append((cc, e.dxf.radius, e.dxf.start_angle - fl.angle, e.dxf.end_angle - fl.angle, e.dxf.handle))
        elif t == "HATCH":
            data["hatch"].append((e.dxf.pattern_name, e.dxf.handle, [ [fl.to_local(v[0], v[1]) for v in p.vertices] if hasattr(p,'vertices') else str(type(p)) for p in e.paths]))
        elif t == "INSERT":
            p = fl.to_local(e.dxf.insert.x, e.dxf.insert.y)
            data["inserts"].append((e.dxf.name, p, e.dxf.rotation - fl.angle, e.dxf.xscale, e.dxf.yscale, e.dxf.handle))
    for e in floor_entities(fl, layers=("Etabs-col","COL"), types="LWPOLYLINE"):
        pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
        data["cols"].append((e.dxf.layer, pts, e.closed, e.dxf.handle))
    for e in floor_entities(fl, layers="WIN"):
        t = e.dxftype()
        if t == "LINE":
            a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
            data["win"].append((a, b, e.dxf.get("linetype","BYLAYER")))
        elif t == "ARC":
            cc = fl.to_local(e.dxf.center.x, e.dxf.center.y)
            data["winarc"].append((cc, e.dxf.radius, e.dxf.start_angle - fl.angle, e.dxf.end_angle - fl.angle))
        else:
            data["win"].append((t,))
    out[fl.label] = data
    print(fl.label, dict(c), "angles:", sorted(angs.items(), key=lambda x:-x[1])[:8])
pickle.dump(out, open(r"C:/Users/hp/AppData/Local/Temp/claude/3de02ce21d7c54c0/d3b44a19-989c-4f10-9b51-d237f635d5e6/scratchpad/wdata.pkl","wb"))
