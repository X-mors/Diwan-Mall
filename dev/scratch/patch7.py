from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)
rep('''    faces0 = [restore(f) for f in raw_faces if f.area >= MIN_FACE]
    faces, slivers, trimmed = [], [], []
    for f in faces0:
        if f.area < MIN_FACE:
            continue
        cores, sl = slice_face(f)
        cores = [close_slits(c) for c in cores]
        faces.extend(c for c in cores if c.area >= MIN_FACE)
        trimmed.extend([None] * len([c for c in cores if c.area >= MIN_FACE]))
        lost = sl + [c for c in cores if c.area < MIN_FACE]
        slivers.extend(lost)
        if lost:
            for k in range(1, len([c for c in cores if c.area >= MIN_FACE]) + 1):
                trimmed[-k] = round(sum(x.area for x in lost), 3)''',
'''    # slicing runs on the RAW free faces (every drawn line is still a 3 cm gap there, so a wall
    # body hanging on a room through a line is a real thin appendage), then each piece is grown
    # back onto the drawn faces and its zero-width slits (free-standing lines) are closed.
    faces, slivers, trimmed = [], [], []
    for f0 in raw_faces:
        if f0.area < MIN_FACE * 0.5:
            continue
        cores, sl = slice_face(f0, r=SLICE_R - EPS, min_sliver=0.012)
        whole = restore(f0)
        cores = [close_slits(restore(c).intersection(whole)) if len(cores) > 1 or sl else close_slits(whole)
                 for c in cores]
        cores = [max(c.geoms, key=lambda q: q.area) if c.geom_type != "Polygon" else c for c in cores]
        sl = [restore(x).intersection(whole) for x in sl]
        good = [c for c in cores if c.area >= MIN_FACE]
        lost = sl + [c for c in cores if c.area < MIN_FACE]
        faces.extend(good)
        slivers.extend(x for x in lost if not x.is_empty)
        t = round(sum(x.area for x in lost), 3) if lost else None
        trimmed.extend([t] * len(good))''')
p.write_text(s, encoding="utf-8")
print("ok")
