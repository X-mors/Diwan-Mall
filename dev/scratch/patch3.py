from pathlib import Path
p = Path(r"D:\حصر المباني\Diwan-Mall\tools\rooms.py")
s = p.read_text(encoding="utf-8")
i0 = s.index("def dim_checks(poly, dims, tol=0.02):")
i1 = s.index("# ============================================================================\n# 7. analysis of one floor")
new = '''def _first_exit(poly, start, u, reach):
    """Distance from an inside point along u to the first crossing of the polygon boundary."""
    ray = LineString([start, (start[0] + u[0] * reach, start[1] + u[1] * reach)])
    x = ray.intersection(poly.boundary)
    if x.is_empty:
        return None
    pts = []
    for part in (x.geoms if hasattr(x, "geoms") else [x]):
        pts.extend(part.coords if part.geom_type != "Point" else [(part.x, part.y)])
    ds = [(q[0] - start[0]) * u[0] + (q[1] - start[1]) * u[1] for q in pts]
    ds = [v for v in ds if v > 1e-6]
    return min(ds) if ds else None


def dim_checks(poly, dims, tol=0.02, min_span=0.5):
    """Architect DIMs (layer DIM, linear: rotated type 0 / aligned type 1) whose two
    definition points both lie on this room's boundary.  The DIM value is the distance
    between its points along its direction (aligned DIMs: the true p2-p3 distance; their
    stored 'angle' is meaningless).  The check casts a ray from just inside the room at
    each DIM point along the DIM direction towards the other point and measures the room's
    clear width there: diff = width - value.  A DIM that measures to a feature not facing
    its other end (a column / wall jog in between) shows up as a mismatch."""
    out = []
    bd = poly.boundary
    for d in dims:
        if d["type"] not in (0, 1):
            continue
        p2, p3 = tuple(d["p2"]), tuple(d["p3"])
        if bd.distance(Point(p2)) > tol or bd.distance(Point(p3)) > tol:
            continue
        if d["type"] == 0:
            a = math.radians(d["angle"])
            u = (math.cos(a), math.sin(a))
        else:
            u = _unit((p3[0] - p2[0], p3[1] - p2[1]))
        proj = (p3[0] - p2[0]) * u[0] + (p3[1] - p2[1]) * u[1]
        span = abs(proj)
        if span < min_span:
            continue
        s = 1.0 if proj > 0 else -1.0
        widths = []
        for start, sg in ((p2, s), (p3, -s)):
            v = (u[0] * sg, u[1] * sg)
            inner = (start[0] + v[0] * 0.03, start[1] + v[1] * 0.03)
            if not poly.contains(Point(inner)):
                continue
            w = _first_exit(poly, inner, v, span + 1.0)
            if w is not None:
                widths.append(w + 0.03)
        if not widths:
            continue
        w = min(widths, key=lambda q: abs(q - span))
        rec = {"dim": d["handle"], "value": round(span, 3), "room_width": round(w, 3),
               "diff": round(w - span, 3), "dir_deg": round(math.degrees(math.atan2(u[1], u[0])) % 180.0, 1),
               "p2": [round(v, 3) for v in p2], "p3": [round(v, 3) for v in p3]}
        if abs(d["value"] - span) > 0.005:
            rec["stored_measurement"] = round(d["value"], 3)
        out.append(rec)
    return out


'''
s = s[:i0] + new + s[i1:]
p.write_text(s, encoding="utf-8")
print("ok")
