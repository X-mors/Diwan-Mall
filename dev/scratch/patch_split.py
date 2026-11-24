p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()

anchor = "# ============================================================================\n# 5. "
i = s.index(anchor)
new_fn = r'''def _clip(ivs, a, b):
    return [(max(s, a), min(e, b)) for s, e in ivs if min(e, b) - max(s, a) > 1e-6]


def split_at_junctions(ctx, runs, min_branch=0.45):
    """Cut every run where another wall abuts it (T-junction), at the branch centre-line, so each
    record is one wall between junctions (as a surveyor measures it, room by room).  The junction
    square stays with the through-wall (half on each side of the cut)."""
    out = []
    n_cuts = 0
    for A in runs:
        D = A["D"]
        cA = (A["d0"] + A["d1"]) / 2
        half = (A["d1"] - A["d0"]) / 2
        stations = []
        for B in runs:
            if B is A or _angdiff(D.ang, B["D"].ang) < 20 or B["e"] - B["s"] < min_branch:
                continue
            Db = B["D"]
            cB = (B["d0"] + B["d1"]) / 2
            sin = abs(math.sin(math.radians(D.ang - Db.ang)))
            for tb, to in ((B["s"], B["e"]), (B["e"], B["s"])):
                tE, dE = D.td(*Db.xy(tb, cB))
                tO, dO = D.td(*Db.xy(to, cB))
                if abs(dE - cA) > half / max(sin, 0.3) + 0.04 or abs(dO - cA) <= abs(dE - cA):
                    continue
                X = _line_intersection(D, cA, Db, cB)
                if X is None:
                    continue
                tX = D.td(*X)[0]
                if not (A["s"] + 0.05 < tX < A["e"] - 0.05):
                    continue
                if any(gp["s"] - 0.02 <= tX <= gp["e"] + 0.02 for gp in A["openings"]):
                    continue
                stations.append(tX)
        stations.sort()
        cuts = []
        for t in stations:
            if not cuts or t - cuts[-1] > 0.05:
                cuts.append(t)
        if not cuts:
            out.append(A)
            continue
        bounds = [A["s"]] + cuts + [A["e"]]
        for k in range(len(bounds) - 1):
            a, b = bounds[k], bounds[k + 1]
            sub = dict(A)
            sub["s"], sub["e"] = a, b
            sub["solid"] = _clip(A["solid"], a, b)
            sub["openings"] = [gp for gp in A["openings"] if gp["s"] >= a - 1e-6 and gp["e"] <= b + 1e-6]
            sub["gaps"] = [gp for gp in A["gaps"] if gp["s"] >= a - 1e-6 and gp["e"] <= b + 1e-6]
            sub["ext"] = [A["ext"][0] if k == 0 else 0.0, A["ext"][1] if k == len(bounds) - 2 else 0.0]
            # corner extensions live outside the solid list: keep them only on the outer pieces
            if k > 0:
                sub["solid"] = [(max(x, a), y) for x, y in sub["solid"]]
            sub["end_reason"] = A.get("end_reason") if k == len(bounds) - 2 else "T-junction"
            sub["split_from"] = id(A)
            out.append(sub)
        n_cuts += len(cuts)
    return out, n_cuts


'''
s = s[:i] + new_fn + s[i:]

old = '''    n_corners = extend_corners(ctx, runs)
    classify_runs(ctx, runs)
    return ctx, runs, {"n_corners": n_corners, **{k: round(v, 3) for k, v in log.items()}}'''
new = '''    n_corners = extend_corners(ctx, runs)
    runs, n_cuts = split_at_junctions(ctx, runs)
    classify_runs(ctx, runs)
    return ctx, runs, {"n_corners": n_corners, "n_junction_cuts": n_cuts,
                       **{k: round(v, 3) for k, v in log.items()}}'''
assert old in s
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("patched")
