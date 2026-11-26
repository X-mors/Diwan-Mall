# -*- coding: utf-8 -*-
"""
rooms — قارئ الفراغات/الغرف (مساحات الأرضيات والأسقف + محيط المحارة) لمساقط الديوان.

Builds the CLOSED ROOM POLYGONS of every floor (F02..F11) in the shared LOCAL frame of
diwan_common (rotation removed, structural-column corner = (0,0), metres) and names them.

METHOD (face extraction, robust to the drafting):
  1. Boundary primitives (all local coords):
       wall      W lines/polylines, stray caps on layer 0, MASS lines (lift-front wall,
                 terrace parapets; MASS lines inside a stair = the stair well, ignored)
       glazing   WIN, CONTINUOUS only (DASHED WIN = projection/cladding lines, ignored);
                 leaf lines/arcs of block-less glazed doors (F02) are dropped; WIN lines inside
                 a stair hull = the stair eye / break line drawn on WIN (F11), ignored like MASS;
                 a MASS line 3-16 cm beside a parallel WIN line over >= 80 % of its length is
                 the other frame line of that glass drawn on the wrong layer (F09) -> glazing
       column    Etabs-col / COL polygons (LWPOLYLINE + HATCH, de-duplicated) = solid
       solid_try hatched `try` boxes (ANSI31 masonry fins at the west curtain wall); a try
                 HATCH with no matching LWPOLYLINE (F09-F11 post at the office 7/8 partition) too
       shaft     un-hatched `try` boxes (their outline; the inside becomes a shaft face); a W
                 stub inside a box with a free end is a stray line, dropped (F09 SH06)
       slab_edge MASS LWPOLYLINE with >= 20 vertices (F02 terrace / planter slab edge); F09-F11
                 try floor outline only where no W / WIN lies within 0.15 m AND it runs through
                 what is open to the outside without it (it never cuts an indoor room short of
                 its curved glass; on F09-F11 it ends up changing nothing)
       door      quad between the two jambs of every door (tools/openings.py), so a
                 door gap closes the room on the wall face
       opening   rectangle across the wall of every door-less opening (openings.py:
                 lift landings, 0.80 opening between office 3/2 on F03/F04)
       extension a W face line whose end touches nothing is extended straight on to
                 the first obstacle within 1.5 m (partition drawn short of the facade /
                 glazing / the deleted round element at the NW and SW corners); every
                 extension is logged and drawn (magenta) for review; an end inside a try
                 shaft box is never extended
     Not boundaries: ST (stair treads), PR (handrails, lift cars), DASH (overhead lines),
     FUR, DIM, X, W hatches (AR-CONC = planter soil fill on F02).
  2. Faces: every primitive is buffered by EPS = 1.5 cm (closes drafting gaps <= 3 cm),
     the union is subtracted from a box around the plan, each free component that does
     not touch the box is a face, and it is grown back by EPS (mitre) -> the polygon
     runs exactly on the drawn inner wall faces.
  3. Classification of each face (in this order):
       shaft     inside an un-hatched `try` box, or spanned by an X of DASH lines
       lift      spanned by an X of PR lines (lift car); one X per car -> n_cars
       stair     contains >= 2 m of ST lines
       room      contains a TEXT / -A-TEXT label (insertion point or estimated text
                 centre); labels in a wall body / outside go to the nearest face <= 1.2 m
       wc        unlabelled face holding a WC pan block 'P' (FUR)  (flagged)
       wall_body thin unlabelled face (inscribed radius < 0.17 m, or < 0.33 m and area
                 < 1.2 m2): the inside of a wall / glazing frame / corner block, not a room
       void      any other unlabelled face (flagged 'unlabelled')
     Categories from the decoded label: office (مكتب n), wc (حمام, حمام ذوي الهمم),
     corridor (ممر), lobby (بهو المصعد), service (IT room, FTR room, DAS/GSM, electric
     room), terrace (تراس سماوي), planter (زرع), stair, lift, shaft.  'المصاعد الادارية
     فقط' is a sign (note), not a name.  open_air = terrace / planter (no ceiling, outside
     plaster) - F02 and F09-F11.  Corridor + lift lobby drawn as one space are split by the
     continuation of the corridor wall face; an extra 'ممر' label standing in the lobby
     (F10/F11) is dropped for the split when the rest gives a corridor-shaped part (flagged).
  4. Per room: area (net, inside the wall faces), perimeter (all rings) and its breakdown
     by what bounds it (wall / column / glazing / door / opening / shaft / slab_edge /
     extension ...) = the base of the plaster takeoff; doors / windows / openings ids on
     its boundary (from openings.py); architect DIMs whose two points lie on the room's
     faces are compared with the room width at that place (dim_checks).
  5. Per floor: net area by category, gross floor area = area inside the outer face of
     the facade (walls, columns and glazing included, open-air terraces / planters and
     thin external fins excluded), open-air area, flags.

CLI (default = all floors):
    python tools/rooms.py                      # F02..F11 -> output/rooms/F<nn>.json + PNGs
    python tools/rooms.py 3 5 --no-png
    python tools/rooms.py 3 --zoom 0 25 10 40  # extra zoomed review PNG (local metres)
API:
    from rooms import analyze_floor
    res = analyze_floor(3)
    res["rooms"]   -> [{id:'F03-R07', name, category, category_ar, open_air, indoor, area, perimeter,
                        perimeter_outer, n_holes, boundary{wall,column,glazing,door,opening,shaft,
                        solid_try,slab_edge,mass,extension,virtual,unresolved}, doors[], openings[],
                        windows[], windows_partial_m{id: facing m}?, labels[], flags[], centroid, bbox,
                        inscribed_r, n_cars?, wc_pans?, free_lines_inside?,
                        dim_checks[{dim, value, room_width, diff, status ok|jog|mismatch, lateral, ...}],
                        _poly (shapely, not in the JSON)}]
    res["totals"]  -> {by_category{cat:{name_ar, n, area, perimeter}}, n_rooms, net_indoor_area,
                        net_usable_area, ceiling_area, open_air_area, gross_floor_area,
                        gross_outline_perimeter, walls_columns_area, boundary_by_kind_indoor{},
                        boundary_by_kind_open_air{}, footprint_bbox}
    res["checks"]  -> labels_unplaced, office_numbers, offices_missing, duplicate_names, rooms_flagged,
                        extensions, corridor_lobby_splits, doors_not_two_sided, windows_unassigned,
                        win_inside_stair_skipped, windows_in_stair_ignored,
                        dims_ok / dims_jog / dims_mismatch, ...
    res["_footprint"], res["_P"] (tagged boundary primitives), res["_wall_bodies"]  (not in the JSON)
  Units: m / m2 in the LOCAL frame.  Perimeter = inner wall-face length (holes included), the base
  of the internal plaster; multiply by the storey height / clear height outside this module.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import OUT_DIR, STOREY_HEIGHT, all_floors, floor_entities, floor_texts, get_floor, is_try_outline  # noqa: E402

from ezdxf import path as ezpath  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box  # noqa: E402
from shapely.ops import linemerge, polylabel, unary_union  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

ROOM_OUT = OUT_DIR / "rooms"
CACHE_DIR = ROOM_OUT / "_cache"
CACHE_VER = "v6"
DOOR_RE = re.compile(r"^D(\d+)W(\d+)$", re.I)
BUILDING_WIN = (-4.0, -5.0, 25.0, 45.0)   # local box holding the plan (+ terraces / planters)


# ============================================================================
# 1. extraction (DXF -> plain local-frame geometry), cached per floor
# ============================================================================
def _dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _in_win(p, pad=0.0):
    return (BUILDING_WIN[0] - pad <= p[0] <= BUILDING_WIN[2] + pad
            and BUILDING_WIN[1] - pad <= p[1] <= BUILDING_WIN[3] + pad)


def _flat(e, dist=0.01):
    """WCS polyline of one primitive, OCS-correct (mirrored arcs / extrusion -Z)."""
    try:
        p = ezpath.make_path(e)
        pts = [(v.x, v.y) for v in p.flattening(dist)]
    except Exception:
        return []
    return [pts] if len(pts) >= 2 else []


def _is_dashed(e, doc):
    lt = e.dxf.get("linetype", "BYLAYER")
    if lt.upper() == "BYLAYER":
        try:
            lt = doc.layers.get(e.dxf.layer).dxf.linetype
        except Exception:
            lt = "CONTINUOUS"
    return lt.upper() not in ("CONTINUOUS", "BYBLOCK", "")


def _hatch_polys(e, L):
    out = []
    for path in e.paths:
        pts = []
        if hasattr(path, "vertices"):
            pts = [L(v[0], v[1]) for v in path.vertices]
        elif hasattr(path, "edges"):
            for ed in path.edges:
                if hasattr(ed, "start") and hasattr(ed, "end"):
                    pts.append(L(ed.start[0], ed.start[1]))
                elif hasattr(ed, "center"):
                    c, r = ed.center, ed.radius
                    a0, a1 = ed.start_angle, ed.end_angle
                    if a1 < a0:
                        a1 += 360
                    n = max(2, int((a1 - a0) / 5))
                    for i in range(n + 1):
                        a = math.radians(a0 + (a1 - a0) * i / n)
                        pts.append(L(c[0] + r * math.cos(a), c[1] + r * math.sin(a)))
        if len(pts) >= 3:
            out.append(pts)
    return out


def extract(fl) -> dict:
    """Plain, picklable LOCAL-frame geometry of one floor."""
    L = fl.to_local
    doc = fl.doc

    def loc(poly):
        return [L(x, y) for x, y in poly]

    g = {"label": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
         "file": fl.file.name, "sheet_index": fl.sheet_index,
         "w": [], "w_hatch": [], "zero": [], "win": [], "win_dashed": [], "cols": [], "try_polys": [],
         "try_lines": [], "st": [], "pr": [], "dash": [], "mass": [], "doors": [], "texts": [], "dims": [],
         "fur": [], "ignored": []}
    for e in floor_entities(fl, layers=("W", "0", "WIN", "PR", "DASH", "ST", "MASS", "-MASS", "try",
                                        "Etabs-col", "COL", "sidewalk", "HAT")):
        lay, t = e.dxf.layer, e.dxftype()
        if t in ("TEXT", "MTEXT", "DIMENSION", "INSERT", "POINT"):
            continue
        if t == "HATCH":
            if lay in ("W", "Etabs-col", "try"):
                key = {"W": "w_hatch", "Etabs-col": "cols", "try": "try_polys"}[lay]
                for pts in _hatch_polys(e, L):
                    g[key].append({"pts": pts, "layer": lay + "(hatch)", "handle": e.dxf.handle,
                                   "pattern": e.dxf.pattern_name, "type": "HATCH"})
            continue
        polys = [loc(p) for p in _flat(e)]
        if not polys:
            continue
        xs = [p[0] for pl in polys for p in pl]
        ys = [p[1] for pl in polys for p in pl]
        if max(xs) - min(xs) > 60 or max(ys) - min(ys) > 80:
            g["ignored"].append({"handle": e.dxf.handle, "layer": lay, "why": "sheet-size (frame)"})
            continue
        if not _in_win((sum(xs) / len(xs), sum(ys) / len(ys)), pad=2.0):
            continue
        rec = {"pts": polys[0], "type": t, "handle": e.dxf.handle,
               "closed": bool(getattr(e, "closed", False)) if t == "LWPOLYLINE" else False}
        if lay == "W":
            g["w"].append(rec)
        elif lay == "0":
            # stray wall caps drawn on layer 0 (short open polylines); skip revision clouds
            if t in ("LINE",) or (t == "LWPOLYLINE" and not e.closed and len(e) <= 4):
                g["zero"].append(rec)
            else:
                g["ignored"].append({"handle": e.dxf.handle, "layer": lay, "why": f"layer 0 {t} (cloud?)"})
        elif lay == "WIN":
            g["win_dashed" if _is_dashed(e, doc) else "win"].append(rec)
        elif lay in ("Etabs-col", "COL"):
            if t == "LWPOLYLINE" and len(rec["pts"]) >= 3:
                rec["layer"] = lay
                g["cols"].append(rec)
        elif lay == "try":
            if t == "LWPOLYLINE" and is_try_outline(rec["pts"]):
                # F09-F11: floor outline (slab edge round the planters) / plot boundary on try
                g.setdefault("try_outlines", []).append(rec)
            elif t == "LWPOLYLINE" and len(rec["pts"]) >= 4 and (e.closed or _dist(rec["pts"][0], rec["pts"][-1]) < 0.01):
                g["try_polys"].append(rec)
            else:
                g["try_lines"].append(rec)
        elif lay == "ST":
            g["st"].append(rec)
        elif lay == "PR":
            g["pr"].append(rec)
        elif lay == "DASH":
            g["dash"].append(rec)
        else:
            rec["layer"] = lay
            g["mass"].append(rec)

    # ---- door blocks D<w>W<t> (any layer): kept for the review drawing ----
    for e in floor_entities(fl, types="INSERT"):
        m = DOOR_RE.match(e.dxf.name)
        if not m:
            continue
        segs, arcs = [], []
        try:
            for v in e.virtual_entities():
                for poly in _flat(v):
                    lp = loc(poly)
                    if v.dxftype() == "ARC":
                        arcs.append(lp)
                    else:
                        segs.extend((a, b) for a, b in zip(lp, lp[1:]) if _dist(a, b) > 1e-4)
        except Exception as ex:  # pragma: no cover
            g["ignored"].append({"handle": e.dxf.handle, "why": f"door explode failed {ex}"})
            continue
        g["doors"].append({"name": e.dxf.name, "layer": e.dxf.layer,
                           "insert": L(e.dxf.insert.x, e.dxf.insert.y), "segs": segs, "arcs": arcs,
                           "handle": e.dxf.handle})

    # ---- furniture (WB = wash basin, P = WC pan): names unlabelled WCs ----
    for e in floor_entities(fl, layers="FUR", types="INSERT"):
        g["fur"].append({"name": e.dxf.name, "insert": L(e.dxf.insert.x, e.dxf.insert.y)})

    # ---- room labels ----
    for t in floor_texts(fl, layers=("TEXT", "-A-TEXT")):
        if _in_win(t["local"]):
            g["texts"].append({"text": t["text"], "raw": t["raw"], "x": t["local"][0], "y": t["local"][1],
                               "layer": t["layer"], "height": t["height"], "handle": t["handle"],
                               "arabic": t["arabic"]})
    g["notes"] = []
    for t in floor_texts(fl, layers=("PR", "TEXT-D", "0")):
        if _in_win(t["local"]):
            g["notes"].append({"text": t["text"], "x": t["local"][0], "y": t["local"][1], "layer": t["layer"]})

    # ---- architect dimensions ----
    for e in floor_entities(fl, types="DIMENSION"):
        d = e.dxf
        try:
            p2, p3 = L(d.defpoint2.x, d.defpoint2.y), L(d.defpoint3.x, d.defpoint3.y)
            p1 = L(d.defpoint.x, d.defpoint.y)
        except Exception:
            continue
        try:
            val = float(e.get_measurement())
        except Exception:
            val = float(d.get("actual_measurement", 0.0) or 0.0)
        g["dims"].append({"layer": d.layer, "p1": p1, "p2": p2, "p3": p3, "value": val,
                          "type": d.dimtype & 7, "angle": (float(d.get("angle", 0.0)) - fl.angle) % 180.0,
                          "text": d.get("text", ""), "handle": d.handle})
    return g


def load_geometry(fl, use_cache=True) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = f"{fl.label}_{fl.file.stem}_{int(os.path.getmtime(fl.file))}_{CACHE_VER}.pkl"
    p = CACHE_DIR / key
    if use_cache and p.exists():
        with open(p, "rb") as f:
            return pickle.load(f)
    g = extract(fl)
    for old in CACHE_DIR.glob(f"{fl.label}_*.pkl"):
        try:
            old.unlink()
        except OSError:
            pass
    with open(p, "wb") as f:
        pickle.dump(g, f)
    return g


# ============================================================================
# 2. doors / door-less openings / windows (from tools/openings.py)
# ============================================================================
OPEN_DIR = OUT_DIR / "openings"


def load_openings(fl, refresh=False):
    """Openings of the floor: output/openings/<F>.json when it is newer than both the
    DXF and tools/openings.py, else openings.analyze_floor() is run in memory."""
    p = OPEN_DIR / f"{fl.label}.json"
    src = Path(__file__).resolve().parent / "openings.py"
    if (not refresh and p.exists() and p.stat().st_mtime >= fl.file.stat().st_mtime
            and (not src.exists() or p.stat().st_mtime >= src.stat().st_mtime)):
        return json.loads(p.read_text(encoding="utf-8")), f"output/openings/{fl.label}.json"
    import openings as opm  # noqa: E402  (slow: ~25 s / floor)
    res = opm.analyze_floor(fl)
    data = opm._clean({k: v for k, v in res.items() if not k.startswith("_")})
    return data, "openings.analyze_floor() (computed in memory)"


# ============================================================================
# 3. boundary primitives -> closed faces
# ============================================================================
EPS = 0.015            # m: half-width of the line buffers (closes drafting gaps up to 3 cm)
MAX_EXT = 1.5          # m: longest extension of a dangling wall face to its first obstacle
MIN_FACE = 0.02        # m2: smaller free faces are drafting noise
LABEL_SNAP = 1.2       # m: a label outside every face goes to the nearest face within this
SNAP_FAR = 0.5         # m: an open-air face named by a label snapped from farther than this is flagged
SEG_STEP = 0.025       # m: boundary sampling step for the perimeter breakdown
KIND_PRIORITY = ["door", "opening", "glazing", "column", "solid_try", "shaft", "slab_edge", "mass",
                 "wall", "extension", "virtual"]
GLASS_OVER_OUTLINE = 0.12  # m: a face sample on the try outline with glazing this close counts as glazing


def _unit(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L) if L > 1e-12 else (0.0, 0.0)


def _poly(pts):
    pg = Polygon(pts)
    if not pg.is_valid:
        pg = pg.buffer(0)
    if pg.geom_type == "MultiPolygon":
        pg = max(pg.geoms, key=lambda q: q.area)
    return pg


def _is_leaf(pts, leaves, tol=0.012):
    """WIN polyline that is the swing arc / leaf line of a raw (non-block) door."""
    for h, r in leaves:
        ds = [_dist(p, h) for p in pts]
        if len(pts) > 2 and all(abs(d - r) <= tol for d in ds):            # leaf arc
            return True
        if len(pts) == 2 and min(ds) <= 0.03 and abs(_dist(pts[0], pts[1]) - r) <= 0.06:  # leaf line
            return True
    return False


def stair_hulls(g):
    """One convex hull per cluster of ST lines (a stair)."""
    if not g["st"]:
        return []
    u = unary_union([LineString(r["pts"]).buffer(0.6) for r in g["st"]])
    parts = list(u.geoms) if hasattr(u, "geoms") else [u]
    out = []
    for p in parts:
        lines = [LineString(r["pts"]) for r in g["st"] if p.intersects(LineString(r["pts"]))]
        if sum(l.length for l in lines) >= 2.0:
            out.append(unary_union(lines).convex_hull)
    return out


FRAME_GAP = (0.03, 0.16)   # m: a MASS line this far from a parallel WIN line = glazing frame line
FRAME_COVER = 0.80         # share of the MASS line that must run beside the WIN line
OUTLINE_CLEAR = 0.15       # m: the try floor outline is dropped wherever W / WIN lies this close


def _segments(pts):
    return [(a, b) for a, b in zip(pts, pts[1:]) if _dist(a, b) > 1e-6]


def _frame_cover(seg, win_segs, gap=FRAME_GAP, ang_tol=0.02):
    """Length share of segment `seg` that runs parallel to a WIN segment at a distance
    within `gap` (projected overlap; union over all WIN segments)."""
    (a, b) = seg
    L = _dist(a, b)
    if L < 1e-6:
        return 0.0
    u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
    n = (-u[1], u[0])
    ivs = []
    for (c, d) in win_segs:
        Lw = _dist(c, d)
        if Lw < 1e-6:
            continue
        w = ((d[0] - c[0]) / Lw, (d[1] - c[1]) / Lw)
        if abs(u[0] * w[1] - u[1] * w[0]) > ang_tol:
            continue                                       # not parallel
        off = abs((c[0] - a[0]) * n[0] + (c[1] - a[1]) * n[1])
        if not (gap[0] <= off <= gap[1]):
            continue
        t0 = (c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1]
        t1 = (d[0] - a[0]) * u[0] + (d[1] - a[1]) * u[1]
        lo, hi = max(0.0, min(t0, t1)), min(L, max(t0, t1))
        if hi > lo:
            ivs.append((lo, hi))
    if not ivs:
        return 0.0
    ivs.sort()
    tot, cur = 0.0, list(ivs[0])
    for lo, hi in ivs[1:]:
        if lo <= cur[1]:
            cur[1] = max(cur[1], hi)
        else:
            tot += cur[1] - cur[0]
            cur = [lo, hi]
    tot += cur[1] - cur[0]
    return tot / L


def build_primitives(g, op):
    """Tagged boundary geometry: list of (shapely geom, kind, ref)."""
    P = []
    leaves = [(tuple(d["hinge"]), d["leaf_r"]) for d in op.get("doors", [])
              if d.get("source") != "block" and d.get("hinge") and d.get("leaf_r")]
    skipped = []
    # stair hulls: MASS and WIN lines inside a stair are its eye / break line, not boundaries
    hulls = [h.buffer(0.05) for h in stair_hulls(g)]
    # open door leaves (hinge -> leaf tip) : W lines lying on one are a leaf drawn on W, not a wall
    leaf_zones = []
    for d in op.get("doors", []):
        lg = d.get("leaf_geom") or {}
        if lg.get("c") and lg.get("p1"):
            leaf_zones.append((LineString([tuple(lg["c"]), tuple(lg["p1"])]).buffer(0.07), d["id"]))
    for r in g["w"]:
        ln = LineString(r["pts"])
        z = next((did for zone, did in leaf_zones if zone.contains(ln)), None)
        if z and ln.length <= 1.3:
            skipped.append(f"W:{r['handle']} (door leaf of {z} drawn on W)")
            continue
        P.append((ln, "wall", "W:" + r["handle"]))
    for r in g["zero"]:
        P.append((LineString(r["pts"]), "wall", "0:" + r["handle"]))
    win_used = []
    for r in g["win"]:
        if _is_leaf(r["pts"], leaves):
            skipped.append("WIN:" + r["handle"] + " (door leaf)")
            continue
        ln = LineString(r["pts"])
        if any(h.contains(ln) for h in hulls):
            # F11: the stair eye (void between the flights) and the break line are drawn on WIN
            # (on MASS on F09/F10 and F02-F08) - not glazing, not a boundary
            skipped.append(f"WIN:{r['handle']} (inside a stair: stair eye / break line drawn on WIN)")
            continue
        win_used.append(r)
        P.append((ln, "glazing", "WIN:" + r["handle"]))
    seen = []
    for r in g["cols"]:
        pg = _poly(r["pts"])
        if pg.area < 0.005 or any(abs(pg.area - q.area) < 0.01 and pg.symmetric_difference(q).area < 0.01
                                  for q in seen):
            continue
        seen.append(pg)
        P.append((pg, "column", r.get("layer", "col") + ":" + r["handle"]))
    hatched = [(_poly(r["pts"]), r) for r in g["try_polys"] if "(hatch)" in r.get("layer", "")]
    lw_try = [_poly(r["pts"]) for r in g["try_polys"] if "(hatch)" not in r.get("layer", "")]
    seen = set()
    for r in g["try_polys"]:
        if "(hatch)" in r.get("layer", ""):
            continue
        pg = _poly(r["pts"])
        key = tuple(round(v, 2) for v in pg.bounds)
        if key in seen:
            continue
        seen.add(key)
        if any(h.intersection(pg).area > 0.8 * pg.area for h, _ in hatched):
            P.append((pg, "solid_try", "try:" + r["handle"]))          # hatched fin box (solid)
        else:
            P.append((LineString(pg.exterior.coords), "shaft", "try:" + r["handle"]))  # inside = shaft
    # F09-F11: a hatched try box with NO matching LWPOLYLINE (the curtain-wall post at the office
    # 7/8 partition) is still a solid post; a hatched box far from any wall / glass is stray
    near_lines = unary_union([p[0] for p in P if p[1] in ("wall", "glazing")]) if P else None
    for h, r in hatched:
        if h.area < 0.005 or any(h.intersection(q).area > 0.8 * h.area for q in lw_try):
            continue
        key = tuple(round(v, 2) for v in h.bounds)
        if key in seen:
            continue
        seen.add(key)
        if near_lines is not None and h.distance(near_lines) <= 0.30:
            P.append((h, "solid_try", "try-hatch:" + r["handle"]))
        else:
            skipped.append(f"try-hatch:{r['handle']} (hatched try box with no polyline, away from every wall / "
                           f"glass: stray object)")
    # MASS: slab edge (F02 terraces/planters), lift-front wall, parapets; not the stair well
    win_segs = [s for r in win_used for s in _segments(r["pts"])]
    for r in g["mass"]:
        xs = [p[0] for p in r["pts"]]
        ys = [p[1] for p in r["pts"]]
        if max(xs) - min(xs) > 30 or max(ys) - min(ys) > 50:
            continue                                   # site / plot boundary
        ln = LineString(r["pts"])
        if any(h.contains(ln) for h in hulls):
            skipped.append(f"MASS:{r['handle']} (inside a stair)")
            continue
        if r["type"] == "LWPOLYLINE" and len(r["pts"]) >= 20:
            P.append((ln, "slab_edge", "MASS:" + r["handle"]))
            continue
        # a MASS line running 3-16 cm beside a continuous WIN line over >= 80 % of its length is
        # the other line of a glazing frame drawn on the wrong layer (F09 west glass, office 10)
        segs = _segments(r["pts"])
        kinds = ["glazing" if _frame_cover(s, win_segs) >= FRAME_COVER else "mass" for s in segs]
        if segs and "glazing" in kinds:
            if all(k == "glazing" for k in kinds):
                P.append((ln, "glazing", "MASS(glazing frame):" + r["handle"]))
            else:
                for s, k in zip(segs, kinds):
                    P.append((LineString(s), k, ("MASS(glazing frame):" if k == "glazing" else "MASS:") + r["handle"]))
            skipped.append(f"MASS:{r['handle']} -> glazing (frame line drawn on MASS beside a WIN line)")
        else:
            P.append((ln, "mass", "MASS:" + r["handle"]))
    # F09-F11: the floor outline on 'try' runs on the facade / glass line (the planters lie OUTSIDE
    # it, behind a MASS parapet).  It is added last and dropped wherever a W / WIN line lies within
    # OUTLINE_CLEAR, so it never cuts an indoor room short of the (curved) glass; what is left only
    # closes the open-air planter ends (plot boundary skipped)
    clear = unary_union([p[0] for p in P if p[1] in ("wall", "glazing")]).buffer(OUTLINE_CLEAR)
    for r in g.get("try_outlines", []):
        xs = [p[0] for p in r["pts"]]
        ys = [p[1] for p in r["pts"]]
        if max(xs) - min(xs) > 30 or max(ys) - min(ys) > 50:
            continue                                   # site / plot boundary
        pts = list(r["pts"]) + [r["pts"][0]]
        ring = LineString(pts)
        rest = ring.difference(clear)
        if rest.geom_type == "MultiLineString":
            rest = linemerge(rest)
        parts = [q for q in (rest.geoms if hasattr(rest, "geoms") else [rest])
                 if q.geom_type == "LineString" and q.length >= 0.02]
        for q in parts:
            P.append((q, "slab_edge", "try-outline:" + r["handle"]))
        skipped.append(f"try-outline:{r['handle']} kept {sum(q.length for q in parts):.2f} of {ring.length:.2f} m "
                       f"(dropped where W / WIN lies within {OUTLINE_CLEAR} m)")
    # doors (block or raw) -> closing quad between the two jambs
    for d in op.get("doors", []):
        ja, jb = d.get("jamb_a"), d.get("jamb_b")
        if not ja or not jb:
            continue
        a0, a1 = map(tuple, ja)
        b0, b1 = map(tuple, jb)
        if _dist(a0, b0) + _dist(a1, b1) > _dist(a0, b1) + _dist(a1, b0):
            b0, b1 = b1, b0
        q = _poly([a0, a1, b1, b0])
        if q.area > 0.005:
            P.append((q, "door", d["id"]))
    # door-less openings (lift landings, ...) -> rectangle across the wall thickness
    for o in op.get("openings", []):
        e1, e2 = map(tuple, o["ends"])
        t = o.get("wall_t") or 0.12
        P.append((LineString([e1, e2]).buffer(t / 2, cap_style=2), "opening", o["id"]))
    return P, skipped


def stray_shaft_stubs(P, touch=0.012):
    """Indices of W lines lying inside an un-hatched try shaft box with an end that touches
    nothing inside the box (F09 SH06: W 4B35, a 0.16 m stub left in the shaft) - a stray line,
    not a wall; it would cut the shaft face into wall-body slivers.  A closed inner box drawn
    on W inside the try box (F05/F07) touches at both ends and is kept."""
    boxes = [Polygon(g_.coords) for g_, k_, _ in P
             if k_ == "shaft" and g_.geom_type == "LineString" and len(g_.coords) >= 4]
    if not boxes:
        return []
    geoms = [p[0] for p in P]
    tree = STRtree(geoms)
    out = []
    for idx, (geom, kind, ref) in enumerate(P):
        if kind != "wall" or geom.geom_type != "LineString":
            continue
        bx = next((b for b in boxes if b.buffer(0.01).contains(geom)), None)
        if bx is None:
            continue
        inner = bx.buffer(-0.01)
        for end in (geom.coords[0], geom.coords[-1]):
            pt = Point(end)
            if inner.is_empty or not inner.contains(pt):
                continue
            if not [j for j in tree.query(pt.buffer(touch)) if j != idx and geoms[j].distance(pt) <= touch]:
                out.append(idx)
                break
    return out


def outline_open_air_only(P, skipped):
    """F09-F11: keep the (already clipped) try floor-outline pieces only where they run through
    what is OPEN TO THE OUTSIDE without them (they then close an open-air planter); a piece that
    runs through a closed face of the plan without the outline would only cut that face (an
    office short of the curved glass: F11 office 11 SW corner) and is dropped."""
    idx = [i for i, p in enumerate(P) if str(p[2]).startswith("try-outline:")]
    if not idx:
        return P
    P0 = [p for i, p in enumerate(P) if i not in set(idx)]
    e0 = dangling_extensions(P0)
    P0x = P0 + [(LineString([tuple(e["from"]), tuple(e["to"])]), "extension", e["wall"]) for e in e0]
    _, _, f0 = free_faces(P0x, box(*BUILDING_WIN))
    U = unary_union(f0) if f0 else None
    out = list(P0)
    kept = dropped = 0.0
    for i in idx:
        geom, kind, ref = P[i]
        rest = geom.difference(U) if U is not None else geom
        if rest.geom_type == "MultiLineString":
            rest = linemerge(rest)
        parts = [q for q in (rest.geoms if hasattr(rest, "geoms") else [rest])
                 if q.geom_type == "LineString" and q.length >= 0.02]
        out.extend((q, kind, ref) for q in parts)
        kept += sum(q.length for q in parts)
        dropped += geom.length - sum(q.length for q in parts)
    if dropped > 0.005:
        skipped.append(f"try-outline: {dropped:.2f} m more dropped where it runs inside a closed face (it would cut "
                       f"that space short of its glass); {kept:.2f} m kept (open-air side)")
    return out


def dangling_extensions(P, max_ext=MAX_EXT, touch=0.012, ray_tol=0.016, min_seg=0.10):
    """Wall-face lines (W) whose end touches nothing are extended straight on to the
    first obstacle within max_ext (a partition drawn short of the facade / glazing)."""
    geoms = [p[0] for p in P]
    tree = STRtree(geoms)
    # inside of the un-hatched try shaft boxes: a W stub ending in there is a stray line in the
    # shaft (F09 SH06), extending it would split the shaft
    shaft_in = [Polygon(g_.coords).buffer(-0.01) for g_, k_, _ in P
                if k_ == "shaft" and g_.geom_type == "LineString" and len(g_.coords) >= 4]
    shaft_in = [q for q in shaft_in if not q.is_empty]
    out = []
    for idx, (geom, kind, ref) in enumerate(P):
        if kind != "wall" or geom.geom_type != "LineString":
            continue
        cs = list(geom.coords)
        if len(cs) < 2 or _dist(cs[0], cs[-1]) < 1e-6:
            continue
        for end, prev in ((cs[0], cs[1]), (cs[-1], cs[-2])):
            if _dist(end, prev) < min_seg:
                continue                      # too short to give a reliable direction
            pt = Point(end)
            if any(q.contains(pt) for q in shaft_in):
                continue                      # dangling end inside a shaft box: not extended
            near = [j for j in tree.query(pt.buffer(touch)) if j != idx and geoms[j].distance(pt) <= touch]
            if near:
                continue
            # the line itself closes back on this end (closed polyline)?
            if LineString(cs[1:-1] if len(cs) > 3 else cs).distance(pt) <= touch and len(cs) > 3:
                continue
            u = _unit((end[0] - prev[0], end[1] - prev[1]))
            ray = LineString([(end[0] + u[0] * 1e-3, end[1] + u[1] * 1e-3),
                              (end[0] + u[0] * max_ext, end[1] + u[1] * max_ext)])
            band = ray.buffer(ray_tol, cap_style=2)      # catches near misses (ends 1-2 cm off line)
            best = None
            for j in tree.query(band):
                if j == idx:
                    continue
                x = band.intersection(geoms[j])
                if x.is_empty:
                    continue
                cs2 = []
                for part in (x.geoms if hasattr(x, "geoms") else [x]):
                    if part.geom_type == "Polygon":
                        cs2.extend(part.exterior.coords)
                    else:
                        cs2.extend(part.coords)
                dd = min(((c[0] - end[0]) * u[0] + (c[1] - end[1]) * u[1]) for c in cs2)
                if dd <= 1e-3:
                    continue
                if best is None or dd < best[0]:
                    best = (dd, P[j][1], P[j][2])
            if best is not None and best[0] > 0.005:
                q = (end[0] + u[0] * best[0], end[1] + u[1] * best[0])
                out.append({"from": [round(end[0], 3), round(end[1], 3)], "to": [round(q[0], 3), round(q[1], 3)],
                            "length": round(best[0], 3), "wall": ref, "hits": f"{best[1]} {best[2]}"})
    return out


def free_faces(P, env):
    mass = unary_union([geom.buffer(EPS, join_style=2, mitre_limit=10.0) if geom.geom_type != "Polygon"
                        else geom.buffer(EPS, join_style=2, mitre_limit=10.0) for geom, _, _ in P])
    free = env.difference(mass)
    parts = list(free.geoms) if hasattr(free, "geoms") else [free]
    outside, faces = [], []
    for f in parts:
        if f.area < 1e-6:
            continue
        (outside if f.intersects(env.exterior) else faces).append(f)
    return mass, outside, faces


def restore(f):
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
    return r if abs(r.area - f.area) < 0.05 + 0.01 * f.area else f


def corridor_like(part, chord, ratio=4.0, min_area=8.0):
    """A long narrow strip whose long side runs parallel to the chord (the corridor)."""
    if part.area < min_area:
        return False
    mrr = part.minimum_rotated_rectangle
    cs = list(mrr.exterior.coords)
    e1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    e2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    L1, L2 = math.hypot(*e1), math.hypot(*e2)
    long_e, Ll, Ls = (e1, L1, L2) if L1 >= L2 else (e2, L2, L1)
    if Ls < 1e-6 or Ll / Ls < ratio:
        return False
    c = list(chord.coords)
    d = _unit((c[1][0] - c[0][0], c[1][1] - c[0][1]))
    u = _unit(long_e)
    return abs(d[0] * u[1] - d[1] * u[0]) < 0.02


def split_by_wall_continuation(face, keep_pts, other_pts, min_len=0.5, max_len=12.0, tol=0.01,
                               other_check=None):
    """Split an open space (corridor + lift lobby drawn as one) by the straight continuation
    of a wall face across its mouth: a chord between two boundary vertices that continues a
    boundary edge at BOTH ends.  The shortest chord that puts every keep_pt on one side and
    at least one other_pt on the other side wins.  Returns (part_keep, part_other, chord) or None."""
    from shapely.ops import polygonize as _pz

    def polygonize(geom):
        from shapely.geometry import GeometryCollection
        return GeometryCollection(list(_pz(geom)))
    ring = list(face.exterior.simplify(0.002).coords)[:-1]
    n = len(ring)
    if n < 4:
        return None
    edges = []                       # per vertex: unit directions of its two incident edges (outwards)
    for i in range(n):
        a = ring[i]
        e1 = _unit((ring[i - 1][0] - a[0], ring[i - 1][1] - a[1]))
        e2 = _unit((ring[(i + 1) % n][0] - a[0], ring[(i + 1) % n][1] - a[1]))
        edges.append((e1, e2))
    fb = face.buffer(0.003)
    best = None
    for i in range(n):
        a = ring[i]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            b = ring[j]
            L = _dist(a, b)
            if L < min_len or L > max_len or (best and L >= best[0]):
                continue
            d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            # an edge at a pointing AWAY from b (wall face ending at a) and one at b pointing away from a
            ok_a = any(abs(e[0] * d[1] - e[1] * d[0]) < tol and (e[0] * d[0] + e[1] * d[1]) < -0.99 for e in edges[i])
            ok_b = any(abs(e[0] * d[1] - e[1] * d[0]) < tol and (e[0] * d[0] + e[1] * d[1]) > 0.99 for e in edges[j])
            if not (ok_a and ok_b):
                continue
            chord = LineString([a, b])
            if not fb.contains(chord) or not face.contains(chord.interpolate(0.5, normalized=True)):
                continue
            try:
                pieces = polygonize(unary_union([face.exterior] + list(face.interiors) + [chord]))
                parts = [q for q in pieces.geoms if q.area > 0.05 and face.buffer(1e-3).contains(q)]
            except Exception:
                continue
            if len(parts) != 2:
                continue
            side = [[q.buffer(1e-4).contains(pt) for q in parts] for pt in keep_pts]
            if not side or not all(sd[0] for sd in side) and not all(sd[1] for sd in side):
                continue
            k = 0 if all(sd[0] for sd in side) else 1
            if other_pts and not any(parts[1 - k].buffer(1e-4).contains(pt) for pt in other_pts):
                continue
            if other_check is not None and not other_check(parts[1 - k], chord):
                continue
            best = (L, parts[k], parts[1 - k], chord)
    return best[1:] if best else None


SLICE_R = 0.16         # m: a face piece narrower than 2 x SLICE_R (walls up to 0.30) is a wall body


def slice_face(f, r=SLICE_R, min_sliver=0.02):
    """Split a face into its 'core' pieces (morphological opening with a square of half
    size r) and the thin slivers between them.  A room face that leaks into the inside of a
    wall (missing cap) loses that leak; a wall body that runs into a shaft box gives the box
    back.  Returns (cores, slivers); the face is returned untouched when nothing thin hangs
    on it (exact area kept)."""
    # mitre_limit 2: square corners stay exact (ratio 1.41) while a zero-width spike (door
    # frame drawn on W) cannot shoot a mitre 10 x r deep into the room
    core = f.buffer(-r, join_style=2, mitre_limit=2.0)
    if core.is_empty:
        return [], [f]
    core = core.buffer(r, join_style=2, mitre_limit=2.0).intersection(f)
    rest = f.difference(core)
    rest_parts = [p for p in (rest.geoms if hasattr(rest, "geoms") else [rest])
                  if p.geom_type == "Polygon" and p.area >= 1e-4]
    if sum(p.area for p in rest_parts) < min_sliver or all(p.area < 0.01 for p in rest_parts):
        return [f], []
    cores = [p for p in (core.geoms if hasattr(core, "geoms") else [core]) if p.geom_type == "Polygon" and p.area > 1e-4]
    # slivers that are tiny corner crumbs of a core stay with it (no area lost to rounding)
    keep, slivers = [], []
    for s in rest_parts:
        if s.area < 0.01:
            best = max(cores, key=lambda c: c.buffer(1e-3).intersection(s).area) if cores else None
            if best is not None and best.distance(s) < 1e-3:
                keep.append((best, s))
                continue
        slivers.append(s)
    merged = []
    for c in cores:
        extra = [s for b, s in keep if b is c]
        merged.append(unary_union([c] + extra) if extra else c)
    out = []
    for m in merged:
        out.extend([q for q in (m.geoms if hasattr(m, "geoms") else [m]) if q.geom_type == "Polygon"])
    return out, slivers


# ============================================================================
# 4. labels -> names / categories
# ============================================================================
CATEGORY_RULES = [                         # (regex on the decoded label, category)
    (re.compile(r"^مكتب"), "office"),
    (re.compile(r"^حمام|ذوي\s*الهمم"), "wc"),
    (re.compile(r"^ممر"), "corridor"),
    (re.compile(r"^بهو"), "lobby"),
    (re.compile(r"تراس"), "terrace"),
    (re.compile(r"^زرع"), "planter"),
    (re.compile(r"(?i)IT\s*room|FTR|DAS|GSM|electric|كهرباء"), "service"),
    (re.compile(r"سلم|درج"), "stair"),
]
NOTE_RE = re.compile(r"المصاعد\s+الادارية|فقط")      # sign next to the lifts, not a room name
OPEN_AIR = {"terrace", "planter"}
CATEGORY_AR = {"office": "مكاتب", "wc": "حمامات", "corridor": "ممرات", "lobby": "بهو المصعد",
               "stair": "سلالم", "lift": "بئر المصاعد", "shaft": "شفتات/دكتات", "terrace": "تراسات سماوية",
               "planter": "أحواض زرع", "service": "غرف خدمات", "void": "فراغ بلا اسم"}
CAT_ORDER = ["office", "wc", "corridor", "lobby", "service", "stair", "lift", "shaft", "terrace", "planter",
             "void"]
CAT_COLORS = {"office": "#a6cee3", "wc": "#b2df8a", "corridor": "#fdbf6f", "lobby": "#ffe08a",
              "service": "#cab2d6", "stair": "#fb9a99", "lift": "#bdbdbd", "shaft": "#ff7f00",
              "terrace": "#7fd8e8", "planter": "#4daf4a", "void": "#ff00ff"}
INDOOR_CEILING = {"office", "wc", "corridor", "lobby", "service", "stair"}


def label_category(txt):
    for rx, cat in CATEGORY_RULES:
        if rx.search(txt):
            return cat
    return None


def _label_center(t):
    """Estimated centre of a label.  Arabic SHX (SOSA / xarb, style ARA) glyphs advance
    to the LEFT: a left-aligned Arabic TEXT ends at its insertion point and runs leftwards
    (labels sit just left of a WC's right wall).  Latin labels (-A-TEXT) run rightwards."""
    h = t.get("height") or 0.15
    n = max(len(t["text"]), 1)
    w = 0.35 * h * n
    return (t["x"] - w / 2 if t.get("arabic", True) else t["x"] + w / 2, t["y"] + 0.5 * h)


def name_room(labels):
    """(name, category, flags) from the labels found inside one space."""
    flags = []
    labels = [l for l in labels if not l.get("note") and not l.get("misplaced")]
    if not labels:
        return None, None, flags
    txts = [l["text"] for l in labels]
    cats = [label_category(t) for t in txts]
    if "ذوي الهمم" in txts:                         # 'حمام' + 'ذوي الهمم' = one accessible WC
        rest = [t for t in txts if t not in ("حمام", "ذوي الهمم")]
        if not rest and txts.count("حمام") <= 1:
            return "حمام ذوي الهمم", "wc", flags
    uniq = list(dict.fromkeys(txts))
    ucats = [c for c in dict.fromkeys(cats) if c]
    if len(uniq) == 1:
        if len(txts) > 1 and cats[0] not in ("terrace", "planter"):
            flags.append(f"multi_label: {len(txts)} x '{uniq[0]}' in one space")
        return uniq[0], cats[0] or "void", flags
    if set(ucats) <= {"corridor", "lobby"}:
        flags.append("corridor_lobby_open: الممر وبهو المصعد فراغ واحد مفتوح (لا حائط بينهما)")
        return " + ".join(uniq), "corridor", flags
    if set(ucats) == {"terrace"} or set(ucats) == {"planter"}:
        return uniq[0], ucats[0], flags
    offices = [t for t in uniq if label_category(t) == "office"]
    if len(offices) == 1 and set(ucats) == {"office", "wc"}:
        flags.append("extra_label: '" + "', '".join(t for t in uniq if t not in offices) + "' inside "
                     + offices[0] + " - the WC walls are not drawn here (label left over?)")
        return offices[0], "office", flags
    flags.append("multi_label: " + " | ".join(uniq) + " - no wall drawn between them?")
    prim = ucats[0] if ucats else "void"
    return " + ".join(uniq), prim, flags


# ============================================================================
# 5. face classification helpers
# ============================================================================
def _diag_segments(recs):
    """Straight segments of DASH / PR records that run diagonal in the local frame."""
    out = []
    for r in recs:
        pts = r["pts"]
        for a, b in zip(pts, pts[1:]):
            L = _dist(a, b)
            if L < 0.4:
                continue
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90.0
            if 15.0 <= ang <= 75.0:
                out.append(LineString([a, b]))
    return out


def count_x(face, segs):
    """Number of X marks (two crossing diagonals spanning the face) inside face."""
    fb = face.buffer(0.06)
    inside = [s for s in segs if fb.contains(s)]
    if len(inside) < 2:
        return 0
    used, n = set(), 0
    for i, s in enumerate(inside):
        if i in used:
            continue
        for j in range(i + 1, len(inside)):
            if j in used:
                continue
            t = inside[j]
            if s.crosses(t) and min(s.length, t.length) >= 0.5:
                used.update((i, j))
                n += 1
                break
    return n


def count_diag(face, segs, frac=0.7):
    """Single diagonals (one stroke of an X, or a '/' shaft mark) spanning the face."""
    fb = face.buffer(0.06)
    x0, y0, x1, y1 = face.bounds
    dg = math.hypot(x1 - x0, y1 - y0)
    return sum(1 for s in segs if fb.contains(s) and s.length >= frac * dg)


def inscribed_radius(poly):
    try:
        c = shapely.maximum_inscribed_circle(poly, tolerance=0.005)
        return c.length
    except Exception:
        p = polylabel(poly, tolerance=0.005)
        return poly.exterior.distance(p)


# ============================================================================
# 6. perimeter breakdown / openings on the boundary / DIM checks
# ============================================================================
def _ring_samples(poly, step=SEG_STEP):
    rings = [poly.exterior] + list(poly.interiors)
    for ri, ring in enumerate(rings):
        cs = list(ring.coords)
        for a, b in zip(cs, cs[1:]):
            L = _dist(a, b)
            if L < 1e-9:
                continue
            n = max(1, int(math.ceil(L / step)))
            for k in range(n):
                t0, t1 = k / n, (k + 1) / n
                m = (a[0] + (b[0] - a[0]) * (t0 + t1) / 2, a[1] + (b[1] - a[1]) * (t0 + t1) / 2)
                yield ri, m, L / n


def boundary_breakdown(poly, P, tree):
    """Length of the room boundary by the kind of primitive it runs along."""
    out = defaultdict(float)
    refs = defaultdict(set)
    prio = {k: i for i, k in enumerate(KIND_PRIORITY)}
    for ri, m, dl in _ring_samples(poly):
        pt = Point(m)
        best = None
        for j in tree.query(pt.buffer(0.04)):
            geom, kind, ref = P[j]
            d = geom.distance(pt) if geom.geom_type != "Polygon" else geom.exterior.distance(pt) \
                if not geom.contains(pt) else 0.0
            key = (round(d, 3), prio.get(kind, 99))
            if d <= 0.035 and (best is None or key < best[0]):
                best = (key, kind, ref)
        if best is not None and best[1] == "slab_edge" and str(best[2]).startswith("try-outline:"):
            # the try floor outline drawn a few cm inside the glass: the face is the glazing
            gl = [P[j] for j in tree.query(pt.buffer(GLASS_OVER_OUTLINE))
                  if P[j][1] == "glazing" and P[j][0].distance(pt) <= GLASS_OVER_OUTLINE]
            if gl:
                best = (best[0], "glazing", gl[0][2])
        if best is None:
            out["unresolved"] += dl
        else:
            out[best[1]] += dl
            if best[1] in ("door", "opening"):
                refs[best[1]].add(best[2])
    return {k: round(v, 3) for k, v in out.items()}, {k: sorted(v) for k, v in refs.items()}


def windows_on(poly, windows, tol=0.32):
    """Windows facing this room -> (ids, {id: facing length m} for windows the room only
    partly faces, e.g. the 13 m west curtain wall shared by offices 8..11)."""
    out, partial = [], {}
    for w in windows:
        ends = w.get("ends") or []
        if len(ends) < 2:
            continue
        seg = LineString([tuple(p) for p in ends])
        if poly.distance(seg) <= tol:
            # the room must face half the window or >= 0.60 m of it (a window round the
            # corner reaches at most `tol` into the zone)
            near = poly.buffer(tol)
            L = seg.intersection(near).length
            if L >= min(0.5 * seg.length, 0.60) - 1e-6:
                out.append(w["id"])
                if L < 0.95 * seg.length:
                    partial[w["id"]] = round(L, 3)
    return out, partial


def _first_exit(poly, start, u, reach):
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
        mid = Point((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
        if bd.distance(mid) < 0.03 or not poly.contains(mid):
            continue                         # measures along one face (window / pier widths)
        s = 1.0 if proj > 0 else -1.0
        nrm = (-u[1], u[0])
        # lateral offset of the two DIM points across the DIM direction: > 5 cm means the DIM
        # runs between two faces that do not face each other (a wall face to a column face
        # beside it) - the ray then hits whatever lies in between ('jog', not an error)
        lateral = abs((p3[0] - p2[0]) * nrm[0] + (p3[1] - p2[1]) * nrm[1])
        widths = []
        for start, sg in ((p2, s), (p3, -s)):
            v = (u[0] * sg, u[1] * sg)
            # a DIM point at a corner / on a face parallel to the DIM: the straight ray runs
            # along that face -> also try it 3 cm to either side
            for off in (0.0, 0.03, -0.03):
                st = (start[0] + nrm[0] * off, start[1] + nrm[1] * off)
                inner = (st[0] + v[0] * 0.03, st[1] + v[1] * 0.03)
                if not poly.contains(Point(inner)):
                    continue
                w = _first_exit(poly, inner, v, span + 1.0)
                if w is not None:
                    widths.append(w + 0.03)
        if not widths:
            continue
        w = min(widths, key=lambda q: abs(q - span))
        status = "ok" if abs(w - span) <= 0.02 else ("jog" if lateral > 0.05 else "mismatch")
        rec = {"dim": d["handle"], "value": round(span, 3), "room_width": round(w, 3),
               "diff": round(w - span, 3), "status": status, "lateral": round(lateral, 3),
               "dir_deg": round(math.degrees(math.atan2(u[1], u[0])) % 180.0, 1),
               "p2": [round(v, 3) for v in p2], "p3": [round(v, 3) for v in p3]}
        if abs(d["value"] - span) > 0.005:
            rec["stored_measurement"] = round(d["value"], 3)
        out.append(rec)
    return out


# ============================================================================
# 7. analysis of one floor
# ============================================================================
def _r(v, n=3):
    if isinstance(v, (list, tuple)):
        return [_r(x, n) for x in v]
    return None if v is None else round(float(v), n)


def analyze_floor(floor, use_cache=True, refresh_openings=False):
    t0 = time.time()
    fl = floor if hasattr(floor, "to_local") else get_floor(int(floor))
    g = load_geometry(fl, use_cache=use_cache)
    op, op_src = load_openings(fl, refresh=refresh_openings)

    P, skipped = build_primitives(g, op)
    stubs = stray_shaft_stubs(P)
    for i in sorted(stubs, reverse=True):
        skipped.append(f"{P[i][2]} (stray stub inside a try shaft box, free end: not a wall)")
        del P[i]
    P = outline_open_air_only(P, skipped)
    # F09-F11: the floor outline on 'try' (bulge-aware: flattened with ezdxf.path) - used to flag
    # open-air faces that lie inside it (planters lie outside the outline)
    outline_poly = None
    for r in g.get("try_outlines", []):
        xs = [p[0] for p in r["pts"]]
        ys = [p[1] for p in r["pts"]]
        if max(xs) - min(xs) <= 30 and max(ys) - min(ys) <= 50 and len(r["pts"]) >= 3:
            q = _poly(r["pts"])
            outline_poly = q if outline_poly is None else outline_poly.union(q)
    hulls = [h.buffer(0.05) for h in stair_hulls(g)]
    win_in_stair = [s_.split(" ")[0] for s_ in skipped if "inside a stair: stair eye" in s_]
    P_ref_geom = {"WIN:" + r["handle"]: LineString(r["pts"]) for r in g["win"]
                  if "WIN:" + r["handle"] in win_in_stair}
    exts = dangling_extensions(P)
    for e in exts:
        P.append((LineString([tuple(e["from"]), tuple(e["to"])]), "extension", e["wall"]))
    env = box(*BUILDING_WIN)
    mass, outside, raw_faces = free_faces(P, env)
    # slicing runs on the RAW free faces (every drawn line is still a 3 cm gap there, so a wall
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
        trimmed.extend([t] * len(good))
    tree = STRtree([p[0] for p in P])

    # ---------------- per-face facts
    try_void = [p[0] for p in P if p[1] == "shaft"]
    try_void = [Polygon(l.coords) for l in try_void]
    dash_diag = _diag_segments(g["dash"] + g["try_lines"])
    pr_diag = _diag_segments(g["pr"])
    st_lines = [LineString(r["pts"]) for r in g["st"]]
    st_tree = STRtree(st_lines) if st_lines else None
    wc_pans = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "P"]
    basins = [Point(f["insert"]) for f in g["fur"] if f["name"].upper() == "WB"]
    soil = [_poly(h["pts"]) for h in g["w_hatch"] if str(h.get("pattern", "")).upper() == "AR-CONC"]
    soil = [h for h in soil if h.area > 0.3]          # (small boxes = text masks)

    F = []
    for i, f in enumerate(faces):
        rec = {"i": i, "poly": f, "area": f.area, "labels": [], "flags": [], "kind": None,
               "trimmed": trimmed[i]}
        rec["r_in"] = inscribed_radius(f)
        rp = f.representative_point()
        rec["in_try"] = any(tv.contains(rp) and f.area <= tv.area * 1.1 + 0.01 for tv in try_void)
        rec["x_dash"] = count_x(f, dash_diag)
        rec["diag_dash"] = count_diag(f, dash_diag)
        rec["x_pr"] = count_x(f, pr_diag)
        st_len = 0.0
        if st_tree is not None:
            for j in st_tree.query(f):
                st_len += st_lines[j].intersection(f).length
        rec["st_len"] = st_len
        # WC pan / basin blocks are inserted ON the wall face behind them -> look 0.25 m around
        fz = f.buffer(0.25)
        rec["wc_pans"] = sum(1 for p in wc_pans if fz.contains(p))
        rec["basins"] = sum(1 for p in basins if fz.contains(p))
        rec["soil"] = (sum(f.intersection(h).area for h in soil if h.intersects(f)) / f.area) if soil else 0.0
        F.append(rec)

    # ---------------- labels
    def candidate(rec):
        return not (rec["r_in"] < 0.17 and rec["area"] < 3.0)

    unplaced = []
    for t in g["texts"]:
        lab = {"text": t["text"], "x": round(t["x"], 3), "y": round(t["y"], 3), "layer": t["layer"],
               "handle": t["handle"], "note": bool(NOTE_RE.search(t["text"]))}
        pts = [Point(_label_center(t)), Point(t["x"], t["y"])]
        host = None
        for p in pts:
            for rec in F:
                if candidate(rec) and rec["poly"].contains(p):
                    host = rec
                    break
            if host:
                break
        if host is None:
            best = None
            for rec in F:
                if not candidate(rec) or rec["in_try"]:
                    continue
                d = rec["poly"].distance(pts[0])
                if d <= LABEL_SNAP and (best is None or d < best[0]):
                    best = (d, rec)
            if best:
                host = best[1]
                lab["snapped"] = round(best[0], 3)
        if host is None:
            unplaced.append(lab)
        else:
            host["labels"].append(lab)

    # ---------------- corridor + lift lobby drawn as one open space -> split at the mouth
    splits = []
    for rec in list(F):
        txt = [l["text"] for l in rec["labels"] if not l["note"]]
        cats = {label_category(t) for t in txt}
        lab_t = {t["handle"]: t for t in g["texts"]}
        dropped = []
        if {"corridor", "lobby"} <= cats:
            unlabelled_corridor = False
            keep = [l for l in rec["labels"] if label_category(l["text"]) == "corridor"]
            oth = [l for l in rec["labels"] if label_category(l["text"]) == "lobby"]
            keep_pts = [Point(_label_center(lab_t[l["handle"]])) for l in keep]
            oth_pts = [Point(l["x"], l["y"]) for l in oth] + [Point(_label_center(lab_t[l["handle"]])) for l in oth]
            res_split = split_by_wall_continuation(rec["poly"], keep_pts, oth_pts)
            if not res_split and len(keep) >= 2:
                # F10/F11: an extra 'ممر' label stands in the lobby (in front of the stair / service
                # doors).  Retry without one (then two) corridor labels: accepted only when the kept
                # part is a corridor-shaped strip and every dropped label falls in the lobby part
                from itertools import combinations
                for k_drop in (1, 2):
                    if res_split or len(keep) - k_drop < 1:
                        break
                    for drop in combinations(range(len(keep)), k_drop):
                        kp = [p for i, p in enumerate(keep_pts) if i not in drop]
                        rs = split_by_wall_continuation(rec["poly"], kp, oth_pts)
                        if not rs:
                            continue
                        pk_, po_, ch_ = rs
                        dpts = [keep_pts[i] for i in drop]
                        if corridor_like(pk_, ch_) and all(po_.buffer(1e-4).contains(p) for p in dpts):
                            if res_split is None or ch_.length < res_split[2].length:
                                res_split, dropped = rs, [keep[i] for i in drop]
                    if res_split:
                        keep = [l for l in keep if l not in dropped]
        elif cats == {"lobby"} and rec["area"] > 50.0:
            # F02: the corridor carries no label; the lobby label sits at the corridor mouth
            unlabelled_corridor = True
            lob = [l for l in rec["labels"] if label_category(l["text"]) == "lobby"]
            res_split = split_by_wall_continuation(rec["poly"], [Point(l["x"], l["y"]) for l in lob], [],
                                                   other_check=corridor_like)
            if res_split:
                po, pk, chord = res_split            # keep = lobby side -> swap so pk = corridor
                res_split = (pk, po, chord)
            keep = []
        else:
            continue
        if not res_split:
            rec["flags"].append("corridor_lobby_open: الممر وبهو المصعد فراغ واحد (لا حائط بينهما) ولم يُقسَّم")
            continue
        pk, po, chord = res_split
        F.remove(rec)
        for l in dropped:
            l["misplaced"] = "corridor label inside the lobby part (extra / left-over label) - not used for the name"
        for part, labs in ((pk, keep), (po, [l for l in rec["labels"] if l not in keep])):
            nr = dict(rec)
            fl_ = [f"split_virtual: separated from the {'lobby' if labs is keep else 'corridor'} by a "
                   f"virtual line {chord.length:.2f} m (continuation of the corridor wall face; no wall drawn)"]
            if labs is keep and unlabelled_corridor:
                fl_.append("corridor_unlabelled: no 'ممر' label on this floor; named corridor from its shape")
                nr["force_name"] = ("ممر", "corridor")
            if labs is not keep and dropped:
                fl_.append("label_in_lobby: " + ", ".join(f"'{l['text']}' {l['handle']} ({l['x']:.2f}, {l['y']:.2f})"
                                                          for l in dropped)
                           + " lies in the lobby part - the corridor/lobby split ignores it")
            nr.update(poly=part, area=part.area, labels=list(labs), r_in=inscribed_radius(part), flags=fl_)
            F.append(nr)
        P.append((chord, "virtual", "split:" + rec["labels"][0]["handle"]))
        splits.append({"chord": _r([list(c) for c in chord.coords]), "length": round(chord.length, 3),
                       "areas": [round(pk.area, 3), round(po.area, 3)]})
        if dropped:
            splits[-1]["labels_ignored"] = [{"text": l["text"], "handle": l["handle"], "x": l["x"], "y": l["y"]}
                                            for l in dropped]
    if splits:
        tree = STRtree([p[0] for p in P])

    # ---------------- classify
    rooms = []
    wall_bodies = []
    pockets = []
    for rec in F:
        f = rec["poly"]
        name, cat, flags = name_room(rec["labels"])
        if rec.get("force_name") and not name:
            name, cat = rec["force_name"]
        flags = rec["flags"] + flags
        n_cars = 0
        if rec["in_try"] or ((rec["x_dash"] or rec["diag_dash"]) and not rec["labels"] and rec["area"] < 4.0):
            cat_auto = "shaft"
        elif rec["x_pr"]:
            cat_auto, n_cars = "lift", rec["x_pr"]
        elif rec["st_len"] >= 2.0:
            cat_auto = "stair"
        else:
            cat_auto = None
        if cat_auto in ("shaft", "lift", "stair") and not name:
            cat = cat_auto
            name = {"shaft": "شفت", "lift": "بئر المصاعد" if n_cars > 1 else "بئر المصعد", "stair": "السلم"}[cat]
        elif cat_auto == "stair" and name:
            flags.append(f"label '{name}' on a stair face")
        elif not name:
            if rec["r_in"] < 0.17 or (rec["r_in"] < 0.33 and rec["area"] < 1.2):
                wall_bodies.append(rec)
                continue
            if rec["area"] < 2.0 and not rec["wc_pans"] and rec.get("soil", 0.0) < 0.5 and not any(
                    P[j][1] in ("door", "opening") and P[j][0].distance(f) < 0.03
                    for j in tree.query(f.buffer(0.03))):
                # small closed pocket, no door / opening / glass: a solid block drawn as an outline
                # (corner blocks at the curved glazing, round element of F02) - not a room
                rec["pocket"] = True
                wall_bodies.append(rec)
                pockets.append({"area": round(rec["area"], 3), "centroid": _r([f.centroid.x, f.centroid.y]),
                                "bbox": _r(list(f.bounds))})
                continue
            if rec["wc_pans"] and rec["area"] < 12.0:
                name, cat = "حمام (بلا اسم)", "wc"
                flags.append("unlabelled_wc: no room label; named from the WC pan block P (FUR) inside")
            elif rec.get("soil", 0.0) >= 0.5:
                name, cat = "زرع (بلا اسم)", "planter"
                flags.append(f"unlabelled_planter: no label; {rec['soil'] * 100:.0f}% of it is covered by an "
                             f"AR-CONC hatch on W (planter soil)")
            else:
                name, cat = "فراغ بلا اسم", "void"
                flags.append("unlabelled")
        if rec["trimmed"] and cat not in ("shaft",) and rec["trimmed"] >= 0.05:
            flags.append(f"trimmed: {rec['trimmed']:.2f} m2 of thin strip(s) (< 0.32 m wide) cut off this "
                         f"space as wall body - check the drawing there")
        if any(l.get("snapped") for l in rec["labels"] if not l["note"]):
            flags.append("label_outside: label snapped from outside the polygon")
        if cat in OPEN_AIR:
            far = [l for l in rec["labels"] if not l["note"] and (l.get("snapped") or 0.0) > SNAP_FAR]
            if far:
                own = [l for l in rec["labels"] if not l["note"] and (l.get("snapped") or 0.0) <= SNAP_FAR]
                flags.append(("label_snapped_far: " if own else "only_label_snapped_far: ")
                             + ", ".join(f"'{l['text']}' {l['handle']} from {l['snapped']:.2f} m" for l in far)
                             + (" (left over from another floor?)" if own else
                                " - the only label lies far outside: is this really a " + cat + "?"))
            if outline_poly is not None and f.intersection(outline_poly).area > 0.5 * f.area:
                flags.append(f"open_air_inside_outline: {f.area:.2f} m2 lies INSIDE the try floor outline (slab "
                             f"edge); planters lie outside it - a strip between glass and parapet, not a {cat}?")
        rooms.append({"rec": rec, "name": name, "category": cat, "flags": flags, "n_cars": n_cars})

    # ---------------- geometry metrics
    # windows (openings.py) lying wholly inside a stair = the stair eye drawn on WIN (F11), not glazing
    windows, windows_in_stair = [], []
    for w in op.get("windows", []):
        ends = w.get("ends") or []
        if len(ends) >= 2 and any(h.contains(LineString([tuple(p) for p in ends])) for h in hulls):
            windows_in_stair.append(w["id"])
        else:
            windows.append(w)
    out_rooms = []
    for k, r in enumerate(sorted(rooms, key=lambda r: (CAT_ORDER.index(r["category"]) if r["category"] in CAT_ORDER else 99,
                                                        -r["rec"]["poly"].centroid.y, r["rec"]["poly"].centroid.x))):
        f = r["rec"]["poly"]
        bd, refs = boundary_breakdown(f, P, tree)
        perim = f.exterior.length + sum(i.length for i in f.interiors)
        c = f.centroid
        cat = r["category"]
        item = {
            "id": f"{fl.label}-R{k + 1:02d}", "name": r["name"], "category": cat,
            "category_ar": CATEGORY_AR.get(cat, cat),
            "open_air": cat in OPEN_AIR, "indoor": cat not in OPEN_AIR,
            "area": round(f.area, 3), "perimeter": round(perim, 3),
            "perimeter_outer": round(f.exterior.length, 3), "n_holes": len(f.interiors),
            "boundary": bd,
            "doors": refs.get("door", []), "openings": refs.get("opening", []),
            "windows": [],
            "labels": [{k2: v for k2, v in l.items() if k2 != "note" or v} for l in r["rec"]["labels"]],
            "flags": r["flags"], "centroid": _r([c.x, c.y]),
            "bbox": _r(list(f.bounds)), "inscribed_r": round(r["rec"]["r_in"], 3),
        }
        item["windows"], wpart = windows_on(f, windows)
        if cat == "stair" and win_in_stair and any(h.intersects(f) for h in hulls):
            hh = [h for h in hulls if h.intersects(f)]
            mine = [x for x in win_in_stair if any(h.contains(P_ref_geom[x]) for h in hh)] if P_ref_geom else []
            if mine:
                item["flags"].append(f"stair_eye_on_WIN: {len(mine)} WIN line(s) inside this stair ({', '.join(mine)}) "
                                     f"= the stair eye / break line drawn on WIN - ignored (not glazing, not a boundary)")
            wis = [x for x in windows_in_stair if any(h.intersects(f) for h in hh)]
            if wis:
                item["windows_in_stair_ignored"] = wis
        if wpart:
            item["windows_partial_m"] = wpart
        if r["n_cars"]:
            item["n_cars"] = r["n_cars"]
        if r["rec"]["wc_pans"] and cat == "wc":
            item["wc_pans"] = r["rec"]["wc_pans"]
        inner = f.buffer(-0.02)
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
        item["dim_checks"] = dim_checks(f, g["dims"])
        bad = [d for d in item["dim_checks"] if d["status"] == "mismatch"]
        if bad:
            item["flags"].append(f"dim_mismatch: {len(bad)} architect DIM(s) between facing faces differ > 2 cm "
                                 f"from the polygon")
        if bd.get("extension", 0) > 0:
            item["flags"].append(f"closed_by_extension: {bd['extension']:.2f} m of the boundary is a "
                                 f"virtual extension of a wall face (drawing gap)")
        if bd.get("unresolved", 0) > 0.10:
            item["flags"].append(f"unresolved_boundary: {bd['unresolved']:.2f} m")
        item["_poly"] = f
        out_rooms.append(item)

    # ---------------- floor totals
    by_cat = {}
    for cat in CAT_ORDER:
        rs = [r for r in out_rooms if r["category"] == cat]
        if rs:
            by_cat[cat] = {"name_ar": CATEGORY_AR[cat], "n": len(rs), "area": round(sum(r["area"] for r in rs), 3),
                           "perimeter": round(sum(r["perimeter"] for r in rs), 3)}
    indoor = [r for r in out_rooms if r["indoor"]]
    open_air = [r for r in out_rooms if r["open_air"]]

    # gross floor area: inside the facade outer face (indoor spaces + their walls/columns/glazing)
    R = unary_union([r["_poly"] for r in indoor if r["category"] != "void" or r["area"] > 0.5])
    solid = unary_union([mass] + [w["poly"] for w in wall_bodies] + slivers)
    near = R.buffer(0.45, join_style=2, mitre_limit=10.0)
    fp = unary_union([R, solid.intersection(near)])
    if open_air:
        fp = fp.difference(unary_union([r["_poly"] for r in open_air]).buffer(0.002))
    fp = fp.buffer(-0.07, join_style=2, mitre_limit=10.0).buffer(0.07, join_style=2, mitre_limit=10.0)
    parts = list(fp.geoms) if hasattr(fp, "geoms") else [fp]
    main = max(parts, key=lambda q: q.area)
    footprint = Polygon(main.exterior)
    dropped = [round(p.area, 3) for p in parts if p is not main and p.area > 0.01]

    totals = {
        "by_category": by_cat,
        "n_rooms": len(out_rooms),
        "net_indoor_area": round(sum(r["area"] for r in indoor), 3),
        "boundary_by_kind_indoor": {k: round(sum(r["boundary"].get(k, 0.0) for r in indoor
                                                 if r["category"] in INDOOR_CEILING), 3)
                                    for k in KIND_PRIORITY + ["unresolved"]
                                    if any(r["boundary"].get(k) for r in indoor if r["category"] in INDOOR_CEILING)},
        "boundary_by_kind_open_air": {k: round(sum(r["boundary"].get(k, 0.0) for r in open_air), 3)
                                      for k in KIND_PRIORITY + ["unresolved"]
                                      if any(r["boundary"].get(k) for r in open_air)},
        "net_usable_area": round(sum(r["area"] for r in indoor if r["category"] in
                                     ("office", "wc", "corridor", "lobby", "service")), 3),
        "ceiling_area": round(sum(r["area"] for r in indoor if r["category"] in INDOOR_CEILING), 3),
        "open_air_area": round(sum(r["area"] for r in open_air), 3),
        "gross_floor_area": round(footprint.area, 3),
        "gross_outline_perimeter": round(footprint.exterior.length, 3),
        "walls_columns_area": round(footprint.area - sum(r["area"] for r in indoor if footprint.buffer(0.01).contains(r["_poly"])), 3),
        "footprint_bbox": _r(list(footprint.bounds)),
        "footprint_dropped_parts": dropped,
    }
    names = Counter(r["name"] for r in out_rooms if r["category"] == "office")
    offices = sorted(int(m.group(1)) for r in out_rooms if r["category"] == "office"
                     for m in re.finditer(r"مكتب\s*(\d+)", r["name"]))
    checks = {
        "labels_unplaced": unplaced,
        "label_count": len(g["texts"]),
        "office_numbers": offices,
        "offices_missing": [n for n in range(1, (max(offices) if offices else 0) + 1) if n not in offices],
        "duplicate_names": [n for n, c in names.items() if c > 1],
        "rooms_flagged": [{"id": r["id"], "name": r["name"], "flags": r["flags"]} for r in out_rooms if r["flags"]],
        "extensions": exts,
        "corridor_lobby_splits": splits,
        "closed_pockets_as_solid": pockets,
        "primitives_skipped": skipped,
        "win_inside_stair_skipped": win_in_stair,
        "windows_in_stair_ignored": windows_in_stair,
        "wall_bodies": {"n": len(wall_bodies) + len(slivers),
                        "area": round(sum(w["area"] for w in wall_bodies) + sum(x.area for x in slivers), 3)},
        "outside_pieces": len(outside),
        "dims_checked": sum(len(r["dim_checks"]) for r in out_rooms),
        # every door should border exactly two spaces; every window at least one room
        "doors_not_two_sided": [{"door": d["id"], "rooms": [r["id"] for r in out_rooms if d["id"] in r["doors"]]}
                                for d in op.get("doors", [])
                                if sum(1 for r in out_rooms if d["id"] in r["doors"]) != 2],
        "windows_unassigned": [w["id"] for w in windows if not any(w["id"] in r["windows"] for r in out_rooms)],
        "dims_ok": sum(1 for r in out_rooms for d in r["dim_checks"] if d["status"] == "ok"),
        "dims_jog": [dict(room=r["id"], **d) for r in out_rooms for d in r["dim_checks"] if d["status"] == "jog"],
        "dims_mismatch": [dict(room=r["id"], **d) for r in out_rooms for d in r["dim_checks"]
                          if d["status"] == "mismatch"],
    }
    res = {
        "floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
        "file": fl.file.name, "sheet_index": fl.sheet_index, "units": "m / m2, LOCAL frame (diwan_common)",
        "storey_height": STOREY_HEIGHT, "openings_source": op_src,
        "rooms": out_rooms, "totals": totals, "checks": checks,
        "_P": P, "_footprint": footprint, "_wall_bodies": [w["poly"] for w in wall_bodies] + slivers, "_g": g, "_op": op,
        "elapsed_s": round(time.time() - t0, 1),
    }
    return res


def to_json(res):
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items() if not k.startswith("_")}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if hasattr(o, "item"):
            return o.item()
        return o
    return clean(res)


# ============================================================================
# 8. review drawing
# ============================================================================
def render(res, out_png, zoom=None, dpi=120, fs=6.0, title_extra=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MplPoly, Patch
    plt.rcParams["font.family"] = "Tahoma"

    g = res["_g"]
    if zoom:
        x0, y0, x1, y1 = zoom
    else:
        x0, y0, x1, y1 = res["totals"]["footprint_bbox"]
        x0, y0, x1, y1 = x0 - 1.5, y0 - 1.5, x1 + 1.5, y1 + 1.5
        for r in res["rooms"]:
            b = r["bbox"]
            x0, y0, x1, y1 = min(x0, b[0] - 0.5), min(y0, b[1] - 0.5), max(x1, b[2] + 0.5), max(y1, b[3] + 0.5)
    W = 14.0 if not zoom else 13.0
    H = W * (y1 - y0) / (x1 - x0)
    fig, ax = plt.subplots(figsize=(W, H + 1.0))

    from matplotlib.path import Path as MPath
    from matplotlib.patches import PathPatch

    def draw_poly(p, **kw):
        polys = list(p.geoms) if hasattr(p, "geoms") else [p]
        for q in polys:
            if q.geom_type != "Polygon" or q.is_empty:
                continue
            verts, codes = [], []
            for ring in [q.exterior] + list(q.interiors):      # holes cut out (columns inside a room)
                cs = list(ring.coords)
                verts.extend(cs)
                codes.extend([MPath.MOVETO] + [MPath.LINETO] * (len(cs) - 2) + [MPath.CLOSEPOLY])
            ax.add_patch(PathPatch(MPath(verts, codes), **kw))

    # footprint
    fp = res["_footprint"]
    ax.plot(*fp.exterior.xy, color="#444", lw=1.6, ls="-", zorder=1)
    for wb in res["_wall_bodies"]:
        draw_poly(wb, fc="#d9d9d9", ec="none", lw=0, zorder=2)
    for geom, kind, ref in res["_P"]:
        if kind == "column":
            draw_poly(geom, fc="#2ca02c", ec="#1b5e20", lw=0.3, alpha=0.75, zorder=3)
        elif kind == "solid_try":
            draw_poly(geom, fc="#8d6e63", ec="none", zorder=3)
    for r in res["rooms"]:
        col = CAT_COLORS.get(r["category"], "#ff00ff")
        flagged = any(not f.startswith(("corridor_lobby_open", "closed_by_extension")) for f in r["flags"])
        draw_poly(r["_poly"], fc=col, ec="#c00000" if flagged else "#333", lw=1.4 if flagged else 0.4,
                  alpha=0.85, zorder=4, hatch="///" if r["open_air"] else None)
    # raw lines on top (thin)
    for key, c, lw in (("w", "#000000", 0.35), ("zero", "#000000", 0.35), ("win", "#0077aa", 0.45)):
        for rec in g[key]:
            xs, ys = zip(*rec["pts"])
            ax.plot(xs, ys, color=c, lw=lw, zorder=5)
    for rec in g["st"]:
        xs, ys = zip(*rec["pts"])
        ax.plot(xs, ys, color="#8c564b", lw=0.25, zorder=5)
    for geom, kind, ref in res["_P"]:
        if kind == "door":
            draw_poly(geom, fc="#ffffff", ec="#1f77b4", lw=0.6, zorder=6)
        elif kind == "opening":
            draw_poly(geom, fc="#ffffff", ec="#ff7f0e", lw=0.6, zorder=6)
        elif kind == "extension":
            xs, ys = geom.xy
            ax.plot(xs, ys, color="#e600e6", lw=1.6, zorder=7)
    for d in g["doors"]:
        for arc in d["arcs"]:
            xs, ys = zip(*arc)
            ax.plot(xs, ys, color="#1f77b4", lw=0.35, zorder=6)
    # labels
    for r in res["rooms"]:
        f = r["_poly"]
        if zoom and not f.intersects(box(x0, y0, x1, y1)):
            continue
        p = polylabel(f, tolerance=0.02) if f.area > 0.3 else f.representative_point()
        short = r["id"].split("-")[1]
        if r["category"] in ("shaft",) and r["area"] < 1.0:
            txt = f"{short}\n{r['area']:.2f}"
            size = fs * 0.65
        elif r["category"] in ("planter",):
            txt = r["name"] + "\n" + f"{r['area']:.2f} m2"
            size = fs * 0.8
        else:
            txt = r["name"] + "\n" + f"{short}  {r['area']:.2f} m2  P={r['perimeter']:.2f}"
            size = fs
        rot = 90 if (f.bounds[3] - f.bounds[1]) > 3 * (f.bounds[2] - f.bounds[0]) and f.area < 12 else 0
        ax.text(p.x, p.y, txt, ha="center", va="center", fontsize=size, zorder=9, rotation=rot,
                color="#000", bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.3), clip_on=True)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.15, color="#bbb")
    t = res["totals"]
    ax.set_title(f"{res['floor']} {res['name_ar']} {res['level']:+.2f}  — الفراغات: {t['n_rooms']} | "
                 f"صافي داخلي {t['net_indoor_area']:.2f} م² | إجمالي (حتى الوجه الخارجي للواجهة) "
                 f"{t['gross_floor_area']:.2f} م² | مكشوف {t['open_air_area']:.2f} م²{title_extra}", fontsize=9)
    handles = [Patch(fc=CAT_COLORS[c], ec="#333", label=f"{CATEGORY_AR[c]} ({c})") for c in CAT_ORDER
               if any(r["category"] == c for r in res["rooms"])]
    handles += [Patch(fc="#2ca02c", label="خرسانة (أعمدة/كور)"), Patch(fc="#d9d9d9", label="جسم حائط/إطار"),
                Patch(fc="white", ec="#1f77b4", label="باب (يغلق الفجوة)"),
                Patch(fc="white", ec="#ff7f0e", label="فتحة بلا باب"),
                Patch(fc="#e600e6", label="امتداد افتراضي لحائط (فجوة رسم)"),
                Patch(fc="white", ec="#c00000", lw=1.4, label="فراغ عليه ملاحظة flag")]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=7, frameon=False)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ============================================================================
# 9. runner
# ============================================================================
def run(floors=None, png=True, zoom=None, use_cache=True, refresh_openings=False):
    fls = [f for f in all_floors() if f.floor_no] if not floors else [get_floor(int(n)) for n in floors]
    ROOM_OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for fl in fls:
        res = analyze_floor(fl, use_cache=use_cache, refresh_openings=refresh_openings)
        data = to_json(res)
        (ROOM_OUT / f"{fl.label}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if png:
            render(res, ROOM_OUT / f"{fl.label}.png", dpi=110)
            fb = res["totals"]["footprint_bbox"]
            ym = (fb[1] + fb[3]) / 2
            render(res, ROOM_OUT / f"{fl.label}_south.png", zoom=(fb[0] - 1.2, fb[1] - 1.5, fb[2] + 2.5, ym + 1.0),
                   dpi=130, fs=7.5, title_extra="  [جنوب]")
            render(res, ROOM_OUT / f"{fl.label}_north.png", zoom=(fb[0] - 1.2, ym - 1.0, fb[2] + 2.5, fb[3] + 1.5),
                   dpi=130, fs=7.5, title_extra="  [شمال]")
            if zoom:
                render(res, ROOM_OUT / f"{fl.label}_zoom.png", zoom=zoom, dpi=150, fs=8)
        t = res["totals"]
        summary[fl.label] = {"level": fl.level, **{k: v for k, v in t.items() if k != "footprint_bbox"},
                             "n_flagged": len(res["checks"]["rooms_flagged"]),
                             "labels_unplaced": len(res["checks"]["labels_unplaced"]),
                             "offices_missing": res["checks"]["offices_missing"],
                             "extensions": len(res["checks"]["extensions"]),
                             "dims_checked": res["checks"]["dims_checked"],
                             "doors_not_two_sided": len(res["checks"]["doors_not_two_sided"]),
                             "windows_unassigned": res["checks"]["windows_unassigned"],
                             "dims_ok": res["checks"]["dims_ok"],
                             "dims_jog": len(res["checks"]["dims_jog"]),
                             "dims_mismatch": len(res["checks"]["dims_mismatch"])}
        print(f"{fl.label} {fl.level:+.2f}: rooms={t['n_rooms']} net_indoor={t['net_indoor_area']:.2f} "
              f"gross={t['gross_floor_area']:.2f} open_air={t['open_air_area']:.2f} "
              f"flagged={len(res['checks']['rooms_flagged'])} unplaced={len(res['checks']['labels_unplaced'])} "
              f"ext={len(res['checks']['extensions'])} dims={res['checks']['dims_checked']}"
              f" ok={res['checks']['dims_ok']} jog={len(res['checks']['dims_jog'])}"
              f" doors!=2:{len(res['checks']['doors_not_two_sided'])} win_unassigned:{len(res['checks']['windows_unassigned'])}"
              f" mismatch={len(res['checks']['dims_mismatch'])} ({res['elapsed_s']} s)")
    # summary.json: floors of this run replace their own entries, other floors are kept
    sp = ROOM_OUT / "summary.json"
    merged = {}
    if sp.exists():
        try:
            merged = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            merged = {}
    merged.update(summary)
    merged = {k: merged[k] for k in sorted(merged)}
    sp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description="Rooms / spaces reader for the Diwan plans (default: all floors)")
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (2..11); default all")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--zoom", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                    help="extra zoomed PNG (local metres)")
    ap.add_argument("--no-cache", action="store_true", help="re-read the DXF (geometry cache in output/rooms/_cache)")
    ap.add_argument("--refresh-openings", action="store_true", help="recompute openings instead of output/openings/*.json")
    a = ap.parse_args()
    run(a.floors or None, png=not a.no_png, zoom=a.zoom, use_cache=not a.no_cache,
        refresh_openings=a.refresh_openings)


if __name__ == "__main__":
    main()
