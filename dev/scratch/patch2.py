from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)

# 1. door leaves drawn on W
rep('''    skipped = []
    for r in g["w"]:
        P.append((LineString(r["pts"]), "wall", "W:" + r["handle"]))''',
'''    skipped = []
    # open door leaves (hinge -> leaf tip) : W lines lying on one are a leaf drawn on W, not a wall
    leaf_zones = []
    for d in op.get("doors", []):
        lg = d.get("leaf_geom") or {}
        if lg.get("c") and lg.get("p1"):
            leaf_zones.append((LineString([tuple(lg["c"]), tuple(lg["p1"])]).buffer(0.07), d["id"]))
    for r in g["w"]:
        ln = LineString(r["pts"])
        z = next((did for zone, did in leaf_zones if zone.contains(ln)), None)
        if z and ln.length <= 1.3:
            skipped.append(f"W:{r['handle']} (door leaf of {z} drawn on W)")
            continue
        P.append((ln, "wall", "W:" + r["handle"]))''')

# 2. tolerant ray
rep('''            u = _unit((end[0] - prev[0], end[1] - prev[1]))
            ray = LineString([(end[0] + u[0] * 1e-3, end[1] + u[1] * 1e-3),
                              (end[0] + u[0] * max_ext, end[1] + u[1] * max_ext)])
            best = None
            for j in tree.query(ray):
                if j == idx:
                    continue
                x = ray.intersection(geoms[j])
                if x.is_empty:
                    continue
                dd = pt.distance(x)
                if best is None or dd < best[0]:
                    best = (dd, P[j][1], P[j][2])''',
'''            u = _unit((end[0] - prev[0], end[1] - prev[1]))
            ray = LineString([(end[0] + u[0] * 1e-3, end[1] + u[1] * 1e-3),
                              (end[0] + u[0] * max_ext, end[1] + u[1] * max_ext)])
            band = ray.buffer(ray_tol, cap_style=2)      # catches near misses (ends 1-2 cm off line)
            best = None
            for j in tree.query(band):
                if j == idx:
                    continue
                x = band.intersection(geoms[j])
                if x.is_empty:
                    continue
                cs2 = []
                for part in (x.geoms if hasattr(x, "geoms") else [x]):
                    if part.geom_type == "Polygon":
                        cs2.extend(part.exterior.coords)
                    else:
                        cs2.extend(part.coords)
                dd = min(((c[0] - end[0]) * u[0] + (c[1] - end[1]) * u[1]) for c in cs2)
                if dd <= 1e-3:
                    continue
                if best is None or dd < best[0]:
                    best = (dd, P[j][1], P[j][2])''')
rep('''def dangling_extensions(P, max_ext=MAX_EXT, touch=0.012):''',
    '''def dangling_extensions(P, max_ext=MAX_EXT, touch=0.012, ray_tol=0.016):''')

# 4. slicing flags: keep track of which face a sliver came from
rep('''    faces, slivers = [], []
    for f in faces0:
        if f.area < MIN_FACE:
            continue
        cores, sl = slice_face(f)
        faces.extend(c for c in cores if c.area >= MIN_FACE)
        slivers.extend(sl + [c for c in cores if c.area < MIN_FACE])''',
'''    faces, slivers, trimmed = [], [], []
    for f in faces0:
        if f.area < MIN_FACE:
            continue
        cores, sl = slice_face(f)
        faces.extend(c for c in cores if c.area >= MIN_FACE)
        trimmed.extend([None] * len([c for c in cores if c.area >= MIN_FACE]))
        lost = sl + [c for c in cores if c.area < MIN_FACE]
        slivers.extend(lost)
        if lost:
            for k in range(1, len([c for c in cores if c.area >= MIN_FACE]) + 1):
                trimmed[-k] = round(sum(x.area for x in lost), 3)''')
rep('''        rec = {"i": i, "poly": f, "area": f.area, "labels": [], "flags": [], "kind": None}''',
    '''        rec = {"i": i, "poly": f, "area": f.area, "labels": [], "flags": [], "kind": None,
               "trimmed": trimmed[i]}''')
rep('''        if any(l.get("snapped") for l in rec["labels"] if not l["note"]):''',
'''        if rec["trimmed"] and cat not in ("shaft",) and rec["trimmed"] >= 0.05:
            flags.append(f"trimmed: {rec['trimmed']:.2f} m2 of thin strip(s) (< 0.32 m wide) cut off this "
                         f"space as wall body - check the drawing there")
        if any(l.get("snapped") for l in rec["labels"] if not l["note"]):''')

# 5. clip texts
rep('''        ax.text(p.x, p.y, txt, ha="center", va="center", fontsize=size, zorder=9, rotation=rot,
                color="#000", bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.3))''',
'''        ax.text(p.x, p.y, txt, ha="center", va="center", fontsize=size, zorder=9, rotation=rot,
                color="#000", bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.3), clip_on=True)''')
p.write_text(s, encoding="utf-8")
print("ok")
