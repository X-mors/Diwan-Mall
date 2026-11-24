from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")


def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)


# --- split: optional shape check for the other part
rep('''def split_by_wall_continuation(face, keep_pts, other_pts, min_len=0.5, max_len=12.0, tol=0.01):''',
    '''def split_by_wall_continuation(face, keep_pts, other_pts, min_len=0.5, max_len=12.0, tol=0.01,
                               other_check=None):''')
rep('''            k = 0 if all(sd[0] for sd in side) else 1
            if not any(parts[1 - k].buffer(1e-4).contains(pt) for pt in other_pts):
                continue''', '''            k = 0 if all(sd[0] for sd in side) else 1
            if other_pts and not any(parts[1 - k].buffer(1e-4).contains(pt) for pt in other_pts):
                continue
            if other_check is not None and not other_check(parts[1 - k], chord):
                continue''')
rep('''def split_by_wall_continuation(face''', '''def corridor_like(part, chord, ratio=4.0, min_area=8.0):
    """A long narrow strip whose long side runs parallel to the chord (the corridor)."""
    if part.area < min_area:
        return False
    mrr = part.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    L1, L2 = math.hypot(*e1), math.hypot(*e2)
    long_e, Ll, Ls = (e1, L1, L2) if L1 >= L2 else (e2, L2, L1)
    if Ls < 1e-6 or Ll / Ls < ratio:
        return False
    c = list(chord.coords)
    d = _unit((c[1][0] - c[0][0], c[1][1] - c[0][1]))
    u = _unit(long_e)
    return abs(d[0] * u[1] - d[1] * u[0]) < 0.02


def split_by_wall_continuation(face''')

# --- split loop: also a lobby-labelled face with no corridor label (F02)
rep('''        cats = {label_category(t) for t in txt}
        if not ({"corridor", "lobby"} <= cats):
            continue
        keep = [l for l in rec["labels"] if label_category(l["text"]) == "corridor"]
        oth = [l for l in rec["labels"] if label_category(l["text"]) == "lobby"]
        lab_t = {t["handle"]: t for t in g["texts"]}
        keep_pts = [Point(_label_center(lab_t[l["handle"]])) for l in keep]
        oth_pts = [Point(l["x"], l["y"]) for l in oth] + [Point(_label_center(lab_t[l["handle"]])) for l in oth]
        res_split = split_by_wall_continuation(rec["poly"], keep_pts, oth_pts)''',
'''        cats = {label_category(t) for t in txt}
        lab_t = {t["handle"]: t for t in g["texts"]}
        if {"corridor", "lobby"} <= cats:
            unlabelled_corridor = False
            keep = [l for l in rec["labels"] if label_category(l["text"]) == "corridor"]
            oth = [l for l in rec["labels"] if label_category(l["text"]) == "lobby"]
            keep_pts = [Point(_label_center(lab_t[l["handle"]])) for l in keep]
            oth_pts = [Point(l["x"], l["y"]) for l in oth] + [Point(_label_center(lab_t[l["handle"]])) for l in oth]
            res_split = split_by_wall_continuation(rec["poly"], keep_pts, oth_pts)
        elif cats == {"lobby"} and rec["area"] > 50.0:
            # F02: the corridor carries no label; the lobby label sits at the corridor mouth
            unlabelled_corridor = True
            lob = [l for l in rec["labels"] if label_category(l["text"]) == "lobby"]
            res_split = split_by_wall_continuation(rec["poly"], [Point(l["x"], l["y"]) for l in lob], [],
                                                   other_check=corridor_like)
            if res_split:
                po, pk, chord = res_split            # keep = lobby side -> swap so pk = corridor
                res_split = (pk, po, chord)
            keep = []
        else:
            continue''')
rep('''        pk, po, chord = res_split
        F.remove(rec)
        for part, labs in ((pk, keep), (po, [l for l in rec["labels"] if l not in keep])):
            nr = dict(rec)
            nr.update(poly=part, area=part.area, labels=list(labs), r_in=inscribed_radius(part),
                      flags=[f"split_virtual: separated from the {'lobby' if labs is keep else 'corridor'} by a "
                             f"virtual line {chord.length:.2f} m (continuation of the corridor wall face; "
                             f"no wall drawn)"])
            F.append(nr)''', '''        pk, po, chord = res_split
        F.remove(rec)
        for part, labs in ((pk, keep), (po, [l for l in rec["labels"] if l not in keep])):
            nr = dict(rec)
            fl_ = [f"split_virtual: separated from the {'lobby' if labs is keep else 'corridor'} by a "
                   f"virtual line {chord.length:.2f} m (continuation of the corridor wall face; no wall drawn)"]
            if labs is keep and unlabelled_corridor:
                fl_.append("corridor_unlabelled: no 'ممر' label on this floor; named corridor from its shape")
                nr["force_name"] = ("ممر", "corridor")
            nr.update(poly=part, area=part.area, labels=list(labs), r_in=inscribed_radius(part), flags=fl_)
            F.append(nr)''')
rep('''        name, cat, flags = name_room(rec["labels"])
        flags = rec["flags"] + flags
''', '''        name, cat, flags = name_room(rec["labels"])
        if rec.get("force_name") and not name:
            name, cat = rec["force_name"]
        flags = rec["flags"] + flags
''')

# --- office + wc labels -> office
rep('''    if set(ucats) == {"terrace"} or set(ucats) == {"planter"}:
        return uniq[0], ucats[0], flags''', '''    if set(ucats) == {"terrace"} or set(ucats) == {"planter"}:
        return uniq[0], ucats[0], flags
    offices = [t for t in uniq if label_category(t) == "office"]
    if len(offices) == 1 and set(ucats) == {"office", "wc"}:
        flags.append("extra_label: '" + "', '".join(t for t in uniq if t not in offices) + "' inside "
                     + offices[0] + " - the WC walls are not drawn here (label left over?)")
        return offices[0], "office", flags''')

# --- planter from AR-CONC hatch
rep('''            if rec["wc_pans"] and rec["area"] < 12.0:
                name, cat = "حمام (بلا اسم)", "wc"
                flags.append("unlabelled_wc: no room label; named from the WC pan block P (FUR) inside")''',
'''            if rec["wc_pans"] and rec["area"] < 12.0:
                name, cat = "حمام (بلا اسم)", "wc"
                flags.append("unlabelled_wc: no room label; named from the WC pan block P (FUR) inside")
            elif rec.get("soil", 0.0) >= 0.5:
                name, cat = "زرع (بلا اسم)", "planter"
                flags.append(f"unlabelled_planter: no label; {rec['soil'] * 100:.0f}% of it is covered by an "
                             f"AR-CONC hatch on W (planter soil)")''')
rep('''        rec["basins"] = sum(1 for p in basins if fz.contains(p))''', '''        rec["basins"] = sum(1 for p in basins if fz.contains(p))
        rec["soil"] = (sum(f.intersection(h).area for h in soil if h.intersects(f)) / f.area) if soil else 0.0''')
rep('''    basins = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "WB"]''',
    '''    basins = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "WB"]
    soil = [_poly(h["pts"]) for h in g["w_hatch"] if str(h.get("pattern", "")).upper() == "AR-CONC"]
    soil = [h for h in soil if h.area > 0.3]          # (small boxes = text masks)''')

# --- dim: skip DIMs running along one face (window widths on a facade line etc.)
rep('''        s = 1.0 if proj > 0 else -1.0
        widths = []''', '''        mid = Point((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
        if bd.distance(mid) < 0.03 or not poly.contains(mid):
            continue                         # measures along one face (window / pier widths)
        s = 1.0 if proj > 0 else -1.0
        widths = []''')
p.write_text(s, encoding="utf-8")
print("ok")
