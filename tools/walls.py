# -*- coding: utf-8 -*-
"""
walls.py — قارئ الحوائط (wall reader, masonry basis) for the Diwan plans.

Reconstructs WALL SEGMENTS from the wall-face lines on layer W of every floor
(F02..F08), in the LOCAL frame of diwan_common (building rotation removed).
Findings / conventions: docs/findings/walls.md

  1. Geometry: W LINEs + straight LWPOLYLINE segments (bulges / ARCs reported,
     not walls).  Ignored: the sheet-size frame polyline on W, small closed
     many-vertex polylines (door-frame profiles drawn on W), degenerate dots, and
     W lines lying on a WIN glazing line (window frame re-drawn on W, >= 0.30 m).
  2. Face lines: segments grouped by direction (tol 1 deg) and by offset
     (tol 12 mm); duplicates / overlaps are merged -> no double counting.
     End CAPS (short U-shaped closing lines: jambs, wall ends) are not faces.
     VIRTUAL fills close a face across a short gap flanked by lines running
     away from the wall while the other face continues (T-junction, nib).
  3. Pairing: along every direction, between CONSECUTIVE parallel faces whose
     gap is a wall thickness (0.04..0.62 m) -> elementary solid cells.
     Cells inside shafts / lift wells (unhatched `try` boxes, X-crossed boxes
     on DASH/try/PR) are void; structural concrete (Etabs-col / COL polygons,
     AR-CONC planter hatches on W) is cut out -> walls end at columns.
     A box that pairs in two directions is given to the wall-like reading.
  4. Runs: collinear pieces (same faces) are chained across OPENINGS - door
     blocks D<w>W<t> (matched by insertion point), windows on WIN, loose door
     arcs, jamb-capped empty gaps <= 3 m, or uncapped gaps <= 1.6 m where both
     faces stop clean -> gross; net = solid only.  An opening whose far jamb is
     a column / core face (window beside a column, lift doors) is bridged up to
     the concrete face.
  5. Corners: L-corners extend both walls to the centre-line crossing
     (centre-line method; the corner square is counted exactly once);
     T-junctions: the through-wall keeps the junction, the branch stops at
     its face; runs are then CUT at every T-junction (one record per wall
     between junctions, as a surveyor measures room by room).
  6. Classification of each record from its two sides: exterior (a ray from
     the face escapes the plan, or a terrace / planter is there), stair_lift
     (stair hall / lift well beside it), shaft (shaft void beside it),
     interior.  needs_check + reason for doubtful records.
  7. Cross-checks: architect DIMENSIONs (layer DIM), plan overlaps between
     records, and how much W linework the records explain.

Lengths are CENTRE-LINE lengths (m). Thickness = face-to-face (m).

Outputs (gitignored):
  output/walls/<F>.json                walls + openings + totals + cross-checks
  output/walls/<F>_walls.png           review drawing (colour = thickness, numbered)
  output/walls/<F>_walls_{south,north}.png   the two halves, larger
  output/walls/summary.json            per-floor totals (all-floor runs only)

CLI:
  python tools/walls.py                 # all floors F02..F08
  python tools/walls.py 3 5             # some floors
  python tools/walls.py 3 --zoom 0 25 10 37   # extra zoomed review PNG
  python tools/walls.py --height 2.98   # indicative areas at another height

API:
  from walls import read_walls
  res = read_walls(3)   # dict: floor, walls[], totals{'0.12|interior': {...}}, ...
  each wall: id, x1,y1,x2,y2 (local centre-line), thickness, family, length_gross,
  length_net, openings[], kind, needs_check, reason, notes, sides[], _band/_t
  (band = face offsets, t = along-wall range in the Dir(angle) frame).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import (OUT_DIR, STOREY_HEIGHT, all_floors, floor_entities,  # noqa: E402
                          floor_texts, get_floor, is_try_outline)

from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402
from ezdxf.path import make_path  # noqa: E402

WALL_OUT = OUT_DIR / "walls"
CACHE_DIR = WALL_OUT / "_cache"

# ---- tunables (metres / degrees) -------------------------------------------
DIR_TOL = 1.0          # deg: segments within this angle are parallel
OFF_TOL = 0.012        # m: faces closer than this are the same line (duplicates, 1 cm drafting slips)
GAP_MIN = 0.04         # m: thinnest wall
GAP_MAX = 0.62         # m: thickest wall (0.60 shaft/duct bodies seen on F02)
MAX_OPENING = 3.0      # m: longest gap bridged as an opening (gross length)
UNCAPPED_OPENING_MAX = 1.6  # m: longest door-less gap bridged when its ends have no jamb line
JUNCTION_MAX = 0.62    # m: longest gap bridged as a wall junction
BUILDING_WIN = (-4.0, -5.0, 25.0, 45.0)  # local window holding the plan

DOOR_RE = re.compile(r"^D(\d+)W(\d+)$", re.I)


# ============================================================================
# 1. extraction (DXF -> plain local-frame geometry), cached per floor
# ============================================================================
def _arc_pts(cx, cy, r, a0, a1, step=5.0):
    if a1 < a0:
        a1 += 360.0
    n = max(2, int((a1 - a0) / step) + 1)
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def _bulge_arc(p, q, b):
    """centre, radius, start/end angle (deg, ccw) of an LWPOLYLINE bulge segment."""
    (x1, y1), (x2, y2) = p, q
    th = 4 * math.atan(b)
    c = math.hypot(x2 - x1, y2 - y1)
    if c < 1e-9 or abs(th) < 1e-9:
        return None
    r = c / (2 * math.sin(abs(th) / 2))
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    h = math.sqrt(max(r * r - c * c / 4, 0.0))
    ux, uy = (x2 - x1) / c, (y2 - y1) / c
    sgn = 1 if (b > 0) == (abs(th) < math.pi) else -1
    cx, cy = mx - uy * h * sgn, my + ux * h * sgn
    a_p = math.degrees(math.atan2(y1 - cy, x1 - cx))
    a_q = math.degrees(math.atan2(y2 - cy, x2 - cx))
    return (cx, cy, abs(r), a_p, a_q) if b > 0 else (cx, cy, abs(r), a_q, a_p)


def _in_win(p, pad=0.0):
    return BUILDING_WIN[0] - pad <= p[0] <= BUILDING_WIN[2] + pad and BUILDING_WIN[1] - pad <= p[1] <= BUILDING_WIN[3] + pad


def extract(fl) -> dict:
    """Plain local-frame geometry of one floor (lists/tuples only -> picklable)."""
    L = fl.to_local
    g = {"label": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
         "file": fl.file.name, "sheet_index": fl.sheet_index,
         "wsegs": [], "warcs": [], "whatch": [], "w_inserts": [], "w_ignored": [],
         "columns": [], "shafts": [], "win": [], "winarcs": [], "doors": [],
         "st": [], "texts": [], "dims": [], "pr_arcs": [], "dash": []}

    # ---- layer W ----
    for e in floor_entities(fl, layers="W"):
        t = e.dxftype()
        h = e.dxf.handle
        if t == "LINE":
            a = L(e.dxf.start.x, e.dxf.start.y)
            b = L(e.dxf.end.x, e.dxf.end.y)
            g["wsegs"].append((a[0], a[1], b[0], b[1], h, "LINE"))
        elif t == "LWPOLYLINE":
            raw = list(e.get_points("xyb"))
            pts = [L(p[0], p[1]) for p in raw]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if max(xs) - min(xs) > 60 or max(ys) - min(ys) > 80:
                g["w_ignored"].append({"handle": h, "type": t, "why": "sheet-size polyline (frame)"})
                continue
            n = len(pts)
            g.setdefault("wpolys", []).append({"handle": h, "n": n, "closed": bool(e.closed),
                                               "bbox": (min(xs), min(ys), max(xs), max(ys))})
            rng = range(n if e.closed else n - 1)
            for i in rng:
                p, q = pts[i], pts[(i + 1) % n]
                bul = raw[i][2]
                if abs(bul) > 1e-6:
                    arc = _bulge_arc(p, q, bul)
                    if arc:
                        g["warcs"].append(arc + (h, "LWPOLY-bulge"))
                    continue
                if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-4:
                    g["wsegs"].append((p[0], p[1], q[0], q[1], h, "LWPOLYLINE"))
        elif t == "ARC":
            c = L(e.dxf.center.x, e.dxf.center.y)
            g["warcs"].append((c[0], c[1], e.dxf.radius, e.dxf.start_angle - fl.angle,
                               e.dxf.end_angle - fl.angle, h, "ARC"))
        elif t == "HATCH":
            polys = []
            for path in e.paths:
                pts = None
                if hasattr(path, "vertices"):
                    pts = [L(v[0], v[1]) for v in path.vertices]
                elif hasattr(path, "edges"):
                    pts = []
                    for ed in path.edges:
                        if hasattr(ed, "start") and hasattr(ed, "end"):
                            pts.append(L(ed.start[0], ed.start[1]))
                        elif hasattr(ed, "center"):
                            cc = ed.center
                            for p in _arc_pts(cc[0], cc[1], ed.radius, ed.start_angle, ed.end_angle):
                                pts.append(L(p[0], p[1]))
                if pts and len(pts) >= 3:
                    polys.append(pts)
            g["whatch"].append({"handle": h, "pattern": e.dxf.pattern_name, "paths": polys})
        elif t == "INSERT":
            p = L(e.dxf.insert.x, e.dxf.insert.y)
            g["w_inserts"].append({"name": e.dxf.name, "x": p[0], "y": p[1], "handle": h})
        else:
            g["w_ignored"].append({"handle": h, "type": t, "why": "unhandled type"})

    # ---- structural columns / cores ----
    for e in floor_entities(fl, layers=("Etabs-col", "COL"), types="LWPOLYLINE"):
        pts = [L(p[0], p[1]) for p in e.get_points("xy")]
        if len(pts) >= 3:
            g["columns"].append({"layer": e.dxf.layer, "pts": pts, "handle": e.dxf.handle})
    # Etabs-col HATCHes are stored as EDGE paths (LINE edges) in these files, not polyline
    # paths -> read every boundary loop through ezdxf.path.  Loops that duplicate a column
    # polyline are skipped; the one that matters is the HATCH-ONLY shear wall 3.90 x 0.40
    # between office 9 and office 10 (x 3.155-7.055, y 18.654-19.054; structure.py SW06),
    # which has no LWPOLYLINE and was read as a 0.40 masonry wall before (v7 fix).
    poly_cols = []
    for c in g["columns"]:
        try:
            pc = Polygon(c["pts"]).buffer(0)
            if pc.area > 1e-4:
                poly_cols.append(pc)
        except Exception:
            pass
    from ezdxf.path import from_hatch
    for e in floor_entities(fl, layers="Etabs-col", types="HATCH"):
        try:
            loops = [[L(q.x, q.y) for q in hp.flattening(0.005)] for hp in from_hatch(e)]
        except Exception:
            loops = []
        for pts in loops:
            if len(pts) >= 2 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 1e-6:
                pts = pts[:-1]
            if len(pts) < 3:
                continue
            try:
                ph = Polygon(pts).buffer(0)
            except Exception:
                continue
            if ph.area < 1e-4:
                continue
            if any(ph.symmetric_difference(pc).area < 0.02 * ph.area for pc in poly_cols):
                continue          # same footprint as a column polyline
            g["columns"].append({"layer": "Etabs-col(hatch)", "pts": pts, "handle": e.dxf.handle})
            poly_cols.append(ph)

    # ---- shafts / ducts (X-crossed boxes) ----
    for e in floor_entities(fl, layers="try", types="LWPOLYLINE"):
        pts = [L(p[0], p[1]) for p in e.get_points("xy")]
        if len(pts) >= 3 and not is_try_outline(pts):   # F09-F11: floor/plot outlines on try
            g["shafts"].append({"pts": pts, "handle": e.dxf.handle})

    # ---- windows ----
    for e in floor_entities(fl, layers="WIN"):
        t = e.dxftype()
        lt = e.dxf.get("linetype", "BYLAYER")
        if t == "LINE":
            a = L(e.dxf.start.x, e.dxf.start.y)
            b = L(e.dxf.end.x, e.dxf.end.y)
            g["win"].append((a[0], a[1], b[0], b[1], lt))
        elif t == "LWPOLYLINE":
            pts = [L(p[0], p[1]) for p in e.get_points("xy")]
            for i in range(len(pts) - 1 + (1 if e.closed else 0)):
                p, q = pts[i], pts[(i + 1) % len(pts)]
                g["win"].append((p[0], p[1], q[0], q[1], lt))
        elif t == "ARC":
            c = L(e.dxf.center.x, e.dxf.center.y)
            g["winarcs"].append((c[0], c[1], e.dxf.radius, e.dxf.start_angle - fl.angle,
                                 e.dxf.end_angle - fl.angle, lt))

    # ---- doors (blocks D<width cm>W<wall cm>, any layer) ----
    for e in floor_entities(fl, types="INSERT"):
        m = DOOR_RE.match(e.dxf.name)
        if not m:
            continue
        pts, arcs = [], []
        try:
            for v in e.virtual_entities():
                try:
                    pth = make_path(v)
                except Exception:
                    continue
                vp = [L(q.x, q.y) for q in pth.flattening(0.02)]
                pts += vp
                if v.dxftype() == "ARC" and len(vp) >= 2:
                    arcs.append(vp)
        except Exception:
            pass
        if not pts:
            continue
        ins = L(e.dxf.insert.x, e.dxf.insert.y)
        wnum = int(m.group(1))
        g["doors"].append({"name": e.dxf.name, "width": wnum / (100.0 if wnum >= 50 else 10.0),
                           "wall": int(m.group(2)) / 100.0, "layer": e.dxf.layer,
                           "x": ins[0], "y": ins[1], "rot": (e.dxf.rotation - fl.angle) % 360,
                           "mirrored": e.dxf.xscale * e.dxf.yscale < 0,
                           "bbox": (min(p[0] for p in pts), min(p[1] for p in pts),
                                    max(p[0] for p in pts), max(p[1] for p in pts)),
                           "arcs": arcs, "handle": e.dxf.handle})

    # ---- DASH / try / PR lines (X-crossed shaft boxes, projections) ----
    for e in floor_entities(fl, layers=("DASH", "try", "PR"), types="LINE LWPOLYLINE"):
        if e.dxftype() == "LINE":
            a = L(e.dxf.start.x, e.dxf.start.y)
            b = L(e.dxf.end.x, e.dxf.end.y)
            g["dash"].append((a[0], a[1], b[0], b[1], e.dxf.layer))
        else:
            pts = [L(p[0], p[1]) for p in e.get_points("xy")]
            for i in range(len(pts) - 1 + (1 if e.closed else 0)):
                p, q = pts[i], pts[(i + 1) % len(pts)]
                g["dash"].append((p[0], p[1], q[0], q[1], e.dxf.layer))
    g["try_hatch"] = []
    for e in floor_entities(fl, layers="try", types="HATCH"):
        for path in e.paths:
            if hasattr(path, "vertices") and len(path.vertices) >= 3:
                g["try_hatch"].append([L(v[0], v[1]) for v in path.vertices])
            elif hasattr(path, "edges"):
                pts = [L(ed.start[0], ed.start[1]) for ed in path.edges if hasattr(ed, "start")]
                if len(pts) >= 3:
                    g["try_hatch"].append(pts)

    # ---- loose door-leaf arcs (PR / WIN outside blocks) ----
    for e in floor_entities(fl, layers=("PR", "WIN"), types="ARC"):
        c = L(e.dxf.center.x, e.dxf.center.y)
        g["pr_arcs"].append((c[0], c[1], e.dxf.radius, e.dxf.layer))

    # ---- stairs ----
    for e in floor_entities(fl, layers="ST", types="LINE"):
        a = L(e.dxf.start.x, e.dxf.start.y)
        b = L(e.dxf.end.x, e.dxf.end.y)
        g["st"].append((a[0], a[1], b[0], b[1]))

    # ---- axis grid (layer X / x1) ----
    g["axes"] = []
    for e in floor_entities(fl, layers=("X", "x1"), types="LINE"):
        a = L(e.dxf.start.x, e.dxf.start.y)
        b = L(e.dxf.end.x, e.dxf.end.y)
        g["axes"].append((a[0], a[1], b[0], b[1]))

    # ---- room labels ----
    for t in floor_texts(fl, layers=("TEXT", "-A-TEXT")):
        if _in_win(t["local"]):
            g["texts"].append({"text": t["text"], "x": t["local"][0], "y": t["local"][1], "layer": t["layer"]})

    # ---- architect dimensions (layer DIM) ----
    for e in floor_entities(fl, layers="DIM", types="DIMENSION"):
        d = e.dxf
        try:
            p2 = L(d.defpoint2.x, d.defpoint2.y)
            p3 = L(d.defpoint3.x, d.defpoint3.y)
            p1 = L(d.defpoint.x, d.defpoint.y)
        except Exception:
            continue
        g["dims"].append({"type": d.dimtype & 7, "value": float(d.get("actual_measurement", 0.0)),
                          "p1": p1, "p2": p2, "p3": p3, "angle": (d.get("angle", 0.0) - fl.angle) % 180,
                          "text": d.get("text", ""), "handle": d.handle})
    return g


def load_geometry(fl, use_cache=True) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{fl.label}_{fl.file.stem}_{int(os.path.getmtime(fl.file))}_v8.pkl"
    p = CACHE_DIR / key
    if use_cache and p.exists():
        with open(p, "rb") as f:
            return pickle.load(f)
    g = extract(fl)
    with open(p, "wb") as f:
        pickle.dump(g, f)
    return g


# ============================================================================
# 2. face lines and pairing
# ============================================================================
class Dir:
    """A wall direction: unit vector u (along), normal n; t = p.u, d = p.n."""

    def __init__(self, ang):
        self.ang = ang % 180.0
        a = math.radians(self.ang)
        self.u = (math.cos(a), math.sin(a))
        self.n = (-self.u[1], self.u[0])

    def td(self, x, y):
        return (x * self.u[0] + y * self.u[1], x * self.n[0] + y * self.n[1])

    def xy(self, t, d):
        return (t * self.u[0] + d * self.n[0], t * self.u[1] + d * self.n[1])

    def rect(self, s, e, d0, d1):
        return Polygon([self.xy(s, d0), self.xy(e, d0), self.xy(e, d1), self.xy(s, d1)])


def _angdiff(a, b):
    return abs((a - b + 90.0) % 180.0 - 90.0)


def cluster_directions(segs, tol=DIR_TOL):
    """Group segments by direction; returns list of (Dir, [seg...]) longest-first."""
    items = []
    for s in segs:
        x1, y1, x2, y2 = s[:4]
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-4:
            continue
        items.append((math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0, L, s))
    items.sort(key=lambda it: -it[1])
    groups = []
    for ang, L, s in items:
        for gr in groups:
            if _angdiff(ang, gr["ang"]) <= tol:
                gr["items"].append((ang, L, s))
                break
        else:
            groups.append({"ang": ang, "items": [(ang, L, s)]})
    out = []
    for gr in groups:
        # length-weighted mean angle (unwrapped around the seed)
        a0 = gr["ang"]
        num = sum(((a - a0 + 90) % 180 - 90) * L for a, L, _ in gr["items"])
        den = sum(L for _, L, _ in gr["items"])
        ang = a0 + num / den
        for snap in (0.0, 90.0, 180.0):   # exact orthogonal frame
            if abs(ang - snap) < 0.05:
                ang = snap
        out.append((Dir(ang), [s for _, _, s in gr["items"]]))
    out.sort(key=lambda x: -sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in x[1]))
    return out


def merge_intervals(ivs, tol=0.002):
    ivs = sorted([list(v) for v in ivs])
    out = []
    for s, e in ivs:
        if out and s <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def build_faces(D, segs, off_tol=OFF_TOL):
    """Collinear segments -> face lines {d, ivs, handles, n_dup}."""
    rows = []
    for s in segs:
        ta, da = D.td(s[0], s[1])
        tb, db = D.td(s[2], s[3])
        rows.append(((da + db) / 2, min(ta, tb), max(ta, tb), s[4]))
    rows.sort()
    groups = []
    for r in rows:
        if groups and r[0] - groups[-1][-1][0] <= off_tol:
            groups[-1].append(r)
        else:
            groups.append([r])
    faces = []
    for gr in groups:
        w = sum(r[2] - r[1] for r in gr) or 1e-9
        d = sum(r[0] * (r[2] - r[1]) for r in gr) / w
        raw_len = sum(r[2] - r[1] for r in gr)
        ivs = merge_intervals([(r[1], r[2]) for r in gr])
        faces.append({"d": d, "ivs": ivs, "handles": [r[3] for r in gr],
                      "dup_len": raw_len - sum(e - s for s, e in ivs)})
    return faces


def covers(ivs, s, e, tol=0.003):
    """True if the merged interval list covers [s, e] entirely."""
    for a, b in ivs:
        if a - tol <= s and b + tol >= e:
            return True
    return False


def cover_len(ivs, s, e):
    return sum(max(0.0, min(b, e) - max(a, s)) for a, b in ivs)


def _all_ivs(f):
    return merge_intervals(f["ivs"] + f.get("vivs", []))


def pair_cells(faces, gmin=GAP_MIN, gmax=GAP_MAX):
    """Elementary solid cells between consecutive active faces (real + virtual intervals)."""
    allivs = [_all_ivs(f) for f in faces]
    bps = sorted({round(x, 4) for ivs in allivs for iv in ivs for x in iv})
    cells = []
    for k in range(len(bps) - 1):
        s, e = bps[k], bps[k + 1]
        if e - s < 1e-3:
            continue
        m = (s + e) / 2
        act = sorted((f["d"], i) for i, f in enumerate(faces)
                     if any(a - 1e-6 <= m <= b + 1e-6 for a, b in allivs[i]))
        for j in range(len(act) - 1):
            g = act[j + 1][0] - act[j][0]
            if gmin <= g <= gmax:
                cells.append({"lo": act[j][1], "hi": act[j + 1][1],
                              "d0": act[j][0], "d1": act[j + 1][0], "s": s, "e": e})
    return cells


# ---- end caps (jamb / wall-end lines) ----------------------------------------
def _endpoint_index(segs, cell=0.05):
    idx = defaultdict(list)
    for k, s in enumerate(segs):
        for end in (0, 1):
            x, y = (s[0], s[1]) if end == 0 else (s[2], s[3])
            idx[(round(x / cell), round(y / cell))].append((k, end))
    return idx


def _touching(idx, segs, x, y, tol=0.012, cell=0.05):
    """(seg index, which end) of segments having an endpoint within tol of (x, y)."""
    out = []
    cx, cy = round(x / cell), round(y / cell)
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k, end in idx.get((cx + i, cy + j), ()):
                s = segs[k]
                px, py = (s[0], s[1]) if end == 0 else (s[2], s[3])
                if abs(px - x) <= tol and abs(py - y) <= tol:
                    out.append((k, end))
    return out


def _seg_ang(s):
    return math.degrees(math.atan2(s[3] - s[1], s[2] - s[0])) % 180.0


def detect_caps(segs, max_len=0.45, VU=None):
    """A cap = short segment closing a wall end: at both endpoints a perpendicular,
    LONGER segment starts and both run to the same side (U shape).  Caps are not
    wall faces (they would otherwise pair with lines of the crossing direction)."""
    idx = _endpoint_index(segs)
    caps = set()
    for k, s in enumerate(segs):
        L = math.hypot(s[2] - s[0], s[3] - s[1])
        if not (0.03 <= L <= max_len):
            continue
        a = _seg_ang(s)
        ux, uy = (s[2] - s[0]) / L, (s[3] - s[1]) / L
        sides = []
        for (x, y) in ((s[0], s[1]), (s[2], s[3])):
            sd = set()
            for k2, end in _touching(idx, segs, x, y):
                if k2 == k:
                    continue
                s2 = segs[k2]
                if _angdiff(_seg_ang(s2), a) < 60:
                    continue
                L2 = math.hypot(s2[2] - s2[0], s2[3] - s2[1])
                if L2 < 0.8 * L:
                    continue
                fx, fy = (s2[2], s2[3]) if end == 0 else (s2[0], s2[1])
                cross = ux * (fy - y) - uy * (fx - x)
                sd.add(1 if cross > 0 else -1)
            sides.append(sd)
        common = sides[0] & sides[1]
        if common:
            if VU is not None:
                sg = next(iter(common))
                mx, my = (s[0] + s[2]) / 2, (s[1] + s[3]) / 2
                inside = Point(mx - uy * 0.05 * sg, my + ux * 0.05 * sg)
                if VU.contains(inside):
                    continue          # the U encloses a shaft void: box side, not a wall end
            caps.add(k)
    return caps


def virtual_fills(D, faces, segs, idx):
    """Close short gaps in a face where the gap is flanked by perpendicular lines that
    run AWAY from the wall body while the opposite face continues: T-junction
    (a branch wall joins) or a nib/pilaster projecting from the face.  Two passes: the
    opposite face may itself have a candidate fill at the same place (pier + nib)."""
    cand = {}
    for fi, f in enumerate(faces):
        ivs = f["ivs"]
        for (a0, a), (b, b1) in zip(ivs, ivs[1:]):
            if not (0.0 < b - a <= JUNCTION_MAX):
                continue
            sg = []
            for t in (a, b):
                x, y = D.xy(t, f["d"])
                ss = set()
                for k2, end in _touching(idx, segs, x, y, tol=0.025):
                    s2 = segs[k2]
                    if _angdiff(_seg_ang(s2), D.ang) < 60:
                        continue
                    fx, fy = (s2[2], s2[3]) if end == 0 else (s2[0], s2[1])
                    dd = D.td(fx, fy)[1] - f["d"]
                    if abs(dd) >= 0.04:
                        ss.add(1 if dd > 0 else -1)
                sg.append(ss)
            for sgn in sg[0] & sg[1]:
                cand.setdefault(fi, []).append((a, b, sgn))
    n = 0
    for fi, f in enumerate(faces):
        f["vivs"] = []
    for fi, lst in cand.items():
        f = faces[fi]
        for a, b, sgn in lst:
            ok = False
            for fj, f2 in enumerate(faces):
                if fj == fi or not (GAP_MIN <= (f["d"] - f2["d"]) * sgn <= GAP_MAX):
                    continue
                ivs2 = merge_intervals(f2["ivs"] + [[x0, x1] for x0, x1, sg2 in cand.get(fj, []) if sg2 == -sgn])
                if covers(ivs2, a, b, tol=0.004):
                    ok = True
                    break
            if ok and not any(abs(v[0] - a) < 1e-6 and abs(v[1] - b) < 1e-6 for v in f["vivs"]):
                f["vivs"].append([a, b])
                n += 1
    return n


# ============================================================================
# 3. concrete / shaft masks
# ============================================================================
def _poly(pts):
    try:
        p = Polygon(pts)
        if not p.is_valid:
            p = p.buffer(0)
        if p.area < 1e-4:
            p = LineString(pts).convex_hull if len(pts) >= 3 else None
        return p if p is not None and p.area > 1e-4 else None
    except Exception:
        return None


def concrete_polys(g):
    """Structural concrete in plan: Etabs-col / COL polygons + AR-CONC hatches on W."""
    out = []
    for c in g["columns"]:
        p = _poly(c["pts"])
        if p is None and len(c["pts"]) >= 3:
            p = LineString(c["pts"]).convex_hull
        if p is not None and p.area > 1e-4:
            out.append({"poly": p, "src": c["layer"], "handle": c["handle"]})
    for h in g["whatch"]:
        if "CONC" in (h["pattern"] or "").upper():
            for pts in h["paths"]:
                p = _poly(pts)
                if p is not None:
                    out.append({"poly": p, "src": f"W-hatch {h['pattern']}", "handle": h["handle"]})
    return out


def void_polys(g, wall_dirs):
    """Shaft / duct / lift voids: `try` boxes that are NOT hatched + boxes spanned by an
    X (diagonal lines on DASH/try/PR).  Hatched `try` boxes are masonry fins (ANSI31)."""
    hatched = [_poly(p) for p in g.get("try_hatch", [])]
    hatched = [h for h in hatched if h is not None]
    out, fins = [], []
    for s in g["shafts"]:
        p = _poly(s["pts"])
        if p is None:
            continue
        if any(p.intersection(h).area > 0.6 * p.area for h in hatched):
            fins.append({"poly": p, "handle": s["handle"], "src": "try+ANSI31 hatch"})
        else:
            out.append({"poly": p, "handle": s["handle"], "src": "try box"})
    # diagonals: not parallel to any wall direction, 0.3..3.5 m long
    for x1, y1, x2, y2, lay in g["dash"]:
        L = math.hypot(x2 - x1, y2 - y1)
        if not (0.3 <= L <= 3.5):
            continue
        a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
        if min(_angdiff(a, D.ang) for D in wall_dirs) < 8.0 or abs(_angdiff(a, 45.0)) < 0.2 or abs(_angdiff(a, 135.0)) < 0.2:
            continue      # parallel to walls, or a 45-deg stair break line
        bx = box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if bx.area < 0.04:
            continue
        if any(bx.intersection(o["poly"]).area > 0.8 * bx.area for o in out):
            continue
        out.append({"poly": bx, "handle": None, "src": f"X-box ({lay})"})
    # a box that contains a smaller void box is the OUTER outline of the shaft walls (F05-F08
    # draw both on `try`): the walls between the two boxes are masonry, not void.
    keep = []
    for o in out:
        if any(o2 is not o and o2["poly"].area < 0.8 * o["poly"].area
               and o["poly"].buffer(0.01).contains(o2["poly"]) for o2 in out):
            continue
        keep.append(o)
    return keep, fins


# ============================================================================
# 4. pieces -> runs -> corners
# ============================================================================
class Piece:
    __slots__ = ("di", "D", "d0", "d1", "s", "e", "lo", "hi", "cells")

    def __init__(self, di, D, d0, d1, s, e, lo, hi):
        self.di, self.D, self.d0, self.d1, self.s, self.e, self.lo, self.hi = di, D, d0, d1, s, e, lo, hi
        self.cells = 1

    @property
    def thk(self):
        return self.d1 - self.d0

    def rect(self, s=None, e=None, pad=0.0):
        return self.D.rect((self.s if s is None else s) - pad, (self.e if e is None else e) + pad,
                           self.d0 - pad, self.d1 + pad)


def _t_ranges(poly, D):
    """t-extent of each polygon part (shapely geometry) in direction D."""
    geoms = getattr(poly, "geoms", [poly])
    out = []
    for gm in geoms:
        if gm.is_empty or gm.area < 1e-6:
            continue
        ts = [D.td(x, y)[0] for x, y in gm.exterior.coords]
        out.append((min(ts), max(ts), gm.area))
    return out


def _subtract(ivs, a, b):
    out = []
    for s, e in ivs:
        if b <= s or a >= e:
            out.append((s, e))
            continue
        if a > s:
            out.append((s, a))
        if b < e:
            out.append((b, e))
    return [(s, e) for s, e in out if e - s > 1e-3]


def make_pieces(g, dirs, CU, VU, log):
    """Pair faces in every direction, drop void cells, cut concrete -> Piece list."""
    pieces = []
    face_index = {}
    allsegs = [s for _, ss in dirs for s in ss]
    caps = detect_caps(allsegs, VU=VU)
    capkeys = {tuple(round(v, 5) for v in allsegs[k][:4]) for k in caps}
    log["caps"] += len(caps)
    idx = _endpoint_index(allsegs)
    for di, (D, segs) in enumerate(dirs):
        fsegs = [s for s in segs if tuple(round(v, 5) for v in s[:4]) not in capkeys]
        faces = build_faces(D, fsegs)
        face_index[di] = faces
        log["dup_len"] += sum(f["dup_len"] for f in faces)
        log["virtual_fills"] += virtual_fills(D, faces, allsegs, idx)
        cells = pair_cells(faces)
        kept = []
        for c in cells:
            r = D.rect(c["s"], c["e"], c["d0"], c["d1"])
            if r.area <= 0:
                continue
            if VU is not None and r.intersection(VU).area > 0.5 * r.area:
                log["void_len"] += c["e"] - c["s"]
                continue
            ivs = [(c["s"], c["e"])]
            if CU is not None and r.intersects(CU):
                inter = r.intersection(CU)
                thk = c["d1"] - c["d0"]
                for a, b, area in _t_ranges(inter, D):
                    if b - a > 1e-4 and area / ((b - a) * thk) >= 0.5:
                        before = sum(e - s for s, e in ivs)
                        ivs = _subtract(ivs, a, b)
                        log["concrete_len"] += before - sum(e - s for s, e in ivs)
            for s, e in ivs:
                kept.append(dict(c, s=s, e=e))
        # merge contiguous cells with the same two faces
        kept.sort(key=lambda c: (c["lo"], c["hi"], c["s"]))
        cur = None
        for c in kept:
            if cur and cur.lo == c["lo"] and cur.hi == c["hi"] and abs(c["s"] - cur.e) < 2e-3:
                cur.e = c["e"]
                cur.cells += 1
                continue
            cur = Piece(di, D, c["d0"], c["d1"], c["s"], c["e"], c["lo"], c["hi"])
            pieces.append(cur)
    pieces = resolve_conflicts(pieces, log)
    keep = []
    for p in pieces:
        if p.e - p.s < 0.02:
            log["sliver_len"] += p.e - p.s
            continue
        keep.append(p)
    return keep, face_index


def _piece_score(p, pieces=None):
    """Which reading of a box is the wall: standard thickness, wall-like proportions, and a
    collinear continuation (same band within MAX_OPENING - e.g. a stub beside a door)."""
    L = p.e - p.s
    sc = 0.0
    if family(p.thk) != "other":
        sc += 2
    if L >= p.thk:
        sc += 1
    if L >= 0.6:
        sc += 1
    if pieces is not None:
        for q in pieces:
            if q is p or q.di != p.di or abs(q.d0 - p.d0) > 0.006 or abs(q.d1 - p.d1) > 0.006:
                continue
            gap = max(q.s - p.e, p.s - q.e)
            if 0 <= gap <= MAX_OPENING:
                sc += 1
                break
    return sc, L


def resolve_conflicts(pieces, log):
    """The same small box can pair in two directions (nib, stub between doors, pier):
    keep the reading with the standard thickness / wall-like proportions, trim the other."""
    from shapely.strtree import STRtree
    changed = True
    rounds = 0
    while changed and rounds < 4:
        changed = False
        rounds += 1
        rects = [p.rect() for p in pieces]
        tree = STRtree(rects)
        drop = {}
        for i, p in enumerate(pieces):
            for j in tree.query(rects[i]):
                j = int(j)
                if j <= i or pieces[j].di == p.di:
                    continue
                inter = rects[i].intersection(rects[j])
                if inter.area < 2e-4:
                    continue
                q = pieces[j]
                loser = q if _piece_score(p, pieces) >= _piece_score(q, pieces) else p
                li = j if loser is q else i
                drop.setdefault(li, []).append(inter)
        if not drop:
            break
        new = []
        for i, p in enumerate(pieces):
            if i not in drop:
                new.append(p)
                continue
            ivs = [(p.s, p.e)]
            for inter in drop[i]:
                for a, b, area in _t_ranges(inter, p.D):
                    if b - a > 1e-4 and area / ((b - a) * p.thk) >= 0.4:
                        ivs = _subtract(ivs, a, b)
            log["conflict_trim"] += (p.e - p.s) - sum(e - s for s, e in ivs)
            for s, e in ivs:
                q = Piece(p.di, p.D, p.d0, p.d1, s, e, p.lo, p.hi)
                new.append(q)
            changed = True
        pieces = new
    return pieces


class Ctx:
    """Everything the gap / corner / side tests need for one floor."""

    def __init__(self, g, dirs, pieces, faces, CU, VU, conc, voids, fins):
        self.g, self.dirs, self.pieces, self.faces = g, dirs, pieces, faces
        self.CU, self.VU, self.conc, self.voids, self.fins = CU, VU, conc, voids, fins
        self.door_polys = [(d, box(*d["bbox"])) for d in g["doors"]]
        self.win_segs = [w for w in g["win"] if "DASH" not in str(w[4]).upper()]
        self.wsegs = [s for s in g["wsegs"] if math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-4]
        self.wlines = [LineString([(s[0], s[1]), (s[2], s[3])]) for s in self.wsegs]
        self.piece_rects = [p.rect() for p in pieces]
        from shapely.strtree import STRtree
        self.piece_tree = STRtree(self.piece_rects) if self.piece_rects else None
        lifts = [v["poly"] for v in voids if "PR" in v["src"]]
        planters = [c["poly"] for c in conc if str(c["src"]).startswith("W-hatch")]
        self.PU = unary_union(planters).buffer(0.01) if planters else None
        self.LU = unary_union(lifts) if lifts else None
        self._tree = None
        self.stair_hulls = _stair_hulls(g)

    def _blockers(self):
        from shapely.strtree import STRtree
        if self._tree is None:
            # lines that do NOT close the building envelope (transparent to the outside test):
            #  - the long terrace / planter outline polyline on W (F02),
            #  - lines lying on concrete-hatched planter boxes (AR-CONC on W),
            #  - circles/arcs on W (round terrace columns / planters).
            outline = {pl["handle"] for pl in self.g.get("wpolys", [])
                       if pl["n"] >= 30 and max(pl["bbox"][2] - pl["bbox"][0], pl["bbox"][3] - pl["bbox"][1]) > 15}
            hatch = [c["poly"].buffer(0.02) for c in self.conc if str(c["src"]).startswith("W-hatch")]
            HU = unary_union(hatch) if hatch else None
            obs = []
            self.transparent = 0
            for sg, ln in zip(self.wsegs, self.wlines):
                if (sg[5] == "LWPOLYLINE" and sg[4] in outline) or (HU is not None and HU.contains(ln)):
                    self.transparent += 1
                    continue
                obs.append(ln)
            obs += [LineString([(w[0], w[1]), (w[2], w[3])]) for w in self.win_segs
                    if math.hypot(w[2] - w[0], w[3] - w[1]) > 1e-4]
            for a in self.g["winarcs"]:
                pts = _arc_pts(a[0], a[1], a[2], a[3], a[4])
                if len(pts) >= 2:
                    obs.append(LineString(pts))
            self._obs = obs
            self._tree = STRtree(obs)
        return self._tree, self._obs

    def visible(self, p, q):
        tree, obs = self._blockers()
        ln = LineString([p, q])
        return not any(obs[int(k)].intersects(ln) for k in tree.query(ln))

    def visible_label(self, pt, rmax=8.0):
        """Nearest room label (layer TEXT / -A-TEXT) seen from pt without crossing W/WIN."""
        cands = sorted((math.hypot(t["x"] - pt[0], t["y"] - pt[1]), k) for k, t in enumerate(self.g["texts"])
                       if abs(t["x"] - pt[0]) < rmax and abs(t["y"] - pt[1]) < rmax)
        for dist, k in cands[:6]:
            t = self.g["texts"][k]
            if dist <= rmax and self.visible(pt, (t["x"], t["y"])):
                return t["text"]
        return None

    def in_stair(self, pt):
        P = Point(pt)
        for H in self.stair_hulls:
            if H.contains(P):
                return True
            if H.buffer(1.4).contains(P):
                from shapely.ops import nearest_points
                q = nearest_points(H, P)[0]
                if self.visible(pt, (q.x, q.y)):
                    return True
        return False

    def ray_escapes(self, pt, nv, length=80.0):
        """True if a ray from pt along nv leaves the plan without hitting W/WIN geometry."""
        return self.visible(pt, (pt[0] + nv[0] * length, pt[1] + nv[1] * length))


def _seg_td(D, s):
    t1, d1 = D.td(s[0], s[1])
    t2, d2 = D.td(s[2], s[3])
    return t1, d1, t2, d2


def _jamb_capped(ctx, D, t, d0, d1):
    """Is there a W segment across the wall band [d0,d1] at station t (a jamb / end cap)?"""
    thk = d1 - d0
    for s in ctx.wsegs:
        t1, e1, t2, e2 = _seg_td(D, s)
        if abs(t1 - t) < 0.012 and abs(t2 - t) < 0.012:
            lo, hi = min(e1, e2), max(e1, e2)
            if lo <= d0 + 0.2 * thk and hi >= d1 - 0.2 * thk and hi - lo <= thk + 0.15:
                return True
    return False


def _w_inside(ctx, R):
    """Any W segment running through the inside of rectangle R (not just touching it)?"""
    core = R.buffer(-0.01)
    if core.is_empty:
        return False
    return any(ln.intersects(core) for ln in ctx.wlines)


def _abutters(ctx, R, piece_ids_exclude, di):
    """Non-parallel pieces touching R (but not overlapping it)."""
    out = []
    Rb = R.buffer(0.015)
    for k, (p, pr) in enumerate(zip(ctx.pieces, ctx.piece_rects)):
        if k in piece_ids_exclude or p.di == di:
            continue
        if pr.intersects(Rb) and pr.intersection(R).area < 0.1 * max(R.area, 1e-9):
            out.append(k)
    return out


def classify_gap(ctx, p, q):
    """What lies between two collinear pieces p (before) and q (after) of the same wall line."""
    D = p.D
    s, e = p.e, q.s
    gap = e - s
    d0, d1 = (p.d0 + q.d0) / 2, (p.d1 + q.d1) / 2
    if gap < 0.003:
        return "contiguous", {}
    R = D.rect(s, e, d0, d1)
    if ctx.CU is not None and R.intersection(ctx.CU).area > 0.2 * R.area:
        return "column", {}
    if ctx.VU is not None and R.intersection(ctx.VU).area > 0.2 * R.area:
        return "void", {}
    other = [k for k, pr in enumerate(ctx.piece_rects)
             if ctx.pieces[k] is not p and ctx.pieces[k] is not q and pr.intersection(R).area > 0.1 * R.area]
    faces = ctx.faces[p.di]
    lo_cov = covers(faces[p.lo]["ivs"], s, e) and p.lo == q.lo
    hi_cov = covers(faces[p.hi]["ivs"], s, e) and p.hi == q.hi
    if gap <= JUNCTION_MAX and not other:
        ab = _abutters(ctx, R, set(), p.di)
        if (lo_cov or hi_cov) and ab:
            return "junction", {"abutters": len(ab)}
        if not lo_cov and not hi_cov and len(ab) >= 2:
            # crossing (X) junction: walls abut from both sides
            sides = set()
            for k in ab:
                c = ctx.piece_rects[k].centroid
                sides.add(D.td(c.x, c.y)[1] > (d0 + d1) / 2)
            if len(sides) == 2:
                return "junction", {"abutters": len(ab), "cross": True}
    if gap > MAX_OPENING or other:
        return "break", {"why": "too long" if gap > MAX_OPENING else "other wall inside gap"}
    aligned = (p.lo == q.lo and p.hi == q.hi
               and _faces_end_at(faces, (p.lo, p.hi), s, +1) and _faces_end_at(faces, (p.lo, p.hi), e, -1))
    return _gap_opening(ctx, D, s, e, d0, d1, excl=(p, q),
                        capped=(_jamb_capped(ctx, D, s, d0, d1), _jamb_capped(ctx, D, e, d0, d1)),
                        aligned=aligned)


def _faces_end_at(faces, idxs, t, direction, tol=0.02):
    """Do ALL the given face lines stop at station t?  direction +1: the face ends at t and does
    not continue beyond it; -1: the face starts at t (nothing before it)."""
    for fi in idxs:
        ivs = faces[fi]["ivs"]
        if direction > 0:
            ok = any(abs(b - t) <= tol for a, b in ivs) and not any(a < t + 0.03 and b > t + 0.03 for a, b in ivs)
        else:
            ok = any(abs(a - t) <= tol for a, b in ivs) and not any(a < t - 0.03 and b > t - 0.03 for a, b in ivs)
        if not ok:
            return False
    return True


def _gap_opening(ctx, D, s, e, d0, d1, excl=(), capped=(False, False), aligned=False,
                 door_wall=None):
    """Is the empty stretch [s, e] of the wall band [d0, d1] an OPENING (bridged for the gross
    length only)?  -> ('door' | 'window' | 'opening', info) or ('break', {'why': ...}).
    excl = pieces bounding the gap (ignored by the parallel-wall tests); capped = whether each
    end is closed by a jamb line; aligned = both faces stop exactly at both ends (an uncapped
    doorway); door_wall = required wall thickness of a matching door block (concrete-side gaps)."""
    gap = e - s
    R = D.rect(s, e, d0, d1)
    ex = {id(x) for x in excl}
    # a parallel wall running alongside the gap -> not an opening (e.g. nib-to-nib on a facade)
    Rs = R.buffer(0.03, join_style=2)
    for k, pr in enumerate(ctx.piece_rects):
        pk = ctx.pieces[k]
        if id(pk) in ex or _angdiff(pk.D.ang, D.ang) > 5:
            continue
        inter = pr.intersection(Rs)
        if inter.area > 1e-6:
            ts = [D.td(x, y)[0] for x, y in getattr(inter, "exterior", inter.envelope.exterior).coords]
            if min(max(ts), e) - max(min(ts), s) >= 0.5 * gap:
                return "break", {"why": "parallel wall alongside gap"}
    # ---- openings (bridged for the GROSS length only) ----
    Rb = R.buffer(0.06)
    best = None
    for d, dp in ctx.door_polys:
        if door_wall is not None and abs(d["wall"] - door_wall) > 0.06:
            continue
        if dp.intersects(Rb):
            ts = [D.td(x, y)[0] for x, y in dp.exterior.coords]
            ov = min(max(ts), e) - max(min(ts), s)
            # the block's insertion point sits on a jamb of ITS opening (rejects a neighbour's swing)
            dist = R.distance(Point(d["x"], d["y"]))
            if ov >= 0.5 * gap and dist <= 0.08 and (best is None or dist < best[0]):
                best = (dist, d)
    if best is not None:
        d = best[1]
        return "door", {"block": d["name"], "door_width": d["width"], "handle": d["handle"]}
    wcov = []
    for w in ctx.win_segs:
        t1, e1, t2, e2 = _seg_td(D, w)
        if abs(e1 - e2) > 0.02:
            continue
        if d0 - 0.06 <= (e1 + e2) / 2 <= d1 + 0.06:
            wcov.append((min(t1, t2), max(t1, t2)))
    if wcov and cover_len(merge_intervals(wcov), s, e) >= 0.5 * gap:
        return "window", {}
    for cx, cy, r, lay in ctx.g["pr_arcs"]:
        tc, dc = D.td(cx, cy)
        if s - 0.15 <= tc <= e + 0.15 and d0 - 0.2 <= dc <= d1 + 0.2 and 0.5 <= r <= 1.6:
            return "door", {"block": f"arc on {lay}", "door_width": round(r, 2)}
    # plain opening: ends jamb-capped (or both faces stop clean at both ends), nothing inside,
    # no glazing / wall running alongside
    near = []
    for w in ctx.win_segs:
        t1, e1, t2, e2 = _seg_td(D, w)
        if abs(e1 - e2) <= 0.02 and d0 - 0.35 <= (e1 + e2) / 2 <= d1 + 0.35:
            near.append((min(t1, t2), max(t1, t2)))
    if near and cover_len(merge_intervals(near), s, e) >= 0.3 * gap:
        return "break", {"why": "glazing alongside gap (facade nib line)"}
    Rw = R.buffer(0.15, join_style=2)
    for k, pr in enumerate(ctx.piece_rects):
        pk = ctx.pieces[k]
        if id(pk) in ex or _angdiff(pk.D.ang, D.ang) > 5:
            continue
        if pr.intersection(Rw).area > 0.05 * R.area:
            return "break", {"why": "parallel wall close to gap"}
    if _w_inside(ctx, R):
        return "break", {"why": "W lines inside the gap"}
    if all(capped):
        return "opening", {"note": "jamb-capped gap without door block/window"}
    if aligned and gap <= UNCAPPED_OPENING_MAX:
        return "opening", {"note": "both faces stop clean at both ends (uncapped doorway) - no door block/window"}
    return "break", {"why": "no opening found"}


def bridge_to_concrete(ctx, runs):
    """A door / window / lift opening whose far jamb is a COLUMN or CORE face (no masonry piece on
    that side): extend the run's GROSS length over the opening up to the concrete face.  The
    concrete must span the wall band; the gap must be empty and hold a door block of the same wall
    thickness, glazing, or start at a jamb-capped wall end.  Returns the number of bridges."""
    if ctx.CU is None:
        return 0
    n = 0
    for r in runs:
        D = r["D"]
        d0, d1 = r["d0"], r["d1"]
        thk = d1 - d0
        for side in (0, 1):
            t_end = r["s"] if side == 0 else r["e"]
            sg = -1 if side == 0 else 1
            a, b = sorted((t_end, t_end + sg * MAX_OPENING))
            probe = D.rect(a, b, d0 + 0.25 * thk, d1 - 0.25 * thk)
            hit = probe.intersection(ctx.CU)
            if hit.is_empty or hit.area < 1e-5:
                continue
            ts = [t for t0, t1, _ in _t_ranges(hit, D) for t in (t0, t1)]
            if not ts:
                continue
            tc = max(ts) if side == 0 else min(ts)
            gap = abs(tc - t_end)
            if not (0.30 <= gap <= MAX_OPENING):
                continue
            # the concrete must close the whole band just beyond tc (a column face across the wall)
            strip = D.rect(min(tc, tc + sg * 0.03), max(tc, tc + sg * 0.03), d0, d1)
            if strip.intersection(ctx.CU).area < 0.6 * strip.area:
                continue
            s, e = sorted((t_end, tc))
            G = D.rect(s, e, d0, d1)
            if ctx.VU is not None and G.intersection(ctx.VU).area > 0.2 * G.area:
                continue
            own = {id(ctx.pieces[k]) for k in r["pieces"]}
            if any(id(ctx.pieces[int(k)]) not in own and ctx.piece_rects[int(k)].intersection(G).area > 0.1 * G.area
                   for k in ctx.piece_tree.query(G)):
                continue
            capped = _jamb_capped(ctx, D, t_end, d0, d1)
            kind, info = _gap_opening(ctx, D, s, e, d0, d1, excl=[ctx.pieces[k] for k in r["pieces"]],
                                      capped=(capped, capped), door_wall=thk)
            if kind == "break":
                continue
            gp = {"s": s, "e": e, "type": kind, "to_concrete": True, **info}
            r["gaps"].append(gp)
            r["openings"].append(gp)
            if side == 0:
                r["s"] = tc
            else:
                r["e"] = tc
            r.setdefault("concrete_jamb", []).append(side)
            n += 1
    return n


def build_runs(ctx):
    """Chain collinear pieces (same faces/offsets) across junctions and openings."""
    by_line = defaultdict(list)
    for k, p in enumerate(ctx.pieces):
        by_line[(p.di, p.lo, p.hi)].append(k)
    runs = []
    for (di, lo, hi), ks in by_line.items():
        ks.sort(key=lambda k: ctx.pieces[k].s)
        cur = None
        for k in ks:
            p = ctx.pieces[k]
            if cur is not None:
                prev = ctx.pieces[cur["pieces"][-1]]
                kind, info = classify_gap(ctx, prev, p)
                if kind in ("contiguous", "junction", "door", "window", "opening"):
                    cur["gaps"].append({"s": prev.e, "e": p.s, "type": kind, **info})
                    cur["pieces"].append(k)
                    continue
                cur["end_reason"] = kind
            cur = {"di": di, "lo": lo, "hi": hi, "pieces": [k], "gaps": [], "end_reason": None}
            runs.append(cur)
    for r in runs:
        ps = [ctx.pieces[k] for k in r["pieces"]]
        r["D"] = ps[0].D
        w = sum(p.e - p.s for p in ps)
        r["d0"] = sum(p.d0 * (p.e - p.s) for p in ps) / w
        r["d1"] = sum(p.d1 * (p.e - p.s) for p in ps) / w
        r["s"], r["e"] = ps[0].s, ps[-1].e
        r["ext"] = [0.0, 0.0]          # corner extensions at start / end
        r["solid"] = [(p.s, p.e) for p in ps] + [(gp["s"], gp["e"]) for gp in r["gaps"]
                                                 if gp["type"] in ("junction", "contiguous")]
        r["openings"] = [gp for gp in r["gaps"] if gp["type"] in ("door", "window", "opening")]
    return runs


def _line_intersection(Da, da, Db, db):
    """Intersection of centre-lines {p: p.n_a = da} and {p: p.n_b = db}."""
    a1, b1 = Da.n
    a2, b2 = Db.n
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-6:
        return None
    return ((da * b2 - db * b1) / det, (a1 * db - a2 * da) / det)


def extend_corners(ctx, runs):
    """L-corners: both walls end near the crossing of their centre-lines and the corner
    square is closed by the outer faces -> extend each to the centre-line crossing."""
    ends = []
    for i, r in enumerate(runs):
        ends.append((i, 0))
        ends.append((i, 1))
    done = set()
    n_corners = 0
    for i, side_a in ends:
        if (i, side_a) in done:
            continue
        A = runs[i]
        Da = A["D"]
        ca = (A["d0"] + A["d1"]) / 2
        ta = A["s"] if side_a == 0 else A["e"]
        best = None
        for j, B in enumerate(runs):
            if j == i or B["di"] == A["di"]:
                continue
            Db = B["D"]
            if _angdiff(Da.ang, Db.ang) < 20:
                continue
            cb = (B["d0"] + B["d1"]) / 2
            X = _line_intersection(Da, ca, Db, cb)
            if X is None:
                continue
            sin = abs(math.sin(math.radians(Da.ang - Db.ang)))
            tXa, _ = Da.td(*X)
            tXb, _ = Db.td(*X)
            ta_lim = (B["d1"] - B["d0"]) / 2 / sin + 0.03
            tb_lim = (A["d1"] - A["d0"]) / 2 / sin + 0.03
            # A's end must lie just before X (outward), within half B's thickness
            da_ = (tXa - ta) if side_a == 1 else (ta - tXa)
            if not (-0.01 <= da_ <= ta_lim):
                continue
            for side_b in (0, 1):
                tb = B["s"] if side_b == 0 else B["e"]
                db_ = (tXb - tb) if side_b == 1 else (tb - tXb)
                if -0.01 <= db_ <= tb_lim and (j, side_b) not in done:
                    if ctx.CU is not None and ctx.CU.contains(Point(X)):
                        continue
                    # outer faces must close the corner: one face of A covers the extension
                    fa = ctx.faces[A["di"]]
                    half_b = 0.5 * (B["d1"] - B["d0"]) / sin
                    s0, e0 = (ta, max(ta, tXa) + half_b) if side_a == 1 else (min(ta, tXa) - half_b, ta)
                    if not (covers(fa[A["lo"]]["ivs"], s0, e0, 0.02) or covers(fa[A["hi"]]["ivs"], s0, e0, 0.02)):
                        continue
                    # the extensions must not run into a third wall (composite piers, nibs)
                    own = set(A["pieces"]) | set(B["pieces"])
                    ext_a = Da.rect(min(ta, tXa), max(ta, tXa), A["d0"], A["d1"])
                    ext_b = Db.rect(min(tb, tXb), max(tb, tXb), B["d0"], B["d1"])
                    clash = False
                    for ex in (ext_a, ext_b):
                        if ex.area < 1e-6:
                            continue
                        for k in ctx.piece_tree.query(ex):
                            k = int(k)
                            if k not in own and ctx.piece_rects[k].intersection(ex).area > 2e-4:
                                clash = True
                                break
                        if clash:
                            break
                    if clash:
                        continue
                    cand = (abs(da_) + abs(db_), j, side_b, tXa, tXb)
                    if best is None or cand < best:
                        best = cand
        if best is None:
            continue
        _, j, side_b, tXa, tXb = best
        B = runs[j]
        if side_a == 0:
            A["ext"][0] += A["s"] - tXa
            A["s"] = tXa
        else:
            A["ext"][1] += tXa - A["e"]
            A["e"] = tXa
        if side_b == 0:
            B["ext"][0] += B["s"] - tXb
            B["s"] = tXb
        else:
            B["ext"][1] += tXb - B["e"]
            B["e"] = tXb
        A.setdefault("corners", []).append(j)
        B.setdefault("corners", []).append(i)
        done.add((i, side_a))
        done.add((j, side_b))
        n_corners += 1
    return n_corners


def _clip(ivs, a, b):
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
            if b - a < 0.01 and len(bounds) > 2:
                continue
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


# ============================================================================
# 5. spaces on both sides of every wall -> classification
# ============================================================================
OUTDOOR_WORDS = ("تراس", "زرع", "سماوي")
WET_WORDS = ("حمام", "مطبخ", "بوفيه", "wc")


def _stair_hulls(g):
    """One convex hull per cluster of stair lines (layer ST)."""
    lines = [LineString([(a, b), (c, d)]) for a, b, c, d in g["st"] if math.hypot(c - a, d - b) > 1e-4]
    if not lines:
        return []
    blobs = unary_union([ln.buffer(0.6) for ln in lines])
    out = []
    for bl in getattr(blobs, "geoms", [blobs]):
        members = [ln for ln in lines if bl.contains(ln.centroid)]
        if len(members) >= 4:
            out.append(unary_union(members).convex_hull)
    return out


def classify_runs(ctx, runs):
    """Look at both sides of every wall: outside (ray escapes / terrace label), shaft void,
    lift well, stair hall, room (nearest visible room label)."""
    for r in runs:
        D = r["D"]
        sides = {0: Counter(), 1: Counter()}
        labels = {0: Counter(), 1: Counter()}
        flags = {0: Counter(), 1: Counter()}
        stations = []
        for s, e in r["solid"] + [(gp["s"], gp["e"]) for gp in r["openings"]]:
            n = max(3, int((e - s) / 0.25))
            stations += [s + (e - s) * (i + 0.5) / n for i in range(n)]
        for t in stations:
            for side, d, sgn in ((0, r["d0"] - 0.03, -1), (1, r["d1"] + 0.03, 1)):
                pt = D.xy(t, d)
                P = Point(pt)
                if ctx.PU is not None and ctx.PU.contains(P):
                    sides[side]["out"] += 1             # planter box (AR-CONC hatch on W) = outside
                    continue
                if ctx.CU is not None and ctx.CU.contains(P):
                    sides[side]["concrete"] += 1
                    continue
                if ctx.piece_tree is not None and any(ctx.piece_rects[int(k)].contains(P)
                                                      for k in ctx.piece_tree.query(P)):
                    sides[side]["solid"] += 1      # another wall / nib touches here
                    continue
                if ctx.LU is not None and ctx.LU.contains(P):
                    sides[side]["void"] += 1
                    flags[side]["lift"] += 1
                    continue
                if ctx.VU is not None and ctx.VU.contains(P):
                    sides[side]["void"] += 1
                    continue
                lab = ctx.visible_label(pt)
                outdoor_lab = bool(lab) and any(w in lab for w in OUTDOOR_WORDS)
                if outdoor_lab or ctx.ray_escapes(pt, (D.n[0] * sgn, D.n[1] * sgn)):
                    sides[side]["out"] += 1
                    if outdoor_lab:
                        labels[side][lab] += 1
                    continue
                sides[side]["room"] += 1
                if lab:
                    labels[side][lab] += 1
                    if any(w in lab.lower() for w in WET_WORDS):
                        flags[side]["wet"] += 1
                if ctx.in_stair(pt):
                    flags[side]["stair"] += 1
        r["sides"] = []
        for side in (0, 1):
            tot = sum(v for k, v in sides[side].items() if k != "solid") or 1
            r["sides"].append({"share": {k: round(v / tot, 2) for k, v in sides[side].items() if k != "solid"},
                               "labels": [k for k, _ in labels[side].most_common(3)],
                               "stair": flags[side]["stair"] / tot >= 0.3,
                               "lift": flags[side]["lift"] / tot >= 0.3,
                               "wet": flags[side]["wet"] / tot >= 0.3})
        out = [r["sides"][k]["share"].get("out", 0) for k in (0, 1)]
        void = [r["sides"][k]["share"].get("void", 0) for k in (0, 1)]
        if max(out) >= 0.5:
            kind = "exterior"
        elif any(r["sides"][k]["stair"] or r["sides"][k]["lift"] for k in (0, 1)):
            kind = "stair_lift"
        elif max(void) >= 0.5:
            kind = "shaft"
        else:
            kind = "interior"
        r["kind"] = kind
        r["mixed"] = (0.2 <= max(out) < 0.5) or (0.25 <= max(void) < 0.5 and kind != "shaft")


# ============================================================================
# 6. driver
# ============================================================================
NOMINAL = (0.10, 0.12, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60)
FAMILY_TOL = 0.016


def family(t):
    best = min(NOMINAL, key=lambda n: abs(n - t))
    return f"{best:.2f}" if abs(best - t) <= FAMILY_TOL else "other"


def clean_wsegs(g):
    """Drop W polylines that are not wall faces: small closed many-vertex shapes (door-frame
    profiles drawn on W) and degenerate dots.  Returns (segments, ignored list)."""
    bad, ignored = set(), []
    for pl in g.get("wpolys", []):
        x0, y0, x1, y1 = pl["bbox"]
        big = max(x1 - x0, y1 - y0)
        if big < 0.02:
            bad.add(pl["handle"])
            ignored.append({"handle": pl["handle"], "why": "degenerate polyline (<2 cm)"})
        elif pl["closed"] and pl["n"] > 6 and big < 0.45:
            bad.add(pl["handle"])
            ignored.append({"handle": pl["handle"], "why": f"small {pl['n']}-vertex closed profile (door frame?)"})
    segs = [s for s in g["wsegs"] if not (s[5] == "LWPOLYLINE" and s[4] in bad)
            and math.hypot(s[2] - s[0], s[3] - s[1]) > 1e-4]
    # W lines lying ON a glazing line (window frame re-drawn on W, F02-F08 east facade y 29.6-32.1,
    # F02 also y 32.7-35.2) are not wall faces: cut out overlaps >= 0.30 m with continuous WIN lines.
    wins = [w for w in g["win"] if "DASH" not in str(w[4]).upper() and math.hypot(w[2] - w[0], w[3] - w[1]) > 0.3]
    out = []
    for s in segs:
        L = math.hypot(s[2] - s[0], s[3] - s[1])
        D = Dir(math.degrees(math.atan2(s[3] - s[1], s[2] - s[0])))
        t1, dd = D.td(s[0], s[1])
        t2, _ = D.td(s[2], s[3])
        lo, hi = min(t1, t2), max(t1, t2)
        ov = []
        if L >= 0.3:
            for w in wins:
                a1, e1 = D.td(w[0], w[1])
                a2, e2 = D.td(w[2], w[3])
                if abs(e1 - dd) <= 0.01 and abs(e2 - dd) <= 0.01:
                    a, b = max(lo, min(a1, a2)), min(hi, max(a1, a2))
                    if b - a > 0:
                        ov.append((a, b))
        ov = [iv for iv in merge_intervals(ov, tol=0.005) if iv[1] - iv[0] >= 0.30]
        if not ov:
            out.append(s)
            continue
        keep = [(lo, hi)]
        for a, b in ov:
            keep = _subtract(keep, a, b)
        ignored.append({"handle": s[4], "why": f"W line on a WIN glazing line ({sum(b - a for a, b in ov):.2f} m cut)"})
        for a, b in keep:
            if b - a > 0.005:
                p, q = D.xy(a, dd), D.xy(b, dd)
                out.append((p[0], p[1], q[0], q[1], s[4], s[5]))
    return out, ignored


def detect(g, height=3.0):
    log = Counter()
    g = dict(g)
    g["wsegs"], ign = clean_wsegs(g)
    g["w_ignored"] = list(g["w_ignored"]) + ign
    dirs = cluster_directions(g["wsegs"])
    conc = concrete_polys(g)
    CU = unary_union([c["poly"] for c in conc]) if conc else None
    voids, fins = void_polys(g, [D for D, _ in dirs])
    VU = unary_union([v["poly"] for v in voids]) if voids else None
    pieces, faces = make_pieces(g, dirs, CU, VU, log)
    ctx = Ctx(g, dirs, pieces, faces, CU, VU, conc, voids, fins)
    runs = build_runs(ctx)
    n_bridges = bridge_to_concrete(ctx, runs)
    n_corners = extend_corners(ctx, runs)
    runs, n_cuts = split_at_junctions(ctx, runs)
    classify_runs(ctx, runs)
    return ctx, runs, {"n_corners": n_corners, "n_junction_cuts": n_cuts, "n_concrete_jamb_bridges": n_bridges,
                       **{k: round(v, 3) for k, v in log.items()}}


def _reading_order(runs):
    def key(r):
        D = r["D"]
        c = (r["d0"] + r["d1"]) / 2
        mx, my = D.xy((r["s"] + r["e"]) / 2, c)
        return (-round(my / 1.5), mx)
    return sorted(runs, key=key)


def wall_records(ctx, runs, height):
    recs = []
    runs = [r for r in runs if r["e"] - r["s"] >= 0.005]
    for i, r in enumerate(_reading_order(runs), 1):
        D = r["D"]
        c = (r["d0"] + r["d1"]) / 2
        thk = r["d1"] - r["d0"]
        p1, p2 = D.xy(r["s"], c), D.xy(r["e"], c)
        gross = r["e"] - r["s"]
        solid = sum(e - s for s, e in r["solid"]) + r["ext"][0] + r["ext"][1]
        op_w = sum(gp["e"] - gp["s"] for gp in r["openings"])
        reasons, notes = [], []
        fam = family(thk)
        if fam == "other":
            reasons.append(f"thickness {thk:.3f} m is not a standard family (composite pier / nib / drafting?)")
        if gross < 0.10:
            reasons.append("tiny fragment (<0.10 m)")
        elif gross < 0.30:
            notes.append("short piece (<0.30 m): nib / stub / pier return")
        if thk >= 0.35 and r["kind"] != "exterior" and fam != "other":
            reasons.append("thick wall (>=0.35) like the shear walls - concrete or masonry?")
        if any(gp["type"] == "opening" for gp in r["openings"]):
            reasons.append("bridged a door-less gap (no door block/window) - opening or missing door?")
        if any(gp.get("to_concrete") for gp in r["openings"]):
            notes.append("gross bridged an opening up to a column/core face (concrete jamb)")
        if r.get("mixed"):
            reasons.append("one side is partly outside/void - classification mixed")
        if not r["sides"][0]["share"] and not r["sides"][1]["share"] and gross >= 0.10:
            reasons.append("both faces touch other walls (no room on either side): "
                           "a narrow space between two walls, or one composite block?")
        if r["kind"] == "exterior" and any(gp["type"] == "window" for gp in r["openings"]):
            notes.append("facade line with glazing bays: gross includes the windows")
        if r["ext"][0] > 1e-6 or r["ext"][1] > 1e-6:
            notes.append("L-corner: extended to the centre-line crossing")
        rec = {
            "id": f"W{i}",
            "x1": round(p1[0], 3), "y1": round(p1[1], 3), "x2": round(p2[0], 3), "y2": round(p2[1], 3),
            "angle": round(D.ang, 2),
            "thickness": round(thk, 3), "family": fam,
            "length_gross": round(gross, 3), "length_net": round(solid, 3),
            "openings_width": round(op_w, 3),
            "kind": r["kind"],
            "needs_check": bool(reasons),
            "reason": "; ".join(reasons),
            "notes": "; ".join(notes),
            "openings": [{"type": gp["type"], "width": round(gp["e"] - gp["s"], 3),
                          "at": [round(v, 3) for v in D.xy((gp["s"] + gp["e"]) / 2, c)],
                          **({"block": gp["block"]} if "block" in gp else {}),
                          **({"door_width": gp["door_width"]} if "door_width" in gp else {}),
                          **({"to_concrete": True} if gp.get("to_concrete") else {})}
                         for gp in r["openings"]],
            "junctions": sum(1 for gp in r["gaps"] if gp["type"] == "junction"),
            "corner_ext": [round(v, 3) for v in r["ext"]],
            "end_reason": r.get("end_reason"),
            "sides": r["sides"],
            "n_pieces": len(r["pieces"]),
            "_band": [round(r["d0"], 4), round(r["d1"], 4)], "_t": [round(r["s"], 4), round(r["e"], 4)],
        }
        recs.append(rec)
    return recs


def totals(recs, height):
    tot = defaultdict(lambda: {"n": 0, "length_gross": 0.0, "length_net": 0.0, "openings_width": 0.0})
    for w in recs:
        for key in (f"{w['family']}|{w['kind']}", f"{w['family']}|ALL", f"ALL|{w['kind']}", "ALL|ALL"):
            t = tot[key]
            t["n"] += 1
            t["length_gross"] += w["length_gross"]
            t["length_net"] += w["length_net"]
            t["openings_width"] += w["openings_width"]
    out = {}
    for k in sorted(tot):
        v = tot[k]
        out[k] = {"n": v["n"], "length_gross": round(v["length_gross"], 2), "length_net": round(v["length_net"], 2),
                  "openings_width": round(v["openings_width"], 2),
                  "area_gross_at_h": round(v["length_gross"] * height, 2),
                  "area_net_at_h": round(v["length_net"] * height, 2)}
    return out


def thickness_histogram(recs):
    h = Counter()
    for w in recs:
        h[f"{w['thickness']:.2f}"] += w["length_net"]
    return {k: round(v, 2) for k, v in sorted(h.items())}


def dim_crosscheck(ctx, recs):
    """Compare the architect's DIMENSIONs (layer DIM) with the wall reading.

    Every linear dimension has two measured points (defpoint2/3).  Each point is classified:
      wall      - lies on a face of a wall record (band edge, within the record's length)
      wall_end  - a station along a wall running in the measuring direction: its end
      opening_jamb - ... or the jamb of an opening bridged in it (facade chains: piers, windows)
      concrete  - on the outline of a column / core (Etabs-col, COL)
      window    - on a WIN line
      face      - on a W face line that is not part of any wall record (pier step, cap, ...)
      axis      - on an axis line (layer X)
      none      - on nothing (e.g. the end of a chain on the dimension line itself)
    Dimensions <= 0.62 m whose two points bound one wall record are THICKNESS dimensions and
    are compared with the record's thickness."""
    g = ctx.g
    axes = [a for a in g.get("axes", []) if math.hypot(a[2] - a[0], a[3] - a[1]) > 1]
    conc_edges = unary_union([c["poly"].boundary for c in ctx.conc]) if ctx.conc else None
    win_lines = [LineString([(w[0], w[1]), (w[2], w[3])]) for w in ctx.win_segs
                 if math.hypot(w[2] - w[0], w[3] - w[1]) > 1e-4]
    stats = Counter()
    thick, unmatched_pts = [], []
    for dm in g["dims"]:
        if dm["type"] not in (0, 1):
            continue
        p2, p3 = dm["p2"], dm["p3"]
        ang = dm["angle"] if dm["type"] == 0 else math.degrees(math.atan2(p3[1] - p2[1], p3[0] - p2[0])) % 180.0
        Dm = Dir(ang)              # measuring direction
        Df = Dir(ang + 90.0)       # faces measured by this dimension run along Df
        kinds, recs_at = [], []
        for P in (p2, p3):
            tP, dP = Df.td(*P)
            hit = None
            for w in recs:
                if _angdiff(w["angle"], Df.ang) > 1.0:
                    continue
                Dw = Dir(w["angle"])
                tw, dw = Dw.td(*P)
                b0, b1 = w["_band"]
                t0, t1 = w["_t"]
                if (abs(dw - b0) <= 0.012 or abs(dw - b1) <= 0.012) and t0 - 0.05 <= tw <= t1 + 0.05:
                    hit = w
                    break
            if hit is not None:
                kinds.append("wall")
                recs_at.append(hit)
                continue
            recs_at.append(None)
            # a station ALONG a wall that runs in the measuring direction: wall end / jamb of a
            # bridged opening (facade chains measure piers and window widths this way)
            st = None
            for w in recs:
                if _angdiff(w["angle"], Dm.ang) > 1.0:
                    continue
                Dw = Dir(w["angle"])
                tw, dw = Dw.td(*P)
                b0, b1 = w["_band"]
                if not (b0 - 0.02 <= dw <= b1 + 0.02):
                    continue
                t0, t1 = w["_t"]
                if min(abs(tw - t0), abs(tw - t1)) <= 0.012:
                    st = "wall_end"
                    break
                for op in w["openings"]:
                    tc = Dw.td(*op["at"])[0]
                    if min(abs(tw - (tc - op["width"] / 2)), abs(tw - (tc + op["width"] / 2))) <= 0.012:
                        st = "opening_jamb"
                        break
                if st:
                    break
            if st:
                kinds.append(st)
                continue
            Pt = Point(P)
            if conc_edges is not None and conc_edges.distance(Pt) <= 0.015:
                kinds.append("concrete")
            elif any(ln.distance(Pt) <= 0.015 for ln in win_lines):
                kinds.append("window")
            elif any(ln.distance(Pt) <= 0.015 for ln in ctx.wlines):
                kinds.append("face")
            elif any(_angdiff(math.degrees(math.atan2(a[3] - a[1], a[2] - a[0])), Df.ang) < 1.0
                     and abs(Df.td(a[0], a[1])[1] - dP) <= 0.015 for a in axes):
                kinds.append("axis")
            else:
                kinds.append("none")
        for k in kinds:
            stats["end_" + k] += 1
        for k, P in zip(kinds, (p2, p3)):
            if k == "face":
                unmatched_pts.append({"at": [round(P[0], 3), round(P[1], 3)], "dim": round(dm["value"], 3)})
        val = dm["value"]
        if val <= GAP_MAX + 0.01 and recs_at[0] is not None and recs_at[0] is recs_at[1]:
            w = recs_at[0]
            ok = abs(w["thickness"] - val) <= 0.012
            thick.append({"value": round(val, 3), "wall": w["id"], "wall_thickness": w["thickness"], "ok": ok})
            stats["thickness_dims"] += 1
            stats["thickness_dims_ok" if ok else "thickness_dims_mismatch"] += 1
    return {"n_dims": len(g["dims"]), "stats": dict(stats), "thickness_dims": thick,
            "points_on_unused_W_faces": unmatched_pts[:60]}


def face_coverage(ctx, recs):
    """How much of the W linework is explained by the wall records.  A W segment is 'used' where
    it lies on a band edge of a wall record (within its length) or on a jamb/cap across a band.
    Unused W length (outside concrete / shaft boxes) points at walls the reader may have missed,
    single-line elements (terrace outline) or architectural details."""
    from shapely.strtree import STRtree
    edges = []
    for w in recs:
        D = Dir(w["angle"])
        t0, t1 = w["_t"]
        b0, b1 = w["_band"]
        rect = D.rect(t0, t1, b0, b1)
        edges.append(rect.boundary.buffer(0.015))
    tree = STRtree(edges) if edges else None
    mask = []
    if ctx.CU is not None:
        mask.append(ctx.CU.buffer(0.02))
    if ctx.VU is not None:
        mask.append(ctx.VU.buffer(0.02))
    if getattr(ctx, "PU", None) is not None:
        mask.append(ctx.PU.buffer(0.02))
    M = unary_union(mask) if mask else None
    total = used = masked = 0.0
    unused = []
    for sg, ln in zip(ctx.wsegs, ctx.wlines):
        L = ln.length
        total += L
        rem = ln
        if M is not None and ln.intersects(M):
            masked += ln.intersection(M).length
            rem = ln.difference(M)
        Lr = rem.length
        if Lr < 1e-6:
            continue
        cov = 0.0
        if tree is not None:
            parts = [edges[int(k)] for k in tree.query(rem)]
            if parts:
                cov = rem.intersection(unary_union(parts)).length
        used += min(cov, Lr)
        rest = Lr - min(cov, Lr)
        if rest > 0.25:
            unused.append({"handle": sg[4], "len": round(rest, 2),
                           "from": [round(sg[0], 2), round(sg[1], 2)], "to": [round(sg[2], 2), round(sg[3], 2)]})
    unused.sort(key=lambda u: -u["len"])
    return {"w_length": round(total, 2), "on_wall_records": round(used, 2),
            "on_concrete_shaft_planter": round(masked, 2),
            "unexplained": round(total - used - masked, 2), "largest_unexplained": unused[:25]}


def _sweep(a0, a1):
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


def overlap_check(recs):
    """Plan overlaps between wall bodies.  The centre-line L-corner rule makes the two walls
    of a corner overlap by a (tA/2 x tB/2) square while leaving the outer quarter empty (the
    volume is still exact); those are reported separately from real double counting."""
    from shapely.strtree import STRtree
    polys = [Dir(w["angle"]).rect(w["_t"][0], w["_t"][1], *w["_band"]) for w in recs]
    tree = STRtree(polys)
    tot, corner, pairs = 0.0, 0.0, []
    for i, p in enumerate(polys):
        for j in tree.query(p):
            j = int(j)
            if j <= i:
                continue
            a = p.intersection(polys[j]).area
            if a <= 1e-4:
                continue
            A, B = recs[i], recs[j]
            sin = max(abs(math.sin(math.radians(A["angle"] - B["angle"]))), 0.05)
            if (max(A["corner_ext"]) > 0 and max(B["corner_ext"]) > 0
                    and a <= (A["thickness"] / 2 + 0.01) * (B["thickness"] / 2 + 0.01) / sin):
                corner += a
                continue
            tot += a
            pairs.append((A["id"], B["id"], round(a, 4)))
    return {"overlap_area_m2": round(tot, 4), "corner_quarter_overlap_m2": round(corner, 4),
            "pairs": pairs[:60]}


# ============================================================================
# 7. review drawing
# ============================================================================
FAM_COLORS = {"0.10": "#ff7f0e", "0.12": "#d62728", "0.15": "#bcbd22", "0.20": "#9467bd",
              "0.25": "#1f77b4", "0.30": "#8c564b", "0.40": "#e377c2", "0.50": "#7f7f7f",
              "0.60": "#17becf", "other": "#000000"}
KIND_HATCH = {"exterior": "////", "shaft": "xxxx", "stair_lift": "....", "interior": None}


def render(res, ctx, out_png, zoom=None, dpi=110, show_ids=True):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly, Patch
    plt.rcParams["font.family"] = "Tahoma"
    g = ctx.g
    if zoom:
        w, h = zoom[2] - zoom[0], zoom[3] - zoom[1]
        fs = (16 * w / max(w, h) + 1.5, 16 * h / max(w, h) + 1.0)
    else:
        fs = (13, 28)
    fig, ax = plt.subplots(figsize=fs)
    for s in g["wsegs"]:
        ax.plot([s[0], s[2]], [s[1], s[3]], color="#555", lw=0.35, zorder=3)
    for wv in ctx.win_segs:
        ax.plot([wv[0], wv[2]], [wv[1], wv[3]], color="#17becf", lw=0.5, zorder=3)
    for a in g["winarcs"] + g["warcs"]:
        pts = _arc_pts(a[0], a[1], a[2], a[3], a[4])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#17becf", lw=0.5, zorder=3)
    for c in ctx.conc:
        planter = str(c["src"]).startswith("W-hatch")
        for gm in getattr(c["poly"], "geoms", [c["poly"]]):
            ax.add_patch(MPoly(list(gm.exterior.coords), closed=True, fc="#c7e9c0" if planter else "#2ca02c",
                               ec="#1a6b1a", alpha=0.45, lw=0.6, hatch="++" if planter else None, zorder=2))
    for v in ctx.voids:
        ax.add_patch(MPoly(list(v["poly"].exterior.coords), closed=True, fc="#ffbb78", ec="#ff7f0e",
                           alpha=0.5, lw=0.5, zorder=2))
    for d in g["doors"]:
        x0, y0, x1, y1 = d["bbox"]
        ax.add_patch(MPoly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True, fill=False,
                           ec="#9467bd", lw=0.4, ls=":", zorder=2))
    for w in res["walls"]:
        D = Dir(w["angle"])
        d0, d1 = w["_band"]
        s, e = w["_t"]
        col = FAM_COLORS.get(w["family"], "#000")
        poly = D.rect(s, e, d0, d1)
        ax.add_patch(MPoly(list(poly.exterior.coords), closed=True, fc=col, ec=col, alpha=0.75, lw=0.3,
                           hatch=KIND_HATCH.get(w["kind"]), zorder=4))
        for op in w["openings"]:
            ox, oy = op["at"]
            t0, _ = D.td(ox, oy)
            pr = D.rect(t0 - op["width"] / 2, t0 + op["width"] / 2, d0, d1)
            ax.add_patch(MPoly(list(pr.exterior.coords), closed=True, fc="white", ec=col, lw=0.6, ls="--",
                               zorder=5))
        if w["needs_check"]:
            ax.add_patch(MPoly(list(poly.buffer(0.06, join_style=2).exterior.coords), closed=True, fill=False,
                               ec="#ff00ff", lw=0.9, zorder=6))
        if show_ids:
            mx, my = (w["x1"] + w["x2"]) / 2, (w["y1"] + w["y2"]) / 2
            ax.text(mx, my, w["id"][1:], fontsize=(5.5 if not zoom else 8), ha="center", va="center",
                    color="black", zorder=7, clip_on=True,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec=col, lw=0.5, alpha=0.9))
    ax.set_aspect("equal")
    if zoom:
        ax.set_xlim(zoom[0], zoom[2])
        ax.set_ylim(zoom[1], zoom[3])
    else:
        ax.set_xlim(-2.5, 21.0)
        ax.set_ylim(-3.0, 41.5)
    ax.grid(True, lw=0.2, alpha=0.5)
    fams = sorted({w["family"] for w in res["walls"]})
    handles = [Patch(fc=FAM_COLORS.get(f, "#000"), label=f"t={f}") for f in fams]
    handles += [Patch(fc="white", ec="#333", hatch=h, label=k) for k, h in KIND_HATCH.items()]
    if any(str(c["src"]).startswith("W-hatch") for c in ctx.conc):
        handles.append(Patch(fc="#c7e9c0", hatch="++", label="planter (AR-CONC hatch on W)"))
    handles += [Patch(fc="#2ca02c", alpha=0.45, label="concrete (Etabs-col/COL)"),
                Patch(fc="#ffbb78", label="shaft/void"),
                Patch(fc="white", ec="#ff00ff", label="needs_check")]
    ax.legend(handles=handles, loc="upper right", fontsize=7, framealpha=0.9)
    T = res["totals"].get("ALL|ALL", {})
    ax.set_title(f"{res['floor']} {res['name_ar']} {res['level']:+.2f}  walls={T.get('n', 0)}  "
                 f"gross={T.get('length_gross', 0):.2f} m  net={T.get('length_net', 0):.2f} m  "
                 f"(local frame, centre-line)", fontsize=10)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ============================================================================
# 8. public API + CLI
# ============================================================================
def read_walls(floor, height=3.0, use_cache=True, with_ctx=False):
    """Run the wall reader on one floor (int floor_no or Floor). Returns a JSON-able dict."""
    fl = get_floor(floor) if isinstance(floor, int) else floor
    g = load_geometry(fl, use_cache=use_cache)
    ctx, runs, diag = detect(g, height)
    recs = wall_records(ctx, runs, height)
    res = {
        "floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
        "source": {"file": fl.file.name, "sheet_index": fl.sheet_index},
        "frame": "local (diwan_common): rotation -10 deg, origin = min corner of Etabs-col",
        "method": "face pairing of layer W; centre-line lengths; T-junctions to through-wall; "
                  "L-corners to centre-line crossing; net excludes openings; split at concrete",
        "height_assumed": height,
        "storey_height": STOREY_HEIGHT,
        "walls": recs,
        "totals": totals(recs, height),
        "thickness_histogram_net": thickness_histogram(recs),
        "diagnostics": {**diag,
                        "w_segments_raw": len(g["wsegs"]), "w_segments_used": len(ctx.g["wsegs"]),
                        "w_arcs": len(g["warcs"]),
                        "w_hatches": [{"pattern": h["pattern"], "handle": h["handle"]} for h in g["whatch"]],
                        "w_inserts": dict(Counter(i["name"] for i in g["w_inserts"])),
                        "w_ignored": ctx.g["w_ignored"],
                        "directions": [round(D.ang, 2) for D, _ in ctx.dirs],
                        "concrete_polys": len(ctx.conc), "voids": len(ctx.voids), "fins": len(ctx.fins),
                        "stair_zones": len(ctx.stair_hulls),
                        "doors_blocks": len(g["doors"]),
                        "doors_matched": sum(1 for w in recs for o in w["openings"] if o["type"] == "door"),
                        },
    }
    res["openings_summary"] = openings_summary(recs)
    res["curves"] = curves_summary(g)
    res["dim_crosscheck"] = dim_crosscheck(ctx, recs)
    res["overlap_check"] = overlap_check(recs)
    res["face_coverage"] = face_coverage(ctx, recs)
    if with_ctx:
        return res, ctx
    return res


def _same_wall(a, b, tol=0.012):
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


def _json_default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
    except Exception:
        pass
    raise TypeError(type(o))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diwan wall reader (masonry basis) -> output/walls/")
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (default: all 2..8)")
    ap.add_argument("--height", type=float, default=3.0, help="wall height for indicative areas (m)")
    ap.add_argument("--zoom", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                    help="also write a zoomed review PNG (local m)")
    ap.add_argument("--no-cache", action="store_true", help="re-read the DXF (ignore geometry cache)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--dpi", type=int, default=120)
    a = ap.parse_args(argv)
    floors = a.floors or [f.floor_no for f in all_floors()]
    WALL_OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for n in floors:
        res, ctx = read_walls(n, height=a.height, use_cache=not a.no_cache, with_ctx=True)
        js = WALL_OUT / f"{res['floor']}.json"
        js.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
        if not a.no_png:
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls.png", dpi=a.dpi)
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls_south.png", zoom=(-1.5, -2.5, 20.5, 21.0), dpi=a.dpi)
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls_north.png", zoom=(-1.5, 19.0, 20.5, 41.0), dpi=a.dpi)
        if a.zoom:
            z = "_".join(f"{v:g}" for v in a.zoom)
            render(res, ctx, WALL_OUT / f"{res['floor']}_walls_zoom_{z}.png", zoom=a.zoom, dpi=a.dpi)
        T = res["totals"]
        summary[res["floor"]] = {"level": res["level"], "totals": T,
                                 "thickness_histogram_net": res["thickness_histogram_net"],
                                 "needs_check": sum(1 for w in res["walls"] if w["needs_check"]),
                                 "diagnostics": {k: v for k, v in res["diagnostics"].items()
                                                 if k not in ("w_ignored", "w_hatches")}}
        A = T.get("ALL|ALL", {})
        print(f"{res['floor']}: walls={A.get('n')} gross={A.get('length_gross')} net={A.get('length_net')} "
              f"needs_check={summary[res['floor']]['needs_check']}  -> {js}")
        for k, v in T.items():
            if k.startswith("ALL|") or k.endswith("|ALL"):
                print(f"   {k:22s} n={v['n']:3d} gross={v['length_gross']:8.2f} net={v['length_net']:8.2f}")
    if not a.floors:
        results = [json.loads((WALL_OUT / f"F{n:02d}.json").read_text(encoding="utf-8")) for n in floors]
        diff = compare_floors(results)
        (WALL_OUT / "floor_diff.json").write_text(json.dumps(diff, ensure_ascii=False, indent=1,
                                                             default=_json_default), encoding="utf-8")
        for F, d in diff.items():
            print(f"diff {F} vs {d['vs']}: only here {d['only_on_this_floor_len']} m, only on ref {d['only_on_ref_len']} m")
        (WALL_OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1,
                                                          default=_json_default), encoding="utf-8")
    return summary


if __name__ == "__main__":
    main()
