import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import openings as O
from shapely.geometry import LineString, Point, MultiPoint
from shapely.strtree import STRtree
for fno in range(2, 9):
    res = O.analyze_floor(fno)
    G = res["_G"]
    verts = []
    for a, b, _ in G.wall_segs:
        if O._len(O._sub(b,a)) < 30: verts += [a, b]
    for a, b in G.win_lines + G.win_dashed: verts += [a, b]
    for pg, _ in G.polys:
        if pg.geom_type == "Polygon": verts += list(pg.exterior.coords)
    for ar in G.raw_arcs: verts += [ar["p0"], ar["p1"], ar["center"]]
    for d in res["doors"]:
        if "jamb_a" in d: verts += list(d["jamb_a"]) + list(d["jamb_b"])
    vt = STRtree([Point(v) for v in verts])
    wl = [LineString([a,b]) for a,b,_ in G.wall_segs if O._len(O._sub(b,a)) < 30]
    wt = STRtree(wl)
    out = []
    for dm in G.dims:
        v = dm["value"]
        if v is None or not (0.3 <= v <= 4.0): continue
        st = []
        for p in (dm["p2"], dm["p3"]):
            P = Point(p)
            anchored = len(vt.query(P.buffer(0.02), predicate="intersects")) > 0
            onwall = len(wt.query(P.buffer(0.02), predicate="intersects")) > 0
            st.append((anchored, onwall))
        if not st[0][0] and not st[1][0] and st[0][1] and st[1][1]:
            out.append((round(v,3), O._r(dm["p2"]), O._r(dm["p3"])))
    print(res["floor"], len(out), out)
