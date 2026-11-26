# -*- coding: utf-8 -*-
"""
openings — قارئ الأبواب والشبابيك والفتحات (خصومات المباني والمحارة) لمساقط الديوان.

Reads every floor (F02..F11) of the Diwan plans and returns, in the shared LOCAL
frame of diwan_common (rotation removed, structural-column corner = (0,0), metres):

  DOORS     * every INSERT of a door block  D<w>W<t>  (D10W12 = 1.00 m door in a
              0.12 wall, D80W12 = 0.80, D90W12 = 0.90, D90W25 = 0.90 in 0.25 wall).
              Geometry is read from the BLOCK DEFINITION (the two jamb lines whose
              length = wall thickness, and the leaf ARC) and pushed through the
              insert's full matrix (rotation, mirror xscale=-1, scale) -> jambs,
              measured width, hinge, swing side, axis.  Doors are inserted on layer
              W *or* PR (same blocks; layer is irrelevant) - read on ANY layer (F10 has
              one D80W12 on DIM, checks.doors_on_other_layers).
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
            * WIN inside a stair zone (buffered hull of the ST lines) = stair eye / break
              line drawn on WIN (F11) -> skipped, checks.win_in_stair_skipped;
            * two WIN lines 0.02-0.06 m apart = ONE glazing line drawn double (F11
              curtain-wall frames) -> merged before pairing;
            * pairs of parallel lines 0.05-0.35 m apart -> one window unit in a wall
              (width = length along the wall, depth = frame line spacing); two lone lines
              up to 0.40 apart that both start on one W cap = glazing return (F11 NE);
            * long pairs not bounded by masonry, or glazing between two concrete
              elements (no W jamb) -> glazed facade / curtain wall;
            * concentric ARC pairs -> curved corner glazing (union of the sweeps of both
              radii x mid radius + chord; flagged when the radii differ > 10 deg);
            * glazing touching a door jamb -> fixed glazing beside a door (F02);
            * units < 0.30 m -> frame pieces (jambs/mullions), kept apart;
            * single unpaired lines/arcs -> single-line glazing (flagged, NOT deducted:
              summary.unresolved_glazing), whatever their length;
            * duplicate glazing items (same line +-0.10, > 80 % overlap) -> one.
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
  ASSEMBLIES  a door + fixed glazing + frame pieces drawn side by side in ONE masonry
            opening (F02 east terrace: 2.35 = 0.10 frame + door 1.00 + glass 1.25, and
            1.35 = 0.15 + door 1.00 + 0.20).  The masonry deduction is the assembly's
            masonry gap; its members carry 'in_assembly'.
  MASONRY   summary.masonry_deduction_widths = what is really cut out of block walls,
            by type and host wall thickness ('door|0.12', 'window|0.25', ...): only
            MASONRY_WINDOW_KINDS windows - no curtain wall, no curved corner glazing, no
            unpaired single-line glazing, no glazed corner doors (they sit in glazing,
            not in masonry), assemblies counted once at their masonry gap.
  CHECKS    door_width_totals (block / clear W gap / smaller face-line gap = what a
            surveyor snapping to W line ends gets), door_gap_vs_block (+ face_gaps),
            windows_dim_projection (facade DIM showing a projection, e.g. 0.786 for a
            0.80 window in the slanted wall), dims_along_solid_wall (architect DIM that
            measures a stretch of solid wall = stale dim / moved window), legacy F03.

Not doors / windows (checked on all floors, see docs/findings/openings.md):
  LP (layer W) = level-mark symbol, WB/P (FUR) = wash basin / WC, ST-2 (PR1) =
  stair arrow, random-named blocks on W ('rt5hrt6', '56y', ...) = CI circle +
  TEXT-DIM letter = AXIS TAGS (ز ا ب ج د / 1 2 3 4) in the sheet margins, the
  random-named X blocks = axis bubbles, PR raw lines = stair handrails + lift cars.

CLI (default = all floors):
    python tools/openings.py                 # F02..F11 -> output/openings/Fxx.json + PNGs
    python tools/openings.py 3 5 --no-png
API:
    from openings import analyze_floor, deduction_table
    res = analyze_floor(3)       # dict: doors / windows / openings / summary / checks
    res["doors"][0]["width"], res["summary"]["doors"]["total_width"]
    rows = deduction_table(res, door_h=2.30, window_h=None)   # heights are NOT in the plans
JSON (output/openings/F0x.json) is the same dict without the private geometry handle.
Every item has: id (F03-D07 door / F03-W12 window / F03-O01 opening / F02-A01 assembly /
F02-F03 frame piece / F03-C01 candidate), center [x,y] local, axis_deg, width (m),
host {gap, gap_minus/plus, bound_*, wall_t_minus/plus, face_gaps[2]} = masonry gap measured
on the walls, host_line {orientation N-S|E-W|slanted, offset_x|offset_y, from/to} = the
wall line it sits in (for matching with tools/walls.py records).
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
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import OUT_DIR, all_floors, floor_entities, floor_texts, get_floor, is_try_outline  # noqa: E402

OUT = OUT_DIR / "openings"
# bump when the extraction / classification changes (read_plan's cache key also hashes this
# file's source, so a bump only documents the change)
#   2 = F09-F11 fixes: WIN inside stair zones skipped, WIN twin lines (0.02-0.06 apart) merged,
#       corner-return pairs up to 0.40 on a common masonry cap, glazing between concrete = curtain
#       wall, duplicate glazing dropped, door blocks read on ANY layer, curved glazing = union of
#       both radii, unpaired single-line glazing kept out of the masonry deductions
READER_VERSION = 2
DOOR_RE = re.compile(r"^D(\d+)W(\d+)$", re.I)
WALL_LAYERS = ("W",)
OBSTACLE_POLY_LAYERS = ("Etabs-col", "COL", "try")
BUILDING_WINDOW = (-4.0, -4.0, 24.0, 44.0)   # local box that contains the building + terraces
LEGACY_F03 = {"doors": 37, "door_width": 34.23}  # user's own AutoCAD dims, Sept 2026
MAX_SEG = 30.0                                    # longer W/WIN pieces = sheet frame, not building
STAIR_ZONE_BUFFER = 0.20     # m around the convex hull of each ST-line cluster (stair zone)
TWIN_GAP = (0.02, 0.06)      # WIN lines this far apart = ONE glazing line drawn double (F11 frames)
CORNER_RETURN_MAX = 0.40     # lone WIN lines up to this far apart pair when both end on one W cap
# window kinds that really cut a MASONRY wall (deduction_table / masonry_deduction_widths)
MASONRY_WINDOW_KINDS = ("window in masonry opening", "window (gap != glazing, check)",
                        "fixed glazing beside a door (same opening)")
UNRESOLVED_KIND = "single-line glazing (unpaired)"

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


def _stair_zones(fl, buffer=STAIR_ZONE_BUFFER):
    """One zone per stair: convex hull of each cluster of ST lines (>= 4 lines, clustered by a
    0.6 m buffer, as walls._stair_hulls), buffered by `buffer`.  LOCAL frame."""
    L = fl.to_local
    st = []
    for e in floor_entities(fl, layers=("ST",), types="LINE LWPOLYLINE POLYLINE"):
        for poly in _flatten(e):
            lp = [L(*p) for p in poly]
            st.extend(LineString([a, b]) for a, b in zip(lp, lp[1:]) if 1e-4 < _len(_sub(b, a)) < MAX_SEG)
    if not st:
        return []
    blobs = unary_union([ln.buffer(0.6) for ln in st])
    out = []
    for bl in getattr(blobs, "geoms", [blobs]):
        members = [ln for ln in st if bl.contains(ln.centroid)]
        if len(members) >= 4:
            out.append(unary_union(members).convex_hull.buffer(buffer))
    return out


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
        self.mass_segs = []          # [(p,q)] MASS lines (only used to anchor curved-glazing ends)
        self.polys = []              # [(Polygon, layer)] columns / shafts
        # door blocks D<w>W<t> on ANY layer: the insertion layer means nothing (W / PR on F02-F11,
        # and F10 has one D80W12 inserted on DIM, handle 44B0)
        self.door_inserts = [e for e in floor_entities(fl, types="INSERT") if DOOR_RE.match(e.dxf.name)]
        self.other_inserts = []
        # stair zones (buffered convex hull of each ST-line cluster): WIN drawn inside one is the
        # stair eye / break line (F11 draws them on WIN, F02-F10 on MASS) - never glazing
        self.stair_zones = _stair_zones(fl)
        self.win_in_stair = []       # skipped WIN entities (reported in checks)
        for e in floor_entities(fl, layers=("MASS",), types="LINE LWPOLYLINE"):
            for poly in _flatten(e):
                lp = [L(*p) for p in poly]
                self.mass_segs.extend((a, b) for a, b in zip(lp, lp[1:]) if 1e-4 < _len(_sub(b, a)) < MAX_SEG)
        for e in floor_entities(fl, layers=("W", "0", "WIN", "PR", "DASH") + OBSTACLE_POLY_LAYERS):
            lay, t = e.dxf.layer, e.dxftype()
            if t == "INSERT":
                if not DOOR_RE.match(e.dxf.name):
                    self.other_inserts.append(e)
                continue
            if t in ("TEXT", "MTEXT", "HATCH", "DIMENSION"):
                continue
            if lay == "WIN" and self.stair_zones:
                pts = [L(*p) for poly in _flatten(e) for p in poly]
                if pts and any(z.covers(LineString(pts) if len(pts) >= 2 else Point(pts[0]))
                               for z in self.stair_zones):
                    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                    self.win_in_stair.append({
                        "handle": e.dxf.handle, "type": t, "dashed": _is_dashed(e, doc),
                        "closed": bool(getattr(e, "closed", False)) if t == "LWPOLYLINE" else None,
                        "bbox": _r([min(xs), min(ys), max(xs), max(ys)]),
                        "reason": "WIN inside a stair zone (stair eye / break line), not glazing"})
                    continue
            if lay in OBSTACLE_POLY_LAYERS:
                if t == "LWPOLYLINE":
                    pts = [L(p[0], p[1]) for p in e.get_points("xy")]
                    if lay == "try" and is_try_outline(pts):
                        continue          # F09-F11: floor / plot outline on try, not a shaft
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
                # drop degenerate pieces and the sheet-size frame polyline drawn on W
                # (~110 x 85 m, far outside the building)
                segs = [(a, b) for a, b in zip(lp, lp[1:]) if 1e-4 < _len(_sub(b, a)) < MAX_SEG]
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
                rec = {"value": _r(d["value"]), "along": _r(hi - lo), "layer": d["layer"], "handle": d["handle"]}
                if d["value"] is not None and abs(d["value"] - (hi - lo)) > 0.005:
                    # e.g. slanted east facade: a LINEAR dim rotated to the building axis
                    # shows 0.786 = projection of a 0.80 window measured along the wall
                    rec["note"] = ("dim value is a projection (linear dim not parallel to the wall); "
                                   "true width along the wall = 'along'")
                out.append(rec)
        return out

    def dims_along_solid_wall(self, anchors, tol=0.02):
        """Architect DIMs (0.3-4 m) whose two defpoints sit on the SAME continuous W face,
        at no vertex of any W / WIN / column / door element: the dim measures a stretch of
        solid wall = a stale dimension (opening moved or deleted) -> review list."""
        from shapely.strtree import STRtree as _T
        vt = _T([Point(p) for p in anchors])
        segs = [(a, b) for a, b, _ in self.wall_segs] + list(self.win_lines)
        st = _T([LineString(s) for s in segs])
        out = []
        for d in self.dims:
            v = d["value"]
            if v is None or not (0.3 <= v <= 4.0):
                continue
            if any(len(vt.query(Point(p).buffer(tol), predicate="intersects")) for p in (d["p2"], d["p3"])):
                continue
            for a, b in segs[:len(self.wall_segs)]:
                ln = LineString([a, b])
                if not (ln.distance(Point(d["p2"])) < tol and ln.distance(Point(d["p3"])) < tol):
                    continue
                uw = _unit(_sub(b, a))
                # a defpoint where another line CROSSES this face (T-junction drawn through,
                # overdrawn face) is also a legitimate anchor
                crossed = False
                for p in (d["p2"], d["p3"]):
                    for k in st.query(Point(p).buffer(tol), predicate="intersects"):
                        q0, q1 = segs[k]
                        if abs(_cross(_unit(_sub(q1, q0)), uw)) > 0.2:
                            crossed = True
                if not crossed:
                    out.append({"value": _r(d["value"]), "p2": _r(d["p2"]), "p3": _r(d["p3"]),
                                "along_wall": _r(_len(_sub(d["p3"], d["p2"]))), "handle": d["handle"]})
                break
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
    rec["host"] = measure_host(G, c, u, width, t, face_offsets=(-t / 2, t / 2))
    rec["host_line"] = host_line(c, u, width)
    dm = G.dim_match(ma, mb)
    rec["dim_check"] = dm[0] if dm else None
    rec["_u"], rec["_n"], rec["_c"] = u, n, c
    return rec


def face_gaps(G, c, u, offsets, reach=2.5, tol=0.006):
    """Gap between the W pieces of EACH face line of the host wall (face lines at the given
    signed offsets along n from the axis through c), i.e. what a surveyor gets by snapping
    to the face-line ends.  Returns [gap on face -n, gap on face +n]; None where a face has
    no piece on one side (wall end, T-junction) or runs straight through."""
    n = _perp(u)
    out = []
    for off in offsets:
        if off is None:
            out.append(None)
            continue
        lo, hi, through = None, None, False
        for a, b, _ in G.wall_segs:
            v = _sub(b, a)
            if _len(v) < 0.02 or abs(_cross(_unit(v), u)) > 0.01:
                continue
            if abs(_dot(_sub(a, c), n) - off) > tol:
                continue
            s0, s1 = sorted((_dot(_sub(a, c), u), _dot(_sub(b, c), u)))
            if s0 < -1e-3 and s1 > 1e-3:
                through = True
            elif s1 <= 1e-3 and s1 > -reach and (lo is None or s1 > lo):
                lo = s1
            elif s0 >= -1e-3 and s0 < reach and (hi is None or s0 < hi):
                hi = s0
        out.append(None if through or lo is None or hi is None else _r(hi - lo))
    return out


def host_line(c, u, width):
    """Where the opening sits: wall orientation, centre-line offset and the along-wall
    range, in the local frame (N-S wall -> offset = x, along = y; E-W -> offset = y)."""
    ang = _axis_angle(u)
    if min(ang, 180 - ang) < 2:
        return {"orientation": "E-W", "offset_y": _r(c[1]), "from_x": _r(c[0] - width / 2), "to_x": _r(c[0] + width / 2)}
    if abs(ang - 90) < 2:
        return {"orientation": "N-S", "offset_x": _r(c[0]), "from_y": _r(c[1] - width / 2), "to_y": _r(c[1] + width / 2)}
    return {"orientation": f"slanted {ang:.1f} deg", "center": _r(c)}


def measure_host(G, c, u, width, t, extra=1.2, face_band=None, face_offsets=None):
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
    th, faces = [], []
    for sgn, nm in ((-1, "minus"), (1, "plus")):
        dd = dist.get(nm, width / 2)
        p = _add(c, _mul(u, sgn * (dd + 0.05)))
        a, _ = G.ray(p, n, 0.6, kinds=("wall",))
        b, _ = G.ray(p, _mul(n, -1), 0.6, kinds=("wall",))
        ok = a is not None and b is not None and a + b < 0.6
        th.append(_r(a + b) if ok else None)
        if ok:
            faces.append((-b, a))
    res["wall_t_minus"], res["wall_t_plus"] = th
    # masonry gap on each face line: doors -> the block's own faces (+-t/2 about the jamb
    # axis); windows -> the two face lines found by the thickness probes above
    if face_offsets is not None:
        res["face_gaps"] = face_gaps(G, c, u, face_offsets)
    elif faces:
        res["face_gaps"] = face_gaps(G, c, u, faces[0])
    else:
        res["face_gaps"] = [None, None]
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
        arc_ends = [q for b in G.raw_arcs if b is not a and b["layer"] == "WIN" and not b["dashed"]
                    for q in (b["p0"], b["p1"])]
        if any(min(_len(_sub(q, c)), _len(_sub(q, far))) < 0.08 for q in arc_ends):
            # leaf closes a gap in the curved corner glazing: no masonry around it
            meta["host_type"] = "curved glazing (no masonry)"
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
def _parallel_overlap(a, b):
    """(perpendicular offset, overlap length along a, len a, len b) of two segments, or None
    when they are not parallel."""
    a0, a1 = a
    b0, b1 = b
    ua = _unit(_sub(a1, a0))
    ub = _unit(_sub(b1, b0))
    if abs(_cross(ua, ub)) > 0.02:
        return None
    La, Lb = _len(_sub(a1, a0)), _len(_sub(b1, b0))
    off = abs(_cross(ua, _sub(b0, a0)))
    s0, s1 = sorted((_dot(_sub(b0, a0), ua), _dot(_sub(b1, a0), ua)))
    return off, min(La, s1) - max(0.0, s0), La, Lb


def _merge_twins(lines, gmin=TWIN_GAP[0], gmax=TWIN_GAP[1], min_ov=0.8):
    """WIN lines that are parallel, gmin..gmax apart and overlap > min_ov of the shorter one are
    ONE glazing line drawn double (F11 curtain-wall frames: 0.04 apart, e.g. 483D/483F x=2.37/2.41).
    Returns (merged_lines, meta): each merged line = mid offset, UNION of the spans; meta[i] =
    {'members': [original lines], 'twin_gap': gap or 0.0}."""
    n = len(lines)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            po = _parallel_overlap(lines[i], lines[j])
            if po is None:
                continue
            off, ov, La, Lb = po
            if gmin <= off <= gmax and ov > min_ov * min(La, Lb):
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    out, meta = [], []
    for root, g in groups.items():
        if len(g) == 1:
            out.append(lines[g[0]])
            meta.append({"members": [lines[g[0]]], "twin_gap": 0.0})
            continue
        segs = [lines[i] for i in g]
        L0 = max(segs, key=lambda s: _len(_sub(s[1], s[0])))
        u = _unit(_sub(L0[1], L0[0]))
        nn = _perp(u)
        o = L0[0]
        ss = [_dot(_sub(p, o), u) for s in segs for p in s]
        oo = [_dot(_sub(p, o), nn) for s in segs for p in s]
        om = (min(oo) + max(oo)) / 2
        p = _add(_add(o, _mul(u, min(ss))), _mul(nn, om))
        q = _add(_add(o, _mul(u, max(ss))), _mul(nn, om))
        out.append((p, q))
        meta.append({"members": segs, "twin_gap": max(oo) - min(oo)})
    return out, meta


def _pair_lines(lines, dmin=0.05, dmax=0.35, min_ov=0.5, wide_ok=None, wide_max=CORNER_RETURN_MAX):
    """Union-find of parallel WIN lines dmin..dmax apart overlapping > min_ov of the shorter.
    wide_ok(i, j): optional second chance for two LONE lines dmax..wide_max apart (corner return
    of a curtain wall spanning a 0.40 wall: F11 46FB/46FC, both ending on the W cap y=36.284)."""
    n = len(lines)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    partner = defaultdict(list)
    wide = []
    for i in range(n):
        for j in range(i + 1, n):
            po = _parallel_overlap(lines[i], lines[j])
            if po is None:
                continue
            off, ov, La, Lb = po
            if ov <= min_ov * min(La, Lb):
                continue
            if dmin <= off <= dmax:
                partner[i].append((j, off))
                partner[j].append((i, off))
                parent[find(i)] = find(j)
            elif wide_ok is not None and dmax < off <= wide_max:
                wide.append((i, j, off))
    wide_pairs = []
    for i, j, off in wide:
        if partner[i] or partner[j] or not wide_ok(i, j):
            continue
        partner[i].append((j, off))
        partner[j].append((i, off))
        parent[find(i)] = find(j)
        wide_pairs.append((i, j, off))
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values()), partner, wide_pairs


def _common_cap(G, a, b, tol=0.01):
    """The short W/0 segment (0.05-0.45 m, across the lines) on which an end of line a AND an end
    of line b both lie (= the masonry cap the glazing return starts from), or None."""
    ua = _unit(_sub(a[1], a[0]))
    for p, q, _ in G.wall_segs:
        v = _sub(q, p)
        Lc = _len(v)
        if not (0.05 <= Lc <= 0.45) or abs(_dot(_unit(v), ua)) > 0.1:
            continue
        cap = LineString([p, q])
        if any(cap.distance(Point(e)) < tol for e in a) and any(cap.distance(Point(e)) < tol for e in b):
            return (p, q)
    return None


def _ang(c, p):
    return math.degrees(math.atan2(p[1] - c[1], p[0] - c[0])) % 360.0


def _arc_iv(c, a):
    """CCW angular interval of a raw arc about centre c (LOCAL frame, mirror-safe: the direction
    is the one passing through the arc's mid point).  Returns (start_deg, span_deg, p_start, p_end)."""
    t0, t1, tm = _ang(c, a["p0"]), _ang(c, a["p1"]), _ang(c, a["pm"])
    span = (t1 - t0) % 360.0
    if (tm - t0) % 360.0 > span:
        return t1, (t0 - t1) % 360.0, a["p1"], a["p0"]
    return t0, span, a["p0"], a["p1"]


def _arc_union(ivs, tol=1e-6):
    """Union of angular intervals on a circle.  ivs = [(start, span, anchored_start, anchored_end)].
    An extreme end of a merged component that is DANGLING (touches no other element: e.g. F10 NW
    inner arc 44FF overshooting 25 deg past the frame return) is pulled back to the extreme
    ANCHORED end of the same side when the other radius has one.  Returns (total_sweep, comps,
    trimmed) where comps = [(start, end)] in degrees (start may be shifted by the cut angle)."""
    if not ivs:
        return 0.0, [], []
    ends = [(s + sp) % 360.0 for s, sp, *_ in ivs]

    def covered(t):
        return any(1e-6 < ((t - s) % 360.0) < sp - 1e-6 for s, sp, *_ in ivs)
    cut = next((e for e in ends if not covered((e + 1e-3) % 360.0)), 0.0)
    items = sorted((((s - cut) % 360.0), ((s - cut) % 360.0) + sp, aa, ab) for s, sp, aa, ab in ivs)
    comps = []
    for s, e, aa, ab in items:
        if comps and s <= comps[-1]["e"] + tol:
            comps[-1]["e"] = max(comps[-1]["e"], e)
            comps[-1]["m"].append((s, e, aa, ab))
        else:
            comps.append({"s": s, "e": e, "m": [(s, e, aa, ab)]})
    total, out, trimmed = 0.0, [], []
    for cp in comps:
        m = cp["m"]
        lo = min(m, key=lambda x: x[0])
        hi = max(m, key=lambda x: x[1])
        s, e = lo[0], hi[1]
        if not lo[2]:
            anch = [x[0] for x in m if x[2]]
            if anch:
                trimmed.append({"side": "start", "from_deg": _r((s + cut) % 360, 1), "to_deg": _r((min(anch) + cut) % 360, 1)})
                s = min(anch)
        if not hi[3]:
            anch = [x[1] for x in m if x[3]]
            if anch:
                trimmed.append({"side": "end", "from_deg": _r((e + cut) % 360, 1), "to_deg": _r((max(anch) + cut) % 360, 1)})
                e = max(anch)
        total += max(0.0, e - s)
        out.append(((s + cut) % 360.0, (e + cut) % 360.0))
    return total, out, trimmed


def _touch_tree(G):
    """STRtree of every line an arc end may legitimately stop on (W / 0, WIN, MASS, column /
    shaft outlines) + the other WIN arcs' end points."""
    geoms = [LineString([a, b]) for a, b, _ in G.wall_segs]
    geoms += [LineString([a, b]) for a, b in G.win_lines + G.win_dashed + G.mass_segs]
    for pg, _ in G.polys:
        if pg.geom_type == "Polygon":
            geoms.append(pg.exterior)
    return STRtree(geoms) if geoms else None


def _anchored(tree, p, arc, arcs, tol=0.01):
    P = Point(p)
    if tree is not None and len(tree.query(P.buffer(tol), predicate="intersects")):
        return True
    return any(b is not arc and min(_len(_sub(b["p0"], p)), _len(_sub(b["p1"], p))) < tol for b in arcs)


def read_windows(fl, G):
    wins = []
    used = getattr(G, "used_leaf_lines", set())
    raw = [s for s in G.win_lines
           if (round(s[0][0], 3), round(s[0][1], 3), round(s[1][0], 3), round(s[1][1], 3)) not in used]
    # (1) a frame drawn as two WIN lines 2-6 cm apart (F11 curtain walls) = ONE glazing line
    lines, meta = _merge_twins(raw)
    G.win_twins = [{"merged": _r(list(ln)), "twin_gap": _r(mt["twin_gap"]), "members": _r(mt["members"])}
                   for ln, mt in zip(lines, meta) if len(mt["members"]) > 1]
    # (2) pair parallel lines 0.05-0.35 apart; two LONE lines up to 0.40 apart that both start on
    #     the same short W cap = the glazing return across a 0.40 wall end (F11 NE corner)
    groups, _, wide = _pair_lines(lines, wide_ok=lambda i, j: _common_cap(G, lines[i], lines[j]) is not None)
    G.win_corner_returns = [{"lines": _r([list(lines[i]), list(lines[j])]), "spacing": _r(off),
                             "cap": _r(list(_common_cap(G, lines[i], lines[j])))} for i, j, off in wide]
    for g in groups:
        segs = [lines[i] for i in g]
        members = [s for i in g for s in meta[i]["members"]]
        twin_gap = max(meta[i]["twin_gap"] for i in g)
        L0 = max(segs, key=lambda s: _len(_sub(s[1], s[0])))
        u = _unit(_sub(L0[1], L0[0]))
        if u[0] < -1e-9 or (abs(u[0]) < 1e-9 and u[1] < 0):
            u = _mul(u, -1)
        n = _perp(u)
        o = L0[0]
        projs = [_dot(_sub(p, o), u) for s in segs for p in s]
        offs = [_dot(_sub(p, o), n) for s in members for p in s]
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
        paired = len(g) >= 2 or twin_gap > 0       # a twin line IS a two-line frame
        host = measure_host(G, c, u, width, max(depth, 0.05), extra=1.0,
                            face_band=max(depth / 2 - 0.005, 0.01))
        gap = host.get("gap")
        # no W jamb on either side: the glazing spans between concrete (column / core / shaft),
        # e.g. F11 stair hall west glazing x=2.14 between the column at y 9.54 and the concrete wall
        # at 12.28 (whose face is ALSO drawn on W, so the ray reports 'wall' there): both glazing
        # ends sit on a concrete outline, or both rays stop on concrete
        concrete_both = (host.get("bound_minus") in ("column", "shaft") and host.get("bound_plus") in ("column", "shaft")) \
            or all(any(pg.distance(Point(e)) < 0.03 for pg, _ in G.polys) for e in (e1, e2))
        door_adj = None
        for d in getattr(G, "_doors", []):
            if "jamb_a" not in d:
                continue
            for jm in (_mid(*d["jamb_a"]), _mid(*d["jamb_b"])):
                if min(_len(_sub(jm, e1)), _len(_sub(jm, e2))) < 0.15 and abs(_cross(u, d["_u"])) < 0.05:
                    door_adj = d["id"]
        note = None
        if width < 0.30:
            kind = "frame piece (jamb/mullion, not a window)"
        elif not paired:
            # a lone line is never promoted to a curtain wall by its length alone
            kind = UNRESOLVED_KIND
        elif width >= 4.0:
            kind = "glazed facade / curtain wall"
        elif door_adj:
            kind = "fixed glazing beside a door (same opening)"
        elif gap is not None and abs(gap - width) <= 0.10:
            if concrete_both:
                kind = "glazed facade / curtain wall"
                note = "glazing between concrete elements (no masonry jamb on either side)"
            else:
                kind = "window in masonry opening"
        elif gap is not None and gap < width + 1.5:
            kind = "window (gap != glazing, check)"
        else:
            kind = "glazed facade / curtain wall"
        dm = G.dim_match(e1, e2)
        rec = {"kind": kind, "shape": "straight", "center": _r(c), "axis_deg": _r(_axis_angle(u), 2),
               "width": _r(width), "span_all_lines": _r(u_hi - u_lo), "frame_depth": _r(depth),
               "n_lines": len(members),
               "ends": _r([e1, e2]), "host": host, "host_line": host_line(c, u, width),
               "dim_check": dm[0] if dm else None,
               "adjoins_door": door_adj,
               "rooms": [x for x in (G.room_on_side(c, n), G.room_on_side(c, _mul(n, -1))) if x],
               "_u": u, "_n": n, "_c": c}
        if twin_gap > 0:
            rec["twin_lines_merged"] = {"gap": _r(twin_gap),
                                        "note": "frame drawn as two WIN lines a few cm apart = ONE glazing line"}
        if any(i in (a, b) for a, b, _ in wide for i in g):
            rec["corner_return"] = "lone WIN lines 0.35-0.40 apart paired: both end on the same W cap"
        if note:
            rec["note"] = note
        wins.append(rec)
    # (3) duplicates: two glazing items on (almost) the same line covering the same span -> keep
    #     the one with more lines / the longer one (safety net after the twin merge)
    G.win_duplicates = []
    st = [w for w in wins if w["width"] >= 0.30]
    drop = set()
    for i, a in enumerate(st):
        for b in st[i + 1:]:
            if id(a) in drop or id(b) in drop or abs(_cross(a["_u"], b["_u"])) > 0.02:
                continue
            if abs(_cross(a["_u"], _sub(b["_c"], a["_c"]))) >= 0.10:
                continue
            sa = sorted(_dot(_sub(p, a["_c"]), a["_u"]) for p in a["ends"])
            sb = sorted(_dot(_sub(p, a["_c"]), a["_u"]) for p in b["ends"])
            ov = min(sa[1], sb[1]) - max(sa[0], sb[0])
            if ov <= 0.8 * min(a["width"], b["width"]):
                continue
            keep, lose = sorted((a, b), key=lambda w: (w["n_lines"], w["width"]), reverse=True)
            drop.add(id(lose))
            G.win_duplicates.append({"dropped": {k: lose[k] for k in ("kind", "center", "width", "n_lines")},
                                     "kept": {k: keep[k] for k in ("kind", "center", "width", "n_lines")}})
    wins = [w for w in wins if id(w) not in drop]
    # arcs: concentric pairs = curved glazing
    arcs = [a for a in G.raw_arcs if a["layer"] == "WIN" and not a["dashed"]]
    ttree = _touch_tree(G) if arcs else None
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
        c = a["center"]
        rin = [arcs[k] for k in grp if abs(arcs[k]["r"] - rs[0]) < 1e-3]
        rout = [arcs[k] for k in grp if abs(arcs[k]["r"] - rs[-1]) < 1e-3]
        # sweep = UNION of the angular intervals of BOTH radii (pieces may be split by a door gap,
        # and on F09 the inner line is cut where the planter walls meet it while the outer runs
        # through); a dangling extreme end is pulled back to the anchored end of the other radius
        ivs = []
        for a2 in [arcs[k] for k in grp]:
            s0, sp, ps, pe = _arc_iv(c, a2)
            ivs.append((s0, sp, _anchored(ttree, ps, a2, arcs), _anchored(ttree, pe, a2, arcs)))
        sweep, comps, trimmed = _arc_union(ivs)
        sw_in = _arc_union([(*_arc_iv(c, a2)[:2], True, True) for a2 in rin])[0]
        sw_out = _arc_union([(*_arc_iv(c, a2)[:2], True, True) for a2 in rout])[0]
        rm = (rs[0] + rs[-1]) / 2
        chord_pts = [p for a2 in rin for p in (a2["p0"], a2["p1"])]
        far = max(((p, q) for p in chord_pts for q in chord_pts), key=lambda pq: _len(_sub(pq[0], pq[1])))
        rec = {"kind": "curved glazing (corner)", "shape": "arc", "center": _r(c), "radius_mid": _r(rm),
               "sweep_deg": _r(sweep, 1), "width": _r(math.radians(sweep) * rm),
               "sweep_inner_deg": _r(sw_in, 1), "sweep_outer_deg": _r(sw_out, 1),
               "chord": _r(_len(_sub(far[0], far[1]))), "frame_depth": _r(rs[-1] - rs[0]),
               "n_lines": len(grp), "pieces": len(rin), "ends": _r(list(far)),
               "host": None, "dim_check": None,
               "rooms": [x for x in [G.room_on_side(c, _unit(_sub(c, rin[0]["pm"])), reach=-rm + 0.3)] if x],
               "_c": c}
        if trimmed:
            rec["sweep_trimmed"] = trimmed
        if abs(sw_in - sw_out) > 10.0:
            rec["flags"] = [f"inner / outer sweeps differ by {abs(sw_in - sw_out):.1f} deg "
                            f"(inner {sw_in:.1f}, outer {sw_out:.1f}, used {sweep:.1f}) - check the corner"]
        wins.append(rec)
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
                "host_line": host_line(c, w, g["width"]),
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


# ----------------------------------------------------------------------------- assemblies
def find_assemblies(fl, G, doors, windows, frame_pieces):
    """Door + fixed glazing + frame pieces drawn side by side in ONE masonry opening
    (F02 east terrace: 0.10 frame + door 1.00 + glazing 1.25 = masonry gap 2.35, and
    0.15 + door 1.00 + 0.20 = 1.35).  For masonry / plaster the deduction is the masonry
    gap of the whole group, not the sum of the products.  Returns a list of records."""
    items = []
    for d in doors:
        if "jamb_a" in d:
            items.append((d["id"], "door", _mid(*d["jamb_a"]), _mid(*d["jamb_b"])))
    for w in windows + frame_pieces:
        if w.get("shape") == "straight":
            items.append((w["id"], "frame" if w["kind"].startswith("frame") else "window",
                          tuple(w["ends"][0]), tuple(w["ends"][1])))
    n = len(items)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        _, _, a0, a1 = items[i]
        ua = _unit(_sub(a1, a0))
        for j in range(i + 1, n):
            _, _, b0, b1 = items[j]
            ub = _unit(_sub(b1, b0))
            if abs(_cross(ua, ub)) > 0.05 or abs(_cross(ua, _sub(b0, a0))) > 0.12:
                continue                      # not collinear (perpendicular mullion lines etc.)
            s = sorted((_dot(_sub(b0, a0), ua), _dot(_sub(b1, a0), ua)))
            La = _len(_sub(a1, a0))
            if s[0] <= La + 0.06 and s[1] >= -0.06:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    out = []
    for g in groups.values():
        kinds = {items[i][1] for i in g}
        if len(g) < 2 or not (kinds & {"door"}):
            continue
        _, _, p0, p1 = items[g[0]]
        u = _unit(_sub(p1, p0))
        if u[0] < -1e-9 or (abs(u[0]) < 1e-9 and u[1] < 0):
            u = _mul(u, -1)
        ss = [_dot(_sub(p, p0), u) for i in g for p in items[i][2:]]
        lo, hi = min(ss), max(ss)
        ofs = sum(_cross(u, _sub(p, p0)) for i in g for p in items[i][2:]) / (2 * len(g))
        n_ = _perp(u)
        e1 = _add(_add(p0, _mul(u, lo)), _mul(n_, ofs))
        e2 = _add(_add(p0, _mul(u, hi)), _mul(n_, ofs))
        c = _mid(e1, e2)
        host = measure_host(G, c, u, hi - lo, 0.12, extra=0.4)
        # short W jamb/cap lines of the door frame may sit INSIDE the opening (F02: a W cap
        # at y=15.835 between frame and leaf) -> prefer a face-line gap equal to the span
        fgs = [x for x in host.get("face_gaps") or [] if x is not None and abs(x - (hi - lo)) <= 0.05]
        if fgs:
            host["gap"] = min(fgs, key=lambda x: abs(x - (hi - lo)))
            host["gap_from"] = "face line"
        out.append({"kind": "glazed door assembly (door + fixed glazing / frame in ONE masonry opening)",
                    "members": [items[i][0] for i in sorted(g, key=lambda i: _dot(_sub(items[i][2], p0), u))],
                    "center": _r(c), "axis_deg": _r(_axis_angle(u), 2), "ends": _r([e1, e2]),
                    "span": _r(hi - lo), "masonry_gap": host.get("gap"), "host": host,
                    "host_line": host_line(c, u, hi - lo),
                    "width": host.get("gap") if host.get("gap") is not None else _r(hi - lo)})
    out.sort(key=lambda o: (-round(o["center"][1] / 0.5), o["center"][0]))
    for k, o in enumerate(out, 1):
        o["id"] = f"{fl.label}-A{k:02d}"
    return out


# ----------------------------------------------------------------------------- floor analysis
def _anchor_points(G, doors):
    """Every vertex a dimension may legitimately snap to (W / WIN ends, column corners,
    arc ends and centres, door jambs)."""
    pts = [p for a, b, _ in G.wall_segs for p in (a, b)]
    pts += [p for a, b in G.win_lines + G.win_dashed for p in (a, b)]
    for pg, _ in G.polys:
        if pg.geom_type == "Polygon":
            pts += list(pg.exterior.coords)
    for a in G.raw_arcs:
        pts += [a["p0"], a["p1"], a["center"]]
    for d in doors:
        if "jamb_a" in d:
            pts += [tuple(p) for p in d["jamb_a"]] + [tuple(p) for p in d["jamb_b"]]
    return pts


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
    for k, w in enumerate(frame_pieces, 1):          # own id series (no clash with W..)
        w["id"] = f"{fl.label}-F{k:02d}"
    openings, candidates, n_expl = find_openings(fl, G, doors, windows)
    assemblies = find_assemblies(fl, G, doors, windows, frame_pieces)
    owner = {m: a["id"] for a in assemblies for m in a["members"]}
    for it in doors + windows + frame_pieces:
        if it.get("id") in owner:
            it["in_assembly"] = owner[it["id"]]
    checks = {
        "door_gap_vs_block": [
            {"id": d["id"], "block_w": d["width"], "gap": d["host"]["gap"],
             "diff": _r(d["host"]["gap"] - d["width"]) if d["host"]["gap"] is not None else None,
             "face_gaps": d["host"].get("face_gaps")}
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
        "windows_dim_projection": [
            {"id": w["id"], "width": w["width"], "dim": w["dim_check"]["value"]}
            for w in windows if w.get("dim_check") and w["dim_check"].get("note")],
        "dims_along_solid_wall": G.dims_along_solid_wall(_anchor_points(G, doors)),
        "other_inserts": sorted({f'{e.dxf.layer}:{e.dxf.name}' for e in G.other_inserts}),
        "wall_gaps_explained": n_expl,
        # door blocks inserted on a layer other than W / PR (read anyway: the layer means nothing)
        "doors_on_other_layers": [{"id": d["id"], "block": d.get("block"), "layer": d.get("layer"),
                                   "handle": d.get("handle")}
                                  for d in doors if d.get("block") and d.get("layer") not in ("W", "PR")],
        # WIN entities skipped because they lie inside a stair zone (eye / break line on WIN, F11)
        "win_in_stair_skipped": G.win_in_stair,
        # WIN frames drawn as two lines 2-6 cm apart, merged into one glazing line (F11)
        "win_twin_lines_merged": getattr(G, "win_twins", []),
        # lone WIN lines 0.35-0.40 apart paired because both start on the same W cap
        "win_corner_return_pairs": getattr(G, "win_corner_returns", []),
        "glazing_duplicates_dropped": getattr(G, "win_duplicates", []),
        "curved_glazing_sweep_mismatch": [
            {"id": w["id"], "sweep_used": w["sweep_deg"], "inner": w.get("sweep_inner_deg"),
             "outer": w.get("sweep_outer_deg"), "trimmed": w.get("sweep_trimmed")}
            for w in windows if w.get("flags")],
        "unresolved_glazing": [w["id"] for w in windows if w["kind"] == UNRESOLVED_KIND],
    }
    # door widths three ways: block (nominal, jamb-to-jamb), clear gap between the W lines
    # (narrowest of both faces), and the smaller FACE-LINE gap (= snapping to W line ends)
    bw = [d["width"] for d in doors if "width" in d]
    # block-less glazed doors (in an assembly or in curved glazing) keep their leaf width
    plain = [d for d in doors if "width" in d and d.get("block")]
    hg = [d["host"]["gap"] if d["host"]["gap"] is not None else d["width"] for d in plain]
    hg += [d["width"] for d in doors if "width" in d and not d.get("block")]
    fg = [d["width"] for d in doors if "width" in d and not d.get("block")]
    for d in plain:
        v = [x for x in d["host"].get("face_gaps", []) if x is not None and abs(x - d["width"]) < 0.3]
        fg.append(min(v) if v else d["width"])
    checks["door_width_totals"] = {"block": _r(sum(bw)), "clear_gap_W": _r(sum(hg)),
                                   "min_face_line_gap": _r(sum(fg))}
    res = {"floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
           "file": fl.file.name, "sheet_index": fl.sheet_index, "units": "m", "reader_version": READER_VERSION,
           "frame": "LOCAL (diwan_common.Floor.to_local: -10 deg, structural-column corner = 0,0)",
           "doors": doors, "windows": windows, "openings": openings, "opening_candidates": candidates,
           "window_frame_pieces": frame_pieces, "assemblies": assemblies,
           "summary": summarize(doors, windows, openings), "checks": checks}
    res["summary"]["assemblies"] = {"count": len(assemblies),
                                    "masonry_width": _r(sum(a["width"] for a in assemblies)),
                                    "members": {a["id"]: a["members"] for a in assemblies}}
    # what is actually cut out of MASONRY walls (no curtain wall / curved glazing / glazed
    # corner doors; assemblies as one masonry gap), by type and host wall thickness
    md = {}
    for r in deduction_table(res, door_h=None, window_h=None, opening_h=None):
        t = r["wall_t"]
        k = f'{r["type"]}|{t:.2f}' if t is not None else f'{r["type"]}|?'
        b = md.setdefault(k, {"count": 0, "width": 0.0})
        b["count"] += 1
        b["width"] = _r(b["width"] + (r["width"] or 0.0))
    res["summary"]["masonry_deduction_widths"] = dict(sorted(md.items()))
    # unpaired single-line glazing is NOT deducted from masonry: kept apart for review
    unr = [w for w in windows if w["kind"] == UNRESOLVED_KIND]
    res["summary"]["unresolved_glazing"] = {
        "count": len(unr), "total_width": _r(sum(w["width"] for w in unr)), "ids": [w["id"] for w in unr],
        "note": "single WIN lines with no parallel partner: not deducted from masonry, not counted as "
                "full-height glazing - review on the drawing"}
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
                    opening_h=DEFAULT_HEIGHTS["opening"], include_curtain_wall=False,
                    include_unresolved=False):
    """Rows {id, type, kind, width, height, area, wall_t} for masonry/plaster deductions.
    height/area are None where no height was given.  Only windows that really cut a masonry
    wall are deducted (MASONRY_WINDOW_KINDS).  Curtain-wall glazing and curved corner glazing
    (no masonry there at all) are added only with include_curtain_wall=True; unpaired
    single-line glazing (unresolved: may be a drafting line, a duplicate or a curtain-wall
    return) only with include_unresolved=True, as type 'unresolved glazing' - see
    summary.unresolved_glazing.  Members of a glazed door ASSEMBLY are replaced by ONE row =
    the masonry gap of the assembly (height = door_h: assumption, to confirm)."""
    rows = []

    def row(it, typ, h, t):
        w = it.get("width")
        rows.append({"id": it["id"], "type": typ, "kind": it.get("kind"), "width": w, "height": h,
                     "area": _r(w * h) if (w is not None and h is not None) else None, "wall_t": t})
    for d in res["doors"]:
        if "no masonry" in (d.get("host_type") or "") and not include_curtain_wall:
            continue
        if "width" in d and not d.get("in_assembly"):
            h = d.get("host") or {}
            t = d.get("nominal_wall_t") or h.get("wall_t_minus") or h.get("wall_t_plus")
            row(d, "door", door_h, t)
    for w in res["windows"]:
        if w.get("in_assembly"):
            continue
        h = w.get("host") or {}
        t = h.get("wall_t_minus") or h.get("wall_t_plus")
        if w["kind"] in MASONRY_WINDOW_KINDS:
            row(w, "window", window_h, t)
        elif w["kind"] == UNRESOLVED_KIND:
            if include_unresolved:
                row(w, "unresolved glazing", window_h, t)
        elif include_curtain_wall:
            row(w, "window", window_h, t)
    for a in res.get("assemblies", []):
        h = a.get("host") or {}
        row(a, "assembly", door_h, h.get("wall_t_minus") or h.get("wall_t_plus"))
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
    # glazed door assemblies (one masonry opening holding door + glazing): dashed outline
    for a in res.get("assemblies", []):
        if not inview(a["center"], 2):
            continue
        e1, e2 = a["ends"]
        u = _unit(_sub(e2, e1))
        n = _perp(u)
        h = 0.22
        q = [_add(e1, _mul(n, h)), _add(e2, _mul(n, h)), _add(e2, _mul(n, -h)), _add(e1, _mul(n, -h))]
        ax.add_patch(MPoly(q, closed=True, fill=False, ec="#0b5d1e", lw=1.2, ls="--"))
        tp = _add(a["center"], _mul(n, -0.45))
        ax.text(tp[0], tp[1], f'{a["id"].split("-")[1]} masonry {a["width"]:.2f}', fontsize=label_size, color="#0b5d1e",
                ha="center", va="center", rotation=0 if (a["axis_deg"] < 45 or a["axis_deg"] > 135) else 90,
                bbox=dict(fc="white", ec="none", alpha=0.65, pad=0.3), clip_on=True)
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
        md = ", ".join(f'{k} {v["count"]}={v["width"]:.2f}' for k, v in s["masonry_deduction_widths"].items())
        print(f'      masonry deductions (type|wall t: n=width m): {md}')
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
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (default: all, F02..F11)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-tiles", action="store_true", help="only the whole-floor PNG")
    a = ap.parse_args()
    run(a.floors or None, png=not a.no_png, tiles=not a.no_tiles)


if __name__ == "__main__":
    main()
