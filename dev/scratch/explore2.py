import pickle, math, collections
D = pickle.load(open("wdata.pkl","rb"))
for F in ["F02","F03"]:
    d = D[F]
    print("=====", F)
    print("INSERTS:")
    for i in d["inserts"]: print("  ", i[0], tuple(round(v,2) for v in i[1]), round(i[2]%360,1), i[3], i[4])
    print("LWPOLY:")
    for pts, cl, bul, h in d["lw"]:
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        print("  ", len(pts), cl, "bbox", round(min(xs),2), round(min(ys),2), round(max(xs),2), round(max(ys),2), "bulges", [round(b,2) for b in bul if b])
    print("ARCS:", [(tuple(round(v,2) for v in a[0]), round(a[1],2), round(a[2]%360,1), round(a[3]%360,1)) for a in d["arcs"]])
    print("HATCH:")
    for h in d["hatch"]:
        print("  ", h[0], [ (len(p), [tuple(round(v,2) for v in q) for q in p[:6]]) if isinstance(p,list) else p for p in h[2]])
    print("COLS:", len(d["cols"]))
    for c in d["cols"]:
        xs=[p[0] for p in c[1]]; ys=[p[1] for p in c[1]]
        print("  ", c[0], len(c[1]), c[2], round(min(xs),2), round(min(ys),2), round(max(xs),2), round(max(ys),2))
