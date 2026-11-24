# -*- coding: utf-8 -*-
"""
structure — قارئ العناصر الإنشائية وطبقات التعليق في مساقط الديوان
(أعمدة / حوائط قص / كور المصاعد / شفتات / سلالم / مصاعد / شبكة المحاور / أبعاد المعماري).

Every floor F02..F08, shared LOCAL frame of diwan_common (rotation removed, Etabs-col
min corner = (0,0), metres; +y = "north" as used in the other findings docs).

STRUCTURE  (concrete that is NOT masonry and whose faces get plaster)
  * Etabs-col LWPOLYLINE (closed)  -> 13 rectangles + 1 C-shaped lift core per floor.
  * Etabs-col HATCH boundaries     -> the same 14 + ONE shear wall drawn ONLY as a hatch
    (3.90 x 0.40 at x 3.155-7.055, y 18.654-19.054; outline drawn on layer W).
  * block 'tr' (layer Etabs-Slab, inserted TWICE at the same place, insertion point far
    off-sheet, geometry on-sheet) = an ETABS export holding 7 MORE elements (Etabs-col
    polylines + Etabs-Slab hatches) that are NOT in model space and that walls.py /
    rooms.py do not read: 0.45x2.30, 0.90x0.50, 0.25x3.35, 1.20x0.60, 0.50x1.00,
    0.80x0.55, 0.45x2.04.  Some fill gaps in the W walls (the "0.80 opening" between
    office 3 and 2 in F03/F04 is exactly the 0.80x0.55 column), some stand in rooms with
    no W outline at all -> flagged for the engineer.
  * COL = two 0.40x0.40 squares with an X (open LWPOLYLINE + 2 diagonals) on the face
    of Etabs-col walls.
  Polygons from all sources are de-duplicated (same footprint = one element, sources
  listed).  kind: column (long/short <= 5), shear_wall (> 5), core (non-rectangular),
  column_xbox (COL).  Each element: id (stable across floors, sorted by position),
  bbox, size, area, perimeter, grid_ref (nearest axes), W walls abutting each face
  (end points of W lines on the outline, paired into wall thicknesses) ->
  exposed_perimeter = perimeter - abutting wall thicknesses (plaster on column faces,
  approximate), outline_on_W (fraction of the outline also drawn as W lines -> risk of
  being counted as masonry), w_inside (W lines running through the element).
SHAFTS     layer 'try' closed boxes (X drawn by DASH diagonals) + DASH-only X boxes;
           hatched try boxes (ANSI31, duplicated) = small posts at the west curtain wall.
STAIRS     ST lines clustered -> flights (tread lines, going, width), landing steps,
           stair eye (MASS rectangle), arrow (PR1 'ST-2'), blank level tags (TEXT-D).
LIFTS      PR rectangles with an X = lift cars; core opening + MASS door lines.
GRID       X lines (DASHDOT) + bubbles (random-named INSERTs on X, CI circle + TEXT on
           TEXT-DIM, SOSA letters) -> x-axes  ا ب ج د ه و ز ح ط  (east -> west) and
           y-axes 1..15 (south -> north).  The 'tags' inserted on W (ز ا ب ج د / 1-4) are
           DISPLACED copies (constant offset) -> labels assigned by abjad order.
DASH       every DASH line classified: door_head / window_head / opening_head (lintel
           line over a gap), stair_flight (upper flight above the cut), shaft_cross
           (diagonals), lift_divider, other.
DIMS       architect DIMENSIONs (dimstyle WWW): displayed text, actual_measurement
           (ezdxf get_measurement() is WRONG for the aligned ones -> not used), local
           extension points, direction, what each end snaps to (X / W / WIN / Etabs-col),
           class: axis_chain / overall / wall_thickness / opening / facade_step /
           interior / other.  Histogram of values.
ANNOTATION TEXT-D (titles + blank '+ 0.00' level tags), level marks (PR), HAT (frame
           lines + 2 hatches in the lift shafts), MASS (stair eye, break lines, lift door
           lines, PLOT BOUNDARY polygon, title-block lines), -MASS (title block of another
           project 'ابراج الفرسان'), sidewalk (area schedule of all floors), PR1, FUR
           (WC 'P' / basin 'WB'), layer-0 notes, LOGO-L1.

CLI (default = all floors):
    python tools/structure.py              # -> output/structure/F0x.json + F0x_structure.png + F0x_dims.png
                                           #    + dims_histogram.png + summary.json (incl. canonical_shafts)
                                           #    + refreshes the <!-- AUTO:... --> tables of docs/findings/structure_diff.md
    python tools/structure.py 3 5 --no-png --no-doc
    python tools/structure.py 3 --zoom 9 17 15 30     # extra zoomed PNG
    Running several floors gives every shaft box the same SHnn id on all floors
    (harmonize_shaft_ids); structural element ids (Cnn/SWnn/CORE01/CXnn) are stable anyway.
API:
    from structure import analyze_floor, read_grid, grid_ref, run, render
    res = analyze_floor(3)                  # dict (JSON-able)
    res["elements"]   # [{id, kind, sources, bbox, size, area, perimeter, exposed_perimeter, grid_ref, ...}]
    res["grid"]       # {"x_axes": [{label, coord, source}], "y_axes": [{label, coord, source}], ...}
    grid_ref(res["grid"], 12.0, 20.5)       # -> 'د+2.25 / 8+1.58' (nearest axis + offset, m)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from ezdxf import path as ezpath
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import (OUT_DIR, all_floors, entity_bbox, floor_entities,  # noqa: E402
                          get_floor, STOREY_HEIGHT)
from sosa_decode import decode, is_arabic_style  # noqa: E402

OUT = OUT_DIR / "structure"
ABJAD = ["ا", "ب", "ج", "د", "ه", "و", "ز", "ح", "ط", "ي", "ك", "ل", "م", "ن"]
WALL_RATIO = 5.0          # long/short > 5 -> shear wall (naming convention only)
TOL = 0.015               # snapping tolerance (m)


# ----------------------------------------------------------------------------- helpers
def _r(v, n=3):
    if isinstance(v, (list, tuple)):
        return [_r(x, n) for x in v]
    if isinstance(v, (float, np.floating)):
        return round(float(v), n)
    return v


def _pts(e, fl, dist=0.005):
    """Local polyline points of an entity (OCS-safe via ezdxf.path)."""
    try:
        p = ezpath.make_path(e)
        return [fl.to_local(q.x, q.y) for q in p.flattening(dist)]
    except Exception:
        return []


def _hatch_polys(e, fl):
    out = []
    try:
        for p in ezpath.from_hatch(e):
            pts = [fl.to_local(q.x, q.y) for q in p.flattening(0.005)]
            if len(pts) >= 3:
                out.append(pts)
    except Exception:
        pass
    return out


def _seg(e, fl):
    s, t = e.dxf.start, e.dxf.end
    return (fl.to_local(s.x, s.y), fl.to_local(t.x, t.y))


def _segments_of(e, fl):
    """LINE / LWPOLYLINE / ARC -> list of local 2-point segments."""
    t = e.dxftype()
    if t == "LINE":
        return [_seg(e, fl)]
    if t in ("LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE"):
        pts = _pts(e, fl, 0.01)
        return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    return []


def _ang(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180.0


def _axis_kind(a, b, tol=1.0):
    g = _ang(a, b)
    if g < tol or g > 180 - tol:
        return "h"
    if abs(g - 90) < tol:
        return "v"
    return "d"


def _clean_poly(pts):
    P = Polygon(pts)
    if not P.is_valid:
        P = P.buffer(0)
    if P.geom_type == "MultiPolygon":
        P = max(P.geoms, key=lambda g: g.area)
    return P.simplify(0.004)


def _is_rect(P, tol=0.03):
    mrr = P.minimum_rotated_rectangle
    return abs(mrr.area - P.area) <= tol * max(P.area, 1e-6) + 0.002


def sheet_inserts(fl, layers):
    """INSERTs whose insertion point is OFF the sheet but whose geometry lies on it
    (axis bubbles, 'tr', title blocks...).  floor_entities() misses these."""
    out = []
    for e in fl.msp.query("INSERT"):
        if e.dxf.layer not in layers:
            continue
        p = e.dxf.insert
        if fl.contains(p.x, p.y, pad=0.5):
            continue
        b = entity_bbox(e)
        if b and fl.contains((b[0] + b[2]) / 2, (b[1] + b[3]) / 2):
            out.append(e)
    return out


def _walk(e, depth=0):
    for v in e.virtual_entities():
        if v.dxftype() == "INSERT" and depth < 3:
            yield from _walk(v, depth + 1)
        else:
            yield v


def _txt(e, doc):
    raw = e.dxf.text if e.dxftype() == "TEXT" else e.plain_text()
    st = e.dxf.get("style", "Standard")
    try:
        ar = is_arabic_style(doc, st)
    except Exception:
        ar = False
    return raw, (decode(raw).strip() if ar else raw.strip())


# ----------------------------------------------------------------------------- floor data
class FloorData:
    """One pass over the floor: entities grouped by layer + W/WIN/X segment arrays."""

    def __init__(self, fl):
        self.fl = fl
        self.doc = fl.doc
        self.by_layer = defaultdict(list)
        for e in floor_entities(fl):
            self.by_layer[e.dxf.layer].append(e)
        self.off_inserts = sheet_inserts(fl, ("X", "W", "Etabs-Slab", "-MASS", "sidewalk", "DIM"))
        self.segs = defaultdict(list)       # layer -> [(p, q)]
        for lay in ("W", "WIN", "X", "x1", "DASH", "ST", "PR", "MASS", "COL", "0"):
            for e in self.by_layer.get(lay, []):
                if e.dxftype() == "INSERT":
                    continue
                self.segs[lay].extend(_segments_of(e, fl))

    def ents(self, layer, types=None):
        L = self.by_layer.get(layer, [])
        if types:
            ts = types.split()
            L = [e for e in L if e.dxftype() in ts]
        return L

    def seg_array(self, layers):
        S = [s for lay in layers for s in self.segs.get(lay, [])]
        if not S:
            return np.zeros((0, 4))
        return np.array([[a[0], a[1], b[0], b[1]] for a, b in S], dtype=float)


def _pt_seg_dist(P, A):
    """distance from point P (2,) to each segment row of A (n,4)."""
    if len(A) == 0:
        return np.zeros(0)
    a = A[:, 0:2]; b = A[:, 2:4]
    ab = b - a
    L2 = (ab ** 2).sum(1)
    L2[L2 == 0] = 1e-12
    t = np.clip(((P - a) * ab).sum(1) / L2, 0, 1)
    proj = a + ab * t[:, None]
    return np.hypot(*(P - proj).T)


# ----------------------------------------------------------------------------- grid
def read_grid(fl, D=None):
    """Axis grid: X lines + bubbles.  Returns dict with x_axes / y_axes (label, coord)."""
    D = D or FloorData(fl)
    doc = fl.doc
    lines = []
    for lay in ("X", "x1"):
        for a, b in D.segs.get(lay, []):
            lines.append((lay, a, b))
    vx, hy, other = {}, {}, []
    for lay, a, b in lines:
        k = _axis_kind(a, b, 0.2)
        if lay == "X" and k == "v":
            vx.setdefault(round((a[0] + b[0]) / 2, 3), []).append((a, b))
        elif lay == "X" and k == "h":
            hy.setdefault(round((a[1] + b[1]) / 2, 3), []).append((a, b))
        else:
            other.append({"layer": lay, "a": _r(a), "b": _r(b), "len": _r(math.dist(a, b))})
    # bubbles: CI circle + TEXT, inserted on X (attached) or W (tags)
    bubbles = []
    for e in D.off_inserts + D.ents("X", "INSERT") + D.ents("W", "INSERT"):
        if e.dxf.layer not in ("X", "W") or re.match(r"^D\d+W\d+$", e.dxf.name) or e.dxf.name in ("LP",):
            continue
        circ, txt = None, None
        try:
            for v in _walk(e):
                if v.dxftype() == "CIRCLE":
                    c = v.ocs().to_wcs(v.dxf.center)
                    circ = (fl.to_local(c.x, c.y), v.dxf.radius)
                elif v.dxftype() == "TEXT":
                    txt = v
        except Exception:
            continue
        if not circ or txt is None:
            continue
        raw, dec = _txt(txt, doc)
        bubbles.append({"layer": e.dxf.layer, "block": e.dxf.name, "label": dec, "raw": raw,
                        "c": circ[0], "r": circ[1]})
    xs = sorted(vx)            # vertical lines (constant x)
    ys = sorted(hy)            # horizontal lines (constant y)
    xspan = (min(min(a[1], b[1]) for v in vx.values() for a, b in v),
             max(max(a[1], b[1]) for v in vx.values() for a, b in v)) if vx else (0, 0)
    yspan = (min(min(a[0], b[0]) for v in hy.values() for a, b in v),
             max(max(a[0], b[0]) for v in hy.values() for a, b in v)) if hy else (0, 0)

    def attached(bb, coord, along, span, vertical):
        # bubble centre on the line's extension, tangent to its end
        c = bb["c"]
        off = abs(c[0] - coord) if vertical else abs(c[1] - coord)
        end = min(abs(c[1] - span[0]), abs(c[1] - span[1])) if vertical else \
            min(abs(c[0] - span[0]), abs(c[0] - span[1]))
        return off < 0.03 and abs(end - bb["r"]) < 0.05

    xlab, ylab = {}, {}
    for bb in bubbles:
        lab = bb["label"]
        isnum = lab.isdigit()
        if not isnum:
            for x in xs:
                if attached(bb, x, None, xspan, True):
                    xlab.setdefault(x, Counter())[lab] += 1
                    bb["axis"] = x
        else:
            for y in ys:
                if attached(bb, y, None, yspan, False):
                    ylab.setdefault(y, Counter())[lab] += 1
                    bb["axis"] = y
    notes = []
    # order-based completion for the displaced W tags
    def complete(coords, labmap, order, descending):
        seq = sorted(coords, reverse=descending)
        known = {c: labmap[c].most_common(1)[0][0] for c in seq if c in labmap}
        out = []
        # index of each known label in the order -> check monotonic
        idx = {c: order.index(l) for c, l in known.items() if l in order}
        pos = 0
        assigned = {}
        for i, c in enumerate(seq):
            if c in idx:
                pos = idx[c]
                assigned[c] = (order[pos], "bubble on X")
            else:
                assigned[c] = None
        # fill gaps by order between known neighbours
        for i, c in enumerate(seq):
            if assigned[c] is None:
                prev = next((seq[j] for j in range(i - 1, -1, -1) if c != seq[j] and seq[j] in idx), None)
                nxt = next((seq[j] for j in range(i + 1, len(seq)) if seq[j] in idx), None)
                if prev is not None:
                    k = idx[prev] + (i - seq.index(prev))
                elif nxt is not None:
                    k = idx[nxt] - (seq.index(nxt) - i)
                else:
                    k = i
                assigned[c] = (order[k] if 0 <= k < len(order) else f"?{i}", "order (no attached bubble)")
        for c in seq:
            out.append({"label": assigned[c][0], "coord": c, "source": assigned[c][1]})
        return out

    num_order = [str(i) for i in range(1, 40)]
    x_axes = complete(xs, xlab, ABJAD, True)
    y_axes = complete(ys, ylab, num_order, False)
    # displaced tags (W layer): offset to their axis
    lab2x = {a["label"]: a["coord"] for a in x_axes}
    lab2y = {a["label"]: a["coord"] for a in y_axes}
    displaced = []
    for bb in bubbles:
        if "axis" in bb:
            continue
        lab = bb["label"]
        if lab in lab2x:
            displaced.append({"label": lab, "layer": bb["layer"], "c": _r(bb["c"]),
                              "axis_coord": lab2x[lab], "offset": _r(bb["c"][0] - lab2x[lab])})
        elif lab in lab2y:
            displaced.append({"label": lab, "layer": bb["layer"], "c": _r(bb["c"]),
                              "axis_coord": lab2y[lab], "offset": _r(bb["c"][1] - lab2y[lab])})
        else:
            displaced.append({"label": lab, "layer": bb["layer"], "c": _r(bb["c"]), "axis_coord": None})
    for a in x_axes:
        if a["source"].startswith("order"):
            offs = sorted({d["offset"] for d in displaced if d["label"] == a["label"] and d.get("offset") is not None})
            a["tag_offsets"] = offs
    for a in y_axes:
        if a["source"].startswith("order"):
            offs = sorted({d["offset"] for d in displaced if d["label"] == a["label"] and d.get("offset") is not None})
            a["tag_offsets"] = offs
    dup = [c for c, v in list(vx.items()) + list(hy.items()) if len(v) > 1]
    if dup:
        notes.append(f"duplicate axis lines at {dup}")
    for a in x_axes + y_axes:
        a["coord"] = _r(a["coord"])
    sp_x = [_r(x_axes[i]["coord"] - x_axes[i + 1]["coord"]) for i in range(len(x_axes) - 1)]
    sp_y = [_r(y_axes[i + 1]["coord"] - y_axes[i]["coord"]) for i in range(len(y_axes) - 1)]
    return {"x_axes": x_axes, "y_axes": y_axes, "x_spacings_east_to_west": sp_x,
            "y_spacings_south_to_north": sp_y,
            "line_extent": {"x_lines_y": _r(list(xspan)), "y_lines_x": _r(list(yspan))},
            "bubbles": [{"label": b["label"], "layer": b["layer"], "c": _r(b["c"]),
                         "attached_to": _r(b.get("axis"))} for b in bubbles],
            "displaced_tags": displaced, "other_lines": other, "notes": notes}


def grid_ref(grid, x, y):
    """'ج+0.30 / 5-0.20' -> nearest x-axis label (+offset) / nearest y-axis label (+offset)."""
    def near(axes, v):
        if not axes:
            return "?"
        a = min(axes, key=lambda a: abs(a["coord"] - v))
        d = v - a["coord"]
        return a["label"] if abs(d) < 0.005 else f"{a['label']}{d:+.2f}"
    return f"{near(grid['x_axes'], x)} / {near(grid['y_axes'], y)}"


def grid_between(grid, x0, x1, y0, y1):
    """Axis labels that an element spans (for citing a range)."""
    xs = [a["label"] for a in grid["x_axes"] if x0 - 0.01 <= a["coord"] <= x1 + 0.01]
    ys = [a["label"] for a in grid["y_axes"] if y0 - 0.01 <= a["coord"] <= y1 + 0.01]
    return xs, ys


# ----------------------------------------------------------------------------- structure
def _collect_struct_polys(fl, D):
    raw = []   # (poly, source)
    for e in D.ents("Etabs-col", "LWPOLYLINE"):
        pts = _pts(e, fl)
        if len(pts) >= 4 and (e.closed or math.dist(pts[0], pts[-1]) < 0.01):
            raw.append((_clean_poly(pts), "Etabs-col polyline"))
    for e in D.ents("Etabs-col", "HATCH"):
        for pts in _hatch_polys(e, fl):
            raw.append((_clean_poly(pts), "Etabs-col hatch"))
    # 'tr' block(s) on Etabs-Slab
    tr_inserts = [e for e in D.off_inserts if e.dxf.layer == "Etabs-Slab"]
    tr_inserts += D.ents("Etabs-Slab", "INSERT")
    seen_tr = set()
    tr_info = {"inserts": [], "duplicates": 0}
    for ins in tr_inserts:
        key = (ins.dxf.name, round(ins.dxf.insert.x, 3), round(ins.dxf.insert.y, 3),
               round(ins.dxf.rotation, 2), round(ins.dxf.xscale, 3))
        tr_info["inserts"].append({"block": ins.dxf.name, "handle": ins.dxf.handle})
        if key in seen_tr:
            tr_info["duplicates"] += 1
            continue
        seen_tr.add(key)
        for v in ins.virtual_entities():
            t = v.dxftype()
            if t == "HATCH":
                for pts in _hatch_polys(v, fl):
                    P = _clean_poly(pts)
                    if P.area > 0.02:
                        raw.append((P, f"block '{ins.dxf.name}' ({v.dxf.layer} hatch)"))
            elif t == "LWPOLYLINE":
                pts = _pts(v, fl)
                if len(pts) >= 4 and math.dist(pts[0], pts[-1]) < 0.01:
                    P = _clean_poly(pts)
                    if P.area > 0.02:
                        raw.append((P, f"block '{ins.dxf.name}' ({v.dxf.layer} polyline)"))
    # COL: open 5-point squares + diagonals
    for e in D.ents("COL", "LWPOLYLINE"):
        pts = _pts(e, fl)
        if len(pts) >= 4 and math.dist(pts[0], pts[-1]) < 0.01:
            raw.append((_clean_poly(pts), "COL polyline (X-box)"))
    # de-duplicate
    elems = []
    for P, src in raw:
        for el in elems:
            Q = el["poly"]
            if P.symmetric_difference(Q).area < 0.01 * max(P.area, Q.area) + 0.003:
                el["sources"].append(src)
                break
        else:
            elems.append({"poly": P, "sources": [src]})
    return elems, tr_info


def _ray_hits(Q, u, A):
    """distance along ray(s) Q + t*u (t>0) to the first crossing of segments A (n,4).
    Q: (m,2) points.  Returns (m,) distances (inf if none) and (m,) index of hit segment."""
    if len(A) == 0:
        return np.full(len(Q), np.inf), np.full(len(Q), -1)
    a = A[:, 0:2]; d = A[:, 2:4] - a                     # (n,2)
    den = u[0] * d[:, 1] - u[1] * d[:, 0]                # cross(u, d)  (n,)
    ok = np.abs(den) > 1e-9
    w = a[None, :, :] - Q[:, None, :]                    # (m,n,2)
    t = (w[..., 0] * d[:, 1] - w[..., 1] * d[:, 0]) / np.where(ok, den, 1)[None, :]
    s = (w[..., 0] * u[1] - w[..., 1] * u[0]) / np.where(ok, den, 1)[None, :]
    good = ok[None, :] & (t > 1e-6) & (s >= -1e-6) & (s <= 1 + 1e-6)
    t = np.where(good, t, np.inf)
    idx = np.argmin(t, axis=1)
    return t[np.arange(len(Q)), idx], idx


def _exposed_faces(P, W, others, step=0.02, off=0.03, tmax=0.66):
    """Sample every face of polygon P every `step` m, 3 cm outside it, and decide if
    that strip of face is free (gets plaster) or covered:
      * 'wall'     - the sample lies between two W face lines that run AWAY from the
                     face (both crossed within tmax along the face direction, both
                     starting at the face) = a wall abutting / continuing the element;
      * 'concrete' - inside another structural element / shaft box.
    Returns per-face dicts + totals."""
    coords = list(P.exterior.coords)
    faces = []
    tot_free = tot_wall = tot_conc = 0.0
    Wd = None
    if len(W):
        dv = W[:, 2:4] - W[:, 0:2]
        Wl = np.hypot(dv[:, 0], dv[:, 1]); Wl[Wl == 0] = 1e-9
        Wd = dv / Wl[:, None]
    for i in range(len(coords) - 1):
        a = np.array(coords[i]); b = np.array(coords[i + 1])
        L = float(np.hypot(*(b - a)))
        if L < 0.01:
            continue
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        mid = (a + b) / 2
        if P.contains(Point(*(mid + n * 0.01))):
            n = -n
        k = max(1, int(round(L / step)))
        ss = (np.arange(k) + 0.5) * (L / k)
        Q = a[None, :] + ss[:, None] * u[None, :] + n[None, :] * off
        state = np.array(["free"] * k, dtype=object)
        # concrete / shaft neighbours
        for O in others:
            if O.distance(Point(*(mid + n * off))) > L:
                continue
            for j in range(k):
                if state[j] == "free" and O.contains(Point(*Q[j])):
                    state[j] = "concrete"
        if Wd is not None:
            # candidate W lines: parallel to n (run away from the face), starting near the face
            par = np.abs(Wd @ u) < 0.1
            noff = np.stack([(W[:, 0:2] - a) @ n, (W[:, 2:4] - a) @ n], 1)
            near = noff.min(1) <= off + 0.03
            cand = W[par & near]
            if len(cand):
                t1, _ = _ray_hits(Q, u, cand)
                t2, _ = _ray_hits(Q, -u, cand)
                wall = (t1 + t2 <= tmax) & (state == "free")
                state[wall] = "wall"
        seg = L / k
        free = float((state == "free").sum() * seg)
        wl = float((state == "wall").sum() * seg)
        cc = float((state == "concrete").sum() * seg)
        # contiguous wall runs -> abutting wall thicknesses
        runs, cur = [], 0
        for st in list(state) + ["end"]:
            if st == "wall":
                cur += 1
            elif cur:
                runs.append(_r(cur * seg, 2)); cur = 0
        tot_free += free; tot_wall += wl; tot_conc += cc
        faces.append({"a": _r(list(a)), "b": _r(list(b)), "len": _r(L), "free": _r(free, 2),
                      "wall_runs": runs, "concrete_or_shaft": _r(cc, 2)})
    return faces, tot_free, tot_wall, tot_conc


def _flush_on_W(P, W, tol=TOL):
    """length of P's outline that also has a W line lying on it."""
    tot = 0.0
    coords = list(P.exterior.coords)
    for i in range(len(coords) - 1):
        a = np.array(coords[i]); b = np.array(coords[i + 1])
        L = float(np.hypot(*(b - a)))
        if L < 1e-6 or not len(W):
            continue
        u = (b - a) / L; n = np.array([-u[1], u[0]])
        dv = W[:, 2:4] - W[:, 0:2]
        Wl = np.hypot(dv[:, 0], dv[:, 1]); Wl[Wl == 0] = 1e-9
        col = (np.abs((dv / Wl[:, None]) @ n) < 0.02) & (np.abs((W[:, 0:2] - a) @ n) < tol)
        iv = []
        for r in W[col]:
            s0, s1 = sorted((float((r[0:2] - a) @ u), float((r[2:4] - a) @ u)))
            s0, s1 = max(s0, 0), min(s1, L)
            if s1 > s0:
                iv.append((s0, s1))
        iv.sort()
        cur = None
        for s0, s1 in iv:
            if cur and s0 <= cur[1]:
                cur[1] = max(cur[1], s1)
            else:
                if cur:
                    tot += cur[1] - cur[0]
                cur = [s0, s1]
        if cur:
            tot += cur[1] - cur[0]
    return tot


def analyze_structure(fl, D, grid, shaft_polys=()):
    elems, tr_info = _collect_struct_polys(fl, D)
    W = D.seg_array(["W"])
    out = []
    for el in elems:
        P = el["poly"]
        x0, y0, x1, y1 = P.bounds
        rect = _is_rect(P)
        w, h = x1 - x0, y1 - y0
        srcs = el["sources"]
        if any(s.startswith("COL") for s in srcs):
            kind = "column_xbox"
        elif not rect:
            kind = "core"
        else:
            sh, lo = min(w, h), max(w, h)
            kind = "shear_wall" if lo / max(sh, 1e-6) > WALL_RATIO else "column"
        others = [o["poly"] for o in elems if o is not el] + list(shaft_polys)
        faces, free, t_wall, t_conc = _exposed_faces(P, W, others)
        flush = _flush_on_W(P, W)
        per = P.length
        inner = P.buffer(-0.02)
        w_inside = 0.0
        if not inner.is_empty:
            for row in W:
                ls = LineString([tuple(row[0:2]), tuple(row[2:4])])
                if ls.intersects(inner):
                    w_inside += ls.intersection(inner).length
        c = P.centroid
        xs_, ys_ = grid_between(grid, x0, x1, y0, y1)
        rec = {
            "kind": kind, "sources": sorted(set(srcs)),
            "in_model_space": any(s.startswith("Etabs-col") or s.startswith("COL") for s in srcs),
            "only_in_tr_block": all(s.startswith("block") for s in srcs),
            "hatch_only": all(s == "Etabs-col hatch" for s in srcs),
            "bbox": _r([x0, y0, x1, y1]), "centroid": _r([c.x, c.y]),
            "size": _r([w, h]) if rect else None,
            "size_txt": (f"{w:.2f} x {h:.2f}" if rect else f"C-core {w:.2f} x {h:.2f}"),
            "area": _r(P.area), "perimeter": _r(per),
            "covered_by_walls": _r(t_wall, 2), "covered_by_concrete_or_shaft": _r(t_conc, 2),
            "exposed_perimeter": _r(free, 2),
            "outline_on_W": _r(flush / per if per else 0, 2),
            "w_inside_len": _r(w_inside),
            "grid_ref": grid_ref(grid, c.x, c.y),
            "spans_axes": {"x": xs_, "y": ys_},
            "faces": faces,
            "outline": _r([list(p) for p in P.exterior.coords]),
        }
        if kind == "core":
            # wall thickness of the C core = min distance between parallel faces
            rec["wall_thickness"] = _r(min(0.3, _core_thickness(P)))
        notes = []
        if rec["only_in_tr_block"]:
            notes.append("only in the ETABS block 'tr' (not in model-space Etabs-col)")
            if w_inside > 0.05:
                notes.append(f"W lines run through it ({w_inside:.2f} m)")
            if flush / per < 0.15 and t_wall < 0.05 and w_inside < 0.05:
                notes.append("no W outline around it -> free-standing in the room on the architectural plan?")
        if rec["hatch_only"]:
            notes.append("drawn only as an Etabs-col HATCH (no polyline); outline drawn on W")
        if rec["outline_on_W"] >= 0.5 and kind != "column_xbox":
            notes.append(f"{rec['outline_on_W']:.0%} of its outline is ALSO drawn on W -> do not count as masonry")
        rec["notes"] = notes
        out.append(rec)
    out.sort(key=lambda r: (round(-r["centroid"][1], 1), round(r["centroid"][0], 1)))
    pre = {"column": "C", "shear_wall": "SW", "core": "CORE", "column_xbox": "CX"}
    cnt = Counter()
    for r in out:
        cnt[r["kind"]] += 1
        r["id"] = f"{pre[r['kind']]}{cnt[r['kind']]:02d}"
    return out, tr_info


def _core_thickness(P):
    coords = list(P.exterior.coords)
    best = 9.0
    for i in range(len(coords) - 1):
        a, b = np.array(coords[i]), np.array(coords[i + 1])
        for j in range(len(coords) - 1):
            if j == i:
                continue
            c, d = np.array(coords[j]), np.array(coords[j + 1])
            u1 = (b - a) / (np.hypot(*(b - a)) or 1)
            u2 = (d - c) / (np.hypot(*(d - c)) or 1)
            if abs(abs(float(np.dot(u1, u2))) - 1) > 1e-3:
                continue
            n = np.array([-u1[1], u1[0]])
            dist = abs(float(np.dot(c - a, n)))
            if dist < 0.05:
                continue
            # overlapping along u1?
            s = sorted((float(np.dot(c - a, u1)), float(np.dot(d - a, u1))))
            L = float(np.hypot(*(b - a)))
            if min(s[1], L) - max(s[0], 0) > 0.05:
                # the strip between them must be inside the polygon
                mid = a + u1 * ((max(s[0], 0) + min(s[1], L)) / 2) + n * (np.dot(c - a, n) / 2)
                if P.contains(Point(*mid)):
                    best = min(best, dist)
    return best


# ----------------------------------------------------------------------------- shafts
def analyze_shafts(fl, D, grid):
    boxes = []
    for e in D.ents("try", "LWPOLYLINE"):
        pts = _pts(e, fl)
        if len(pts) >= 4:
            boxes.append((_clean_poly(pts), "try polyline"))
    hatched = []
    for e in D.ents("try", "HATCH"):
        for pts in _hatch_polys(e, fl):
            hatched.append(_clean_poly(pts))
    dash = D.segs.get("DASH", [])
    diag = [(a, b) for a, b in dash if _axis_kind(a, b, 2.0) == "d"]
    # DASH-only X boxes: diagonals grouped by (approximately) the same bbox
    def bb(s):
        (a, b) = s
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
    groups = []
    for s_ in diag:
        k = bb(s_)
        for g in groups:
            if all(abs(k[i] - g["bb"][i]) < 0.06 for i in range(4)):
                g["segs"].append(s_)
                g["bb"] = (min(g["bb"][0], k[0]), min(g["bb"][1], k[1]), max(g["bb"][2], k[2]), max(g["bb"][3], k[3]))
                break
        else:
            groups.append({"bb": k, "segs": [s_]})

    def iou(A, B):
        u = A.union(B).area
        return A.intersection(B).area / u if u else 0
    out = []
    for P, src in boxes:
        dup = next((o for o in out if iou(P, o["_P"]) > 0.85), None)
        if dup:
            dup["duplicates"] += 1
            continue
        x0, y0, x1, y1 = P.bounds
        n_diag = sum(1 for s_ in diag if P.buffer(0.03).contains(LineString(s_)))
        is_hatched = any(iou(P, H) > 0.85 for H in hatched)
        kind = "post_at_curtain_wall (hatched)" if is_hatched else ("shaft (X)" if n_diag >= 2 else
                                                                    ("shaft? (1 diagonal)" if n_diag == 1 else "box (no X)"))
        out.append({"_P": P, "kind": kind, "source": src, "duplicates": 0, "bbox": _r([x0, y0, x1, y1]),
                    "size_txt": f"{x1 - x0:.2f} x {y1 - y0:.2f}", "area": _r(P.area), "perimeter": _r(P.length),
                    "dash_diagonals": n_diag, "hatched": is_hatched,
                    "grid_ref": grid_ref(grid, (x0 + x1) / 2, (y0 + y1) / 2)})
    # nested try boxes: an outer box around a shaft = enclosure outline (not a second shaft)
    for o in out:
        inner = [q for q in out if q is not o and o["_P"].buffer(0.01).contains(q["_P"])]
        if inner and o["kind"].startswith("shaft"):
            o["kind"] = "shaft enclosure (box around " + ", ".join(q["size_txt"] for q in inner) + ")"
    # DASH X boxes not covered by a try box
    for g in groups:
        k = g["bb"]
        Bx = box(*k)
        if any(Bx.intersection(o["_P"]).area > 0.5 * Bx.area for o in out):
            continue
        n = len(g["segs"])
        out.append({"_P": Bx, "kind": "shaft (X, DASH only)" if n >= 2 else "shaft? (1 DASH diagonal, no try box)",
                    "source": "DASH diagonals", "duplicates": 0, "bbox": _r(list(k)),
                    "size_txt": f"{k[2] - k[0]:.2f} x {k[3] - k[1]:.2f}", "area": _r(Bx.area),
                    "perimeter": _r(Bx.length), "dash_diagonals": n, "hatched": False,
                    "grid_ref": grid_ref(grid, (k[0] + k[2]) / 2, (k[1] + k[3]) / 2)})
    out.sort(key=lambda r: (round(-r["bbox"][1], 1), r["bbox"][0]))
    for i, r in enumerate(out, 1):
        r["id"] = f"SH{i:02d}"
    return out


# ----------------------------------------------------------------------------- stairs & lifts
def _cluster_segs(segs, gap=0.6):
    """cluster segments whose bboxes are within gap."""
    items = [list(s) for s in segs]
    bbs = [(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for a, b in items]
    parent = list(range(len(items)))

    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = bbs[i], bbs[j]
            if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                parent[f(i)] = f(j)
    cl = defaultdict(list)
    for i in range(len(items)):
        cl[f(i)].append(i)
    return [[items[i] for i in v] for v in cl.values()]


def _flights(segs, min_len=0.6):
    """group parallel tread lines (same length, regular spacing) into flights."""
    tr = [s for s in segs if math.dist(*s) >= min_len]
    fl_ = []
    for orient in ("v", "h"):
        L = [s for s in tr if _axis_kind(*s, 1.0) == orient]
        # key = extent along the tread direction
        groups = defaultdict(list)
        for a, b in L:
            if orient == "v":
                k = (round(min(a[1], b[1]), 2), round(max(a[1], b[1]), 2)); pos = (a[0] + b[0]) / 2
            else:
                k = (round(min(a[0], b[0]), 2), round(max(a[0], b[0]), 2)); pos = (a[1] + b[1]) / 2
            groups[k].append(pos)
        for k, poss in groups.items():
            poss = sorted(poss)
            if len(poss) < 2:
                continue
            sp = np.diff(poss)
            fl_.append({"orientation": "treads N-S (walk E-W)" if orient == "v" else "treads E-W (walk N-S)",
                        "tread_lines": len(poss), "width": _r(k[1] - k[0]),
                        "going_median": _r(float(np.median(sp))) if len(sp) else None,
                        "from": _r(poss[0]), "to": _r(poss[-1]), "extent": _r(list(k))})
    return fl_


def analyze_stairs(fl, D, grid):
    st = D.segs.get("ST", [])
    out = []
    for cl in _cluster_segs(st, 0.6):
        xs = [p[0] for s in cl for p in s]; ys = [p[1] for s in cl for p in s]
        if len(cl) < 6:
            continue
        bb = [min(xs), min(ys), max(xs), max(ys)]
        B = box(*bb).buffer(0.3)
        flights = _flights(cl)
        dash_in = [s for s in D.segs.get("DASH", []) if B.contains(LineString(s)) and _axis_kind(*s) != "d"]
        dash_fl = _flights(dash_in)
        eye = []
        for e in D.ents("MASS", "LWPOLYLINE"):
            pts = _pts(e, fl)
            if pts and all(B.contains(Point(p)) for p in pts) and e.closed:
                P = Polygon(pts)
                eye.append({"bbox": _r(list(P.bounds)), "size_txt": f"{P.bounds[2] - P.bounds[0]:.2f} x {P.bounds[3] - P.bounds[1]:.2f}"})
        mass_lines = [s for s in D.segs.get("MASS", []) if B.contains(LineString(s))]
        if mass_lines:
            mx = [p[0] for s in mass_lines for p in s]; my = [p[1] for s in mass_lines for p in s]
            eye.append({"bbox": _r([min(mx), min(my), max(mx), max(my)]), "from": "MASS lines"})
        arrows = [e for e in D.ents("PR1", "INSERT") if B.contains(Point(fl.to_local(e.dxf.insert.x, e.dxf.insert.y)))]
        tags = [t for t in _texts(fl, D, ("TEXT-D",)) if B.buffer(0.6).contains(Point(t["local"])) and re.match(r"^\+\s*0+\.0+$", t["text"])]
        lps = [e for e in D.ents("W", "INSERT") if e.dxf.name == "LP" and B.buffer(0.6).contains(Point(fl.to_local(e.dxf.insert.x, e.dxf.insert.y)))]
        rails = [s for s in D.segs.get("PR", []) if B.contains(LineString(s)) and math.dist(*s) > 1.0]
        out.append({"bbox": _r(bb), "size_txt": f"{bb[2] - bb[0]:.2f} x {bb[3] - bb[1]:.2f}",
                    "grid_ref": grid_ref(grid, (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2),
                    "st_lines": len(cl), "flights_ST": flights, "flights_DASH_above_cut": dash_fl,
                    "eye": eye, "arrows_PR1": len(arrows), "handrail_lines_PR": len(rails),
                    "blank_level_tags": [{"text": t["text"], "at": _r(list(t["local"]))} for t in tags],
                    "LP_level_symbols": len(lps)})
    out.sort(key=lambda r: -r["bbox"][1])
    for i, r in enumerate(out, 1):
        r["id"] = f"ST{i}"
    return out


def analyze_lifts(fl, D, grid, elements):
    cars = []
    pr = D.ents("PR", "LWPOLYLINE")
    diag = [s for s in D.segs.get("PR", []) if _axis_kind(*s, 2.0) == "d"]
    for e in pr:
        pts = _pts(e, fl)
        if not (e.closed and len(pts) >= 4):
            continue
        P = Polygon(pts)
        nd = sum(1 for s in diag if P.buffer(0.05).contains(LineString(s)))
        if nd >= 2:
            x0, y0, x1, y1 = P.bounds
            cars.append({"bbox": _r([x0, y0, x1, y1]), "size_txt": f"{x1 - x0:.2f} x {y1 - y0:.2f}",
                         "grid_ref": grid_ref(grid, (x0 + x1) / 2, (y0 + y1) / 2)})
    cars.sort(key=lambda c: c["bbox"][1])
    cores = [el for el in elements if el["kind"] == "core"]
    doors = []
    for core in cores:
        x0, y0, x1, y1 = core["bbox"]
        B = box(x0 - 0.4, y0, x1, y1)
        for a, b in D.segs.get("MASS", []):
            if B.contains(LineString([a, b])) and _axis_kind(a, b) in ("v", "h"):
                doors.append(_r([list(a), list(b)]))
    # unique door lines
    uniq = []
    for d in doors:
        if not any(math.dist(d[0], u[0]) < 0.01 and math.dist(d[1], u[1]) < 0.01 for u in uniq):
            uniq.append(d)
    hat = []
    for e in D.ents("HAT", "HATCH"):
        for pts in _hatch_polys(e, fl):
            P = Polygon(pts)
            hat.append({"bbox": _r(list(P.bounds)), "pattern": e.dxf.pattern_name})
    res = {"cars": cars, "count": len(cars), "core_ids": [c["id"] for c in cores],
           "door_lines_MASS": uniq, "HAT_hatches_in_shafts": hat}
    for core in cores:
        res["core_outline"] = core["outline"]
        res["core_size"] = core["size_txt"]
        res["core_wall_thickness"] = core.get("wall_thickness")
    return res


# ----------------------------------------------------------------------------- texts
_TXT_CACHE = {}


def _texts(fl, D, layers):
    out = []
    for lay in layers:
        for e in D.ents(lay, "TEXT MTEXT"):
            raw, dec = _txt(e, fl.doc)
            p = e.dxf.insert
            out.append({"layer": lay, "raw": raw, "text": dec, "local": fl.to_local(p.x, p.y),
                        "height": e.dxf.get("height", 0.0) if e.dxftype() == "TEXT" else e.dxf.get("char_height", 0.0)})
    return out


# ----------------------------------------------------------------------------- DASH
def classify_dash(fl, D, openings_res, stairs, lifts, shafts, elements):
    dash = []
    for e in D.ents("DASH"):
        for s in _segments_of(e, fl):
            dash.append((s, e.dxftype()))
    door_rects = []
    if openings_res:
        for d in openings_res.get("doors", []):
            if d.get("jamb_a") and d.get("jamb_b"):
                pts = d["jamb_a"] + d["jamb_b"]
                door_rects.append((Polygon(pts).convex_hull.buffer(0.03), d["id"], d.get("width")))
        win_lines = []
        for w in openings_res.get("windows", []):
            if w.get("shape") == "straight" and w.get("ends"):
                win_lines.append((LineString(w["ends"]), w["id"], w.get("width")))
        open_lines = []
        for o in openings_res.get("openings", []):
            if o.get("ends"):
                open_lines.append((LineString(o["ends"]), o["id"], o.get("width")))
    else:
        win_lines, open_lines = [], []
    stair_boxes = [box(*s["bbox"]).buffer(0.1) for s in stairs]
    core_boxes = [box(*el["bbox"]) for el in elements if el["kind"] == "core"]
    shaft_boxes = [box(*s["bbox"]).buffer(0.03) for s in shafts]
    struct_edges = [Polygon(el["outline"]).buffer(0.02) for el in elements]
    res = []
    for (a, b), typ in dash:
        ls = LineString([a, b])
        L = ls.length
        k = _axis_kind(a, b, 2.0)
        cls, ref = "other", None
        if k == "d" and any(B.contains(ls) for B in shaft_boxes):
            cls = "shaft_cross"
        elif k == "d":
            cls = "diagonal_other"
        elif any(B.contains(ls) for B in shaft_boxes):
            cls = "shaft_outline"
        elif any(B.contains(ls) for B in struct_edges):
            cls = "on_structure_face"
        elif any(B.contains(ls) for B in stair_boxes):
            cls = "stair_flight_above_cut"
        elif any(B.buffer(0.05).contains(ls) for B in core_boxes):
            cls = "lift_core_divider"
        else:
            for R, did, wd in door_rects:
                if R.contains(ls):
                    cls, ref = "door_head", did
                    break
            if cls == "other":
                for W, wid, wd in win_lines + open_lines:
                    if W.buffer(0.42).contains(ls) and L > 0.5 * (wd or 0):
                        cls, ref = ("window_head" if "-W" in wid else "opening_head"), wid
                        break
        res.append({"a": _r(list(a)), "b": _r(list(b)), "len": _r(L), "class": cls, "ref": ref, "entity": typ})
    summ = defaultdict(lambda: {"n": 0, "len": 0.0})
    for r in res:
        summ[r["class"]]["n"] += 1
        summ[r["class"]]["len"] += r["len"]
    summ = {k: {"n": v["n"], "len": _r(v["len"], 2)} for k, v in sorted(summ.items())}
    return {"lines": res, "summary": summ}


# ----------------------------------------------------------------------------- DIMs
def read_dims(fl, D, grid, openings_res=None):
    feats = {lay: D.seg_array([lay]) for lay in ("W", "WIN", "X", "Etabs-col", "MASS", "COL")}
    # Etabs-col edges (polylines) are not in D.segs -> add
    ec = []
    for e in D.ents("Etabs-col", "LWPOLYLINE"):
        pts = _pts(e, fl)
        ec += [[pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]] for i in range(len(pts) - 1)]
    for e in D.ents("Etabs-col", "HATCH"):
        for pts in _hatch_polys(e, fl):
            ec += [[pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]] for i in range(len(pts) - 1)]
    feats["Etabs-col"] = np.array(ec) if ec else np.zeros((0, 4))
    win_ends = []
    if openings_res:
        for w in openings_res.get("windows", []):
            for p in (w.get("ends") or []):
                win_ends.append(p)
        for d in openings_res.get("doors", []):
            for j in (d.get("jamb_a"), d.get("jamb_b")):
                if j:
                    win_ends.append(j[0]); win_ends.append(j[1])
    win_ends = np.array(win_ends) if win_ends else np.zeros((0, 2))
    xs = [a["coord"] for a in grid["x_axes"]]
    ys = [a["coord"] for a in grid["y_axes"]]
    tagx = [d["c"][0] for d in grid["displaced_tags"] if d.get("offset") is not None and not d["label"].isdigit()]
    tagy = [d["c"][1] for d in grid["displaced_tags"] if d.get("offset") is not None and d["label"].isdigit()]
    # building footprint (WIN + Etabs-col + ST, like Floor.plan_bbox) for inside/outside tests
    fp = np.vstack([A for A in (feats["WIN"], feats["Etabs-col"], D.seg_array(["ST"])) if len(A)])
    bx0, by0 = fp[:, [0, 2]].min(), fp[:, [1, 3]].min()
    bx1, by1 = fp[:, [0, 2]].max(), fp[:, [1, 3]].max()
    # 'old' grid positions = displaced W tags + X lines shifted by the common tag offset
    offx = Counter(round(d["offset"], 2) for d in grid["displaced_tags"] if d.get("offset") is not None and not d["label"].isdigit())
    offy = Counter(round(d["offset"], 2) for d in grid["displaced_tags"] if d.get("offset") is not None and d["label"].isdigit())
    ox = offx.most_common(1)[0][0] if offx else 0.0
    oy = offy.most_common(1)[0][0] if offy else 0.0
    tagx = tagx + [x + ox for x in xs]
    tagy = tagy + [y + oy for y in ys]
    dims = []
    for e in D.ents("DIM", "DIMENSION"):
        dt = e.dimtype
        p2 = e.dxf.get("defpoint2"); p3 = e.dxf.get("defpoint3"); p1 = e.dxf.defpoint
        if p2 is None or p3 is None:
            continue
        a = fl.to_local(p2.x, p2.y); b = fl.to_local(p3.x, p3.y); dl = fl.to_local(p1.x, p1.y)
        act = e.dxf.get("actual_measurement")
        disp = None
        try:
            blk = e.get_geometry_block()
            if blk is not None:
                for x in blk:
                    if x.dxftype() in ("MTEXT", "TEXT"):
                        disp = (x.plain_text() if x.dxftype() == "MTEXT" else x.dxf.text).strip()
                        break
        except Exception:
            pass
        ovr = e.dxf.get("text", "")
        if ovr and ovr != "<>":
            disp = ovr
        if dt == 0:
            ang = (e.dxf.get("angle", 0.0) - fl.angle) % 180.0
            u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        else:
            d = (b[0] - a[0], b[1] - a[1]); L = math.hypot(*d) or 1
            u = (d[0] / L, d[1] / L)
            ang = math.degrees(math.atan2(u[1], u[0])) % 180.0
        meas = abs((b[0] - a[0]) * u[0] + (b[1] - a[1]) * u[1])
        try:
            dv = float(disp) if disp else None
        except ValueError:
            dv = None
        direction = "x" if (ang < 1 or ang > 179) else ("y" if abs(ang - 90) < 1 else "skew")

        def snaps(p):
            P = np.array(p)
            out = []
            for lay, A in feats.items():
                if len(A) and _pt_seg_dist(P, A).min() < 0.012:
                    out.append(lay)
            if len(win_ends) and np.hypot(*(win_ends - P).T).min() < 0.02:
                out.append("opening_end")
            if direction == "y" and (any(abs(p[1] - y) < 0.012 for y in ys)):
                out.append("axis")
            if direction == "x" and (any(abs(p[0] - x) < 0.012 for x in xs)):
                out.append("axis")
            if direction == "y" and any(abs(p[1] - y) < 0.012 for y in tagy):
                out.append("axis_tag")
            if direction == "x" and any(abs(p[0] - x) < 0.012 for x in tagx):
                out.append("axis_tag")
            return out
        sa, sb = snaps(a), snaps(b)
        outside = not (bx0 - 0.3 <= dl[0] <= bx1 + 0.3 and by0 - 0.3 <= dl[1] <= by1 + 0.3)
        far = (dl[0] < bx0 - 5 or dl[0] > bx1 + 5 or dl[1] < by0 - 5 or dl[1] > by1 + 5)
        v = act if act is not None else meas
        on_geom = lambda s_: bool({"W", "WIN", "Etabs-col", "opening_end"} & set(s_))
        on_axis = lambda s_: bool({"axis", "axis_tag"} & set(s_))
        if v > 15:
            cls = "overall"
        elif far and on_axis(sa) and on_axis(sb) and not (on_geom(sa) and on_geom(sb)):
            cls = "axis_chain"
        elif far and not (on_geom(sa) or on_geom(sb)):
            cls = "facade_chain"
        elif "opening_end" in sa and "opening_end" in sb:
            cls = "opening"
        elif not outside and v <= 0.65 and _is_wall_thickness(a, b, u, feats["W"], feats["Etabs-col"], feats["WIN"]):
            cls = "wall_thickness"
        elif outside and v <= 0.65:
            cls = "facade_step"
        elif outside:
            cls = "facade_chain"
        elif sa and sb:
            cls = "interior"
        else:
            cls = "other (end not on any line)"
        dims.append({"handle": e.dxf.handle, "type": "linear" if dt == 0 else ("aligned" if dt == 1 else f"type{dt}"),
                     "text": disp, "value": _r(dv if dv is not None else v), "actual": _r(act, 4) if act is not None else None,
                     "measured_on_points": _r(meas, 4),
                     "p2": _r(list(a)), "p3": _r(list(b)), "dimline": _r(list(dl)), "direction": direction,
                     "angle_local": _r(ang, 1), "snap_p2": sa, "snap_p3": sb, "class": cls,
                     "grid_ref": grid_ref(grid, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2)})
    dims.sort(key=lambda d: (d["class"], d["dimline"][1], d["dimline"][0]))
    for i, d in enumerate(dims, 1):
        d["id"] = f"DIM{i:03d}"
    # axis chains vs the X-line grid: which labels does each chain end sit on?
    tag_pos_x = {d["label"]: d["c"][0] for d in grid["displaced_tags"] if d.get("offset") is not None and not d["label"].isdigit()}
    tag_pos_y = {d["label"]: d["c"][1] for d in grid["displaced_tags"] if d.get("offset") is not None and d["label"].isdigit()}

    def lab_of(v, axes, tagpos, off):
        best = None
        for a in axes:
            for kind, pos in (("X line", a["coord"]), ("tag", tagpos.get(a["label"])), ("X line + tag offset", a["coord"] + off)):
                if pos is not None and abs(v - pos) < 0.012:
                    if best is None or kind == "tag":
                        best = (a["label"], kind)
        return best
    axis_check = []
    for d in dims:
        if not d["class"].startswith("axis_chain"):
            continue
        if d["direction"] == "x":
            la = lab_of(d["p2"][0], grid["x_axes"], tag_pos_x, ox); lb = lab_of(d["p3"][0], grid["x_axes"], tag_pos_x, ox)
            lab2c = {a["label"]: a["coord"] for a in grid["x_axes"]}
        elif d["direction"] == "y":
            la = lab_of(d["p2"][1], grid["y_axes"], tag_pos_y, oy); lb = lab_of(d["p3"][1], grid["y_axes"], tag_pos_y, oy)
            lab2c = {a["label"]: a["coord"] for a in grid["y_axes"]}
        else:
            continue
        rec = {"dim": d["id"], "text": d["text"], "dimline": d["dimline"], "from": la, "to": lb}
        if la and lb:
            sp = abs(lab2c[la[0]] - lab2c[lb[0]])
            rec["x_line_spacing"] = _r(sp)
            rec["matches_X_lines"] = abs(sp - d["value"]) < 0.006
        axis_check.append(rec)
    hist = Counter(d["text"] for d in dims)
    by_class = Counter(d["class"] for d in dims)
    wt = Counter(d["text"] for d in dims if d["class"] == "wall_thickness")
    mism = [d["id"] for d in dims if d["text"] and d["actual"] is not None and
            abs(float(d["text"]) - d["actual"]) > 0.006]
    return {"dims": dims, "n": len(dims), "by_class": dict(by_class),
            "histogram": dict(sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))),
            "wall_thickness_values": dict(sorted(wt.items(), key=lambda kv: (-kv[1], kv[0]))),
            "text_vs_actual_mismatch": mism, "axis_chain_check": axis_check,
            "old_grid_offset": {"x": ox, "y": oy}}


def _is_wall_thickness(a, b, u, W, EC, WIN):
    """Both extension points on face lines perpendicular to u that overlap (a wall)."""
    n = np.array([-u[1], u[0]])
    uu = np.array(u)
    res = []
    for p in (a, b):
        P = np.array(p)
        found = []
        for A in (W, EC):
            if not len(A):
                continue
            d = _pt_seg_dist(P, A)
            for i in np.where(d < 0.012)[0]:
                s, t = A[i, 0:2], A[i, 2:4]
                dv = t - s
                L = np.hypot(*dv)
                if L < 0.03:
                    continue
                if abs(float(np.dot(dv / L, uu))) < 0.05:      # perpendicular to u
                    found.append(sorted((float(np.dot(s, n)), float(np.dot(t, n)))))
        res.append(found)
    if not res[0] or not res[1]:
        return False
    for f0 in res[0]:
        for f1 in res[1]:
            if min(f0[1], f1[1]) - max(f0[0], f1[0]) > 0.04:
                return True
    return False


# ----------------------------------------------------------------------------- annotations
def read_annotations(fl, D, grid):
    doc = fl.doc
    T = _texts(fl, D, ("TEXT-D", "PR", "0", "LOGO-L1", "-A-TEXT"))
    titles = [t["text"] for t in T if t["layer"] == "TEXT-D" and not re.match(r"^\+", t["text"])]
    blanks = [{"text": t["text"], "at": _r(list(t["local"]))} for t in T if t["layer"] == "TEXT-D" and re.match(r"^\+", t["text"])]
    levels = [{"text": t["text"], "at": _r(list(t["local"]))} for t in T if t["layer"] == "PR"]
    notes0 = [t["text"] for t in T if t["layer"] == "0"]
    logo = [t["text"] for t in T if t["layer"] == "LOGO-L1"]
    # off-sheet inserted blocks: sidewalk (area schedule), -MASS (title block)
    area_table, title_block = [], []
    for e in D.off_inserts:
        if e.dxf.layer in ("sidewalk", "-MASS"):
            for v in _walk(e):
                if v.dxftype() in ("TEXT", "MTEXT"):
                    raw, dec = _txt(v, doc)
                    (area_table if e.dxf.layer == "sidewalk" else title_block).append(dec)
    areas = {}
    for s in area_table:
        m = re.match(r"^(.*?)\s*=\s*([\d.]+)", s)
        if m:
            areas[re.sub(r"\s+", " ", m.group(1)).strip()] = float(m.group(2))
    # MASS
    mass = {"stair_eye_rects": 0, "break_lines": 0, "lift_door_lines": 0, "plot_boundary": None, "title_lines": 0}
    for e in D.ents("MASS", "LWPOLYLINE"):
        pts = _pts(e, fl)
        if not pts:
            continue
        P = Polygon(pts) if len(pts) >= 3 else None
        if e.closed and P is not None and P.area > 100:
            x = [p[0] for p in pts]; y = [p[1] for p in pts]
            mass["plot_boundary"] = {"vertices": _r([list(p) for p in pts[:-1] if True]),
                                     "area": _r(P.area, 2), "perimeter": _r(P.length, 2),
                                     "side_lengths": _r([math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)], 2)}
        elif e.closed:
            mass["stair_eye_rects"] += 1
        else:
            mass["break_lines"] += 1
    for a, b in D.segs.get("MASS", []):
        L = math.dist(a, b)
        if a[0] > 30 or a[1] < -5:
            mass["title_lines"] += 1
    hat = {"frame_lines": sum(1 for e in D.ents("HAT", "LINE")),
           "hatches": len(D.ents("HAT", "HATCH"))}
    fur = Counter(e.dxf.name for e in D.ents("FUR", "INSERT"))
    fur_pos = [{"block": e.dxf.name, "at": _r(list(fl.to_local(e.dxf.insert.x, e.dxf.insert.y)), 2)}
               for e in D.ents("FUR", "INSERT")]
    lp = [_r(list(fl.to_local(e.dxf.insert.x, e.dxf.insert.y)), 2) for e in D.ents("W", "INSERT") if e.dxf.name == "LP"]
    pr1 = [{"block": e.dxf.name, "at": _r(list(fl.to_local(e.dxf.insert.x, e.dxf.insert.y)), 2)} for e in D.ents("PR1", "INSERT")]
    return {"titles_TEXT_D": titles, "blank_level_tags_TEXT_D": blanks, "level_marks_PR": levels,
            "notes_layer0": notes0, "logo": logo, "area_schedule_sidewalk": areas,
            "title_block_minus_MASS": title_block, "MASS": mass, "HAT": hat,
            "FUR": {"counts": dict(fur), "items": fur_pos}, "LP_level_symbols": lp, "PR1_stair_arrows": pr1}


# ----------------------------------------------------------------------------- main analysis
def analyze_floor(floor, openings_res="auto"):
    fl = floor if hasattr(floor, "label") else get_floor(int(floor))
    D = FloorData(fl)
    grid = read_grid(fl, D)
    if openings_res == "auto":
        try:
            from openings import analyze_floor as op_analyze
            openings_res = op_analyze(fl.floor_no)
        except Exception as ex:  # pragma: no cover
            print("  (openings.py unavailable:", ex, ")")
            openings_res = None
    shafts = analyze_shafts(fl, D, grid)
    elements, tr_info = analyze_structure(fl, D, grid, [box(*sh["bbox"]) for sh in shafts
                                                         if sh["kind"].startswith("shaft")])
    stairs = analyze_stairs(fl, D, grid)
    lifts = analyze_lifts(fl, D, grid, elements)
    dash = classify_dash(fl, D, openings_res, stairs, lifts, shafts, elements)
    dims = read_dims(fl, D, grid, openings_res)
    ann = read_annotations(fl, D, grid)
    ann["MASS"]["lift_door_lines"] = len(lifts["door_lines_MASS"])
    # openings that coincide with a structural element (e.g. the 0.80 'opening' = tr column)
    op_vs_struct = []
    if openings_res:
        for o in openings_res.get("openings", []):
            if not o.get("ends"):
                continue
            ls = LineString(o["ends"])
            for el in elements:
                P = Polygon(el["outline"])
                if P.buffer(0.03).contains(ls):
                    op_vs_struct.append({"opening": o["id"], "width": o["width"], "element": el["id"],
                                         "element_size": el["size_txt"], "sources": el["sources"]})
    kinds = Counter(el["kind"] for el in elements)
    tot = defaultdict(lambda: {"n": 0, "area": 0.0, "perimeter": 0.0, "exposed_perimeter": 0.0})
    for el in elements:
        grp = el["kind"] + (" (tr block only)" if el["only_in_tr_block"] else "")
        t = tot[grp]
        t["n"] += 1; t["area"] += el["area"]; t["perimeter"] += el["perimeter"]; t["exposed_perimeter"] += el["exposed_perimeter"]
    tot = {k: {kk: _r(vv, 3) for kk, vv in v.items()} for k, v in sorted(tot.items())}
    sh = [s for s in shafts if s["kind"].startswith("shaft") and not s["kind"].startswith("shaft enclosure")]
    res = {
        "floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
        "storey_height": STOREY_HEIGHT, "file": fl.file.name, "sheet_index": fl.sheet_index,
        "frame": "local (diwan_common): rotation -10 deg, origin = min corner of Etabs-col; +y = north",
        "grid": grid,
        "elements": elements,
        "tr_block": tr_info,
        "shafts": [{k: v for k, v in s.items() if k != "_P"} for s in shafts],
        "stairs": stairs, "lifts": lifts, "dash": dash, "dims": dims, "annotations": ann,
        "openings_on_structure": op_vs_struct,
        "summary": {
            "elements_by_kind": dict(kinds),
            "totals_by_kind": tot,
            "plaster_perimeter_all": _r(sum(el["exposed_perimeter"] for el in elements if el["kind"] != "column_xbox"), 2),
            "plaster_perimeter_model_space_only": _r(sum(el["exposed_perimeter"] for el in elements
                                                         if el["kind"] != "column_xbox" and not el["only_in_tr_block"]), 2),
            "shafts": len(sh), "shaft_area": _r(sum(s["area"] for s in sh), 3),
            "stairs": len(stairs), "lift_cars": lifts["count"],
            "x_axes": " ".join(a["label"] for a in grid["x_axes"]),
            "y_axes": " ".join(a["label"] for a in grid["y_axes"]),
            "dims": dims["n"], "dims_by_class": dims["by_class"],
            "dash": dash["summary"],
        },
    }
    return res


# ----------------------------------------------------------------------------- rendering
KIND_COL = {"column": "#2ca02c", "shear_wall": "#1f77b4", "core": "#9467bd", "column_xbox": "#8c564b"}
DASH_COL = {"door_head": "#2ca02c", "window_head": "#17becf", "opening_head": "#ff7f0e",
            "stair_flight_above_cut": "#8c564b", "shaft_cross": "#ff7f0e", "shaft_outline": "#ff7f0e", "lift_core_divider": "#9467bd", "on_structure_face": "#e377c2",
            "other": "#d62728", "diagonal_other": "#d62728"}
DIM_COL = {"axis_chain": "#ff9999", "overall": "#7f7f7f", "wall_thickness": "#d62728", "opening": "#17becf",
           "facade_step": "#bcbd22", "facade_chain": "#1f77b4", "interior": "#2ca02c", "axis_chain?": "#ffbbbb",
           "other (end not on any line)": "#ff00ff"}


def render(res, out_png, mode="structure", zoom=None, dpi=110):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, Rectangle, Circle
    from matplotlib.lines import Line2D
    plt.rcParams["font.family"] = "Tahoma"
    fl = get_floor(res["floor_no"])
    D = FloorData(fl)
    fig, ax = plt.subplots(figsize=(15, 30) if not zoom else (15, 15))
    for a, b in D.segs.get("W", []):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#bbbbbb", lw=0.5, zorder=1)
    for a, b in D.segs.get("WIN", []):
        ax.plot([a[0], b[0]], [a[1], b[1]], color="#a6dfe8", lw=0.5, zorder=1)
    g = res["grid"]
    ylo, yhi = -2.5, 41.5
    xlo, xhi = -1.8, 19.5
    for a in g["x_axes"]:
        ax.plot([a["coord"]] * 2, [ylo + 0.6, yhi - 0.6], color="#ff9999", lw=0.6, ls="-.", zorder=0)
        for yy in (ylo + 0.3, yhi - 0.3):
            ax.add_patch(Circle((a["coord"], yy), 0.3, fc="white", ec="#d62728", lw=0.8, zorder=5))
            ax.text(a["coord"], yy, a["label"], ha="center", va="center", fontsize=8, color="#d62728", zorder=6)
    for a in g["y_axes"]:
        ax.plot([xlo + 0.6, xhi - 0.6], [a["coord"]] * 2, color="#ff9999", lw=0.6, ls="-.", zorder=0)
        for xx in (xlo + 0.3, xhi - 0.3):
            ax.add_patch(Circle((xx, a["coord"]), 0.3, fc="white", ec="#d62728", lw=0.8, zorder=5))
            ax.text(xx, a["coord"], a["label"], ha="center", va="center", fontsize=7, color="#d62728", zorder=6)
    if mode == "structure":
        for el in res["elements"]:
            col = KIND_COL[el["kind"]]
            ls = "--" if el["only_in_tr_block"] else "-"
            ax.add_patch(MPoly(el["outline"], closed=True, fc=col, alpha=0.35 if not el["only_in_tr_block"] else 0.15,
                               ec=col, lw=1.4, ls=ls, zorder=3))
            if el["hatch_only"] or el["only_in_tr_block"]:
                ax.add_patch(MPoly(el["outline"], closed=True, fill=False, ec="magenta", lw=2.2, ls=ls, zorder=4))
            cx, cy = el["centroid"]
            ax.text(cx, cy, f"{el['id']}\n{el['size_txt']}\nP={el['exposed_perimeter']:.2f}",
                    fontsize=5.5, ha="center", va="center", zorder=7, color="black",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=col, lw=0.6, alpha=0.85))
        for s in res["shafts"]:
            x0, y0, x1, y1 = s["bbox"]
            col = "#ff7f0e" if s["kind"].startswith("shaft") else "#7f7f7f"
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=col, alpha=0.3, ec=col, lw=1, zorder=3))
            ax.plot([x0, x1], [y0, y1], color=col, lw=0.6); ax.plot([x0, x1], [y1, y0], color=col, lw=0.6)
            ax.text(x1 + 0.05, y1, s["id"], fontsize=5, color=col, zorder=7)
        for st in res["stairs"]:
            x0, y0, x1, y1 = st["bbox"]
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="#8c564b", lw=1.5, ls=":", zorder=3))
            for a, b in D.segs.get("ST", []):
                if x0 - 0.01 <= a[0] <= x1 + 0.01 and y0 - 0.01 <= a[1] <= y1 + 0.01:
                    ax.plot([a[0], b[0]], [a[1], b[1]], color="#8c564b", lw=0.5, zorder=2)
            fdesc = "; ".join(f"{f['tread_lines']}x{f['going_median']} w={f['width']}" for f in st["flights_ST"])
            ax.text(x0, y1 + 0.1, f"{st['id']} {st['size_txt']}  [{fdesc}]", fontsize=6, color="#8c564b", zorder=7)
        for c in res["lifts"]["cars"]:
            x0, y0, x1, y1 = c["bbox"]
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="#9467bd", lw=1, zorder=3))
            ax.plot([x0, x1], [y0, y1], color="#9467bd", lw=0.6); ax.plot([x0, x1], [y1, y0], color="#9467bd", lw=0.6)
        for d in res["lifts"]["door_lines_MASS"]:
            ax.plot([d[0][0], d[1][0]], [d[0][1], d[1][1]], color="#e377c2", lw=2, zorder=4)
        for ln in res["dash"]["lines"]:
            col = DASH_COL.get(ln["class"], "#d62728")
            ax.plot([ln["a"][0], ln["b"][0]], [ln["a"][1], ln["b"][1]], color=col, lw=1.0 if ln["class"] != "other" else 2.0,
                    ls="--", zorder=2)
        handles = [Line2D([], [], color=c, lw=6, alpha=0.5, label=k) for k, c in KIND_COL.items()]
        handles += [Line2D([], [], color="magenta", lw=2, ls="--", label="only in ETABS block 'tr' / hatch-only")]
        handles += [Line2D([], [], color="#ff7f0e", lw=6, alpha=0.4, label="shaft (try / DASH X)")]
        handles += [Line2D([], [], color=c, lw=1.2, ls="--", label=f"DASH {k}") for k, c in DASH_COL.items() if k != "diagonal_other"]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.005, 1.0), fontsize=8, framealpha=0.9)
        ax.set_title(f"{res['floor']} {res['name_ar']} {res['level']:+.2f} — العناصر الإنشائية والشفتات والسلالم والمحاور "
                     f"(P = المحيط المعرض للمحارة، م)", fontsize=11)
    else:  # dims
        for el in res["elements"]:
            ax.add_patch(MPoly(el["outline"], closed=True, fc="#2ca02c", alpha=0.2, ec="#2ca02c", lw=0.6, zorder=2))
        for d in res["dims"]["dims"]:
            col = DIM_COL.get(d["class"], "#000")
            a, b, dl = d["p2"], d["p3"], d["dimline"]
            ang = math.radians(d["angle_local"])
            u = (math.cos(ang), math.sin(ang))
            # dim line through dl along u, between projections of a and b
            def proj(p):
                t = (p[0] - dl[0]) * u[0] + (p[1] - dl[1]) * u[1]
                return (dl[0] + u[0] * t, dl[1] + u[1] * t)
            pa, pb = proj(a), proj(b)
            ax.plot([pa[0], pb[0]], [pa[1], pb[1]], color=col, lw=0.9, zorder=4)
            ax.plot([a[0], pa[0]], [a[1], pa[1]], color=col, lw=0.3, zorder=3)
            ax.plot([b[0], pb[0]], [b[1], pb[1]], color=col, lw=0.3, zorder=3)
            m = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
            rot = d["angle_local"] if d["angle_local"] <= 90 else d["angle_local"] - 180
            ax.text(m[0], m[1], d["text"] or "", fontsize=4.5, color=col, rotation=rot, ha="center", va="bottom", zorder=6)
        handles = [Line2D([], [], color=c, lw=2, label=k) for k, c in DIM_COL.items()]
        ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.9)
        ax.set_title(f"{res['floor']} — أبعاد المعماري (DIM, WWW) ملونة حسب التصنيف", fontsize=11)
        xlo, xhi, ylo, yhi = -16, 30, -19.5, 50.5
    ax.set_aspect("equal")
    if zoom:
        ax.set_xlim(zoom[0], zoom[2]); ax.set_ylim(zoom[1], zoom[3])
        # texts are not clipped -> drop those outside the window (else bbox_inches='tight'
        # blows the figure up to the whole plan)
        for t_ in list(ax.texts):
            x_, y_ = t_.get_position()
            if not (zoom[0] <= x_ <= zoom[2] and zoom[1] <= y_ <= zoom[3]):
                t_.remove()
    else:
        ax.set_xlim(xlo, xhi); ax.set_ylim(ylo, yhi)
    ax.grid(True, lw=0.2)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_png


def render_dims_hist(all_res, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Tahoma"
    cnt = defaultdict(Counter)
    for r in all_res:
        for d in r["dims"]["dims"]:
            if d["value"] is not None and d["value"] <= 7.0:
                cnt[d["class"]][round(d["value"], 2)] += 1
    vals = sorted({v for c in cnt.values() for v in c})
    fig, ax = plt.subplots(figsize=(18, 6))
    bottom = np.zeros(len(vals))
    for k, c in cnt.items():
        h = np.array([c.get(v, 0) for v in vals])
        ax.bar(range(len(vals)), h, bottom=bottom, color=DIM_COL.get(k, "#000"), label=k)
        bottom += h
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels([f"{v:.2f}" for v in vals], rotation=90, fontsize=6)
    ax.set_ylabel("عدد الأبعاد (كل الأدوار)")
    ax.set_title("هيستوجرام قيم أبعاد المعماري حتى 7 م (كل الأدوار F02–F08) ملون حسب التصنيف")
    ax.legend(fontsize=8)
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)


# ----------------------------------------------------------------------------- CLI
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def harmonize_shaft_ids(allres):
    """Give the same SHnn id to the same shaft box on every floor (per-floor numbering
    shifts when a floor has one box more/less, e.g. the F05-F08 enclosure 0.64x0.84).
    Canonical list = union of all floors' boxes (bbox IoU > 0.8), sorted like
    analyze_shafts (north -> south, then west -> east).  Adds shaft['floors'] (floors
    on which that box exists).  Returns the canonical list."""
    def iou(a, b):
        ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
        inter = ix * iy
        ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return inter / ua if ua > 0 else 0.0
    canon = []
    for r in allres:
        for s in r["shafts"]:
            c = next((c for c in canon if iou(c["bbox"], s["bbox"]) > 0.8), None)
            if c is None:
                c = {"bbox": s["bbox"], "kind": s["kind"], "size_txt": s["size_txt"], "area": s["area"],
                     "perimeter": s["perimeter"], "dash_diagonals": s["dash_diagonals"],
                     "grid_ref": s["grid_ref"], "floors": [], "kinds": Counter()}
                canon.append(c)
            c["floors"].append(r["floor"])
            c["kinds"][s["kind"]] += 1
            s["_canon"] = c
    canon.sort(key=lambda c: (round(-c["bbox"][1], 1), c["bbox"][0]))
    for i, c in enumerate(canon, 1):
        c["id"] = f"SH{i:02d}"
        c["kind"] = c["kinds"].most_common(1)[0][0]
        c["kinds"] = dict(c["kinds"])
    for r in allres:
        for s in r["shafts"]:
            c = s.pop("_canon")
            s["id"] = c["id"]
            s["floors"] = c["floors"]
        r["shafts"].sort(key=lambda s: s["id"])
    return canon


# ----------------------------------------------------------------------------- findings doc tables
DOC = Path(__file__).resolve().parent.parent / "docs" / "findings" / "structure_diff.md"


def replace_doc_block(text, name, body):
    """Replace '{{NAME}}' (first fill) or the '<!-- AUTO:NAME -->...<!-- /AUTO:NAME -->'
    block (refresh) with `body`."""
    start, end = f"<!-- AUTO:{name} -->", f"<!-- /AUTO:{name} -->"
    block = f"{start}\n{body}\n{end}"
    if start in text and end in text:
        i = text.index(start)
        j = text.index(end) + len(end)
        return text[:i] + block + text[j:]
    return text.replace("{{" + name + "}}", block)


def update_doc(blocks, path=DOC):
    path = Path(path)
    if not path.exists():
        return None
    t = path.read_text(encoding="utf-8")
    for k, v in blocks.items():
        t = replace_doc_block(t, k, v)
    path.write_text(t, encoding="utf-8")
    return path


def _src_label(el):
    if el["kind"] == "column_xbox":
        return "COL (مربع X)"
    if el["only_in_tr_block"]:
        return "**بلوك tr فقط**"
    if el["hatch_only"]:
        return "**HATCH فقط**"
    return "Etabs-col"


def doc_tables(allres, canon_shafts=None):
    """Markdown tables for docs/findings/structure_diff.md from the per-floor results."""
    B = {}
    labels = [r["floor"] for r in allres]
    ref = next((r for r in allres if r["floor"] == "F06"), allres[0])
    # elements (identical on every floor -> one row each; exposed perimeter min-max over floors)
    exp = defaultdict(list)
    for r in allres:
        for el in r["elements"]:
            exp[el["id"]].append(el["exposed_perimeter"])
    L = ["| id | النوع | المقاس (م) | x من–إلى | y من–إلى | المحاور (أقرب محور ± الإزاحة) | المساحة م² | المحيط م | "
         "ملاصق لحوائط م | ملاصق لخرسانة/شفت م | **المعرض للمحارة م** | على W | المصدر |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    kind_ar = {"column": "عمود", "shear_wall": "حائط قص", "core": "كور مصاعد", "column_xbox": "مربع COL"}
    for el in sorted(ref["elements"], key=lambda e: (-e["centroid"][1], e["centroid"][0])):
        x0, y0, x1, y1 = el["bbox"]
        e_ = exp[el["id"]]
        ev = f"{min(e_):.2f}" if max(e_) - min(e_) < 0.005 else f"{min(e_):.2f}–{max(e_):.2f}"
        L.append(f"| {el['id']} | {kind_ar[el['kind']]} | {el['size_txt']} | {x0:.3f}–{x1:.3f} | {y0:.3f}–{y1:.3f} | "
                 f"{el['grid_ref']} | {el['area']:.3f} | {el['perimeter']:.2f} | {el['covered_by_walls']:.2f} | "
                 f"{el['covered_by_concrete_or_shaft']:.2f} | {ev} | {el['outline_on_W']:.0%} | {_src_label(el)} |")
    B["ELEMENTS_TABLE"] = "\n".join(L)
    # per floor totals
    L = ["| الدور | أعمدة | حوائط قص | كور | مربعات COL | مساحة الخرسانة م² (بدون COL) | المحيط الكلي م | "
         "المعرض للمحارة م (الكل) | المعرض (model space فقط، بدون tr) | شفتات (عدد / م²) | سلالم | كبائن مصاعد | أبعاد DIM |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in allres:
        s = r["summary"]; k = s["elements_by_kind"]
        els = [e for e in r["elements"] if e["kind"] != "column_xbox"]
        L.append(f"| {r['floor']} | {k.get('column', 0)} | {k.get('shear_wall', 0)} | {k.get('core', 0)} | "
                 f"{k.get('column_xbox', 0)} | {sum(e['area'] for e in els):.3f} | {sum(e['perimeter'] for e in els):.2f} | "
                 f"**{s['plaster_perimeter_all']:.2f}** | {s['plaster_perimeter_model_space_only']:.2f} | "
                 f"{s['shafts']} / {s['shaft_area']:.3f} | {s['stairs']} | {s['lift_cars']} | {s['dims']} |")
    B["FLOOR_TABLE"] = "\n".join(L)
    # shafts (canonical, with floors)
    if canon_shafts is None:
        canon_shafts = harmonize_shaft_ids(allres)
    L = ["| id | النوع | المقاس (م) | x من–إلى | y من–إلى | المحاور | المساحة م² | المحيط م | أقطار DASH | الأدوار |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for c in canon_shafts:
        x0, y0, x1, y1 = c["bbox"]
        fl_ = "كل الأدوار" if len(c["floors"]) == len(labels) else ", ".join(c["floors"])
        L.append(f"| {c['id']} | {c['kind']} | {c['size_txt']} | {x0:.3f}–{x1:.3f} | {y0:.3f}–{y1:.3f} | {c['grid_ref']} | "
                 f"{c['area']:.3f} | {c['perimeter']:.2f} | {c['dash_diagonals']} | {fl_} |")
    B["SHAFT_TABLE"] = "\n".join(L)
    # DASH classes per floor
    classes = sorted({k for r in allres for k in r["dash"]["summary"]})
    L = ["| تصنيف DASH | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for c in classes:
        cells = []
        for r in allres:
            v = r["dash"]["summary"].get(c)
            cells.append(f"{v['n']} / {v['len']:.2f}" if v else "—")
        L.append(f"| `{c}` | " + " | ".join(cells) + " |")
    L.append("| **المجموع** | " + " | ".join(
        f"{sum(v['n'] for v in r['dash']['summary'].values())} / {sum(v['len'] for v in r['dash']['summary'].values()):.2f}"
        for r in allres) + " |")
    B["DASH_TABLE"] = "(كل خلية = عدد الخطوط / الطول م)\n\n" + "\n".join(L)
    # DIMS
    classes = sorted({k for r in allres for k in r["dims"]["by_class"]})
    L = ["| تصنيف البُعد | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for c in classes:
        L.append(f"| `{c}` | " + " | ".join(str(r["dims"]["by_class"].get(c, 0)) for r in allres) + " |")
    L.append("| **المجموع** | " + " | ".join(str(r["dims"]["n"]) for r in allres) + " |")
    L.append("| قيم `wall_thickness` | " + " | ".join(
        (", ".join(f"{k}×{v}" for k, v in r["dims"]["wall_thickness_values"].items()) or "—") for r in allres) + " |")
    L.append("| أبعاد بلا تطابق نص/قياس | " + " | ".join(str(len(r["dims"]["text_vs_actual_mismatch"])) for r in allres) + " |")
    # histogram of the most frequent values (all floors) with their dominant class
    vc = defaultdict(Counter)
    for r in allres:
        for d in r["dims"]["dims"]:
            vc[d["text"]][d["class"]] += 1
    top = sorted(vc.items(), key=lambda kv: -sum(kv[1].values()))[:25]
    H = ["| القيمة (م) | العدد في الأدوار السبعة | التصنيف |", "|---|---|---|"]
    for v, c in top:
        H.append(f"| {v} | {sum(c.values())} | " + ", ".join(f"{k} {n}" for k, n in c.most_common()) + " |")
    B["DIMS_TABLE"] = "\n".join(L) + "\n\nأكثر 25 قيمة تكرارًا (كل الأدوار):\n\n" + "\n".join(H)
    return B


def run(floors=None, png=True, doc=True):
    OUT.mkdir(parents=True, exist_ok=True)
    fls = [f for f in all_floors() if not floors or f.floor_no in floors]
    allres = []
    for fl in fls:
        t0 = time.time()
        res = analyze_floor(fl)
        s = res["summary"]
        print(f"{fl.label}: elements {s['elements_by_kind']}  plaster perim {s['plaster_perimeter_all']} m "
              f"(model-space only {s['plaster_perimeter_model_space_only']})  shafts {s['shafts']}  stairs {s['stairs']}  "
              f"lifts {s['lift_cars']}  dims {s['dims']} {s['dims_by_class']}  ({time.time() - t0:.0f}s)", flush=True)
        allres.append(res)
    canon = harmonize_shaft_ids(allres) if len(allres) > 1 else None
    for res in allres:
        (OUT / f"{res['floor']}.json").write_text(json.dumps(_jsonable(res), ensure_ascii=False, indent=1), encoding="utf-8")
        if png:
            render(res, OUT / f"{res['floor']}_structure.png")
            render(res, OUT / f"{res['floor']}_dims.png", mode="dims")
    if png and allres:
        render_dims_hist(allres, OUT / "dims_histogram.png")
    summ = {r["floor"]: r["summary"] for r in allres}
    if canon:
        summ["canonical_shafts"] = [{k: v for k, v in c.items()} for c in canon]
    (OUT / "summary.json").write_text(json.dumps(_jsonable(summ), ensure_ascii=False, indent=1), encoding="utf-8")
    if doc and len(allres) == 7:
        p = update_doc(doc_tables(allres, canon))
        if p:
            print("doc tables refreshed:", p)
    return allres


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (default: all 2..8)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-doc", action="store_true", help="do not refresh the AUTO tables in docs/findings/structure_diff.md")
    ap.add_argument("--zoom", nargs=4, type=float, help="extra zoomed PNG (local x0 y0 x1 y1) for the first floor")
    a = ap.parse_args()
    allres = run(a.floors or None, png=not a.no_png, doc=not a.no_doc)
    if a.zoom and allres:
        r = allres[0]
        p = render(r, OUT / f"{r['floor']}_zoom_{'_'.join(str(int(v)) for v in a.zoom)}.png", zoom=a.zoom)
        print("saved", p)


if __name__ == "__main__":
    main()
