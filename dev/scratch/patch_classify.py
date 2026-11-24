p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()
i = s.index("OUTDOOR_WORDS = ")
j = s.index("# ============================================================================\n# 6. driver")
new = r'''OUTDOOR_WORDS = ("تراس", "زرع", "سماوي")
WET_WORDS = ("حمام", "مطبخ", "بوفيه", "wc")


def _stair_hulls(g):
    """One convex hull per cluster of stair lines (layer ST)."""
    lines = [LineString([(a, b), (c, d)]) for a, b, c, d in g["st"] if math.hypot(c - a, d - b) > 1e-4]
    if not lines:
        return []
    blobs = unary_union([ln.buffer(0.6) for ln in lines])
    out = []
    for bl in getattr(blobs, "geoms", [blobs]):
        members = [ln for ln in lines if bl.contains(ln.centroid)]
        if len(members) >= 4:
            out.append(unary_union(members).convex_hull)
    return out


def classify_runs(ctx, runs):
    """Look at both sides of every wall: outside (ray escapes / terrace label), shaft void,
    lift well, stair hall, room (nearest visible room label)."""
    for r in runs:
        D = r["D"]
        sides = {0: Counter(), 1: Counter()}
        labels = {0: Counter(), 1: Counter()}
        flags = {0: Counter(), 1: Counter()}
        stations = []
        for s, e in r["solid"] + [(gp["s"], gp["e"]) for gp in r["openings"]]:
            n = max(3, int((e - s) / 0.25))
            stations += [s + (e - s) * (i + 0.5) / n for i in range(n)]
        for t in stations:
            for side, d, sgn in ((0, r["d0"] - 0.03, -1), (1, r["d1"] + 0.03, 1)):
                pt = D.xy(t, d)
                P = Point(pt)
                if ctx.CU is not None and ctx.CU.contains(P):
                    sides[side]["concrete"] += 1
                    continue
                if ctx.piece_tree is not None and any(ctx.piece_rects[int(k)].contains(P)
                                                      for k in ctx.piece_tree.query(P)):
                    sides[side]["solid"] += 1      # another wall / nib touches here
                    continue
                if ctx.LU is not None and ctx.LU.contains(P):
                    sides[side]["void"] += 1
                    flags[side]["lift"] += 1
                    continue
                if ctx.VU is not None and ctx.VU.contains(P):
                    sides[side]["void"] += 1
                    continue
                lab = ctx.visible_label(pt)
                outdoor_lab = bool(lab) and any(w in lab for w in OUTDOOR_WORDS)
                if outdoor_lab or ctx.ray_escapes(pt, (D.n[0] * sgn, D.n[1] * sgn)):
                    sides[side]["out"] += 1
                    if outdoor_lab:
                        labels[side][lab] += 1
                    continue
                sides[side]["room"] += 1
                if lab:
                    labels[side][lab] += 1
                    if any(w in lab.lower() for w in WET_WORDS):
                        flags[side]["wet"] += 1
                if ctx.in_stair(pt):
                    flags[side]["stair"] += 1
        r["sides"] = []
        for side in (0, 1):
            tot = sum(v for k, v in sides[side].items() if k != "solid") or 1
            r["sides"].append({"share": {k: round(v / tot, 2) for k, v in sides[side].items() if k != "solid"},
                               "labels": [k for k, _ in labels[side].most_common(3)],
                               "stair": flags[side]["stair"] / tot >= 0.3,
                               "lift": flags[side]["lift"] / tot >= 0.3,
                               "wet": flags[side]["wet"] / tot >= 0.3})
        out = [r["sides"][k]["share"].get("out", 0) for k in (0, 1)]
        void = [r["sides"][k]["share"].get("void", 0) for k in (0, 1)]
        if max(out) >= 0.5:
            kind = "exterior"
        elif any(r["sides"][k]["stair"] or r["sides"][k]["lift"] for k in (0, 1)):
            kind = "stair_lift"
        elif max(void) >= 0.5:
            kind = "shaft"
        else:
            kind = "interior"
        r["kind"] = kind
        r["mixed"] = (0.2 <= max(out) < 0.5) or (0.25 <= max(void) < 0.5 and kind != "shaft")


'''
s = s[:i] + new + s[j:]

old = '''    def ray_escapes(self, pt, nv, length=80.0):'''
new = '''    def _blockers(self):
        from shapely.strtree import STRtree
        if self._tree is None:
            obs = list(self.wlines)
            obs += [LineString([(w[0], w[1]), (w[2], w[3])]) for w in self.win_segs
                    if math.hypot(w[2] - w[0], w[3] - w[1]) > 1e-4]
            for a in self.g["warcs"] + self.g["winarcs"]:
                pts = _arc_pts(a[0], a[1], a[2], a[3], a[4])
                if len(pts) >= 2:
                    obs.append(LineString(pts))
            self._obs = obs
            self._tree = STRtree(obs)
        return self._tree, self._obs

    def visible(self, p, q):
        tree, obs = self._blockers()
        ln = LineString([p, q])
        return not any(obs[int(k)].intersects(ln) for k in tree.query(ln))

    def visible_label(self, pt, rmax=8.0):
        """Nearest room label (layer TEXT / -A-TEXT) seen from pt without crossing W/WIN."""
        cands = sorted((math.hypot(t["x"] - pt[0], t["y"] - pt[1]), k) for k, t in enumerate(self.g["texts"])
                       if abs(t["x"] - pt[0]) < rmax and abs(t["y"] - pt[1]) < rmax)
        for dist, k in cands[:6]:
            t = self.g["texts"][k]
            if dist <= rmax and self.visible(pt, (t["x"], t["y"])):
                return t["text"]
        return None

    def in_stair(self, pt):
        P = Point(pt)
        for H in self.stair_hulls:
            if H.contains(P):
                return True
            if H.buffer(1.4).contains(P):
                from shapely.ops import nearest_points
                q = nearest_points(H, P)[0]
                if self.visible(pt, (q.x, q.y)):
                    return True
        return False

    def ray_escapes(self, pt, nv, length=80.0):'''
assert old in s
s = s.replace(old, new)
old = '''        self._tree = None
'''
new = '''        self._tree = None
        self.stair_hulls = _stair_hulls(g)
'''
assert old in s
s = s.replace(old, new, 1)
i = s.index("    def ray_escapes(self, pt, nv, length=80.0):")
j = s.index("\n\n\n", i)
s = s[:i] + '''    def ray_escapes(self, pt, nv, length=80.0):
        """True if a ray from pt along nv leaves the plan without hitting W/WIN geometry."""
        return self.visible(pt, (pt[0] + nv[0] * length, pt[1] + nv[1] * length))''' + s[j:]

old = '''    spaces, foot = build_spaces(ctx, runs)
    classify_runs(ctx, runs, spaces, foot)
    return ctx, runs, spaces, foot, {"n_corners": n_corners, **{k: round(v, 3) for k, v in log.items()}}'''
new = '''    classify_runs(ctx, runs)
    return ctx, runs, {"n_corners": n_corners, **{k: round(v, 3) for k, v in log.items()}}'''
assert old in s
s = s.replace(old, new)
old = '''    ctx, runs, spaces, foot, diag = detect(g, height)'''
new = '''    ctx, runs, diag = detect(g, height)'''
assert old in s
s = s.replace(old, new)
old = '''                        "spaces": len(spaces),
                        "footprint_area": round(foot.area, 2) if foot is not None else None,
'''
new = '''                        "stair_zones": len(ctx.stair_hulls),
'''
assert old in s
s = s.replace(old, new)
old = '''        unk = max(r["sides"][k]["share"].get("unknown", 0) for k in (0, 1))
        if unk >= 0.5:
            reasons.append("side space not enclosed (polygonize leak)")
'''
assert old in s
s = s.replace(old, "")
open(p, "w", encoding="utf-8").write(s)
print("patched")
