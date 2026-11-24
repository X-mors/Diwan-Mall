from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new):
    global s
    assert old in s, old[:60]
    s = s.replace(old, new)
rep('''    wc_pans = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "P"]
''', '''    wc_pans = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "P"]
    basins = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "WB"]
''')
rep('''        rec["x_dash"] = count_x(f, dash_diag)
''', '''        rec["x_dash"] = count_x(f, dash_diag)
        rec["diag_dash"] = count_diag(f, dash_diag)
''')
rep('''        rec["wc_pans"] = sum(1 for p in wc_pans if f.contains(p))
''', '''        # WC pan / basin blocks are inserted ON the wall face behind them -> look 0.25 m around
        fz = f.buffer(0.25)
        rec["wc_pans"] = sum(1 for p in wc_pans if fz.contains(p))
        rec["basins"] = sum(1 for p in basins if fz.contains(p))
''')
rep('''        if rec["in_try"] or (rec["x_dash"] and not rec["labels"] and rec["area"] < 4.0):''',
    '''        if rec["in_try"] or ((rec["x_dash"] or rec["diag_dash"]) and not rec["labels"] and rec["area"] < 4.0):''')
rep('''        elif not name:
            if rec["wc_pans"]:
                name, cat = "حمام (بلا اسم - به قاعدة مرحاض)", "wc"
                flags.append("unlabelled_wc: no label, named from the WC pan block P")
            elif rec["r_in"] < 0.17 or (rec["r_in"] < 0.33 and rec["area"] < 1.2):
                wall_bodies.append(rec)
                continue
            else:
                name, cat = "فراغ بلا اسم", "void"
                flags.append("unlabelled")''', '''        elif not name:
            if rec["r_in"] < 0.17 or (rec["r_in"] < 0.33 and rec["area"] < 1.2):
                wall_bodies.append(rec)
                continue
            if rec["wc_pans"] and rec["area"] < 12.0:
                name, cat = "حمام (بلا اسم)", "wc"
                flags.append("unlabelled_wc: no room label; named from the WC pan block P (FUR) inside")
            else:
                name, cat = "فراغ بلا اسم", "void"
                flags.append("unlabelled")''')
rep('''    solid = unary_union([mass] + [w["poly"] for w in wall_bodies])''',
    '''    solid = unary_union([mass] + [w["poly"] for w in wall_bodies] + slivers)''')
rep('''"_wall_bodies": [w["poly"] for w in wall_bodies],''', '''"_wall_bodies": [w["poly"] for w in wall_bodies] + slivers,''')
rep('''        "wall_bodies": {"n": len(wall_bodies), "area": round(sum(w["area"] for w in wall_bodies), 3)},''',
    '''        "wall_bodies": {"n": len(wall_bodies) + len(slivers),
                        "area": round(sum(w["area"] for w in wall_bodies) + sum(x.area for x in slivers), 3)},''')
rep('''def inscribed_radius(poly):''', '''def count_diag(face, segs, frac=0.7):
    """Single diagonals (one stroke of an X, or a '/' shaft mark) spanning the face."""
    fb = face.buffer(0.06)
    x0, y0, x1, y1 = face.bounds
    dg = math.hypot(x1 - x0, y1 - y0)
    return sum(1 for s in segs if fb.contains(s) and s.length >= frac * dg)


def inscribed_radius(poly):''')
lines = s.split("\n")
for i, l in enumerate(lines):
    if 'txt = f"{short}  {r[\'name\']}' in l:
        lines[i] = l[:l.index("txt")] + 'txt = f"{r[\'name\']}\n{short}  {r[\'area\']:.2f} m2  P={r[\'perimeter\']:.2f}"'
    elif 'txt = f"{r[\'name\']} {r[\'area\']:.2f}"' in l:
        lines[i] = l[:l.index("txt")] + 'txt = f"{r[\'name\']}\n{r[\'area\']:.2f} m2"'
s = "\n".join(lines)
p.write_text(s, encoding="utf-8")
print("ok")
