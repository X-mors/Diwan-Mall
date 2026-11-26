# -*- coding: utf-8 -*-
"""
قارئ اللوحة الإنشائية للديوان (Dewan STR-UPDATED-REV01) — البلاطات والمناسيب والسُّمك والكمرات
==============================================================================================

Reads dxf/Dewan_STR_REV01.dxf (ODA conversion of drawings/"Dewan STR-UPDATED-REV01.dwg") and
returns, for every slab plan ("سقف ..."):

  * which ARCHITECTURAL floor it is the CEILING of.  A structural "سقف الدور X" sheet is the
    slab ABOVE floor X (not the floor-X plan).  The upper sheets are mis-named in the drawing
    (owner, 2026-11-26): "السابع المتكرر" = 8th, "الثامن" = 9th, "التاسع" = 10th,
    "العاشر" = 11th.  "سقف 6 و 5 و 3 و 2" is the typical slab above floors 2, 3, 5, 6.
  * top-of-slab level (the big "+xx.xx" mark in the plan; the typical sheet has none, its
    levels follow the 3.30 m storey of the drawing).  The top of a slab is ONE level per floor;
    the thickness changes downwards only.
  * thickness zones: faces of the slab outline (layer "Slab edge") cut by the "Etabs-Slab"
    zone polygons, the small "Slab edge" split lines and the closed "slab thickness" pads,
    each labelled by the big thickness bubble ("slab thickness" TEXT, 20 / 35 cm) inside it.
    A face with no bubble takes the plan's general thickness (the one of the largest labelled
    face) and is flagged `assumed`.  Small bubbles (< 0.3 m text) are stair flights.
  * beams: pairs of parallel "BEAMS" lines (width 0.12-0.40) labelled "ك n ) b * h (" (cm).
    h = total depth from the top of the slab.
  * columns (layer Etabs-col, also inside the blocks inserted on every plan).

Every plan is the same drawing translated: the axes block (layer RC) is inserted at one
reference point per plan, rotation 0, scale 1.  The building is rotated 10 deg like the
architectural plans.  `to_arch_local()` maps a structural plan point to the architectural
LOCAL frame (diwan_common: rotation removed, origin = min corner of the architectural Etabs-col
columns): rotate by -angle, subtract the plan reference point, add ONE offset found by
matching the structural columns to the architectural ones (`calibrate()`).

CLI:
    python tools/str_slabs.py                 # table of plans / levels / zones / beams
    python tools/str_slabs.py --json          # + output/structure_str/slabs.json
API:
    from str_slabs import read_structural, plan_for_ceiling, soffit_profile
    S = read_structural()
    P = plan_for_ceiling(S, 9)                # slab above architectural floor 9
    soffit_profile(P, (x0, y0), (x1, y1))     # [(t0, t1, depth_m, source)] along a local segment
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import pickle
import re
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diwan_common import OUT_DIR, REPO, rot  # noqa: E402
from sosa_decode import decode_if_encoded, is_arabic_style  # noqa: E402

STR_DXF = REPO / "dxf" / "Dewan_STR_REV01.dxf"
OUT = OUT_DIR / "structure_str"
CACHE_VER = "s2"
STR_STOREY = 3.30          # m, top-to-top of slab as DRAWN in the structural sheets (+4.50 ... +40.80)
EXEC_STOREY = 3.20         # m, top-to-top AS EXECUTED (owner 2026-11-26: clear 3.00 under the 20 cm slab on
                           # floors 2-11) = the architectural levels (+8.90 ... +37.70).  The structural
                           # level marks (3.30 steps) are WRONG; only thicknesses and beams are used.
ANGLE = 10.0               # building rotation (same as the architectural plans)
AXES_BLOCK_LAYER = "RC"    # the axes block inserted once per plan = the plan reference point

# decoded title -> architectural floors whose CEILING this slab is (owner's correction applied)
TITLE_CEILING_OF = [
    (r"سقف\s+البدروم\s+السفلي", [-2]),
    (r"سقف\s+البدروم\s+العلوي", [-1]),
    (r"سقف\s+السابع\s+المتكرر", [8]),
    (r"سقف\s+6\s*و\s*5\s*و\s*3\s*و\s*2", [2, 3, 5, 6]),
    (r"سقف\s+الارضي", [0]),
    (r"سقف\s+الاول", [1]),
    (r"سقف\s+الرابع", [4]),
    (r"سقف\s+السابع", [7]),
    (r"سقف\s+الثامن", [9]),
    (r"سقف\s+التاسع", [10]),
    (r"سقف\s+العاشر", [11]),
]
TITLE_NOTE = "upper sheets renamed by the owner: السابع المتكرر=8, الثامن=9, التاسع=10, العاشر=11"

LEVEL_RE = re.compile(r"^\s*\+\s*(\d+\.\d+)\s*$")
BEAM_RE = re.compile(r"(?:ك|كا)\s*(\d+)\s*\)\s*(\d+)\s*\*\s*(\d+)\s*\(")
THK_RE = re.compile(r"^\s*(\d{2,3})\s*$")


def _r(v, n=3):
    return None if v is None else round(float(v), n)


# ----------------------------------------------------------------------------- raw extraction
def _flatten(e, tol=0.01):
    from ezdxf import path as ezpath
    try:
        return [(v.x, v.y) for v in ezpath.make_path(e).flattening(tol)]
    except Exception:
        return []


def _hatch_polys(e):
    from ezdxf import path as ezpath
    out = []
    try:
        for p in ezpath.from_hatch(e):
            pts = [(v.x, v.y) for v in p.flattening(0.01)]
            if len(pts) >= 3:
                out.append(pts)
    except Exception:
        pass
    return out


def extract(use_cache=True):
    """Raw world geometry of the structural DXF (cached: the DXF takes ~20 s to load)."""
    OUT.mkdir(parents=True, exist_ok=True)
    st = STR_DXF.stat()
    cache = OUT / "_cache" / f"raw_{CACHE_VER}_{st.st_size}.pkl"
    if use_cache and cache.exists():
        with open(cache, "rb") as f:
            return pickle.load(f)
    import ezdxf
    logging.disable(logging.WARNING)
    doc = ezdxf.readfile(str(STR_DXF))
    logging.disable(logging.NOTSET)
    msp = doc.modelspace()
    g = {"anchors": [], "texts": [], "slab_edge": [], "etabs_slab": [], "thk_polys": [],
         "beams": [], "cols": [], "x_lines": [], "w_lines": []}
    for e in msp:
        lay, t = e.dxf.layer, e.dxftype()
        if t == "INSERT" and lay == AXES_BLOCK_LAYER:
            g["anchors"].append({"x": e.dxf.insert.x, "y": e.dxf.insert.y, "block": e.dxf.name})
        if t in ("TEXT", "MTEXT"):
            raw = e.dxf.text if t == "TEXT" else e.plain_text()
            style = e.dxf.get("style", "Standard")
            txt = decode_if_encoded(raw) if is_arabic_style(doc, style) else raw
            h = e.dxf.get("height", 0.0) if t == "TEXT" else e.dxf.get("char_height", 0.0)
            g["texts"].append({"layer": lay, "x": e.dxf.insert.x, "y": e.dxf.insert.y, "h": h,
                               "text": txt.strip(), "raw": raw, "handle": e.dxf.handle})
        if lay == "Slab edge" and t in ("LWPOLYLINE", "LINE", "ARC", "POLYLINE"):
            g["slab_edge"].append({"pts": _flatten(e), "closed": bool(getattr(e, "closed", False)),
                                   "handle": e.dxf.handle})
        # facade walls drawn on the structural sheets: they close a slab outline left open (sheets 9-11 SW)
        if lay == "W" and t in ("LWPOLYLINE", "LINE", "ARC", "POLYLINE"):
            pts = _flatten(e)
            if len(pts) >= 2:
                g["w_lines"].append(pts)
        if lay == "Etabs-Slab" and t == "LWPOLYLINE":
            g["etabs_slab"].append({"pts": _flatten(e), "handle": e.dxf.handle})
        if lay == "slab thickness" and t == "LWPOLYLINE" and e.closed:
            g["thk_polys"].append({"pts": _flatten(e), "handle": e.dxf.handle})
        if lay == "BEAMS" and t == "LINE":
            g["beams"].append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y), e.dxf.handle))
        if lay == "X" and t == "LINE":
            g["x_lines"].append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
        # columns: Etabs-col directly, or inside the column blocks of each plan
        if t == "INSERT" and e.dxf.name not in ("A$Ce5825899",):
            try:
                ves = list(e.virtual_entities())
            except Exception:
                ves = []
            for v in ves:
                if v.dxf.layer == "Etabs-col" and v.dxftype() == "LWPOLYLINE":
                    g["cols"].append({"pts": _flatten(v), "src": f"block {e.dxf.name} {e.dxf.handle}"})
        if lay == "Etabs-col" and t == "LWPOLYLINE":
            g["cols"].append({"pts": _flatten(e), "src": f"model space {e.dxf.handle}"})
    cache.parent.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as f:
        pickle.dump(g, f)
    return g


# ----------------------------------------------------------------------------- plans
def _local(p, anchor):
    """structural world -> structural plan frame (rotation removed, anchor = origin)."""
    a = rot(anchor, -ANGLE)
    q = rot(p, -ANGLE)
    return (q[0] - a[0], q[1] - a[1])


def _poly(pts):
    from shapely.geometry import Polygon
    if len(pts) < 3:
        return None
    P = Polygon(pts).buffer(0)
    return None if P.is_empty else P


def _close_open_outline(pts, w_lines):
    """Some sheets (ceilings of 9, 10, 11) leave the Slab-edge polyline OPEN at the SW corner
    (from the step at the west wall down to the end of the SW arc).  Closing it with a straight
    chord invents a diagonal slab edge.  The engineer drew the facade wall (layer W) along the
    missing edge, so close the gap along those W lines; return None if they do not close it."""
    from shapely.geometry import LineString, Point, box
    from shapely.ops import nearest_points, polygonize, unary_union
    a, b = Point(pts[0]), Point(pts[-1])
    region = box(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)).buffer(2.5)
    W = [LineString(q) for q in w_lines if LineString(q).intersects(region)]
    W = [w.intersection(region) for w in W]
    W = [w for w in W if not w.is_empty and w.length > 0.05]
    if not W:
        return None
    Wu = unary_union(W)
    path = LineString(pts)
    lines = [path] + W
    for p in (a, b):
        q = nearest_points(p, Wu)[1]
        if p.distance(q) < 2.0:
            lines.append(LineString([p, q]))
        else:
            return None
    faces = list(polygonize(unary_union(lines)))
    if not faces:
        return None
    P = max(faces, key=lambda f: f.area)
    chord = _poly(pts)
    # sanity: the closed outline differs from the chord closure only near the gap
    if chord is None or P.symmetric_difference(chord).area > 0.25 * a.distance(b) * 4 + 5:
        return None
    return P.buffer(0)


def _plans(g):
    from shapely.geometry import Point, box
    titles = []
    for t in g["texts"]:
        if t["layer"] != "TEXT-D" or t["h"] < 0.3 or not t["text"].startswith("سقف"):
            continue
        for pat, fls in TITLE_CEILING_OF:
            if re.search(pat, t["text"]):
                titles.append({**t, "ceiling_of": fls})
                break
    anchors = sorted({(round(a["x"], 3), round(a["y"], 3)) for a in g["anchors"]})
    outlines = []
    for s in g["slab_edge"]:
        P = _poly(s["pts"])
        if P is not None and P.area > 300:
            gap = math.dist(s["pts"][0], s["pts"][-1])
            if gap > 0.3:
                P = _close_open_outline(s["pts"], g.get("w_lines", [])) or P
            outlines.append((P, s["handle"]))
    plans = []
    for ax, ay in anchors:
        # the slab outline of this plan = the big Slab-edge polygon nearest the anchor
        cand = sorted(outlines, key=lambda o: o[0].centroid.distance(Point(ax, ay)))
        if not cand or cand[0][0].centroid.distance(Point(ax, ay)) > 15:
            continue
        P, h = cand[0]
        x0, y0, x1, y1 = P.bounds
        # title: the "سقف ..." text just below / right of the outline
        tt = [t for t in titles if x0 - 5 <= t["x"] <= x1 + 25 and y0 - 30 <= t["y"] <= y0 + 5]
        tt.sort(key=lambda t: abs(t["x"] - (x1 + 2)) + abs(t["y"] - y0))
        title = tt[0] if tt else None
        B = box(x0 - 1, y0 - 1, x1 + 1, y1 + 1)
        lv = [t for t in g["texts"] if t["h"] >= 0.3 and LEVEL_RE.match(t["raw"] or "")
              and B.contains(Point(t["x"], t["y"]))]
        level = float(LEVEL_RE.match(lv[0]["raw"]).group(1)) if lv else None
        plans.append({"anchor": (ax, ay), "outline_handle": h, "_outline_w": P, "bbox_w": (x0, y0, x1, y1),
                      "title": title["text"] if title else None,
                      "ceiling_of": title["ceiling_of"] if title else [],
                      "level_top": level, "level_source": "plan level mark" if lv else None})
    # typical sheet has no level mark: fill from the 3.30 m storey of the drawing
    known = {f: p["level_top"] for p in plans for f in p["ceiling_of"] if p["level_top"] is not None and len(p["ceiling_of"]) == 1}
    for p in plans:
        if p["level_top"] is None and p["ceiling_of"]:
            lv = []
            for f in p["ceiling_of"]:
                ref = min(known, key=lambda k: abs(k - f)) if known else None
                lv.append(_r(known[ref] + (f - ref) * STR_STOREY, 2) if ref is not None else None)
            p["levels_top_by_floor"] = dict(zip(p["ceiling_of"], lv))
            p["level_source"] = f"no mark on the sheet: nearest marked ceiling +/- {STR_STOREY} m per storey"
        else:
            p["levels_top_by_floor"] = {f: p["level_top"] for f in p["ceiling_of"]}
    return plans


RASTER = 0.05      # m, grid of the thickness-zone flood fill
BARRIER_R = 0.12   # m, half-width of a rasterised split line


def _raster_faces(O, lines):
    """Faces of the outline O cut by `lines`, by flood fill on a RASTER grid.
    (GEOS polygonize misses splits whose ends lie 1e-12 off another line; a raster does not care.)
    Barrier cells are handed to the nearest face, so the faces tile the outline."""
    import numpy as np
    from matplotlib.path import Path as MPath
    from scipy import ndimage
    from shapely.geometry import box
    from shapely.ops import unary_union
    x0, y0, x1, y1 = O.bounds
    x0 -= 0.2; y0 -= 0.2
    nx = int((x1 + 0.2 - x0) / RASTER) + 1
    ny = int((y1 + 0.2 - y0) / RASTER) + 1
    xs = x0 + (np.arange(nx) + 0.5) * RASTER
    ys = y0 + (np.arange(ny) + 0.5) * RASTER
    XX, YY = np.meshgrid(xs, ys)
    pts = np.column_stack([XX.ravel(), YY.ravel()])
    inside = np.zeros(nx * ny, bool)
    for ring in [O.exterior] if O.geom_type == "Polygon" else [p.exterior for p in O.geoms]:
        inside |= MPath(np.asarray(ring.coords)).contains_points(pts)
    inside = inside.reshape(ny, nx)
    bar = np.zeros((ny, nx), bool)
    for L in lines:
        segs = [L] if L.geom_type in ("LineString", "LinearRing") else list(getattr(L, "geoms", []))
        for S_ in segs:
            n = max(2, int(S_.length / (RASTER / 2)) + 1)
            P = np.array([S_.interpolate(t, normalized=True).coords[0] for t in np.linspace(0, 1, n)])
            ix = ((P[:, 0] - x0) / RASTER).astype(int)
            iy = ((P[:, 1] - y0) / RASTER).astype(int)
            ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
            bar[iy[ok], ix[ok]] = True
    r = int(round(BARRIER_R / RASTER))
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    bar = ndimage.binary_dilation(bar, structure=(xx * xx + yy * yy) <= r * r)
    free = inside & ~bar
    lab, n = ndimage.label(free)          # 4-connectivity
    if n == 0:
        return [O]
    # barrier cells inside the outline -> nearest region
    _, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
    full = np.where(inside, lab[iy, ix], 0)
    faces = []
    for k in range(1, n + 1):
        m = full == k
        if m.sum() * RASTER * RASTER < 0.05:
            continue
        boxes = []
        for j in np.nonzero(m.any(axis=1))[0]:
            row = np.concatenate([[0], m[j].astype(np.int8), [0]])
            d = np.diff(row)
            for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
                boxes.append(box(x0 + a * RASTER, y0 + j * RASTER, x0 + b * RASTER, y0 + (j + 1) * RASTER))
        F = unary_union(boxes).intersection(O).simplify(RASTER / 2)
        if not F.is_empty and F.area > 0.05:
            faces.append(F.buffer(0))
    return faces



def _zones(g, plan):
    """Thickness faces of one slab plan (structural plan frame)."""
    from shapely.geometry import LineString, Point
    from shapely.ops import polygonize, unary_union
    O = plan["_outline_w"]
    Ob = O.buffer(0.05)
    lines = [O.exterior]
    # the outline polyline itself may trace a split line in and out (a spike that buffer(0)
    # removes, e.g. the south 35/20 limit on the lower sheets) -> keep its raw linework too
    raw = next((s["pts"] for s in g["slab_edge"] if s["handle"] == plan["outline_handle"]), None)
    if raw and len(raw) >= 2:
        lines.append(LineString(raw + [raw[0]]) if math.dist(raw[0], raw[-1]) <= 0.3 else LineString(raw))
    for s in g["slab_edge"]:
        if len(s["pts"]) >= 2:
            L = LineString(s["pts"])
            if Ob.intersects(L) and s["handle"] != plan["outline_handle"]:
                lines.append(L)
    for z in g["etabs_slab"] + g["thk_polys"]:
        if len(z["pts"]) >= 3:
            L = LineString(z["pts"] + [z["pts"][0]])
            if Ob.intersects(L):
                lines.append(L)
    # split lines drawn short of the outline / of each other (F10 south strip: gaps 0.1-0.6 m):
    # join each free end to the nearest outline point or other line within SNAP
    SNAP = 0.7
    splits = lines[1:]
    for i, L in enumerate(splits):
        for end in (Point(L.coords[0]), Point(L.coords[-1])):
            others = [O.exterior] + [M for j, M in enumerate(splits) if j != i]
            if any(M.distance(end) < 1e-3 for M in others):
                continue
            # first: extend along the line's own direction (up to 1.5 m) to the first thing it hits
            cs = list(L.coords)
            a0, a1 = (cs[1], cs[0]) if end.equals(Point(cs[0])) else (cs[-2], cs[-1])
            dx, dy = a1[0] - a0[0], a1[1] - a0[1]
            n = math.hypot(dx, dy)
            hit = None
            if n > 1e-9:
                ray = LineString([a1, (a1[0] + dx / n * 1.5, a1[1] + dy / n * 1.5)])
                for M in others:
                    X = ray.intersection(M)
                    if X.is_empty:
                        continue
                    pts = [X] if X.geom_type == "Point" else [g for g in getattr(X, "geoms", []) if g.geom_type == "Point"]
                    for q in pts:
                        d = end.distance(q)
                        if d > 1e-6 and (hit is None or d < hit[0]):
                            hit = (d, q)
            if hit is not None:
                lines.append(LineString([end, hit[1]]))
                continue
            best = min(others, key=lambda M: M.distance(end))
            if best.distance(end) <= SNAP:
                from shapely.ops import nearest_points
                q = nearest_points(end, best)[1]
                lines.append(LineString([end, q]))
    faces = _raster_faces(O, lines[1:])
    bub = [t for t in g["texts"] if t["layer"] == "slab thickness" and t["h"] >= 0.3 and THK_RE.match(t["text"])
           and O.buffer(0.5).contains(Point(t["x"], t["y"]))]
    out = []
    for f in faces:
        inside = [int(THK_RE.match(t["text"]).group(1)) for t in bub if f.contains(Point(t["x"], t["y"]))]
        out.append({"_poly_w": f, "area": f.area, "labels": inside,
                    "_bubbles_w": [(t["x"], t["y"], int(THK_RE.match(t["text"]).group(1))) for t in bub
                                   if f.contains(Point(t["x"], t["y"]))]})
    # a small pad (closed 'slab thickness' polygon, ~1 m2 drop at a column) is labelled by a
    # bubble drawn just beside it: move that bubble's value onto the pad
    for z in out:
        if z["labels"] or z["area"] > 5:
            continue
        near = sorted(bub, key=lambda t: z["_poly_w"].distance(Point(t["x"], t["y"])))
        if near and z["_poly_w"].distance(Point(near[0]["x"], near[0]["y"])) <= 1.5:
            v = int(THK_RE.match(near[0]["text"]).group(1))
            z["labels"] = [v]
            z["label_moved"] = True
            for o in out:
                if o is not z and v in o["labels"] and o["_poly_w"].contains(Point(near[0]["x"], near[0]["y"])):
                    o["labels"].remove(v)
    labelled = [z for z in out if z["labels"]]
    general = None
    if labelled:
        general = Counter()
        for z in labelled:
            general[max(z["labels"])] += z["area"]
        general = general.most_common(1)[0][0]
    for z in out:
        if z["labels"]:
            z["thickness"] = max(z["labels"]) / 100.0
            z["assumed"] = len(set(z["labels"])) > 1
        else:
            z["thickness"] = (general or 20) / 100.0
            z["assumed"] = True
    # bubbles that fell outside every face (drawn on the edge) -> reported
    plan["general_thickness"] = (general or 20) / 100.0
    return out


def _beams(g, plan):
    """Beam bands from pairs of parallel BEAMS lines inside the outline, labelled b*h (cm)."""
    from shapely.geometry import LineString, Point, Polygon
    O = plan["_outline_w"].buffer(0.5)
    segs = [(a, b, h) for a, b, h in g["beams"] if O.contains(Point(a)) or O.contains(Point(b))]
    bands = []
    used = set()
    for i, (a, b, h) in enumerate(segs):
        L1 = math.dist(a, b)
        if L1 < 0.3:
            continue
        ux, uy = (b[0] - a[0]) / L1, (b[1] - a[1]) / L1
        best = None
        for j, (c, d, h2) in enumerate(segs):
            if j == i or j in used:
                continue
            L2 = math.dist(c, d)
            if L2 < 0.3:
                continue
            vx, vy = (d[0] - c[0]) / L2, (d[1] - c[1]) / L2
            if abs(ux * vy - uy * vx) > 0.02:
                continue
            off = abs((c[0] - a[0]) * -uy + (c[1] - a[1]) * ux)
            if not 0.10 <= off <= 0.42:
                continue
            ta = sorted(((c[0] - a[0]) * ux + (c[1] - a[1]) * uy, (d[0] - a[0]) * ux + (d[1] - a[1]) * uy))
            ov = min(L1, ta[1]) - max(0, ta[0])
            if ov < 0.3:
                continue
            if best is None or off < best[0]:
                best = (off, j, ta)
        if best is None:
            continue
        off, j, ta = best
        used.update({i, j})
        c, d, _ = segs[j]
        s0, s1 = max(0, ta[0]), min(L1, ta[1])
        nx, ny = -uy, ux
        sg = 1 if ((c[0] - a[0]) * nx + (c[1] - a[1]) * ny) > 0 else -1
        p0 = (a[0] + ux * s0, a[1] + uy * s0)
        p1 = (a[0] + ux * s1, a[1] + uy * s1)
        q1 = (p1[0] + sg * nx * off, p1[1] + sg * ny * off)
        q0 = (p0[0] + sg * nx * off, p0[1] + sg * ny * off)
        bands.append({"_poly_w": Polygon([p0, p1, q1, q0]), "width": off, "handles": [h, segs[j][2]]})
    labels = []
    for t in g["texts"]:
        m = BEAM_RE.search(t["text"])
        if m and plan["_outline_w"].buffer(2).contains(Point(t["x"], t["y"])):
            labels.append({"name": f"ك{m.group(1)}", "b": int(m.group(2)) / 100, "h": int(m.group(3)) / 100,
                           "x": t["x"], "y": t["y"]})
    for bd in bands:
        cands = [lb for lb in labels if abs(lb["b"] - bd["width"]) <= 0.04]
        cands.sort(key=lambda lb: bd["_poly_w"].distance(Point(lb["x"], lb["y"])))
        if cands and bd["_poly_w"].distance(Point(cands[0]["x"], cands[0]["y"])) <= 2.5:
            lb = cands[0]
            bd.update({"name": lb["name"], "b": lb["b"], "depth": lb["h"], "label_dist": _r(bd["_poly_w"].distance(Point(lb["x"], lb["y"])), 2)})
        else:
            near = sorted(labels, key=lambda lb: bd["_poly_w"].distance(Point(lb["x"], lb["y"])))
            bd.update({"name": None, "b": _r(bd["width"], 2),
                       "depth": max((lb["h"] for lb in labels), default=None), "assumed": True,
                       "note": "no b*h label of this width nearby -> deepest beam of the plan assumed"
                               + (f" (nearest label {near[0]['name']})" if near else "")})
    return bands, labels


def _columns(g, plan):
    from shapely.geometry import Point
    O = plan["_outline_w"].buffer(1.0)
    out = []
    seen = []
    for c in g["cols"]:
        P = _poly(c["pts"])
        if P is None or P.area < 0.05 or P.area > 15 or not O.contains(P.centroid):
            continue
        if any(P.symmetric_difference(Q).area < 0.02 for Q in seen):
            continue
        seen.append(P)
        out.append({"_poly_w": P, "src": c["src"]})
    return out


# ----------------------------------------------------------------------------- frames
def _rot_poly(P, anchor, off=(0.0, 0.0)):
    from shapely.affinity import rotate, translate
    a = rot(anchor, -ANGLE)
    Q = rotate(P, -ANGLE, origin=(0, 0), use_radians=False)
    return translate(Q, -a[0] + off[0], -a[1] + off[1])


def _arch_columns():
    """Architectural Etabs-col columns in the architectural LOCAL frame, F06 and F09."""
    from diwan_common import floor_entities, get_floor
    out = {}
    for fno in (6, 9):
        fl = get_floor(fno)
        ps = []
        for e in floor_entities(fl, layers="Etabs-col", types="LWPOLYLINE"):
            pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
            P = _poly(pts)
            if P is not None:
                ps.append(P)
        out[fno] = ps
    return out


def calibrate(plans, arch_cols=None):
    """One offset (structural plan frame -> architectural local frame) for every plan: vote on
    the translation that maps the structural columns onto the architectural ones (same size
    +-5 cm), then refine on the matched pairs.  Returns {offset, matched, residual_max, per_plan}."""
    arch_cols = arch_cols or _arch_columns()
    A = arch_cols[9] or arch_cols[6]
    votes = Counter()
    pairs_all = []
    for p in plans:
        for c in p["columns"]:
            S = _rot_poly(c["_poly_w"], p["anchor"])
            sx, sy = S.bounds[2] - S.bounds[0], S.bounds[3] - S.bounds[1]
            for Q in A:
                qx, qy = Q.bounds[2] - Q.bounds[0], Q.bounds[3] - Q.bounds[1]
                if abs(sx - qx) <= 0.05 and abs(sy - qy) <= 0.05:
                    d = (Q.centroid.x - S.centroid.x, Q.centroid.y - S.centroid.y)
                    votes[(round(d[0] / 0.05), round(d[1] / 0.05))] += 1
                    pairs_all.append((d, p["title"]))
    if not votes:
        return {"offset": (0.0, 0.0), "matched": 0, "note": "no column matched"}
    (kx, ky), n = votes.most_common(1)[0]
    near = [d for d, _ in pairs_all if abs(d[0] - kx * 0.05) <= 0.08 and abs(d[1] - ky * 0.05) <= 0.08]
    off = (sum(d[0] for d in near) / len(near), sum(d[1] for d in near) / len(near))
    res = max(math.hypot(d[0] - off[0], d[1] - off[1]) for d in near)
    return {"offset": (_r(off[0], 4), _r(off[1], 4)), "matched": len(near), "residual_max": _r(res, 4)}


def to_arch_local(plan, x, y=None, cal=None):
    if y is None:
        x, y = x
    off = (cal or plan.get("_cal") or {"offset": (0, 0)})["offset"]
    q = _local((x, y), plan["anchor"])
    return (q[0] + off[0], q[1] + off[1])


# ----------------------------------------------------------------------------- main reader
@lru_cache(maxsize=2)
def read_structural(use_cache=True):
    g = extract(use_cache=use_cache)
    plans = _plans(g)
    for p in plans:
        p["zones"] = _zones(g, p)
        p["beams"], p["beam_labels"] = _beams(g, p)
        p["columns"] = _columns(g, p)
    cal = calibrate(plans)
    for p in plans:
        p["_cal"] = cal
        off = cal["offset"]
        p["_outline"] = _rot_poly(p["_outline_w"], p["anchor"], off)
        for z in p["zones"]:
            z["_poly"] = _rot_poly(z["_poly_w"], p["anchor"], off)
            z["_bubbles"] = [(*to_arch_local(p, x, y, cal), v) for x, y, v in z.get("_bubbles_w", [])]
        for b in p["beams"]:
            b["_poly"] = _rot_poly(b["_poly_w"], p["anchor"], off)
        for c in p["columns"]:
            c["_poly"] = _rot_poly(c["_poly_w"], p["anchor"], off)
    _borrow_splits(plans)
    return {"plans": plans, "calibration": cal, "storey": STR_STOREY, "note": TITLE_NOTE}


def _borrow_splits(plans):
    """A face holding both a 20 and a 35 bubble has a limit the drafter left out (ceilings of the
    ground and 1st floors: the 35 bubble of the south strip but no 20/35 line).  Take that limit from
    the nearest sheet that draws it: its zone of the minority thickness containing the bubble is cut
    out of the mixed face (architectural local frame).  Marked `split_from`."""
    from shapely.geometry import Point
    donors = [p for p in plans if not any(len(set(z["labels"])) > 1 for z in p["zones"])]
    for p in plans:
        new = []
        for z in p["zones"]:
            if len(set(z["labels"])) <= 1:
                new.append(z)
                continue
            gen = int(round(p["general_thickness"] * 100))
            rest = z["_poly"]
            pieces = []
            for bx, by, v in z.get("_bubbles", []):
                if v == gen:
                    continue
                P = Point(bx, by)
                for d in sorted(donors, key=lambda d: abs(min(d["ceiling_of"] or [99]) - min(p["ceiling_of"] or [99]))):
                    dz = next((q for q in d["zones"] if int(round(q["thickness"] * 100)) == v and not q["assumed"]
                               and q["_poly"].buffer(0.5).contains(P)), None)
                    if dz is None:
                        continue
                    cut = rest.intersection(dz["_poly"]).buffer(0)
                    if cut.area > 1:
                        pieces.append({"_poly_w": None, "_poly": cut, "area": cut.area, "labels": [v],
                                       "thickness": v / 100.0, "assumed": False, "split_from": d["title"]})
                        rest = rest.difference(dz["_poly"]).buffer(0)
                    break
            if pieces:
                new += pieces
                new.append({**z, "_poly": rest, "area": rest.area, "labels": [gen], "thickness": gen / 100.0,
                            "assumed": False, "split_from": pieces[0]["split_from"]})
            else:
                new.append(z)
        p["zones"] = new
        # general thickness again after the split
        th = Counter()
        for z in new:
            if not z["assumed"]:
                th[z["thickness"]] += z["area"]
        if th:
            p["general_thickness"] = th.most_common(1)[0][0]
        for z in new:
            if z["assumed"] and not z["labels"]:
                z["thickness"] = p["general_thickness"]
                # owner, 2026-11-26: the unlabelled band between the two north 35 strips is 20 cm
                # (an unlabelled face = the general thickness of the sheet)
                if abs(p["general_thickness"] - 0.20) < 1e-6:
                    z["assumed"] = False
                    z["source"] = "unlabelled = general 0.20 (owner confirmed 2026-11-26)"


def plan_for_ceiling(S, floor_no):
    for p in S["plans"]:
        if floor_no in p["ceiling_of"]:
            return p
    return None


def level_top(S, ceiling_of_floor):
    p = plan_for_ceiling(S, ceiling_of_floor)
    return None if p is None else p["levels_top_by_floor"].get(ceiling_of_floor)


def storey(S, floor_no, executed=True):
    """Top of slab under floor N to top of slab above it.  executed=True (default) -> the executed
    3.20 m (architectural levels); False -> as drawn in the structural sheets (3.30, wrong)."""
    if executed:
        return EXEC_STOREY, None, None
    lo, hi = level_top(S, floor_no - 1), level_top(S, floor_no)
    if lo is None or hi is None:
        return None, lo, hi
    return _r(hi - lo, 3), lo, hi


def _prepared(plan):
    """Prepared (buffered) zone / beam polygons of a plan, built once."""
    if "_prep" not in plan:
        from shapely.prepared import prep
        zs = sorted(plan["zones"], key=lambda z: -z["thickness"])
        bs = sorted([b for b in plan["beams"] if b.get("depth")], key=lambda b: -b["depth"])
        plan["_prep"] = ([(prep(z["_poly"].buffer(0.02)), z) for z in zs],
                         [(prep(b["_poly"].buffer(0.03)), b) for b in bs])
    return plan["_prep"]


def soffit_at(plan, x, y):
    """(depth, source) of the concrete above LOCAL point (x, y): the thickest slab zone there, or
    the deepest beam band containing it when deeper than the slab."""
    from shapely.geometry import Point
    P = Point(x, y)
    zs, bs = _prepared(plan)
    d, src = None, None
    for pz, z in zs:
        if pz.contains(P):
            d, src = z["thickness"], "slab" + (" (assumed)" if z["assumed"] else "")
            break
    if d is None:
        d, src = plan.get("general_thickness", 0.20), "outside slab outline (general thickness)"
    for pb, b in bs:
        if b["depth"] <= d:
            break
        if pb.contains(P):
            d, src = b["depth"], f"beam {b.get('name') or '?'} {int(round(b.get('b', 0) * 100))}x{int(round(b['depth'] * 100))}" + (" (assumed)" if b.get("assumed") else "")
            break
    return d, src


def soffit_profile(plan, p0, p1, step=0.05):
    """Depth of the concrete above a LOCAL segment p0-p1 (architectural frame): the slab zone
    thickness, or the beam depth where the segment runs inside a beam band (beam > slab).
    Returns runs [(t0, t1, depth, source)] in metres along the segment."""
    L = math.dist(p0, p1)
    if L < 1e-6:
        return []
    n = max(1, int(L / step))
    runs = []
    for i in range(n):
        t = (i + 0.5) * L / n
        d, src = soffit_at(plan, p0[0] + (p1[0] - p0[0]) * t / L, p0[1] + (p1[1] - p0[1]) * t / L)
        t0, t1 = i * L / n, (i + 1) * L / n
        if runs and runs[-1][2] == d and runs[-1][3] == src:
            runs[-1] = (runs[-1][0], t1, d, src)
        else:
            runs.append((t0, t1, d, src))
    return [(_r(a, 3), _r(b, 3), d, s) for a, b, d, s in runs]


def summary(S):
    rows = []
    for p in S["plans"]:
        th = Counter()
        for z in p["zones"]:
            th[(z["thickness"], z["assumed"])] += z["area"]
        rows.append({"title": p["title"], "ceiling_of": p["ceiling_of"], "anchor": [_r(v, 3) for v in p["anchor"]],
                     "level_top": p["level_top"], "levels_top_by_floor": p["levels_top_by_floor"],
                     "level_source": p["level_source"], "outline_area": _r(p["_outline"].area, 2),
                     "general_thickness": p.get("general_thickness"),
                     "zones": [{"thickness": z["thickness"], "assumed": z["assumed"], "area": _r(z["area"], 2),
                                "labels": z["labels"], "split_from": z.get("split_from"), "source": z.get("source"), "bbox_local": [_r(v, 2) for v in z["_poly"].bounds]}
                               for z in sorted(p["zones"], key=lambda z: -z["area"])],
                     "area_by_thickness": {f"{k[0]:.2f}{' (assumed)' if k[1] else ''}": _r(v, 2) for k, v in sorted(th.items())},
                     "beams": [{"name": b.get("name"), "b": b.get("b"), "depth": b.get("depth"), "assumed": b.get("assumed", False),
                                "length": _r(max(b["_poly"].minimum_rotated_rectangle.exterior.length / 2 - b["width"], 0), 2),
                                "bbox_local": [_r(v, 2) for v in b["_poly"].bounds]} for b in p["beams"]],
                     "beam_labels": [f"{lb['name']} {int(lb['b'] * 100)}x{int(lb['h'] * 100)}" for lb in p["beam_labels"]],
                     "columns": len(p["columns"])})
    return {"file": STR_DXF.name, "storey_m": S["storey"], "note": S["note"], "calibration": S["calibration"], "plans": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="write output/structure_str/slabs.json")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    S = read_structural(use_cache=not a.no_cache)
    js = summary(S)
    print("calibration (structural plan -> architectural local):", js["calibration"])
    for r in js["plans"]:
        print(f"{r['title']!s:24} ceiling of {r['ceiling_of']}  top {r['levels_top_by_floor']}  "
              f"general t={r['general_thickness']}  {r['area_by_thickness']}  beams {len(r['beams'])} "
              f"{sorted(set(r['beam_labels']))}  cols {r['columns']}")
    if a.json:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "slabs.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
        print("->", OUT / "slabs.json")


if __name__ == "__main__":
    main()
