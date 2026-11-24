import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import openings as O
from shapely.geometry import LineString, Point
for fno in range(2, 9):
    res = O.analyze_floor(fno)
    G = res["_G"]
    cover = []
    for w in res["windows"] + res["window_frame_pieces"]:
        if w["shape"] == "straight":
            cover.append(LineString(w["ends"]).buffer(max(w["frame_depth"],0.05)/2+0.03))
        else:
            c = Point(w["center"]); cover.append(c.buffer(w["radius_mid"]+0.2).difference(c.buffer(max(w["radius_mid"]-0.2,0.01))))
    for d in res["doors"]:
        if d.get("hinge"):
            cover.append(Point(d["hinge"]).buffer(d["leaf_r"]+0.05))
    orph = []
    for a, b in G.win_lines:
        ln = LineString([a, b])
        if not any(cv.contains(ln) or cv.intersection(ln).length > 0.9*ln.length for cv in cover):
            orph.append((round(a[0],3), round(a[1],3), round(b[0],3), round(b[1],3), round(ln.length,3)))
    arcs_orph = []
    for a in G.raw_arcs:
        if a["layer"] != "WIN": continue
        p = Point(a["pm"])
        if not any(cv.contains(p) for cv in cover):
            arcs_orph.append((a["r"], a["center"], a["dashed"]))
    # door pairs too close
    dd = [d for d in res["doors"] if "center" in d]
    close = [(d1["id"], d2["id"]) for i, d1 in enumerate(dd) for d2 in dd[i+1:] if math.dist(d1["center"], d2["center"]) < 0.5]
    print(res["floor"], "WIN cont lines", len(G.win_lines), "dashed", len(G.win_dashed), "orphans", len(orph), "arc orphans", arcs_orph, "close doors", close)
    for o in orph: print("   ", o)
    # W/PR arcs not part of doors
    other_arcs = [(a["layer"], round(a["r"],3), O._r(a["center"])) for a in G.raw_arcs if a["layer"] != "WIN"]
    print("   W/PR raw arcs:", other_arcs)
