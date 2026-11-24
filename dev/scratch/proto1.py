import pickle, math, collections
D = pickle.load(open("wdata.pkl","rb"))

def segs_of(d):
    S = []
    for a,b,h,lt in d["lines"]:
        S.append((a,b))
    for pts, cl, bul, h in d["lw"]:
        xs=[p[0] for p in pts]
        if max(xs)-min(xs) > 80: continue
        n = len(pts)
        rng = range(n if cl else n-1)
        for i in rng:
            p, q = pts[i], pts[(i+1)%n]
            if abs(bul[i]) > 1e-6: continue   # arcs handled separately
            S.append((p,q))
    return [s for s in S if math.hypot(s[1][0]-s[0][0], s[1][1]-s[0][1]) > 1e-4]

def cluster_dirs(S, tol=1.0):
    items = []
    for a,b in S:
        ang = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 180
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        items.append((ang, L, a, b))
    clusters = []
    for it in sorted(items, key=lambda x:-x[1]):
        for c in clusters:
            da = abs((it[0]-c["ang"]+90)%180-90)
            if da <= tol:
                c["items"].append(it); break
        else:
            clusters.append({"ang": it[0], "items":[it]})
    return clusters

def face_lines(cl, dtol=0.004):
    th = math.radians(cl["ang"]); u=(math.cos(th), math.sin(th)); n=(-u[1], u[0])
    rows = []
    for ang,L,a,b in cl["items"]:
        da = a[0]*n[0]+a[1]*n[1]; db = b[0]*n[0]+b[1]*n[1]
        ta = a[0]*u[0]+a[1]*u[1]; tb = b[0]*u[0]+b[1]*u[1]
        rows.append(((da+db)/2, min(ta,tb), max(ta,tb)))
    rows.sort()
    groups = []
    for r in rows:
        if groups and r[0]-groups[-1][-1][0] <= dtol: groups[-1].append(r)
        else: groups.append([r])
    faces = []
    for g in groups:
        d = sum(r[0]*(r[2]-r[1]) for r in g)/max(1e-9,sum(r[2]-r[1] for r in g))
        iv = sorted((r[1], r[2]) for r in g)
        merged = []
        for s,e in iv:
            if merged and s <= merged[-1][1]+0.002: merged[-1][1] = max(merged[-1][1], e)
            else: merged.append([s,e])
        faces.append({"d": d, "iv": merged})
    return u, n, faces

def pair(faces, gmin=0.03, gmax=0.6):
    bps = sorted(set(round(x,4) for f in faces for iv in f["iv"] for x in iv))
    cells = []
    for k in range(len(bps)-1):
        s,e = bps[k], bps[k+1]
        if e-s < 1e-4: continue
        m = (s+e)/2
        act = [f["d"] for f in faces if any(iv[0]-1e-6 <= m <= iv[1]+1e-6 for iv in f["iv"])]
        act.sort()
        for i in range(len(act)-1):
            g = act[i+1]-act[i]
            if gmin <= g <= gmax:
                cells.append((act[i], act[i+1], s, e))
    return cells

for F in ["F03"]:
    S = segs_of(D[F])
    cls = cluster_dirs(S)
    hist = collections.Counter()
    for cl in cls:
        u,n,faces = face_lines(cl)
        cells = pair(faces)
        tot = sum(c[3]-c[2] for c in cells)
        print(F, "dir", round(cl["ang"],2), "segs", len(cl["items"]), "faces", len(faces), "cells", len(cells), "len", round(tot,1))
        for c in cells:
            hist[round(c[1]-c[0],2)] += c[3]-c[2]
    for k,v in sorted(hist.items()):
        if v>0.3: print("  t=%.2f  L=%.2f" % (k,v))
