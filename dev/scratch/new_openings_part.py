# ----------------------------------------------------------------------------- door-less openings
def _face_run(G, p, dirv, tol=0.004, max_len=1.0):
    """Length of W wall face running from point p in direction dirv (collinear pieces merged)."""
    iv = []
    for a, b, _ in G.wall_segs:
        v = _sub(b, a)
        if _len(v) < 1e-4 or abs(_cross(_unit(v), dirv)) > 0.01:
            continue
        if abs(_cross(dirv, _sub(a, p))) > tol:
            continue
        s0, s1 = sorted((_dot(_sub(a, p), dirv), _dot(_sub(b, p), dirv)))
        if s1 > 1e-4:
            iv.append((s0, s1))
    reach = 0.0
    for s0, s1 in sorted(iv):
        if s0 <= reach + 0.003:
            reach = max(reach, s1)
            if reach >= max_len:
                break
    return reach


def _wall_end_caps(G, tmin=0.05, tmax=0.45, tol=0.006):
    """Short W/0 segments closing BOTH faces of a wall end.
    Returns dicts: c (cap centre), w (outward unit), t (cap length), cap (a,b), depth
    (shorter of the two faces running back from the cap: piers beside doors are ~0.12)."""
    segs = [(a, b) for a, b, _ in G.wall_segs]
    ends = defaultdict(list)

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))
    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            k = key(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    ends[(k[0] + dx, k[1] + dy)].append(i)
    caps = []
    for i, (a, b) in enumerate(segs):
        t = _len(_sub(b, a))
        if not (tmin <= t <= tmax):
            continue
        d = _unit(_sub(b, a))
        n = _perp(d)
        sides = []
        for p in (a, b):
            sgn = set()
            for j in set(ends[key(p)]):
                if j == i:
                    continue
                q0, q1 = segs[j]
                if _len(_sub(q0, p)) < tol:
                    far = q1
                elif _len(_sub(q1, p)) < tol:
                    far = q0
                else:
                    continue
                v = _sub(far, p)
                if _len(v) < 0.02:
                    continue
                cosv = _dot(_unit(v), d)
                if abs(cosv) > 0.1:
                    if abs(abs(cosv) - 1) < 0.01 and _dot(v, _sub(p, _mid(a, b))) > 0:
                        sgn.add(9)          # collinear continuation -> part of a longer face
                    continue
                sgn.add(1 if _dot(v, n) > 0 else -1)
            sides.append(sgn)
        if 9 in sides[0] or 9 in sides[1]:
            continue
        common = sides[0] & sides[1]
        if len(common) != 1:
            continue
        s = common.pop()
        w = _mul(n, -s)
        back = _mul(w, -1)
        depth = min(_face_run(G, a, back), _face_run(G, b, back))
        caps.append({"c": _mid(a, b), "w": w, "t": t, "cap": (a, b), "depth": depth})
    return caps


def _face_groups(G, min_len=0.03):
    """W segments grouped into face LINES: (angle, offset) -> merged intervals along u."""
    items = []
    for a, b, _ in G.wall_segs:
        v = _sub(b, a)
        if _len(v) < min_len:
            continue
        ang = math.degrees(math.atan2(v[1], v[0])) % 180.0
        if ang > 179.7:
            ang -= 180.0
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        off = _cross(u, a)
        s0, s1 = sorted((_dot(u, a), _dot(u, b)))
        items.append((ang, off, s0, s1))
    items.sort()
    groups = []
    for ang, off, s0, s1 in items:
        for g in groups:
            if abs(g["ang"] - ang) < 0.25 and abs(g["off"] - off) < 0.004:
                g["iv"].append((s0, s1))
                break
        else:
            groups.append({"ang": ang, "off": off, "iv": [(s0, s1)]})
    for g in groups:
        merged = []
        for s0, s1 in sorted(g["iv"]):
            if merged and s0 <= merged[-1][1] + 0.003:
                merged[-1][1] = max(merged[-1][1], s1)
            else:
                merged.append([s0, s1])
        g["iv"] = merged
        g["u"] = (math.cos(math.radians(g["ang"])), math.sin(math.radians(g["ang"])))
        g["gaps"] = [(merged[k][1], merged[k + 1][0]) for k in range(len(merged) - 1)]
    return groups


def _band_gaps(G, gmin=0.30, gmax=4.0, tmin=0.07, tmax=0.40, tol=0.08):
    """Gaps where BOTH faces of a wall band are interrupted at the same place and the
    gap is empty (no crossing wall, no column) -> opening in a wall line."""
    groups = _face_groups(G)
    out = []
    for gi, g in enumerate(groups):
        for g0, g1 in g["gaps"]:
            if not (gmin <= g1 - g0 <= gmax):
                continue
            best = None
            for gj, h in enumerate(groups):
                if gj == gi or abs(h["ang"] - g["ang"]) > 0.3:
                    continue
                t = abs(h["off"] - g["off"])
                if not (tmin <= t <= tmax):
                    continue
                for h0, h1 in h["gaps"]:
                    if abs(h0 - g0) <= tol and abs(h1 - g1) <= tol:
                        if best is None or t < best[0]:
                            best = (t, h, h0, h1)
            if best is None:
                continue
            t, h, h0, h1 = best
            s_lo, s_hi = max(g0, h0), min(g1, h1)
            if s_hi - s_lo < gmin:
                continue
            u = g["u"]
            n = _perp(u)
            o_lo, o_hi = sorted((g["off"], h["off"]))

            def P(s, o, u=u, n=n):
                return _add(_mul(u, s), _mul(n, o))
            rect = Polygon([P(s_lo, o_lo), P(s_hi, o_lo), P(s_hi, o_hi), P(s_lo, o_hi)])
            inner = Polygon([P(s_lo + 0.015, o_lo + 0.01), P(s_hi - 0.015, o_lo + 0.01),
                             P(s_hi - 0.015, o_hi - 0.01), P(s_lo + 0.015, o_hi - 0.01)])
            if any(inner.intersects(G.wall_tree.geometries[k]) for k in G.wall_tree.query(inner)):
                continue
            if any(pg.intersects(rect) and pg.intersection(rect).area > 0.15 * rect.area for pg, _ in G.polys):
                continue
            out.append({"c0": P(s_lo, (o_lo + o_hi) / 2), "c1": P(s_hi, (o_lo + o_hi) / 2),
                        "t": t, "width": s_hi - s_lo, "rect": rect, "src": "band",
                        "capped": None})
    return out


def find_openings(fl, G, doors, windows):
    """Door-less openings.  Returns (openings, candidates, n_explained)."""
    door_polys = []
    for d in doors:
        if "jamb_a" in d:
            ja, jb = d["jamb_a"], d["jamb_b"]
            pg = Polygon([ja[0], ja[1], jb[1], jb[0]]).convex_hull.buffer(0.03)
            door_polys.append((pg, d["id"]))
    win_polys = []
    for w in windows:
        if w["shape"] == "straight":
            e1, e2 = w["ends"]
            win_polys.append((LineString([e1, e2]).buffer(max(w["frame_depth"], 0.05) / 2 + 0.15), w["id"]))
        else:
            win_polys.append((Point(w["center"]).buffer(w["radius_mid"] + 0.3).difference(
                Point(w["center"]).buffer(max(w["radius_mid"] - 0.4, 0.01))), w["id"]))

    def explain(rect):
        for pg, did in door_polys:
            if pg.intersects(rect) and pg.intersection(rect).area > 0.3 * min(pg.area, rect.area):
                return ("door", did)
        for pg, wid in win_polys:
            if pg.intersects(rect) and pg.intersection(rect).area > 0.2 * rect.area:
                return ("window", wid)
        return None

    caps = _wall_end_caps(G)
    raw = []
    single = []
    # (A) a wall end facing another wall end across an empty gap
    for k, cp in enumerate(caps):
        c, w, t = cp["c"], cp["w"], cp["t"]
        d = _perp(w)
        hits = [G.ray(_add(c, _mul(d, o)), w, max_len=4.0) for o in (-0.3 * t, 0.0, 0.3 * t)]
        if any(h[0] is None for h in hits):
            continue
        dist = min(h[0] for h in hits)
        if dist < 0.25:
            continue
        far = _add(c, _mul(w, dist))
        mate = None
        for m, cq in enumerate(caps):
            if m == k or _dot(cq["w"], w) > -0.99:
                continue
            v = _sub(cq["c"], c)
            if abs(_dot(v, w) - dist) > 0.03:
                continue
            a0, a1 = sorted((_dot(_sub(cp["cap"][0], c), d), _dot(_sub(cp["cap"][1], c), d)))
            b0, b1 = sorted((_dot(_sub(cq["cap"][0], c), d), _dot(_sub(cq["cap"][1], c), d)))
            if min(a1, b1) - max(a0, b0) >= 0.5 * min(a1 - a0, b1 - b0):
                mate = cq
                break
        a, b = cp["cap"]
        rect = Polygon([_add(a, _mul(w, 0.01)), _add(b, _mul(w, 0.01)),
                        _add(b, _mul(w, dist - 0.01)), _add(a, _mul(w, dist - 0.01))])
        if not rect.is_valid:
            rect = rect.buffer(0)
        rec = {"c0": c, "c1": far, "t": t, "width": dist, "rect": rect, "src": "caps",
               "capped": mate is not None, "depth": cp["depth"],
               "depth_far": mate["depth"] if mate else None, "t_far": mate["t"] if mate else None,
               "bound": hits[[h[0] for h in hits].index(dist)][1]}
        if mate is not None and min(cp["depth"], mate["depth"]) >= 0.25:
            raw.append(rec)
        elif mate is None:
            single.append(rec)
    # (B) both faces of a wall band interrupted (uncapped ends included)
    raw.extend(_band_gaps(G))

    def dedupe(lst):
        keep = []
        for g in sorted(lst, key=lambda g: (g["src"] != "caps", g["width"])):
            cg = _mid(g["c0"], g["c1"])
            dup = [k for k in keep if _len(_sub(cg, _mid(k["c0"], k["c1"]))) < 0.1 and abs(g["width"] - k["width"]) < 0.1]
            if dup:
                dup[0].setdefault("found_by", {dup[0]["src"]}).add(g["src"])
                continue
            g.setdefault("found_by", {g["src"]})
            keep.append(g)
        return keep
    raw = dedupe(raw)
    dash_lines = [LineString(s) for s in G.dash_segs]
    openings, n_expl = [], {"door": 0, "window": 0}
    for g in raw:
        ex = explain(g["rect"])
        if ex:
            n_expl[ex[0]] += 1
            continue
        openings.append(g)
    cands = []
    known = [_mid(g["c0"], g["c1"]) for g in raw]
    for g in single:
        cg = _mid(g["c0"], g["c1"])
        if g["depth"] < 0.25 or not (0.6 <= g["width"] <= 2.0) or g["bound"] != "wall":
            continue
        if explain(g["rect"]) or any(_len(_sub(cg, k)) < 0.15 for k in known):
            continue
        cands.append(g)

    def record(g, conf):
        c = _mid(g["c0"], g["c1"])
        w = _unit(_sub(g["c1"], g["c0"]))
        n = _perp(w)
        rb = g["rect"].buffer(0.02)
        dash = [ln for ln in dash_lines if ln.intersects(rb)]
        return {"kind": "opening (no door/window)", "center": _r(c), "axis_deg": _r(_axis_angle(w), 2),
                "width": _r(g["width"]), "wall_t": _r(g["t"]), "ends": _r([g["c0"], g["c1"]]),
                "found_by": sorted(g.get("found_by", {g["src"]})),
                "dash_across": bool(dash), "dash_len_in_gap": _r(sum(ln.intersection(rb).length for ln in dash)),
                "side_a": G.room_on_side(c, n), "side_b": G.room_on_side(c, _mul(n, -1)), "confidence": conf}
    out = []
    for g in openings:
        conf = "high" if g["width"] <= 3.0 else "medium"
        if g["src"] == "caps" and g.get("t_far") is not None and abs(g["t_far"] - g["t"]) > 0.03:
            conf = "medium"
        out.append(record(g, conf))
    out.sort(key=lambda o: (-round(o["center"][1] / 0.5), o["center"][0]))
    for k, o in enumerate(out, 1):
        o["id"] = f"{fl.label}-O{k:02d}"
    cand = [record(g, "low") for g in cands]
    for o in cand:
        o["kind"] = "candidate: wall end facing a perpendicular wall (review)"
    cand.sort(key=lambda o: (-round(o["center"][1] / 0.5), o["center"][0]))
    for k, o in enumerate(cand, 1):
        o["id"] = f"{fl.label}-C{k:02d}"
    return out, cand, n_expl


