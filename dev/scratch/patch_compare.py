p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()
anchor = "def _json_default(o):"
fn = r'''def _same_wall(a, b, tol=0.012):
    if _angdiff(a["angle"], b["angle"]) > 0.5:
        return 0.0
    if abs(a["_band"][0] - b["_band"][0]) > tol or abs(a["_band"][1] - b["_band"][1]) > tol:
        return 0.0
    lo = max(a["_t"][0], b["_t"][0])
    hi = min(a["_t"][1], b["_t"][1])
    return max(0.0, hi - lo)


def compare_floors(results, ref="F03"):
    """Walls that differ between floors (same local frame on every floor): for every floor,
    the wall length (net, solid) that has no counterpart on the reference floor and vice versa."""
    R = {r["floor"]: r for r in results}
    if ref not in R:
        return {}
    base = R[ref]["walls"]
    out = {}
    for F, r in R.items():
        if F == ref:
            continue
        only_here, only_ref = [], []
        for w in r["walls"]:
            ov = sum(_same_wall(w, b) for b in base)
            miss = w["length_gross"] - ov
            if miss > 0.20:
                only_here.append({"id": w["id"], "thickness": w["thickness"], "kind": w["kind"],
                                  "missing_len": round(miss, 2), "x1": w["x1"], "y1": w["y1"], "x2": w["x2"], "y2": w["y2"]})
        for b in base:
            ov = sum(_same_wall(b, w) for w in r["walls"])
            miss = b["length_gross"] - ov
            if miss > 0.20:
                only_ref.append({"id": b["id"], "thickness": b["thickness"], "kind": b["kind"],
                                 "missing_len": round(miss, 2), "x1": b["x1"], "y1": b["y1"], "x2": b["x2"], "y2": b["y2"]})
        out[F] = {"vs": ref,
                  "only_on_this_floor_len": round(sum(x["missing_len"] for x in only_here), 2),
                  "only_on_ref_len": round(sum(x["missing_len"] for x in only_ref), 2),
                  "only_on_this_floor": only_here, "only_on_ref": only_ref}
    return out


'''
i = s.index(anchor)
s = s[:i] + fn + s[i:]
old = '''    if not a.floors:
        (WALL_OUT / "summary.json").write_text('''
new = '''    if not a.floors:
        results = [json.loads((WALL_OUT / f"F{n:02d}.json").read_text(encoding="utf-8")) for n in floors]
        diff = compare_floors(results)
        (WALL_OUT / "floor_diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=1,
                                                             default=_json_default), encoding="utf-8")
        for F, d in diff.items():
            print(f"diff {F} vs {d['vs']}: only here {d['only_on_this_floor_len']} m, only on ref {d['only_on_ref_len']} m")
        (WALL_OUT / "summary.json").write_text('''
assert old in s
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("ok")
