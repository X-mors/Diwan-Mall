p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()
old = '''    res["dim_crosscheck"] = dim_crosscheck(ctx, recs)'''
new = '''    res["openings_summary"] = openings_summary(recs)
    res["curves"] = curves_summary(g)
    res["dim_crosscheck"] = dim_crosscheck(ctx, recs)'''
assert old in s
s = s.replace(old, new)
anchor = "def overlap_check(recs):"
fn = r'''def _sweep(a0, a1):
    sw = (a1 - a0) % 360.0
    return sw if sw > 1e-9 else 360.0


def curves_summary(g):
    """Curved elements: arcs on W (F02: round terrace columns + terrace outline) and the
    curved glazing on WIN (rounded NW / SW corners).  None of them is a masonry wall."""
    w = []
    for a in g["warcs"]:
        sw = _sweep(a[3], a[4])
        w.append({"center": [round(a[0], 2), round(a[1], 2)], "r": round(a[2], 3), "sweep_deg": round(sw, 1),
                  "length": round(math.radians(sw) * a[2], 2), "src": a[6] if len(a) > 6 else "ARC"})
    win = []
    for a in g["winarcs"]:
        sw = _sweep(a[3], a[4])
        win.append({"center": [round(a[0], 2), round(a[1], 2)], "r": round(a[2], 3), "sweep_deg": round(sw, 1),
                    "length": round(math.radians(sw) * a[2], 2)})
    return {"w_arcs": w, "win_arcs": win,
            "win_arcs_length": round(sum(x["length"] for x in win), 2)}


def openings_summary(recs):
    out = defaultdict(lambda: {"n": 0, "width": 0.0})
    blocks = Counter()
    for w in recs:
        for o in w["openings"]:
            k = f"{o['type']}|{w['kind']}"
            out[k]["n"] += 1
            out[k]["width"] += o["width"]
            if o.get("block"):
                blocks[o["block"]] += 1
    return {"by_type_kind": {k: {"n": v["n"], "width": round(v["width"], 2)} for k, v in sorted(out.items())},
            "door_blocks": dict(blocks)}


'''
i = s.index(anchor)
s = s[:i] + fn + s[i:]
open(p, "w", encoding="utf-8").write(s)
print("ok")
