from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)

rep('''KIND_PRIORITY = ["door", "opening", "glazing", "column", "solid_try", "shaft", "slab_edge", "mass",
                 "wall", "extension"]''', '''KIND_PRIORITY = ["door", "opening", "glazing", "column", "solid_try", "shaft", "slab_edge", "mass",
                 "wall", "extension", "virtual"]''')

# helper before '# 4. labels' section
rep('''SLICE_R = 0.16 ''', '''def split_by_wall_continuation(face, keep_pts, other_pts, min_len=0.5, max_len=12.0, tol=0.01):
    """Split an open space (corridor + lift lobby drawn as one) by the straight continuation
    of a wall face across its mouth: a chord between two boundary vertices that continues a
    boundary edge at BOTH ends.  The shortest chord that puts every keep_pt on one side and
    at least one other_pt on the other side wins.  Returns (part_keep, part_other, chord) or None."""
    from shapely.ops import split as shp_split
    ring = list(face.exterior.simplify(0.002).coords)[:-1]
    n = len(ring)
    if n < 4:
        return None
    edges = []                       # per vertex: unit directions of its two incident edges (outwards)
    for i in range(n):
        a = ring[i]
        e1 = _unit((ring[i - 1][0] - a[0], ring[i - 1][1] - a[1]))
        e2 = _unit((ring[(i + 1) % n][0] - a[0], ring[(i + 1) % n][1] - a[1]))
        edges.append((e1, e2))
    fb = face.buffer(0.003)
    best = None
    for i in range(n):
        a = ring[i]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            b = ring[j]
            L = _dist(a, b)
            if L < min_len or L > max_len or (best and L >= best[0]):
                continue
            d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            # an edge at a pointing AWAY from b (wall face ending at a) and one at b pointing away from a
            ok_a = any(abs(e[0] * d[1] - e[1] * d[0]) < tol and (e[0] * d[0] + e[1] * d[1]) < -0.99 for e in edges[i])
            ok_b = any(abs(e[0] * d[1] - e[1] * d[0]) < tol and (e[0] * d[0] + e[1] * d[1]) > 0.99 for e in edges[j])
            if not (ok_a and ok_b):
                continue
            chord = LineString([a, b])
            if not fb.contains(chord) or not face.contains(chord.interpolate(0.5, normalized=True)):
                continue
            ext = LineString([(a[0] - d[0] * 0.002, a[1] - d[1] * 0.002), (b[0] + d[0] * 0.002, b[1] + d[1] * 0.002)])
            try:
                parts = [q for q in shp_split(face, ext).geoms if q.area > 0.05]
            except Exception:
                continue
            if len(parts) != 2:
                continue
            side = [[q.buffer(1e-4).contains(pt) for q in parts] for pt in keep_pts]
            if not side or not all(sd[0] for sd in side) and not all(sd[1] for sd in side):
                continue
            k = 0 if all(sd[0] for sd in side) else 1
            if not any(parts[1 - k].buffer(1e-4).contains(pt) for pt in other_pts):
                continue
            best = (L, parts[k], parts[1 - k], chord)
    return best[1:] if best else None


SLICE_R = 0.16 ''')

rep('''    # ---------------- classify
''', '''    # ---------------- corridor + lift lobby drawn as one open space -> split at the mouth
    splits = []
    for rec in list(F):
        txt = [l["text"] for l in rec["labels"] if not l["note"]]
        cats = {label_category(t) for t in txt}
        if not ({"corridor", "lobby"} <= cats):
            continue
        keep = [l for l in rec["labels"] if label_category(l["text"]) == "corridor"]
        oth = [l for l in rec["labels"] if label_category(l["text"]) == "lobby"]
        lab_t = {t["handle"]: t for t in g["texts"]}
        keep_pts = [Point(_label_center(lab_t[l["handle"]])) for l in keep]
        oth_pts = [Point(l["x"], l["y"]) for l in oth] + [Point(_label_center(lab_t[l["handle"]])) for l in oth]
        res_split = split_by_wall_continuation(rec["poly"], keep_pts, oth_pts)
        if not res_split:
            rec["flags"].append("corridor_lobby_open: الممر وبهو المصعد فراغ واحد (لا حائط بينهما) ولم يُقسَّم")
            continue
        pk, po, chord = res_split
        F.remove(rec)
        for part, labs in ((pk, keep), (po, [l for l in rec["labels"] if l not in keep])):
            nr = dict(rec)
            nr.update(poly=part, area=part.area, labels=list(labs), r_in=inscribed_radius(part),
                      flags=[f"split_virtual: separated from the {'lobby' if labs is keep else 'corridor'} by a "
                             f"virtual line {chord.length:.2f} m (continuation of the corridor wall face; "
                             f"no wall drawn)"])
            F.append(nr)
        P.append((chord, "virtual", "split:" + rec["labels"][0]["handle"]))
        splits.append({"chord": _r([list(c) for c in chord.coords]), "length": round(chord.length, 3),
                       "areas": [round(pk.area, 3), round(po.area, 3)]})
    if splits:
        tree = STRtree([p[0] for p in P])

    # ---------------- classify
''')
rep('''        name, cat, flags = name_room(rec["labels"])
''', '''        name, cat, flags = name_room(rec["labels"])
        flags = rec["flags"] + flags
''')
rep('''        "extensions": exts,
''', '''        "extensions": exts,
        "corridor_lobby_splits": splits,
''')
p.write_text(s, encoding="utf-8")
print("ok")
