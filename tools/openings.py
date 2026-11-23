# -*- coding: utf-8 -*-
"""
openings — قارئ الأبواب والشبابيك والفتحات (خصومات المباني والمحارة) لمساقط الديوان.

Reads every floor (F02..F08) of the Diwan plans and returns, in the shared LOCAL
frame of diwan_common (rotation removed, structural-column corner = (0,0), metres):

  DOORS     * every INSERT of a door block  D<w>W<t>  (D10W12 = 1.00 m door in a
              0.12 wall, D80W12 = 0.80, D90W12 = 0.90, D90W25 = 0.90 in 0.25 wall).
              Geometry is read from the BLOCK DEFINITION (the two jamb lines whose
              length = wall thickness, and the leaf ARC) and pushed through the
              insert's full matrix (rotation, mirror xscale=-1, scale) -> jambs,
              measured width, hinge, swing side, axis.  Doors are inserted on layer
              W *or* PR (same blocks; layer is irrelevant).
            * doors drawn WITHOUT a block (F02 terrace doors, glazed, layer WIN): an
              ARC r 0.6-1.4 m (not concentric with another arc) with a leaf LINE
              through its hinge, or whose hinge sits on a glazing end and whose
              closed end continues that glazing (corner doors in curved glazing).
            * for each door: the masonry gap measured along the wall axis inside the
              wall band (first W/column/shaft crossed, or first W face that starts in
              the band = face ending at the jamb with no cap), the host wall
              thickness probed just beyond each jamb, the rooms on both sides
              (nearest room label visible without crossing W or a closed door), and
              any architect DIM matching it (none do: interior DIMs are room widths).
  WINDOWS   layer WIN, linetype CONTINUOUS only (DASHED WIN lines = projection /
            cladding edge lines, reported separately, never glazing):
            * pairs of parallel lines 0.05-0.35 m apart -> one window unit in a wall
              (width = length along the wall, depth = frame line spacing);
            * long pairs not bounded by masonry -> glazed facade / curtain wall;
            * concentric ARC pairs -> curved corner glazing (arc length + chord);
            * glazing touching a door jamb -> fixed glazing beside a door (F02);
            * units < 0.30 m -> frame pieces (jambs/mullions), kept apart;
            * single unpaired lines/arcs -> single-line glazing (flagged).
            Masonry gap + host-wall thickness by the same ray cast; architect facade
            DIM chains (layer DIM) are matched to window ends as a cross-check.
            Plans carry NO sill / head heights (no text, no tags) -> open question.
  OPENINGS  door-less gaps in a wall line, two detectors merged:
            (a) a wall END CAP (short W/0 segment closing both faces, with a face
                >= 0.25 m behind it - door-side piers excluded) facing another cap
                across an empty gap; (b) BOTH faces of a wall band interrupted at the
                same place, gap empty (no W line, column or shaft inside).
            Gaps explained by a door block or a window are dropped.  A wall end
            facing a perpendicular wall (no wall on the far side) is only a
            'candidate' (JSON opening_candidates, not drawn, not totalled).
            DASH lines across the gap (lintel / soffit lines) reported as evidence.

Not doors / windows (checked on all floors, see docs/findings/openings.md):
  LP (layer W) = level-mark symbol, WB/P (FUR) = wash basin / WC, ST-2 (PR1) =
  stair arrow, random-named blocks on W ('rt5hrt6', '56y', ...) = CI circle +
  TEXT-DIM letter = AXIS TAGS (ز ا ب ج د / 1 2 3 4) in the sheet margins, the
  random-named X blocks = axis bubbles, PR raw lines = stair handrails + lift cars.

CLI (default = all floors):
    python tools/openings.py                 # F02..F08 -> output/openings/F0x.json + PNGs
    python tools/openings.py 3 5 --no-png
API:
    from openings import analyze_floor, deduction_table
    res = analyze_floor(3)       # dict: doors / windows / openings / summary / checks
    res["doors"][0]["width"], res["summary"]["doors"]["total_width"]
    rows = deduction_table(res, door_h=2.30, window_h=None)   # heights are NOT in the plans
JSON (output/openings/F0x.json) is the same dict without the private geometry handle.
Every item has: id (F03-D07 / F03-W12 / F03-O01), center [x,y] local, axis_deg, width (m),
host {gap, gap_minus/plus, bound_*, wall_t_minus/plus} = masonry gap measured on the walls.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from ezdxf import path as ezpath
from ezdxf.math import Vec3
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import OUT_DIR, all_floors, floor_entities, floor_texts, get_floor  # noqa: E402

OUT = OUT_DIR / "openings"
DOOR_RE = re.compile(r"^D(\d+)W(\d+)$", re.I)
WALL_LAYERS = ("W",)
OBSTACLE_POLY_LAYERS = ("Etabs-col", "COL", "try")
BUILDING_WINDOW = (-4.0, -4.0, 24.0, 44.0)   # local box that contains the building + terraces
LEGACY_F03 = {"doors": 37, "door_width": 34.23}  # user's own AutoCAD dims, Sept 2026

# ----------------------------------------------------------------------------- vectors
def _sub(a, b): return (a[0] - b[0], a[1] - b[1])
def _add(a, b): return (a[0] + b[0], a[1] + b[1])
def _mul(a, k): return (a[0] * k, a[1] * k)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1]
def _cross(a, b): return a[0] * b[1] - a[1] * b[0]
def _len(a): return math.hypot(a[0], a[1])
def _unit(a):
    L = _len(a)
    return (a[0] / L, a[1] / L) if L > 1e-12 else (0.0, 0.0)
def _perp(a): return (-a[1], a[0])
def _mid(a, b): return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
def _r(v, n=3):
    if isinstance(v, (list, tuple)):
        return [_r(x, n) for x in v]
    return None if v is None else round(float(v), n)


def _axis_angle(u):
    """Undirected axis angle in [0,180)."""
    return math.degrees(math.atan2(u[1], u[0])) % 180.0


def _is_dashed(e, doc):
    lt = e.dxf.get("linetype", "BYLAYER")
    if lt.upper() == "BYLAYER":
        try:
            lt = doc.layers.get(e.dxf.layer).dxf.linetype
        except Exception:
            lt = "CONTINUOUS"
    return lt.upper() not in ("CONTINUOUS", "BYBLOCK", "")


def _flatten(e, dist=0.01):
    """WCS polylines of one primitive (OCS-correct: mirrored arcs / polylines)."""
    try:
        p = ezpath.make_path(e)
    except Exception:
        return []
    try:
        pts = [(v.x, v.y) for v in p.flattening(dist)]
    except Exception:
        return []
    return [pts] if len(pts) >= 2 else []


# ----------------------------------------------------------------------------- floor geometry
class FloorGeom:
    """All primitives needed for openings, in LOCAL coordinates."""

    def __init__(self, fl):
        self.fl = fl
        doc = fl.doc
        L = fl.to_local
        self.wall_segs = []          # [(p,q,layer)]
        self.win_lines = []          # [(p,q)] continuous WIN lines
        self.win_dashed = []         # [(p,q)] DASHED WIN lines (projection lines)
        self.raw_arcs = []           # [dict] ARCs on WIN/W/PR (local)
        self.raw_lines = {"WIN": [], "W": [], "PR": []}
        self.dash_segs = []
        self.polys = []              # [(Polygon, layer)] columns / shafts
        self.door_inserts = []
        self.other_inserts = []
        for e in floor_entities(fl, layers=("W", "0", "WIN", "PR", "DASH") + OBSTACLE_POLY_LAYERS):
            lay, t = e.dxf.layer, e.dxftype()
            if t == "INSERT":
                (self.door_inserts if DOOR_RE.match(e.dxf.name) else self.other_inserts).append(e)
                continue
            if t in ("TEXT", "MTEXT", "HATCH", "DIMENSION"):
                continue
            if lay in OBSTACLE_POLY_LAYERS:
                if t == "LWPOLYLINE":
                    pts = [L(p[0], p[1]) for p in e.get_points("xy")]
                    if len(pts) >= 3:
                        pg = Polygon(pts)
                        if not pg.is_valid:
                            pg = pg.buffer(0)
                        if pg.area > 0.01:
                            self.polys.append((pg, lay))
                continue
            if lay == "0":
                # stray wall caps drawn on layer 0 (e.g. F05 6.94,13.62-13.74);
                # skip revision clouds (closed, many vertices)
                if t == "LWPOLYLINE" and not e.closed and len(e) <= 4:
                    for poly in _flatten(e):
                        lp = [L(*p) for p in poly]
                        for a, b in zip(lp, lp[1:]):
                            if _len(_sub(b, a)) > 1e-4:
                                self.wall_segs.append((a, b, "0"))
                continue
            if t == "ARC" and lay in ("WIN", "W", "PR"):
                c = e.dxf.center
                arc = e.construction_tool()
                sp, ep = arc.start_point, arc.end_point
                mp = arc.vertices([arc.start_angle + (arc.angle_span / 2)])
                mp = list(mp)[0]
                ocs = e.ocs()
                cw = ocs.to_wcs(Vec3(c.x, c.y, 0))
                spw, epw, mpw = (ocs.to_wcs(Vec3(v.x, v.y, 0)) for v in (sp, ep, mp))
                self.raw_arcs.append({
                    "layer": lay, "handle": e.dxf.handle, "r": e.dxf.radius,
                    "center": L(cw.x, cw.y), "p0": L(spw.x, spw.y), "p1": L(epw.x, epw.y),
                    "pm": L(mpw.x, mpw.y), "span": arc.angle_span,
                    "dashed": _is_dashed(e, doc),
                })
            for poly in _flatten(e):
                lp = [L(*p) for p in poly]
                segs = [(a, b) for a, b in zip(lp, lp[1:]) if _len(_sub(b, a)) > 1e-4]
                if lay == "W":
                    self.wall_segs.extend((a, b, "W") for a, b in segs)
                    if t == "LINE":
                        self.raw_lines["W"].extend(segs)
                elif lay == "WIN" and t != "ARC":
                    (self.win_dashed if _is_dashed(e, doc) else self.win_lines).extend(segs)
                    self.raw_lines["WIN"].extend(segs)
                elif lay == "PR":
                    self.raw_lines["PR"].extend(segs)
                elif lay == "DASH":
                    self.dash_segs.extend(segs)
        # obstacle index (walls + column/shaft outlines) for ray casting
        self._obs_geoms, self._obs_kind = [], []
        for a, b, lay in self.wall_segs:
            self._obs_geoms.append(LineString([a, b]))
            self._obs_kind.append("wall" if lay in ("W", "0") else lay)
        for pg, lay in self.polys:
            ring = pg.exterior if pg.geom_type == "Polygon" else None
            if ring is None:
                continue
            cs = list(ring.coords)
            for a, b in zip(cs, cs[1:]):
                self._obs_geoms.append(LineString([a, b]))
                self._obs_kind.append("column" if lay != "try" else "shaft")
        self.obs_tree = STRtree(self._obs_geoms)
        self.wall_tree = STRtree([LineString([a, b]) for a, b, _ in self.wall_segs])
        # room labels
        self.labels = []
        for t in floor_texts(fl, layers=("TEXT", "-A-TEXT")):
            x, y = t["local"]
            if BUILDING_WINDOW[0] < x < BUILDING_WINDOW[2] and BUILDING_WINDOW[1] < y < BUILDING_WINDOW[3]:
                txt = t["text"].strip()
                # room names are 1-2 words ('مكتب 5', 'حمام', 'بهو المصعد', 'IT room');
                # longer texts are notes ('المصاعد الادارية فقط') -> not a room
                if txt and not txt.startswith("+") and len(txt.split()) <= 2:
                    self.labels.append((txt, (x, y)))
        # architect dims (all DIMENSION entities on the sheet)
        self.dims = []
        for e in floor_entities(fl, types="DIMENSION"):
            d = e.dxf
            try:
                p2, p3 = L(d.defpoint2.x, d.defpoint2.y), L(d.defpoint3.x, d.defpoint3.y)
            except Exception:
                continue
            try:
                m = e.get_measurement()
            except Exception:
                m = None
            self.dims.append({"layer": e.dxf.layer, "p2": p2, "p3": p3,
                              "value": float(m) if isinstance(m, (int, float)) else None,
                              "type": d.dimtype & 7, "handle": d.handle})

    # ------------------------------------------------------------------ queries
    def ray(self, origin, direction, max_len=6.0, kinds=None):
        """Distance to the first obstacle crossed by the ray, and its kind (wall/column/shaft)."""
        end = _add(origin, _mul(direction, max_len))
        ln = LineString([origin, end])
        best, kind = None, None
        for i in self.obs_tree.query(ln, predicate="intersects"):
            g = self._obs_geoms[i]
            k = self._obs_kind[i]
            if kinds and k not in kinds:
                continue
            x = ln.intersection(g)
            if x.is_empty:
                continue
            pts = []
            if x.geom_type == "Point":
                pts = [(x.x, x.y)]
            elif x.geom_type in ("MultiPoint", "GeometryCollection"):
                for gg in x.geoms:
                    if gg.geom_type == "Point":
                        pts.append((gg.x, gg.y))
                    else:
                        pts.extend(gg.coords)
            else:  # collinear overlap
                pts = list(x.coords)
            for p in pts:
                dd = _dot(_sub(p, origin), direction)
                # walls win ties (a shaft box drawn on the wall face is still the wall)
                if dd > 1e-4 and (best is None or dd < best - 1e-6 or (abs(dd - best) <= 1e-6 and k == "wall")):
                    best, kind = dd, k
        return best, kind

    def face_ends(self, c, u, half_band, side, max_len):
        """Distance along side*u from c to where a wall FACE parallel to u (inside the band
        |offset| <= half_band) begins.  Catches wall faces that simply stop at a jamb with
        no cap line (the cap is drawn by the door block).  Returns (dist, through) where
        through=True means a face runs continuously across c (no opening on that face)."""
        best, through = None, False
        for a, b, lay in self.wall_segs:
            v = _sub(b, a)
            L = _len(v)
            if L < 0.03 or abs(_cross(_unit(v), u)) > 0.02:
                continue
            o = _cross(u, _sub(a, c))
            if abs(o) > half_band:
                continue
            pa, pb = side * _dot(_sub(a, c), u), side * _dot(_sub(b, c), u)
            lo, hi = min(pa, pb), max(pa, pb)
            if hi <= 1e-4 or lo > max_len:
                continue
            if lo < -1e-3:
                through = True
                continue
            if best is None or lo < best:
                best = lo
        return best, through

    def crosses_wall(self, a, b, tol=0.0):
        """Number of W segments (+ door closing lines once doors are known) touched by a-b."""
        tree = getattr(self, "los_tree", None) or self.wall_tree
        return len(tree.query(LineString([a, b]), predicate="intersects"))

    def close_doors(self, doors):
        """Treat every door as a closed line for room look-ups (no seeing through doorways)."""
        geoms = [LineString([a, b]) for a, b, _ in self.wall_segs]
        for d in doors:
            if "jamb_a" in d:
                geoms.append(LineString([_mid(*d["jamb_a"]), _mid(*d["jamb_b"])]))
        self.los_tree = STRtree(geoms)

    def room_on_side(self, c, n, reach=0.25, max_d=32.0, half=0.4):
        """Nearest room label on side +n of point c that is VISIBLE (segment to the label
        crosses no W line) from one of a few points just inside that side.  Returns the
        label, or None when no label is visible (never a guess)."""
        u = _perp(n)
        origins = [_add(c, _mul(n, reach)), _add(_add(c, _mul(n, reach)), _mul(u, half)),
                   _add(_add(c, _mul(n, reach)), _mul(u, -half)), _add(c, _mul(n, 0.9))]
        best = None
        for txt, p in self.labels:
            v = _sub(p, c)
            if _dot(v, n) <= 0.05:
                continue
            d = _len(v)
            if d > max_d or (best is not None and d >= best[0]):
                continue
            if any(self.crosses_wall(o, p) == 0 for o in origins):
                best = (d, txt)
        return best[1] if best else None

    def dim_match(self, e1, e2, max_off=1.2, tol=0.04):
        """Architect DIMENSION whose two defpoints sit on the two ends e1, e2 (along their axis)."""
        u = _unit(_sub(e2, e1))
        W = _len(_sub(e2, e1))
        out = []
        for d in self.dims:
            a = _dot(_sub(d["p2"], e1), u)
            b = _dot(_sub(d["p3"], e1), u)
            oa = abs(_cross(u, _sub(d["p2"], e1)))
            ob = abs(_cross(u, _sub(d["p3"], e1)))
            if oa > max_off or ob > max_off:
                continue
            lo, hi = min(a, b), max(a, b)
            if abs(lo) <= tol and abs(hi - W) <= tol:
                out.append({"value": _r(d["value"]), "along": _r(hi - lo), "layer": d["layer"], "handle": d["handle"]})
        return out


# ----------------------------------------------------------------------------- door blocks
@lru_cache(maxsize=64)
def _door_block_model(doc_key, name):
    """Jambs / leaf of a D<w>W<t> block, in BLOCK coordinates."""
    from diwan_common import open_doc
    doc = open_doc(doc_key)
    blk = doc.blocks.get(name)
    m = DOOR_RE.match(name)
    nw = int(m.group(1))
    nominal_w = nw / 10.0 if nw <= 30 else nw / 100.0     # D10 = 10 dm, D80 = 80 cm
    nominal_t = int(m.group(2)) / 100.0
    segs, arcs = [], []
    for e in blk:
        t = e.dxftype()
        if t == "ARC":
            arcs.append(e)
        elif t in ("LINE", "LWPOLYLINE"):
            for poly in _flatten(e):
                segs.extend((a, b) for a, b in zip(poly, poly[1:]))
    cands = [s for s in segs if abs(_len(_sub(s[1], s[0])) - nominal_t) <= 0.0015]
    best = None
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            da, db = _unit(_sub(a[1], a[0])), _unit(_sub(b[1], b[0]))
            if abs(_cross(da, db)) > 0.01:
                continue
            ma, mb = _mid(*a), _mid(*b)
            sep = _sub(mb, ma)
            along = abs(_cross(da, sep))          # distance between the two jamb lines
            slide = abs(_dot(da, sep))            # misalignment along the jamb
            if slide > 0.01:
                continue
            score = abs(along - nominal_w)
            if best is None or score < best[0]:
                best = (score, a, b)
    if best is None or best[0] > 0.05:
        return None
    _, ja, jb = best
    arc = max(arcs, key=lambda a: a.dxf.radius) if arcs else None
    leaf = None
    if arc is not None:
        c = arc.dxf.center
        a0, a1 = math.radians(arc.dxf.start_angle), math.radians(arc.dxf.end_angle)
        if a1 < a0:
            a1 += 2 * math.pi
        r = arc.dxf.radius
        leaf = {"c": (c.x, c.y), "r": r,
                "p0": (c.x + r * math.cos(a0), c.y + r * math.sin(a0)),
                "p1": (c.x + r * math.cos(a1), c.y + r * math.sin(a1)),
                "pm": (c.x + r * math.cos((a0 + a1) / 2), c.y + r * math.sin((a0 + a1) / 2))}
    return {"jamb_a": ja, "jamb_b": jb, "nominal_w": nominal_w, "nominal_t": nominal_t, "leaf": leaf}


def _xf(ins, fl):
    M = ins.matrix44()

    def f(p):
        w = M.transform(Vec3(p[0], p[1], 0))
        return fl.to_local(w.x, w.y)
    return f


def _door_from_frame(fl, G, ja, jb, leaf, meta):
    """Common door record from jamb lines + leaf (all LOCAL)."""
    ma, mb = _mid(*ja), _mid(*jb)
    u = _unit(_sub(mb, ma))
    n = _perp(u)
    width = _len(_sub(mb, ma))
    t = _len(_sub(ja[1], ja[0]))
    c = _mid(ma, mb)
    rec = dict(meta)
    rec.update({
        "center": _r(c), "axis_deg": _r(_axis_angle(u), 2),
        "width": _r(width), "wall_t_block": _r(t),
        "jamb_a": _r(list(ja)), "jamb_b": _r(list(jb)),
    })
    if leaf:
        hinge = leaf["c"]
        side = _dot(_sub(leaf["pm"], c), n)
        rec.update({"hinge": _r(hinge), "leaf_r": _r(leaf["r"]),
                    "swing_side": "+n" if side > 0 else "-n",
                    "hinge_at": "a" if _len(_sub(hinge, ma)) < _len(_sub(hinge, mb)) else "b"})
        rec["_sw"] = n if side > 0 else _mul(n, -1)
    else:
        rec["_sw"] = n
    rec["host"] = measure_host(G, c, u, width, t)
    dm = G.dim_match(ma, mb)
    rec["dim_check"] = dm[0] if dm else None
    rec["_u"], rec["_n"], rec["_c"] = u, n, c
    return rec


def measure_host(G, c, u, width, t, extra=1.2, face_band=None):
    """Masonry gap along the wall axis + host wall thickness beyond each jamb.

    On each side the gap ends at the FIRST of: a W line / column / shaft edge crossed by
    rays run along the axis inside the wall band (offsets -0.3t, 0, +0.3t), or the start
    of a W face line lying in the band (faces that stop at the jamb without a cap)."""
    offs = (-0.3 * t, 0.0, 0.3 * t) if t > 0.03 else (0.0,)
    n = _perp(u)
    res = {}
    dist = {}
    for sgn, nm in ((-1, "minus"), (1, "plus")):
        hits = []
        for o in offs:
            d, k = G.ray(_add(c, _mul(n, o)), _mul(u, sgn), max_len=width / 2 + extra)
            if d is not None:
                hits.append((d, k))
        fb = face_band if face_band is not None else max(t / 2 + 0.02, 0.05)
        fe, through = G.face_ends(c, u, fb, sgn, width / 2 + extra)
        if fe is not None:
            hits.append((fe, "wall face end"))
        if hits:
            d, k = min(hits, key=lambda h: (round(h[0], 4), h[1] != "wall"))
            dist[nm] = d
            res[f"gap_{nm}"], res[f"bound_{nm}"] = _r(d), k
        else:
            res[f"gap_{nm}"], res[f"bound_{nm}"] = None, None
        if through:
            res[f"face_through_{nm}"] = True
    res["gap"] = _r(dist["minus"] + dist["plus"]) if len(dist) == 2 else None
    # wall thickness probes just beyond each jamb
    th = []
    for sgn, nm in ((-1, "minus"), (1, "plus")):
        dd = dist.get(nm, width / 2)
        p = _add(c, _mul(u, sgn * (dd + 0.05)))
        a, _ = G.ray(p, n, 0.6, kinds=("wall",))
        b, _ = G.ray(p, _mul(n, -1), 0.6, kinds=("wall",))
        th.append(_r(a + b) if a is not None and b is not None and a + b < 0.6 else None)
    res["wall_t_minus"], res["wall_t_plus"] = th
    return res


def read_doors(fl, G):
    doors = []
    key = str(fl.file)
    for ins in G.door_inserts:
        name = ins.dxf.name
        model = _door_block_model(key, name)
        meta = {"source": "block", "block": name, "layer": ins.dxf.layer, "handle": ins.dxf.handle,
                "insert": _r(fl.to_local(ins.dxf.insert.x, ins.dxf.insert.y)),
                "rotation_local": _r((ins.dxf.rotation - fl.angle) % 360, 2),
                "mirrored": (ins.dxf.xscale * ins.dxf.yscale) < 0,
                "scale": _r([ins.dxf.xscale, ins.dxf.yscale], 4)}
        if model is None:
            meta["problem"] = "jambs not found in block"
            doors.append(meta)
            continue
        f = _xf(ins, fl)
        ja = (f(model["jamb_a"][0]), f(model["jamb_a"][1]))
        jb = (f(model["jamb_b"][0]), f(model["jamb_b"][1]))
        leaf = None
        if model["leaf"]:
            lf = model["leaf"]
            leaf = {"c": f(lf["c"]), "pm": f(lf["pm"]), "p0": f(lf["p0"]), "p1": f(lf["p1"]),
                    "r": lf["r"] * abs(ins.dxf.xscale)}
        meta.update({"nominal_width": model["nominal_w"], "nominal_wall_t": model["nominal_t"],
                     "kind": "single swing"})
        rec = _door_from_frame(fl, G, ja, jb, leaf, meta)
        rec["leaf_geom"] = {k: _r(v) for k, v in (leaf or {}).items() if k != "r"}
        doors.append(rec)
    # raw (block-less) swing doors, two drafting styles seen on F02:
    #  (a) ARC r 0.6-1.4 + radial LEAF line from its centre (east terrace doors, WIN layer)
    #  (b) ARC whose CENTRE and one END sit on the two ends of a gap in the glazing
    #      (corner terrace doors in the curved glazing; no leaf line drawn)
    used_lines = set()
    glz_ends = []                       # ends of every other WIN element
    for s_ in G.win_lines:
        glz_ends.extend(s_)
    for b in G.raw_arcs:
        if b["layer"] == "WIN" and not b["dashed"]:
            glz_ends.extend([(b["handle"], b["p0"]), (b["handle"], b["p1"])])
    for a in G.raw_arcs:
        if not (0.6 <= a["r"] <= 1.4) or a["dashed"] or not (50 <= a["span"] <= 135):
            continue
        # the same arc must not be a glazing arc (concentric partner)
        if any(b is not a and _len(_sub(b["center"], a["center"])) < 0.02 and 0.03 < abs(b["r"] - a["r"]) < 0.4
               for b in G.raw_arcs):
            continue
        c = a["center"]
        far, style, gap_chord = None, None, None
        # (a) leaf line: passes (within 2 cm) through the hinge and ends at one arc end (open tip)
        for lay, segs in G.raw_lines.items():
            for s_ in segs:
                if LineString(s_).distance(Point(c)) > 0.02:
                    continue
                for tip, other in ((a["p0"], a["p1"]), (a["p1"], a["p0"])):
                    if min(_len(_sub(s_[0], tip)), _len(_sub(s_[1], tip))) < 0.06:
                        far, style = other, "arc + leaf line"
                        used_lines.add((round(s_[0][0], 3), round(s_[0][1], 3), round(s_[1][0], 3), round(s_[1][1], 3)))
        # (b) no leaf line: hinge sits on the end of a glazing element; the CLOSED leaf
        #     continues that element's direction (the open end is ~90 deg off it)
        if far is None:
            tang = None
            best_d = 0.15
            for s_ in G.win_lines:
                for e0, e1 in ((s_[0], s_[1]), (s_[1], s_[0])):
                    dd = _len(_sub(e0, c))
                    if dd < best_d and _len(_sub(e1, e0)) > 0.05:
                        best_d, tang, hinge_end = dd, _unit(_sub(e1, e0)), e0
            for b in G.raw_arcs:
                if b is a or b["layer"] != "WIN" or b["dashed"]:
                    continue
                for e0 in (b["p0"], b["p1"]):
                    dd = _len(_sub(e0, c))
                    if dd < best_d:
                        best_d, tang, hinge_end = dd, _perp(_unit(_sub(e0, b["center"]))), e0
            if tang is not None:
                cos0 = abs(_dot(_unit(_sub(a["p0"], c)), tang))
                cos1 = abs(_dot(_unit(_sub(a["p1"], c)), tang))
                if max(cos0, cos1) > 0.7 and min(cos0, cos1) < 0.5:
                    far = a["p0"] if cos0 > cos1 else a["p1"]
                    style = "arc only, hinge on a glazing end (no leaf line)"
                    ends = [q for s_ in G.win_lines for q in s_] + \
                           [q for b in G.raw_arcs if b is not a and b["layer"] == "WIN" for q in (b["p0"], b["p1"])]
                    near = min(ends, key=lambda q: _len(_sub(q, far)))
                    if _len(_sub(near, far)) < 0.08:
                        gap_chord = _len(_sub(near, hinge_end))
        if far is None:
            continue
        u = _unit(_sub(far, c))
        n = _perp(u)
        tt = 0.12
        ja = (_add(c, _mul(n, -tt / 2)), _add(c, _mul(n, tt / 2)))
        jb = (_add(far, _mul(n, -tt / 2)), _add(far, _mul(n, tt / 2)))
        meta = {"source": f"raw drawing, no block: {style}", "block": None, "layer": a["layer"],
                "handle": a["handle"], "nominal_width": None, "nominal_wall_t": None,
                "kind": "single swing, glazed (drawn on WIN)" if a["layer"] == "WIN" else "single swing (drawn)",
                "mirrored": None}
        rec = _door_from_frame(fl, G, ja, jb, {"c": c, "pm": a["pm"], "r": a["r"]}, meta)
        rec["wall_t_block"] = None
        rec["glazing_gap_chord"] = _r(gap_chord)   # distance between the glazing ends the leaf closes
        rec["leaf_geom"] = {"c": _r(c), "pm": _r(a["pm"]), "p0": _r(a["p0"]), "p1": _r(a["p1"])}
        doors.append(rec)
    G.used_leaf_lines = used_lines
    # rooms on both sides, with every door closed (no line of sight through doorways)
    G.close_doors(doors)
    for d in doors:
        if "_c" in d:
            d["opens_into"] = G.room_on_side(d["_c"], d["_sw"])
            d["other_side"] = G.room_on_side(d["_c"], _mul(d["_sw"], -1))
    # double doors = two leaves sharing a jamb line
    for i, d1 in enumerate(doors):
        for d2 in doors[i + 1:]:
            if "_c" not in d1 or "_c" not in d2:
                continue
            if abs(_cross(d1["_u"], d2["_u"])) > 0.02:
                continue
            gap = _len(_sub(d1["_c"], d2["_c"])) - (d1["width"] + d2["width"]) / 2
            off = abs(_cross(d1["_u"], _sub(d2["_c"], d1["_c"])))
            if abs(gap) < 0.05 and off < 0.05:
                d1["kind"] = d2["kind"] = "double (two leaves)"
                d1["pair"], d2["pair"] = d2["handle"], d1["handle"]
    # ids in reading order (top->bottom, left->right)
    doors.sort(key=lambda d: (-round(d.get("center", [0, 0])[1] / 0.5), d.get("center", [0, 0])[0]))
    for k, d in enumerate(doors, 1):
        d["id"] = f"{fl.label}-D{k:02d}"
    return doors


# ----------------------------------------------------------------------------- windows
def _pair_lines(lines, dmin=0.05, dmax=0.35, min_ov=0.5):
    n = len(lines)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    partner = defaultdict(list)
    for i in range(n):
        a0, a1 = lines[i]
        ua = _unit(_sub(a1, a0))
        La = _len(_sub(a1, a0))
        for j in range(i + 1, n):
            b0, b1 = lines[j]
            ub = _unit(_sub(b1, b0))
            if abs(_cross(ua, ub)) > 0.02:
                continue
            off = abs(_cross(ua, _sub(b0, a0)))
            if not (dmin <= off <= dmax):
                continue
            s0, s1 = sorted((_dot(_sub(b0, a0), ua), _dot(_sub(b1, a0), ua)))
            ov = min(La, s1) - max(0.0, s0)
            Lb = _len(_sub(b1, b0))
            if ov <= min_ov * min(La, Lb):
                continue
            partner[i].append((j, off))
            partner[j].append((i, off))
            parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values()), partner


def read_windows(fl, G):
    wins = []
    used = getattr(G, "used_leaf_lines", set())
    lines = [s for s in G.win_lines
             if (round(s[0][0], 3), round(s[0][1], 3), round(s[1][0], 3), round(s[1][1], 3)) not in used]
    groups, _ = _pair_lines(lines)
    for g in groups:
        segs = [lines[i] for i in g]
        L0 = max(segs, key=lambda s: _len(_sub(s[1], s[0])))
        u = _unit(_sub(L0[1], L0[0]))
        if u[0] < -1e-9 or (abs(u[0]) < 1e-9 and u[1] < 0):
            u = _mul(u, -1)
        n = _perp(u)
        o = L0[0]
        projs = [_dot(_sub(p, o), u) for s in segs for p in s]
        offs = [_dot(_sub(p, o), n) for s in segs for p in s]
        u_lo, u_hi = min(projs), max(projs)
        # glazing width = span COMMON to all lines of the unit (one frame line is often
        # drawn a few cm longer into the jamb, e.g. F03 east 2.419 vs 2.35 -> 2.35 = DIM)
        lo = max(min(_dot(_sub(p, o), u) for p in s) for s in segs)
        hi = min(max(_dot(_sub(p, o), u) for p in s) for s in segs)
        if hi - lo < 0.5 * (u_hi - u_lo):
            lo, hi = u_lo, u_hi
        omin, omax = min(offs), max(offs)
        e1 = _add(_add(o, _mul(u, lo)), _mul(n, (omin + omax) / 2))
        e2 = _add(_add(o, _mul(u, hi)), _mul(n, (omin + omax) / 2))
        width = hi - lo
        c = _mid(e1, e2)
        depth = omax - omin
        paired = len(g) >= 2
        host = measure_host(G, c, u, width, max(depth, 0.05), extra=1.0,
                            face_band=max(depth / 2 - 0.005, 0.01))
        gap = host.get("gap")
        door_adj = None
        for d in getattr(G, "_doors", []):
            if "jamb_a" not in d:
                continue
            for jm in (_mid(*d["jamb_a"]), _mid(*d["jamb_b"])):
                if min(_len(_sub(jm, e1)), _len(_sub(jm, e2))) < 0.15 and abs(_cross(u, d["_u"])) < 0.05:
                    door_adj = d["id"]
        if width < 0.30:
            kind = "frame piece (jamb/mullion, not a window)"
        elif width >= 4.0:
            kind = "glazed facade / curtain wall"
        elif door_adj:
            kind = "fixed glazing beside a door (same opening)"
        elif not paired:
            kind = "single-line glazing (unpaired)"
        elif gap is not None and abs(gap - width) <= 0.10:
            kind = "window in masonry opening"
        elif gap is not None and gap < width + 1.5:
            kind = "window (gap != glazing, check)"
        else:
            kind = "glazed facade / curtain wall"
        dm = G.dim_match(e1, e2)
        wins.append({"kind": kind, "shape": "straight", "center": _r(c), "axis_deg": _r(_axis_angle(u), 2),
                     "width": _r(width), "span_all_lines": _r(u_hi - u_lo), "frame_depth": _r(depth), "n_lines": len(g),
                     "ends": _r([e1, e2]), "host": host, "dim_check": dm[0] if dm else None,
                     "adjoins_door": door_adj,
                     "rooms": [x for x in (G.room_on_side(c, n), G.room_on_side(c, _mul(n, -1))) if x],
                     "_u": u, "_n": n, "_c": c})
    # arcs: concentric pairs = curved glazing
    arcs = [a for a in G.raw_arcs if a["layer"] == "WIN" and not a["dashed"]]
    used_a = set()
    for i, a in enumerate(arcs):
        if i in used_a:
            continue
        grp = [i]
        for j in range(len(arcs)):
            if j != i and j not in used_a and _len(_sub(arcs[j]["center"], a["center"])) < 0.02 \
                    and abs(arcs[j]["r"] - a["r"]) < 0.4:
                grp.append(j)
        rs = sorted({round(arcs[k]["r"], 3) for k in grp})
        if len(rs) < 2:
            continue   # single arcs: doors (handled) or single-line glazing below
        for k in grp:
            used_a.add(k)
        # sweep from the arcs of the smaller radius (pieces may be split by a door gap)
        rin = [arcs[k] for k in grp if abs(arcs[k]["r"] - rs[0]) < 1e-3]
        sweep = sum(a2["span"] for a2 in rin)
        rm = (rs[0] + rs[-1]) / 2
        chord_pts = [p for a2 in rin for p in (a2["p0"], a2["p1"])]
        far = max(((p, q) for p in chord_pts for q in chord_pts), key=lambda pq: _len(_sub(pq[0], pq[1])))
        c = a["center"]
        wins.append({"kind": "curved glazing (corner)", "shape": "arc", "center": _r(c), "radius_mid": _r(rm),
                     "sweep_deg": _r(sweep, 1), "width": _r(math.radians(sweep) * rm),
                     "chord": _r(_len(_sub(far[0], far[1]))), "frame_depth": _r(rs[-1] - rs[0]),
                     "n_lines": len(grp), "pieces": len(rin), "ends": _r(list(far)),
                     "host": None, "dim_check": None,
                     "rooms": [x for x in [G.room_on_side(c, _unit(_sub(c, rin[0]["pm"])), reach=-rm + 0.3)] if x],
                     "_c": c})
    for i, a in enumerate(arcs):
        if i in used_a or (0.6 <= a["r"] <= 1.4 and any(_len(_sub(d, a["center"])) < 0.02 for d in G._door_hinges)):
            continue
        wins.append({"kind": "curved glazing, single line", "shape": "arc", "center": _r(a["center"]),
                     "radius_mid": _r(a["r"]), "sweep_deg": _r(a["span"], 1),
                     "width": _r(math.radians(a["span"]) * a["r"]), "chord": _r(_len(_sub(a["p0"], a["p1"]))),
                     "frame_depth": 0.0, "n_lines": 1, "ends": _r([a["p0"], a["p1"]]), "host": None,
                     "dim_check": None, "rooms": [], "_c": a["center"]})
    wins.sort(key=lambda w: (-round(w["center"][1] / 0.5), w["center"][0]))
    for k, w in enumerate(wins, 1):
        w["id"] = f"{fl.label}-W{k:02d}"
    return wins


# ----------------------------------------------------------------------------- door-less openings
def _face_run(G, p, dirv, tol=0.004, max_len=1.0):
    """Length of W wall face running from point p in direction dirv (collinear pieces merged)."""
    iv = []
    for a, b, _ in G.wall_segs:
        v = _sub(b, a)
        if _len(v) < 1e-4 or abs(_cross(_unit(v), dirv)) > 0.01:
            continue
        if abs(_cross(dirv, _sub(a, p))) > tol:
            continue
        s0, s1 = sorted((_dot(_sub(a, p), dirv), _dot(_sub(b, p), dirv)))
        if s1 > 1e-4:
            iv.append((s0, s1))
    reach = 0.0
    for s0, s1 in sorted(iv):
        if s0 <= reach + 0.003:
            reach = max(reach, s1)
            if reach >= max_len:
                break
    return reach


def _wall_end_caps(G, tmin=0.05, tmax=0.45, tol=0.006):
    """Short W/0 segments closing BOTH faces of a wall end.
    Returns dicts: c (cap centre), w (outward unit), t (cap length), cap (a,b), depth
    (shorter of the two faces running back from the cap: piers beside doors are ~0.12)."""
    segs = [(a, b) for a, b, _ in G.wall_segs]
    ends = defaultdict(list)

    def key(p):
        return (round(p[0] / tol), round(p[1] / tol))
    for i, (a, b) in enumerate(segs):
        for p in (a, b):
            k = key(p)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    ends[(k[0] + dx, k[1] + dy)].append(i)
    caps = []
    for i, (a, b) in enumerate(segs):
        t = _len(_sub(b, a))
        if not (tmin <= t <= tmax):
            continue
        d = _unit(_sub(b, a))
        n = _perp(d)
        sides = []
        for p in (a, b):
            sgn = set()
            for j in set(ends[key(p)]):
                if j == i:
                    continue
                q0, q1 = segs[j]
                if _len(_sub(q0, p)) < tol:
                    far = q1
                elif _len(_sub(q1, p)) < tol:
                    far = q0
                else:
                    continue
                v = _sub(far, p)
                if _len(v) < 0.02:
                    continue
                cosv = _dot(_unit(v), d)
                if abs(cosv) > 0.1:
                    if abs(abs(cosv) - 1) < 0.01 and _dot(v, _sub(p, _mid(a, b))) > 0:
                        sgn.add(9)          # collinear continuation -> part of a longer face
                    continue
                sgn.add(1 if _dot(v, n) > 0 else -1)
            sides.append(sgn)
        if 9 in sides[0] or 9 in sides[1]:
            continue
        common = sides[0] & sides[1]
        if len(common) != 1:
            continue
        s = common.pop()
        w = _mul(n, -s)
        back = _mul(w, -1)
        # depth = LONGER face running back from the cap: a door-side pier has both
        # faces ~= the jamb (0.12); a real wall end has at least one long face
        depth = max(_face_run(G, a, back), _face_run(G, b, back))
        caps.append({"c": _mid(a, b), "w": w, "t": t, "cap": (a, b), "depth": depth})
    return caps


def _face_groups(G, min_len=0.03):
    """W segments grouped into face LINES: (angle, offset) -> merged intervals along u."""
    items = []
    for a, b, _ in G.wall_segs:
        v = _sub(b, a)
        if _len(v) < min_len:
            continue
        ang = math.degrees(math.atan2(v[1], v[0])) % 180.0
        if ang > 179.7:
            ang -= 180.0
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        off = _cross(u, a)
        s0, s1 = sorted((_dot(u, a), _dot(u, b)))
        items.append((ang, off, s0, s1))
    items.sort()
    groups = []
    for ang, off, s0, s1 in items:
        for g in groups:
            if abs(g["ang"] - ang) < 0.25 and abs(g["off"] - off) < 0.004:
                g["iv"].append((s0, s1))
                break
        else:
            groups.append({"ang": ang, "off": off, "iv": [(s0, s1)]})
    for g in groups:
        merged = []
        for s0, s1 in sorted(g["iv"]):
            if merged and s0 <= merged[-1][1] + 0.003:
                merged[-1][1] = max(merged[-1][1], s1)
            else:
                merged.append([s0, s1])
        g["iv"] = merged
        g["u"] = (math.cos(math.radians(g["ang"])), math.sin(math.radians(g["ang"])))
        g["gaps"] = [(merged[k][1], merged[k + 1][0]) for k in range(len(merged) - 1)]
    return groups


def _band_gaps(G, gmin=0.30, gmax=4.0, tmin=0.07, tmax=0.40, tol=0.08):
    """Gaps where BOTH faces of a wall band are interrupted at the same place and the
    gap is empty (no crossing wall, no column) -> opening in a wall line."""
    groups = _face_groups(G)
    out = []
    for gi, g in enumerate(groups):
        for g0, g1 in g["gaps"]:
            if not (gmin <= g1 - g0 <= gmax):
                continue
            best = None
            for gj, h in enumerate(groups):
                if gj == gi or abs(h["ang"] - g["ang"]) > 0.3:
                    continue
                t = abs(h["off"] - g["off"])
                if not (tmin <= t <= tmax):
                    continue
                for h0, h1 in h["gaps"]:
                    if abs(h0 - g0) <= tol and abs(h1 - g1) <= tol:
                        if best is None or t < best[0]:
                            best = (t, h, h0, h1)
            if best is None:
                continue
            t, h, h0, h1 = best
            s_lo, s_hi = max(g0, h0), min(g1, h1)
            if s_hi - s_lo < gmin:
                continue
            u = g["u"]
            n = _perp(u)
            o_lo, o_hi = sorted((g["off"], h["off"]))

            def P(s, o, u=u, n=n):
                return _add(_mul(u, s), _mul(n, o))
            rect = Polygon([P(s_lo, o_lo), P(s_hi, o_lo), P(s_hi, o_hi), P(s_lo, o_hi)])
            inner = Polygon([P(s_lo + 0.015, o_lo + 0.01), P(s_hi - 0.015, o_lo + 0.01),
                             P(s_hi - 0.015, o_hi - 0.01), P(s_lo + 0.015, o_hi - 0.01)])
            if any(inner.intersects(G.wall_tree.geometries[k]) for k in G.wall_tree.query(inner)):
                continue
            if any(pg.intersects(rect) and pg.intersection(rect).area > 0.15 * rect.area for pg, _ in G.polys):
                continue
            out.append({"c0": P(s_lo, (o_lo + o_hi) / 2), "c1": P(s_hi, (o_lo + o_hi) / 2),
                        "t": t, "width": s_hi - s_lo, "rect": rect, "src": "band",
                        "capped": None})
    return out


def find_openings(fl, G, doors, windows):
    """Door-less openings.  Returns (openings, candidates, n_explained)."""
    door_polys = []
    for d in doors:
        if "jamb_a" in d:
            ja, jb = d["jamb_a"], d["jamb_b"]
            pg = Polygon([ja[0], ja[1], jb[1], jb[0]]).convex_hull.buffer(0.03)
            door_polys.append((pg, d["id"]))
    win_polys = []
    for w in windows:
        if w["shape"] == "straight":
            e1, e2 = w["ends"]
            win_polys.append((LineString([e1, e2]).buffer(max(w["frame_depth"], 0.05) / 2 + 0.15), w["id"]))
        else:
            win_polys.append((Point(w["center"]).buffer(w["radius_mid"] + 0.3).difference(
                Point(w["center"]).buffer(max(w["radius_mid"] - 0.4, 0.01))), w["id"]))

    def explain(rect):
        for pg, did in door_polys:
            if pg.intersects(rect) and pg.intersection(rect).area > 0.3 * min(pg.area, rect.area):
                return ("door", did)
        for pg, wid in win_polys:
            if pg.intersects(rect) and pg.intersection(rect).area > 0.2 * rect.area:
                return ("window", wid)
        return None

    caps = _wall_end_caps(G)
    raw = []
    single = []
    # (A) a wall end facing another wall end across an empty gap
    for k, cp in enumerate(caps):
        c, w, t = cp["c"], cp["w"], cp["t"]
        d = _perp(w)
        hits = [G.ray(_add(c, _mul(d, o)), w, max_len=4.0) for o in (-0.3 * t, 0.0, 0.3 * t)]
        if any(h[0] is None for h in hits):
            continue
        dist = min(h[0] for h in hits)
        if dist < 0.25:
            continue
        far = _add(c, _mul(w, dist))
        mate = None
        for m, cq in enumerate(caps):
            if m == k or _dot(cq["w"], w) > -0.99:
                continue
            v = _sub(cq["c"], c)
            if abs(_dot(v, w) - dist) > 0.03:
                continue
            a0, a1 = sorted((_dot(_sub(cp["cap"][0], c), d), _dot(_sub(cp["cap"][1], c), d)))
            b0, b1 = sorted((_dot(_sub(cq["cap"][0], c), d), _dot(_sub(cq["cap"][1], c), d)))
            if min(a1, b1) - max(a0, b0) >= 0.5 * min(a1 - a0, b1 - b0):
                mate = cq
                break
        a, b = cp["cap"]
        rect = Polygon([_add(a, _mul(w, 0.01)), _add(b, _mul(w, 0.01)),
                        _add(b, _mul(w, dist - 0.01)), _add(a, _mul(w, dist - 0.01))])
        if not rect.is_valid:
            rect = rect.buffer(0)
        rec = {"c0": c, "c1": far, "t": t, "width": dist, "rect": rect, "src": "caps",
               "capped": mate is not None, "depth": cp["depth"],
               "depth_far": mate["depth"] if mate else None, "t_far": mate["t"] if mate else None,
               "bound": hits[[h[0] for h in hits].index(dist)][1]}
        if mate is not None and min(cp["depth"], mate["depth"]) >= 0.25:
            raw.append(rec)
        elif mate is None:
            single.append(rec)
    # (B) both faces of a wall band interrupted (uncapped ends included)
    raw.extend(_band_gaps(G))

    def dedupe(lst):
        keep = []
        for g in sorted(lst, key=lambda g: (g["src"] != "caps", g["width"])):
            cg = _mid(g["c0"], g["c1"])
            dup = [k for k in keep if _len(_sub(cg, _mid(k["c0"], k["c1"]))) < 0.1 and abs(g["width"] - k["width"]) < 0.1]
            if dup:
                dup[0].setdefault("found_by", {dup[0]["src"]}).add(g["src"])
                continue
            g.setdefault("found_by", {g["src"]})
            keep.append(g)
        return keep
    raw = dedupe(raw)
    dash_lines = [LineString(s) for s in G.dash_segs]
    openings, n_expl = [], {"door": 0, "window": 0}
    for g in raw:
        ex = explain(g["rect"])
        if ex:
            n_expl[ex[0]] += 1
            continue
        openings.append(g)
    cands = []
    known = [_mid(g["c0"], g["c1"]) for g in raw]
    for g in single:
        cg = _mid(g["c0"], g["c1"])
        if g["depth"] < 0.25 or not (0.6 <= g["width"] <= 1.6) or g["bound"] != "wall":
            continue
        if explain(g["rect"]) or any(_len(_sub(cg, k)) < 0.15 for k in known):
            continue
        cands.append(g)

    def record(g, conf):
        c = _mid(g["c0"], g["c1"])
        w = _unit(_sub(g["c1"], g["c0"]))
        n = _perp(w)
        rb = g["rect"].buffer(0.02)
        dash = [ln for ln in dash_lines if ln.intersects(rb)]
        near_col = [lay for pg, lay in G.polys if lay != "try"
                    and pg.distance(Point(g["c0"])) < 0.06 and pg.distance(Point(g["c1"])) < 0.06]
        return {"kind": "opening in concrete core/column wall (not masonry)" if near_col else "opening (no door/window)",
                "center": _r(c), "axis_deg": _r(_axis_angle(w), 2),
                "width": _r(g["width"]), "wall_t": _r(g["t"]), "ends": _r([g["c0"], g["c1"]]),
                "found_by": sorted(g.get("found_by", {g["src"]})),
                "dash_across": bool(dash), "dash_len_in_gap": _r(sum(ln.intersection(rb).length for ln in dash)),
                "side_a": G.room_on_side(c, n), "side_b": G.room_on_side(c, _mul(n, -1)), "confidence": conf}

    def hint(rec):
        sides = " ".join(x for x in (rec["side_a"], rec["side_b"]) if x)
        if "مصعد" in sides or "المصاعد" in sides:
            rec["kind"] = "lift landing opening (lift door by supplier, no door block)"
        return rec
    out = []
    for g in openings:
        conf = "high" if g["width"] <= 3.0 else "medium"
        if g["src"] == "caps" and g.get("t_far") is not None and abs(g["t_far"] - g["t"]) > 0.03:
            conf = "medium"
        out.append(hint(record(g, conf)))
    out.sort(key=lambda o: (-round(o["center"][1] / 0.5), o["center"][0]))
    for k, o in enumerate(out, 1):
        o["id"] = f"{fl.label}-O{k:02d}"
    cand = [record(g, "low") for g in cands]
    for o in cand:
        o["kind"] = "candidate: wall end facing a perpendicular wall (review)"
    cand.sort(key=lambda o: (-round(o["center"][1] / 0.5), o["center"][0]))
    for k, o in enumerate(cand, 1):
        o["id"] = f"{fl.label}-C{k:02d}"
    return out, cand, n_expl


# ----------------------------------------------------------------------------- floor analysis
def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float):
        return round(o, 4)
    return o


def summarize(doors, windows, openings):
    s = {"doors": {"count": 0, "total_width": 0.0, "by_type": {}},
         "windows": {"count": 0, "total_width": 0.0, "by_kind": {}},
         "openings": {"count": 0, "total_width": 0.0, "by_confidence": {}}}
    for d in doors:
        if "width" not in d:
            continue
        key = d.get("block") or "raw (no block)"
        b = s["doors"]["by_type"].setdefault(key, {"count": 0, "total_width": 0.0, "widths": []})
        b["count"] += 1
        b["total_width"] += d["width"]
        if d["width"] not in b["widths"]:
            b["widths"].append(d["width"])
        s["doors"]["count"] += 1
        s["doors"]["total_width"] += d["width"]
    for w in windows:
        b = s["windows"]["by_kind"].setdefault(w["kind"], {"count": 0, "total_width": 0.0})
        b["count"] += 1
        b["total_width"] += w["width"]
        s["windows"]["count"] += 1
        s["windows"]["total_width"] += w["width"]
    for o in openings:
        b = s["openings"]["by_confidence"].setdefault(o["confidence"], {"count": 0, "total_width": 0.0})
        b["count"] += 1
        b["total_width"] += o["width"]
        s["openings"]["count"] += 1
        s["openings"]["total_width"] += o["width"]
    return _clean(s)


def analyze_floor(floor):
    fl = get_floor(floor) if isinstance(floor, int) else floor
    G = FloorGeom(fl)
    G._door_hinges = []
    doors = read_doors(fl, G)
    G._door_hinges = [tuple(d["hinge"]) for d in doors if d.get("hinge")]
    G._doors = doors
    windows = read_windows(fl, G)
    frame_pieces = [w for w in windows if w["kind"].startswith("frame piece")]
    windows = [w for w in windows if not w["kind"].startswith("frame piece")]
    for k, w in enumerate(windows, 1):
        w["id"] = f"{fl.label}-W{k:02d}"
    openings, candidates, n_expl = find_openings(fl, G, doors, windows)
    checks = {
        "door_gap_vs_block": [
            {"id": d["id"], "block_w": d["width"], "gap": d["host"]["gap"],
             "diff": _r(d["host"]["gap"] - d["width"]) if d["host"]["gap"] is not None else None}
            for d in doors if "host" in d and (d["host"]["gap"] is None or abs(d["host"]["gap"] - d["width"]) > 0.005)],
        "door_wall_t_vs_block": [
            {"id": d["id"], "block_t": d.get("nominal_wall_t"), "measured": [d["host"]["wall_t_minus"], d["host"]["wall_t_plus"]]}
            for d in doors if d.get("nominal_wall_t") and any(
                v is not None and abs(v - d["nominal_wall_t"]) > 0.02 for v in (d["host"]["wall_t_minus"], d["host"]["wall_t_plus"]))],
        "windows_with_dim": sum(1 for w in windows if w.get("dim_check")),
        "windows_dim_mismatch": [
            {"id": w["id"], "width": w["width"], "dim": w["dim_check"]["value"]}
            for w in windows if w.get("dim_check") and w["dim_check"]["value"] is not None
            and abs(w["dim_check"]["value"] - w["width"]) > 0.02],
        "doors_with_dim": sum(1 for d in doors if d.get("dim_check")),
        "other_inserts": sorted({f'{e.dxf.layer}:{e.dxf.name}' for e in G.other_inserts}),
        "wall_gaps_explained": n_expl,
    }
    res = {"floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
           "file": fl.file.name, "sheet_index": fl.sheet_index, "units": "m",
           "frame": "LOCAL (diwan_common.Floor.to_local: -10 deg, structural-column corner = 0,0)",
           "doors": doors, "windows": windows, "openings": openings, "opening_candidates": candidates,
           "window_frame_pieces": frame_pieces,
           "summary": summarize(doors, windows, openings), "checks": checks}
    if fl.floor_no == 3:
        res["checks"]["legacy_f03_user_dims"] = LEGACY_F03
    res["_G"] = G
    return res


# ----------------------------------------------------------------------------- deductions
# Heights are NOT in the plans.  2.30 m is the user's own convention from the legacy F03/F04
# takeoff (doors and windows x 2.30, deducted).  Windows / door-less openings have no
# default: pass them explicitly once the engineer confirms (sections / schedules).
DEFAULT_HEIGHTS = {"door": 2.30, "window": None, "opening": None}


def deduction_table(res, door_h=DEFAULT_HEIGHTS["door"], window_h=DEFAULT_HEIGHTS["window"],
                    opening_h=DEFAULT_HEIGHTS["opening"], include_curtain_wall=False):
    """Rows {id, type, kind, width, height, area, wall_t} for masonry/plaster deductions.
    height/area are None where no height was given.  Curtain-wall glazing (no masonry)
    is skipped unless include_curtain_wall=True."""
    rows = []

    def row(it, typ, h, t):
        w = it.get("width")
        rows.append({"id": it["id"], "type": typ, "kind": it.get("kind"), "width": w, "height": h,
                     "area": _r(w * h) if (w is not None and h is not None) else None, "wall_t": t})
    for d in res["doors"]:
        if "width" in d:
            h = d.get("host") or {}
            t = d.get("nominal_wall_t") or h.get("wall_t_minus") or h.get("wall_t_plus")
            row(d, "door", door_h, t)
    for w in res["windows"]:
        if "curtain" in w["kind"] and not include_curtain_wall:
            continue
        h = w.get("host") or {}
        row(w, "window", window_h, h.get("wall_t_minus") or h.get("wall_t_plus"))
    for o in res["openings"]:
        row(o, "opening", opening_h, o.get("wall_t"))
    return rows


# ----------------------------------------------------------------------------- review PNG
def render_review(res, out_png, zoom=None, dpi=110, label_size=5.5):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as MPoly
    plt.rcParams["font.family"] = "Tahoma"
    G = res["_G"]
    fl = G.fl
    if zoom:
        x0, y0, x1, y1 = zoom
    else:
        xs = [p[0] for a, b, _ in G.wall_segs for p in (a, b)]
        ys = [p[1] for a, b, _ in G.wall_segs for p in (a, b)]
        xs = [x for x in xs if BUILDING_WINDOW[0] < x < BUILDING_WINDOW[2]]
        ys = [y for y in ys if BUILDING_WINDOW[1] < y < BUILDING_WINDOW[3]]
        x0, y0, x1, y1 = min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1
    W, H = x1 - x0, y1 - y0
    sc = 26.0 / max(W, H)
    fig, ax = plt.subplots(figsize=(max(W * sc, 6) + 1.5, max(H * sc, 6) + 1))

    def inview(p, m=0.5):
        return x0 - m <= p[0] <= x1 + m and y0 - m <= p[1] <= y1 + m
    for pg, lay in G.polys:
        if pg.geom_type == "Polygon" and inview(pg.centroid.coords[0], 3):
            ax.add_patch(MPoly(list(pg.exterior.coords), closed=True, fc="#dfe9df" if lay != "try" else "#f3e8d8",
                               ec="#9ab09a", lw=0.4))
    for a, b, _ in G.wall_segs:
        if inview(a) or inview(b):
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#555555", lw=0.6)
    for a, b in G.win_lines:
        if inview(a) or inview(b):
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#9fe3ee", lw=0.5)
    for a, b in G.win_dashed:
        if inview(a) or inview(b):
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#9fe3ee", lw=0.4, ls="--")
    for a, b in G.dash_segs:
        if inview(a) or inview(b):
            ax.plot([a[0], b[0]], [a[1], b[1]], color="#d9d27a", lw=0.4, ls="--")
    for txt, p in G.labels:
        if inview(p, 0):
            ax.text(p[0], p[1], txt, fontsize=label_size + 0.5, color="#777777", ha="center", va="center", clip_on=True)
    # windows (cyan)
    for w in res["windows"]:
        if not inview(w["center"], 2):
            continue
        if w["shape"] == "straight":
            e1, e2 = w["ends"]
            ax.plot([e1[0], e2[0]], [e1[1], e2[1]], color="#00a8c6", lw=3.2, alpha=0.75, solid_capstyle="butt")
        else:
            c, r = w["center"], w["radius_mid"]
            pts = []
            for a in G.raw_arcs:
                if a["layer"] == "WIN" and _len(_sub(a["center"], c)) < 0.02:
                    pts.append(a)
            for a in pts:
                v0, v1 = _sub(a["p0"], c), _sub(a["p1"], c)
                t0 = math.atan2(v0[1], v0[0]); t1 = math.atan2(v1[1], v1[0])
                if t1 < t0:
                    t1 += 2 * math.pi
                ts = [t0 + (t1 - t0) * i / 40 for i in range(41)]
                ax.plot([c[0] + r * math.cos(t) for t in ts], [c[1] + r * math.sin(t) for t in ts],
                        color="#00a8c6", lw=3.2, alpha=0.75)
        m = w["ends"][0] if w["shape"] == "arc" else w["center"]
        lab = f'{w["id"].split("-")[1]} {w["width"]:.2f}'
        if w["kind"].startswith("glazed facade"):
            lab += " CW"
        elif "single" in w["kind"]:
            lab += " (1L)"
        elif "check" in w["kind"]:
            lab += " ?"
        ax.text(m[0], m[1], lab, fontsize=label_size, color="#006b80", rotation=0 if w.get("axis_deg", 0) < 45 or w.get("axis_deg", 0) > 135 else 90,
                ha="center", va="center", bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.3), clip_on=True)
    # doors (green)
    for d in res["doors"]:
        if "jamb_a" not in d or not inview(d["center"], 2):
            continue
        ja, jb = d["jamb_a"], d["jamb_b"]
        ax.add_patch(MPoly([ja[0], ja[1], jb[1], jb[0]], closed=True, fc="#2ca02c", ec="#1a6b1a", alpha=0.45, lw=0.6))
        lg = d.get("leaf_geom") or {}
        if lg.get("c") and d.get("leaf_r"):
            c = lg["c"]
            r = d["leaf_r"]
            p0 = lg.get("p0") or lg.get("pm")
            p1 = lg.get("p1") or lg.get("pm")
            t0 = math.atan2(p0[1] - c[1], p0[0] - c[0]); t1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
            tm = math.atan2(lg["pm"][1] - c[1], lg["pm"][0] - c[0])
            # walk the short way that passes through pm
            span = (t1 - t0) % (2 * math.pi)
            if ((tm - t0) % (2 * math.pi)) > span:
                t0, t1 = t1, t0
                span = (t1 - t0) % (2 * math.pi)
            ts = [t0 + span * i / 30 for i in range(31)]
            ax.plot([c[0] + r * math.cos(t) for t in ts], [c[1] + r * math.sin(t) for t in ts], color="#2ca02c", lw=0.8)
        c = d["center"]
        n = d["_n"]
        off = 0.32 if d.get("swing_side") == "-n" else -0.32
        tp = (c[0] + n[0] * off, c[1] + n[1] * off)
        ax.text(tp[0], tp[1], f'{d["id"].split("-")[1]} {d["width"]:.2f}', fontsize=label_size, color="#145a14",
                ha="center", va="center", rotation=0 if (d["axis_deg"] < 45 or d["axis_deg"] > 135) else 90,
                bbox=dict(fc="white", ec="none", alpha=0.65, pad=0.3), clip_on=True)
    # openings (orange)
    for o in res["openings"]:
        if not inview(o["center"], 2):
            continue
        e1, e2 = o["ends"]
        col = {"high": "#ff7f0e", "medium": "#ffa040", "low": "#ffc080"}[o["confidence"]]
        ax.plot([e1[0], e2[0]], [e1[1], e2[1]], color=col, lw=4, alpha=0.7, solid_capstyle="butt")
        ax.text(o["center"][0], o["center"][1], f'{o["id"].split("-")[1]} {o["width"]:.2f}' + ("" if o["confidence"] == "high" else "?"),
                fontsize=label_size, color="#a04000", ha="center", va="center",
                rotation=0 if (o["axis_deg"] < 45 or o["axis_deg"] > 135) else 90,
                bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.3), clip_on=True)
    s = res["summary"]
    ax.set_title(f'{fl.label} {fl.name_ar} {fl.level:+.2f}  doors {s["doors"]["count"]} = {s["doors"]["total_width"]:.2f} m | '
                 f'windows {s["windows"]["count"]} = {s["windows"]["total_width"]:.2f} m | openings {s["openings"]["count"]}  '
                 f'(green=door, cyan=window, CW=curtain wall, orange=opening)', fontsize=9)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.15)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ----------------------------------------------------------------------------- CLI
def run(floors=None, png=True, tiles=True):
    fls = all_floors()
    if floors:
        fls = [f for f in fls if f.floor_no in floors]
    OUT.mkdir(parents=True, exist_ok=True)
    allsum = {}
    items = defaultdict(dict)      # (kind, rounded centre, width) -> {floor: id}
    for fl in fls:
        res = analyze_floor(fl)
        data = _clean({k: v for k, v in res.items() if k != "_G"})
        for cat in ("doors", "windows", "openings"):
            for it in data[cat]:
                if "center" in it and "width" in it:
                    key = (cat, round(it["center"][0] / 0.1), round(it["center"][1] / 0.1), round(it["width"], 2))
                    items[key][fl.label] = it["id"]
        (OUT / f"{fl.label}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        if png:
            render_review(res, OUT / f"{fl.label}.png")
            if tiles:
                for nm, z in (("south", (-2.5, -2.5, 17.5, 13.5)), ("middle", (-2.5, 11.5, 20.5, 27.5)),
                              ("north", (-2.5, 25.5, 17.5, 41.0))):
                    render_review(res, OUT / f"{fl.label}_{nm}.png", zoom=z, dpi=120, label_size=7)
        s = data["summary"]
        allsum[fl.label] = s
        bt = ", ".join(f'{k}x{v["count"]}' for k, v in sorted(s["doors"]["by_type"].items()))
        print(f'{fl.label} {fl.level:+.2f}  doors {s["doors"]["count"]:3d} = {s["doors"]["total_width"]:6.2f} m [{bt}]'
              f' | windows {s["windows"]["count"]:3d} = {s["windows"]["total_width"]:6.2f} m'
              f' | openings {s["openings"]["count"]:3d} = {s["openings"]["total_width"]:6.2f} m')
    # items that are NOT on every analysed floor (same local position +-10 cm and width)
    labels = [f.label for f in fls]
    diff = []
    for (cat, kx, ky, w), fl_ids in sorted(items.items(), key=lambda kv: (kv[0][0], -kv[0][2], kv[0][1])):
        if len(fl_ids) < len(labels):
            diff.append({"type": cat, "center": [kx / 10, ky / 10], "width": w,
                         "present_on": sorted(fl_ids), "ids": fl_ids})
    allsum["_not_on_all_floors"] = diff
    (OUT / "summary.json").write_text(json.dumps(allsum, ensure_ascii=False, indent=1), encoding="utf-8")
    if len(labels) > 1:
        print(f"items not on all {len(labels)} floors: {len(diff)}")
        for d in diff:
            print(f'  {d["type"]:8s} @({d["center"][0]:5.1f},{d["center"][1]:5.1f}) w={d["width"]:.2f}  on {",".join(d["present_on"])}')
    return allsum


def main():
    ap = argparse.ArgumentParser(description="Doors / windows / openings reader (Diwan plans)")
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (default: all 2..8)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-tiles", action="store_true", help="only the whole-floor PNG")
    a = ap.parse_args()
    run(a.floors or None, png=not a.no_png, tiles=not a.no_tiles)


if __name__ == "__main__":
    main()
