from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)
rep('''def restore(f):
    """Grow a free face back onto the drawn faces, then close zero-width slits (a single
    free-standing line inside a room would otherwise leave a slit counted twice in the
    perimeter)."""
    r = f.buffer(EPS, join_style=2, mitre_limit=10.0)
    r = r.buffer(0.002, join_style=2, mitre_limit=10.0).buffer(-0.002, join_style=2, mitre_limit=10.0)
    if r.geom_type == "MultiPolygon":
        r = max(r.geoms, key=lambda q: q.area)
    return r''', '''def restore(f):
    """Grow a free face back onto the drawn faces (mitre: corners stay square)."""
    r = f.buffer(EPS, join_style=2, mitre_limit=10.0)
    if r.geom_type == "MultiPolygon":
        r = max(r.geoms, key=lambda q: q.area)
    return r


def close_slits(f):
    """Close zero-width slits: a single free-standing line inside a room (or a door-frame
    spike) would otherwise be counted twice in the perimeter.  Done AFTER slice_face, so a
    wall body that hangs on a room only through such a slit has already been cut off."""
    r = f.buffer(0.002, join_style=2, mitre_limit=2.0).buffer(-0.002, join_style=2, mitre_limit=2.0)
    if r.geom_type == "MultiPolygon":
        r = max(r.geoms, key=lambda q: q.area)
    return r if abs(r.area - f.area) < 0.05 + 0.01 * f.area else f''')
rep('''    core = f.buffer(-r, join_style=2, mitre_limit=10.0)
    if core.is_empty:
        return [], [f]
    core = core.buffer(r, join_style=2, mitre_limit=10.0).intersection(f)''',
'''    # mitre_limit 2: square corners stay exact (ratio 1.41) while a zero-width spike (door
    # frame drawn on W) cannot shoot a mitre 10 x r deep into the room
    core = f.buffer(-r, join_style=2, mitre_limit=2.0)
    if core.is_empty:
        return [], [f]
    core = core.buffer(r, join_style=2, mitre_limit=2.0).intersection(f)''')
rep('''        cores, sl = slice_face(f)
        faces.extend(c for c in cores if c.area >= MIN_FACE)''', '''        cores, sl = slice_face(f)
        cores = [close_slits(c) for c in cores]
        faces.extend(c for c in cores if c.area >= MIN_FACE)''')
p.write_text(s, encoding="utf-8")
print("ok")
