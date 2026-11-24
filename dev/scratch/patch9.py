from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:70])
    s = s.replace(old, new)
rep('''            if rec["r_in"] < 0.17 or (rec["r_in"] < 0.33 and rec["area"] < 1.2):
                wall_bodies.append(rec)
                continue
''', '''            if rec["r_in"] < 0.17 or (rec["r_in"] < 0.33 and rec["area"] < 1.2):
                wall_bodies.append(rec)
                continue
            if rec["area"] < 2.0 and not rec["wc_pans"] and rec.get("soil", 0.0) < 0.5 and not any(
                    P[j][1] in ("door", "opening", "glazing") and P[j][0].distance(f) < 0.03
                    for j in tree.query(f.buffer(0.03))):
                # small closed pocket, no door / opening / glass: a solid block drawn as an outline
                # (corner blocks at the curved glazing, round element of F02) - not a room
                rec["pocket"] = True
                wall_bodies.append(rec)
                pockets.append({"area": round(rec["area"], 3), "centroid": _r([f.centroid.x, f.centroid.y]),
                                "bbox": _r(list(f.bounds))})
                continue
''')
rep('''    rooms = []
    wall_bodies = []''', '''    rooms = []
    wall_bodies = []
    pockets = []''')
rep('''        "corridor_lobby_splits": splits,''', '''        "corridor_lobby_splits": splits,
        "closed_pockets_as_solid": pockets,''')
# boundary totals by kind
rep('''        "net_indoor_area": round(sum(r["area"] for r in indoor), 3),''', '''        "net_indoor_area": round(sum(r["area"] for r in indoor), 3),
        "boundary_by_kind_indoor": {k: round(sum(r["boundary"].get(k, 0.0) for r in indoor
                                                 if r["category"] in INDOOR_CEILING), 3)
                                    for k in KIND_PRIORITY + ["unresolved"]
                                    if any(r["boundary"].get(k) for r in indoor if r["category"] in INDOOR_CEILING)},
        "boundary_by_kind_open_air": {k: round(sum(r["boundary"].get(k, 0.0) for r in open_air), 3)
                                      for k in KIND_PRIORITY + ["unresolved"]
                                      if any(r["boundary"].get(k) for r in open_air)},''')
p.write_text(s, encoding="utf-8")
print("ok")
