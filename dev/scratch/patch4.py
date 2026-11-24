from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)
rep('''def restore(f):
    r = f.buffer(EPS, join_style=2, mitre_limit=10.0)
    if r.geom_type == "MultiPolygon":
        r = max(r.geoms, key=lambda q: q.area)
    return r''', '''def restore(f):
    """Grow a free face back onto the drawn faces, then close zero-width slits (a single
    free-standing line inside a room would otherwise leave a slit counted twice in the
    perimeter)."""
    r = f.buffer(EPS, join_style=2, mitre_limit=10.0)
    r = r.buffer(0.002, join_style=2, mitre_limit=10.0).buffer(-0.002, join_style=2, mitre_limit=10.0)
    if r.geom_type == "MultiPolygon":
        r = max(r.geoms, key=lambda q: q.area)
    return r''')
rep('''        for end, prev in ((cs[0], cs[1]), (cs[-1], cs[-2])):
            pt = Point(end)''', '''        for end, prev in ((cs[0], cs[1]), (cs[-1], cs[-2])):
            if _dist(end, prev) < min_seg:
                continue                      # too short to give a reliable direction
            pt = Point(end)''')
rep('''def dangling_extensions(P, max_ext=MAX_EXT, touch=0.012, ray_tol=0.016):''',
    '''def dangling_extensions(P, max_ext=MAX_EXT, touch=0.012, ray_tol=0.016, min_seg=0.15):''')
# free-standing lines inside a room
rep('''        item["dim_checks"] = dim_checks(f, g["dims"])''', '''        inner = f.buffer(-0.02)
        free_len = 0.0
        if not inner.is_empty:
            for j in tree.query(inner):
                geom, kind, ref = P[j]
                if kind in ("wall", "glazing", "extension") and geom.geom_type == "LineString":
                    free_len += geom.intersection(inner).length
        if free_len > 0.05:
            item["free_lines_inside"] = round(free_len, 3)
            item["flags"].append(f"free_lines_inside: {free_len:.2f} m of single W/WIN lines stand inside this "
                                 f"space (not part of its perimeter) - partial wall / screen?")
        item["dim_checks"] = dim_checks(f, g["dims"])''')
p.write_text(s, encoding="utf-8")
print("ok")
