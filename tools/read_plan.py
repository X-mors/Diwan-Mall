# -*- coding: utf-8 -*-
"""
read_plan — قراءة المسقط كاملًا: يشغّل القرّاء الأربعة معًا ويجمع نتائجهم في ملف واحد لكل دور
(Diwan plans, F02..F08).  This is a READING summary + a PRELIMINARY (تقديري) masonry /
plaster estimate; heights are NOT in the plans and are CLI parameters.

Readers (imported, no logic duplicated here):
    tools/openings.py   doors D<w>W<t> / windows (WIN) / door-less openings / assemblies
    tools/rooms.py      closed room polygons, names, areas, perimeters split by what bounds them
                        (fed with the SAME in-memory openings result -> no second openings run)
    tools/walls.py      wall records (centre-line, thickness family, gross/net, kind)
    tools/structure.py  columns / shear walls / core (+ ETABS block 'tr'), shafts, stairs, lifts,
                        grid, DASH, DIMs (fed with the in-memory openings + rooms results)
  The per-floor reader results are cached in output/plan/_cache (key = DXF + reader sources
  mtimes), so re-running read_plan only to change heights / the workbook is fast.

Integration (what read_plan adds on top of the readers):
  * cross_checks  doors / windows / door-less openings counted by openings.py vs bridged in the
                  walls; footprint area rooms vs structure; concrete face length rooms vs
                  structure; wall face length rooms vs a walls-based estimate.
  * conflicts     wall records lying on a structural element (model-space concrete => excluded
                  from masonry; ETABS 'tr'-only element => kept, listed, and an alternative
                  total "if tr is real" is given), door-less openings that are a 'tr' column,
                  needs_check counts of every reader.
  * preliminary   masonry m2 = gross length x H_m - sum(opening width x opening height),
                  H_m = storey - slab - beam drop;  plaster m2 (internal) = solid room faces
                  (rooms.py: wall + column/core + hatched fins + extensions) x H_p + strips above
                  doors / door-less openings + strips under windows (sills) ; ceilings = rooms
                  ceiling_area ; external (facade, plaster OR cladding?) = outer outline minus
                  full-height glazing x facade height - windows.  ALL heights are assumptions.

Outputs (gitignored):
    output/plan/<F>.json       merged reading of the floor (compact records of every reader +
                               cross_checks + conflicts + preliminary + params)
    output/plan/<F>_plan.png   ONE combined review drawing: rooms (category colour, name, net
                               area), walls by thickness, doors (leaf + swing), windows, openings,
                               concrete (ETABS 'tr'-only hatched red)
    output/plan/summary.xlsx   (all floors; a partial run writes summary_F0x_....xlsx)
                               Arabic workbook (RTL, values only): reading summary, walls by
                               thickness, doors & windows, rooms, room list, concrete,
                               preliminary masonry, preliminary plaster, conflicts, assumptions
    output/plan/summary.json   the same numbers as JSON

CLI (default = all floors F02..F08):
    python tools/read_plan.py
    python tools/read_plan.py 3 6                 # some floors -> summary_F03_F06.xlsx (summary.xlsx = all floors only)
    python tools/read_plan.py --floor 3
    python tools/read_plan.py --slab 0.22 --beam 0.0 --door-h 2.20 --window-sill 0.90
    python tools/read_plan.py --no-cache          # re-run every reader (walls/rooms keep their own
                                                  #   DXF geometry caches; add --deep to drop them too)
API:
    from read_plan import read_floor, merge_floor, Params
    b = read_floor(3)                 # raw bundle of the four readers (cached)
    plan = merge_floor(b, Params())   # merged dict (= output/plan/F03.json)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import OUT_DIR, REPO, STOREY_HEIGHT, all_floors, get_floor  # noqa: E402

PLAN_OUT = OUT_DIR / "plan"
CACHE_DIR = PLAN_OUT / "_cache"
TOOLS = Path(__file__).resolve().parent
READER_SOURCES = ["diwan_common.py", "sosa_decode.py", "walls.py", "openings.py", "rooms.py", "structure.py"]
BUNDLE_VER = "b2"   # b2: + try_outline (F09-F11 facade line)

KIND_AR = {"exterior": "خارجي (واجهة)", "interior": "داخلي", "shaft": "حول شفت", "stair_lift": "سلم / مصعد"}
FAMILY_ORDER = ["0.10", "0.12", "0.15", "0.20", "0.25", "0.30", "0.40", "0.50", "0.60", "other"]
FAMILY_AR = {f: f"سمك {f}" for f in FAMILY_ORDER}
FAMILY_AR["other"] = "سمك غير قياسي"
ELEM_KIND_AR = {"column": "أعمدة", "shear_wall": "حوائط قص", "core": "كور المصاعد",
                "round_column": "أعمدة دائرية (أقواس W)", "column_xbox": "مربعات COL بعلامة X"}
DOOR_TYPE_AR = {"D10W12": "باب 1.00 في حائط 0.12 (D10W12)", "D80W12": "باب 0.80 في حائط 0.12 (D80W12)",
                "D90W12": "باب 0.90 في حائط 0.12 (D90W12)", "D90W25": "باب 0.90 في حائط 0.25 — السلم (D90W25)",
                "raw (no block)": "باب زجاجي بلا بلوك (F02)"}
DED_TYPE_AR = {"door": "أبواب", "window": "شبابيك", "assembly": "مجموعات باب+زجاج", "opening": "فتحات بلا باب"}
SOLID_KINDS = ("wall", "column", "solid_try", "extension", "mass", "shaft")


# ============================================================================
# parameters (heights are NOT in the plans)
# ============================================================================
@dataclass
class Params:
    storey: float = STOREY_HEIGHT     # floor-to-floor (level marks +8.90 ... +28.10)
    slab: float = 0.20                # slab thickness: UNKNOWN (0.20 -> H_m 3.00 = the owner's legacy height)
    beam: float = 0.0                 # beam drop below the slab over the walls: UNKNOWN (no beams in these plans)
    door_h: float = 2.30              # door height: the owner's legacy convention (not in the plans)
    window_sill: float = 1.00         # window sill: the owner's legacy 5th-floor takeoff (19 sills x 1.00)
    window_h: float | None = None     # None -> window up to the masonry top (H_m - sill)
    opening_h: float | None = None    # door-less openings (lift landings, 0.80 gap): None -> door_h
    plaster_h: float | None = None    # internal plaster height: None -> storey - slab (to the soffit)
    facade_h: float | None = None     # external face height per storey: None -> storey
    tr_concrete: bool = True          # ETABS 'tr'-block elements are real concrete (owner, 2026-11-26: all 7 are in the structural)
    str_concrete: bool = True         # deduct wall lengths running inside STRUCTURAL columns/cores missing or thinner in the
                                      # architectural plan (owner, 2026-11-26: the structural is what was built)
    heights: str = "structural"       # masonry height per wall: "structural" = 3.20 - concrete depth above it
                                      # (slab 20/35 zone or beam, tools/masonry_heights.py); "flat" = H_m everywhere

    @property
    def H_m(self):                    # masonry height
        return round(self.storey - self.slab - self.beam, 4)

    @property
    def win_h(self):
        return self.window_h if self.window_h is not None else max(0.0, self.H_m - self.window_sill)

    @property
    def open_h(self):
        return self.opening_h if self.opening_h is not None else self.door_h

    @property
    def H_p(self):
        return self.plaster_h if self.plaster_h is not None else round(self.storey - self.slab, 4)

    @property
    def H_f(self):
        return self.facade_h if self.facade_h is not None else self.storey

    def as_dict(self):
        d = asdict(self)
        d.update({"masonry_height": self.H_m, "window_height_used": self.win_h,
                  "opening_height_used": self.open_h, "plaster_height_used": self.H_p,
                  "facade_height_used": self.H_f})
        return d


# ============================================================================
# 1. run the four readers on one floor (cached bundle)
# ============================================================================
def _bundle_key(fl):
    h = hashlib.sha1()
    h.update(BUNDLE_VER.encode())
    h.update(f"{fl.file.name}:{fl.file.stat().st_mtime_ns}:{fl.sheet_index}".encode())
    for s in READER_SOURCES:
        p = TOOLS / s
        if p.exists():
            h.update(f"{s}:{p.stat().st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def _np_default(o):
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
    except Exception:
        pass
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(type(o))


def _plain(o):
    """JSON round trip (numpy scalars -> float, tuples -> lists, '_private' keys kept out)."""
    return json.loads(json.dumps(o, ensure_ascii=False, default=_np_default))


def run_readers(fl, deep=False, log=print):
    """Run openings -> rooms -> walls -> structure on one floor.  Returns the raw bundle."""
    import openings as opm
    import rooms as rmm
    import structure as stm
    import walls as wlm
    t0 = time.time()
    tm = {}
    op_res = opm.analyze_floor(fl)
    op = opm._clean({k: v for k, v in op_res.items() if not k.startswith("_")})
    tm["openings"] = round(time.time() - t0, 1)

    t1 = time.time()
    orig = rmm.load_openings
    rmm.load_openings = lambda _fl, refresh=False: (op, "openings.analyze_floor() (read_plan, in memory)")
    try:
        rr = rmm.analyze_floor(fl, use_cache=not deep)
    finally:
        rmm.load_openings = orig
    rooms_json = rmm.to_json(rr)
    rooms_polys = {r["id"]: r["_poly"] for r in rr["rooms"] if r.get("_poly") is not None}
    tm["rooms"] = round(time.time() - t1, 1)

    t2 = time.time()
    wres = wlm.read_walls(fl, height=3.0, use_cache=not deep)
    tm["walls"] = round(time.time() - t2, 1)

    t3 = time.time()
    st = stm.analyze_floor(fl, openings_res=op, rooms_res=rr)
    st_json = stm._jsonable(st)
    tm["structure"] = round(time.time() - t3, 1)
    log(f"  {fl.label}: readers ran in {time.time() - t0:.0f} s {tm}")
    return {"floor": fl.label, "floor_no": fl.floor_no, "name_ar": fl.name_ar, "level": fl.level,
            "file": fl.file.name, "sheet_index": fl.sheet_index,
            "walls": _plain(wres), "openings": _plain(op), "rooms": _plain(rooms_json),
            "structure": _plain(st_json), "rooms_polys": rooms_polys, "footprint": rr.get("_footprint"),
            "try_outline": try_outline_area(fl), "timing_s": tm}


def try_outline_area(fl):
    """F09-F11: area / perimeter of the FACADE line drawn as a closed polyline on layer `try`
    (is_try_outline; the plot boundary - >1500 m2 - is skipped).  Bulge-aware (arcs of the curved
    corners flattened to 1 cm via ezdxf.path).  None on floors without one (F02-F08)."""
    from diwan_common import floor_entities, is_try_outline
    from ezdxf import path as ezpath
    from shapely.geometry import Polygon
    out = []
    for e in floor_entities(fl, layers="try", types="LWPOLYLINE"):
        pts = [fl.to_local(p[0], p[1]) for p in e.get_points("xy")]
        if not is_try_outline(pts):
            continue
        try:
            fpts = [fl.to_local(v.x, v.y) for v in ezpath.make_path(e).flattening(0.01)]
            P = Polygon(fpts).buffer(0)
        except Exception:
            continue
        if P.is_empty or P.area > 1500:
            continue
        out.append({"handle": e.dxf.handle, "area_m2": round(P.area, 3), "perimeter_m": round(P.exterior.length, 3)
                    if P.geom_type == "Polygon" else round(P.length, 3)})
    return out or None


def read_floor(floor, use_cache=True, deep=False, log=print):
    fl = get_floor(floor) if isinstance(floor, int) else floor
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / f"{fl.label}_{_bundle_key(fl)}.pkl"
    if use_cache and p.exists():
        with open(p, "rb") as f:
            log(f"  {fl.label}: reader results from cache {p.name}")
            return pickle.load(f)
    b = run_readers(fl, deep=deep, log=log)
    for old in CACHE_DIR.glob(f"{fl.label}_*.pkl"):
        try:
            old.unlink()
        except Exception:
            pass
    with open(p, "wb") as f:
        pickle.dump(b, f)
    return b


# ============================================================================
# 2. merge: compact records, cross-checks, conflicts, preliminary quantities
# ============================================================================
def _r(v, n=3):
    return None if v is None else round(float(v), n)


def _wall_rect(w):
    from walls import Dir
    D = Dir(w["angle"])
    d0, d1 = w["_band"]
    s, e = w["_t"]
    return D, D.rect(s, e, d0, d1)


def wall_structure_overlaps(walls, elements, min_frac=0.05):
    """Wall records whose body lies on a structural element (area overlap)."""
    from shapely.geometry import Polygon
    els = []
    for el in elements:
        try:
            P = Polygon(el["outline"]).buffer(0)
        except Exception:
            continue
        if P.area > 1e-4:
            els.append((el, P))
    out = []
    for w in walls:
        _, R = _wall_rect(w)
        if R.area < 1e-6:
            continue
        for el, P in els:
            a = R.intersection(P).area
            if a > 0.005 and a / R.area >= min_frac:
                out.append({"wall": w["id"], "family": w["family"], "kind": w["kind"],
                            "length_gross": w["length_gross"], "length_net": w["length_net"],
                            "element": el["id"], "element_kind": el["kind"], "element_size": el.get("size_txt"),
                            "tr_only": bool(el.get("only_in_tr_block")),
                            "model_space": bool(el.get("in_model_space", not el.get("only_in_tr_block"))),
                            "overlap_m2": _r(a, 3), "overlap_frac": _r(a / R.area, 2)})
    return out


def _wall_opening_heights(op_type, P):
    return {"door": P.door_h, "window": P.win_h, "opening": P.open_h}.get(op_type, P.door_h)


def masonry_estimate(walls, P, exclude_ids=(), HW=None, conc_len=None):
    """PRELIMINARY masonry per family x kind: gross x H - sum(width x height) of the openings
    bridged in each wall record (widths = masonry gaps measured by walls.py).
    HW (masonry_heights.wall_heights) -> H per wall = 3.20 - concrete depth above its centre line
    (length-weighted), openings capped at / windows up to the height at the opening; else H = P.H_m."""
    import masonry_heights as mh
    agg = defaultdict(lambda: defaultdict(float))
    for w in walls:
        if w["id"] in exclude_ids:
            continue
        g = w["length_gross"]
        H = HW[w["id"]]["H_mean"] if HW and w["id"] in HW else P.H_m
        ded = defaultdict(float)
        for o in w["openings"]:
            Ho = (mh.height_at(HW, *o["at"]) if HW and o.get("at") else None) or H
            if o["type"] == "window" and P.window_h is None:
                h = max(0.0, Ho - P.window_sill)
            else:
                h = min(_wall_opening_heights(o["type"], P), Ho)
            ded[o["type"]] += o["width"] * h
        lc = min((conc_len or {}).get(w["id"], 0.0), g)
        ded["concrete"] = lc * H
        gross_a = g * H
        net_a = gross_a - sum(ded.values())
        for key in (f"{w['family']}|{w['kind']}", f"{w['family']}|ALL", f"ALL|{w['kind']}", "ALL|ALL"):
            a = agg[key]
            a["n"] += 1
            a["length_gross"] += g
            a["length_net"] += w["length_net"]
            a["area_gross"] += gross_a
            a["ded_door"] += ded["door"]
            a["ded_window"] += ded["window"]
            a["ded_opening"] += ded["opening"]
            a["ded_concrete"] += ded["concrete"]
            a["length_in_str_concrete"] += lc
            a["area_net"] += net_a
    return {k: {kk: (int(vv) if kk == "n" else _r(vv, 2)) for kk, vv in v.items()} for k, v in sorted(agg.items())}


def concrete_faces_on_rooms(b, tr_only=False, band=0.03):
    """Length of the ceiling-room boundaries lying on concrete outlines (geometric: within
    `band` of a model-space element outline, or of a 'tr'-only one with tr_only=True).
    rooms.py labels a face 'column' only where no W line is drawn on it, so its own
    boundary['column'] under-counts the concrete (W lines are drawn on 45-96 % of the outlines)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from rooms import INDOOR_CEILING
    zones = []
    for e in b["structure"]["elements"]:
        if e["kind"] == "column_xbox" or not e.get("outline") or bool(e.get("only_in_tr_block")) != tr_only:
            continue
        try:
            P = Polygon(e["outline"]).buffer(0)
        except Exception:
            continue
        zones.append(P.buffer(band, join_style=2).difference(P.buffer(-band, join_style=2)))
    if not zones:
        return 0.0
    Z = unary_union(zones)
    L = 0.0
    for r in b["rooms"]["rooms"]:
        pg = b["rooms_polys"].get(r["id"])
        if pg is None or not (r.get("indoor") and r["category"] in INDOOR_CEILING):
            continue
        L += pg.boundary.intersection(Z).length
    return L


GLAZING_FOOTPRINT_TOL = 0.30   # m: full-height glazing counts on the facade only this close to the rooms footprint edge


def plaster_estimate(rooms_j, op, st, walls_tot, P, conc_geom=None, footprint=None):
    """PRELIMINARY internal plaster (room faces) + ceilings + external facade estimate."""
    from rooms import INDOOR_CEILING
    Hp = P.H_p
    ind = [r for r in rooms_j["rooms"] if r.get("indoor") and r["category"] in INDOOR_CEILING]
    bd = defaultdict(float)
    for r in ind:
        for k, v in r["boundary"].items():
            bd[k] += v
    solid = sum(bd.get(k, 0.0) for k in SOLID_KINDS)
    col = conc_geom if conc_geom is not None else bd.get("column", 0.0)
    door_len = bd.get("door", 0.0)                 # both sides (each room on either side)
    open_len = bd.get("opening", 0.0)
    win_masonry = [w for w in op["windows"] if w["kind"] == "window in masonry opening" and not w.get("in_assembly")]
    win_w = sum(w["width"] for w in win_masonry)
    asm_w = sum(a["width"] for a in op.get("assemblies", []))
    win_top = P.window_sill + P.win_h
    strip_door = door_len * max(0.0, Hp - P.door_h)
    strip_open = open_len * max(0.0, Hp - P.open_h)
    strip_win = win_w * (min(P.window_sill, Hp) + max(0.0, Hp - win_top))
    strip_asm = asm_w * max(0.0, Hp - P.door_h)
    faces = solid * Hp
    walls_int = faces + strip_door + strip_open + strip_win + strip_asm
    ceil = rooms_j["totals"]["ceiling_area"]
    # external: outer outline of the facade minus full-height glazing (curtain wall, curved corners)
    # only glazing ON the building outline (F11 drew a stair eye on WIN; any glazing line far from
    # the rooms footprint edge is not facade) - the distance is taken from the item's end chord
    glz = [w for w in op["windows"] if ("curtain" in w["kind"] or w["shape"] == "arc")]
    off_fp = []
    if footprint is not None and not footprint.is_empty:
        from shapely.geometry import LineString, Point
        edge = footprint.boundary
        keep = []
        for w in glz:
            try:
                if w["shape"] == "arc":     # curved corner: nearest point of the arc itself (both senses)
                    cx, cy = w["center"]
                    (ax, ay), (bx, by) = w["ends"]
                    rad = math.hypot(ax - cx, ay - cy)
                    a0, a1 = math.atan2(ay - cy, ax - cx), math.atan2(by - cy, bx - cx)
                    sw = (a1 - a0) % (2 * math.pi)
                    d = min(Point(cx + rad * math.cos(a0 + sg * t / 24), cy + rad * math.sin(a0 + sg * t / 24)).distance(edge)
                            for sg, span in ((1, sw), (-1, 2 * math.pi - sw)) for t in [i * span for i in range(25)])
                else:
                    d = LineString(w["ends"]).distance(edge)
            except Exception:
                d = 0.0
            (keep if d <= GLAZING_FOOTPRINT_TOL else off_fp).append(w)
        glz = keep
    full_glz = sum(w["width"] for w in glz)
    outline = rooms_j["totals"]["gross_outline_perimeter"]
    ext_open = win_w * P.win_h + asm_w * P.door_h
    ext_area = max(0.0, outline - full_glz) * P.H_f - ext_open
    S = st["summary"]
    tr_extra = (S.get("plaster_perimeter_all") or 0.0) - (S.get("plaster_perimeter_model_space_only") or 0.0)
    lift = [r for r in rooms_j["rooms"] if r["category"] == "lift"]
    shafts = [r for r in rooms_j["rooms"] if r["category"] == "shaft"]
    oa = rooms_j["totals"].get("boundary_by_kind_open_air", {}) or {}
    # walls-based cross-check of the face length: both faces of interior / stair walls, one face of
    # facade and shaft walls (net solid length; ends and junctions make it differ from the rooms)
    def tnet(k):
        return (walls_tot.get(f"ALL|{k}") or {}).get("length_net", 0.0)
    walls_based = 2 * (tnet("interior") + tnet("stair_lift")) + tnet("exterior") + tnet("shaft")
    return {
        "H_p": Hp,
        "faces_by_kind_m": {k: _r(v, 2) for k, v in sorted(bd.items())},
        "solid_faces_m": _r(solid, 2), "of_which_concrete_m": _r(col, 2),
        "wall_faces_m2": _r(faces, 2),
        "strip_above_doors_m2": _r(strip_door, 2), "strip_above_openings_m2": _r(strip_open, 2),
        "strip_windows_m2": _r(strip_win, 2), "strip_above_assemblies_m2": _r(strip_asm, 2),
        "internal_walls_m2": _r(walls_int, 2),
        "ceilings_m2": _r(ceil, 2),
        "internal_total_m2": _r(walls_int + ceil, 2),
        "masonry_windows_width_m": _r(win_w, 3), "assemblies_width_m": _r(asm_w, 3),
        "external": {"outline_m": _r(outline, 2), "full_height_glazing_m": _r(full_glz, 2),
                     "glazing_off_footprint": [{"id": w.get("id"), "kind": w["kind"], "width": w["width"]} for w in off_fp],
                     "facade_windows_m": _r(win_w + asm_w, 2), "H_f": P.H_f,
                     "area_m2": _r(ext_area, 2)},
        "not_included": {
            "lift_shaft_faces_m": _r(sum(r["perimeter"] for r in lift), 2),
            "structure_lift_shaft_faces_m": S.get("lift_shaft_perimeter"),
            "shaft_faces_m": _r(sum(r["perimeter"] for r in shafts), 2),
            "tr_block_concrete_faces_m": _r(tr_extra, 2),
            "tr_block_concrete_faces_m2": _r(tr_extra * Hp, 2),
            "open_air_solid_faces_m": _r(sum(v for k, v in oa.items() if k in SOLID_KINDS + ("slab_edge",)), 2),
            "corridor_lobby_virtual_line_m": _r(bd.get("virtual", 0.0), 2),
        },
        "cross_check_face_length": {
            "rooms_non_concrete_solid_m": _r(solid - col, 2),
            "walls_based_2xinterior_plus_exterior_m": _r(walls_based, 2),
            "rooms_concrete_faces_m": _r(col, 2),
            "rooms_boundary_labelled_column_m": _r(bd.get("column", 0.0), 2),
            "structure_interior_free_faces_model_space_m": S.get("plaster_perimeter_model_space_only"),
            "structure_interior_free_faces_all_m": S.get("plaster_perimeter_all"),
        },
    }


def _compact_wall(w):
    return {k: w[k] for k in ("id", "x1", "y1", "x2", "y2", "angle", "thickness", "family", "kind",
                              "length_gross", "length_net", "openings_width", "needs_check", "reason")} | {
        "openings": [{k: o[k] for k in ("type", "width", "at") if k in o} | ({"block": o["block"]} if "block" in o else {})
                     for o in w["openings"]]}


def _compact_door(d):
    keys = ("id", "block", "width", "nominal_wall_t", "center", "axis_deg", "kind", "jamb_a", "jamb_b",
            "leaf_geom", "opens_into", "other_side", "host_type", "in_assembly")
    return {k: d[k] for k in keys if k in d}


def _compact_window(w):
    keys = ("id", "kind", "shape", "width", "ends", "center", "radius_mid", "sweep_deg", "in_assembly", "rooms")
    out = {k: w[k] for k in keys if k in w}
    h = w.get("host") or {}
    out["wall_t"] = h.get("wall_t_minus") or h.get("wall_t_plus")
    return out


def _compact_room(r):
    keys = ("id", "name", "category", "category_ar", "open_air", "indoor", "area", "perimeter", "boundary",
            "doors", "windows", "openings", "centroid", "flags")
    return {k: r[k] for k in keys if k in r}


def _compact_element(e):
    keys = ("id", "kind", "size_txt", "bbox", "area", "perimeter", "exposed_interior", "exposed_exterior",
            "exposed_lift_shaft", "covered_by_walls", "only_in_tr_block", "hatch_only", "in_model_space",
            "grid_ref", "sources", "outline")
    return {k: e[k] for k in keys if k in e}


def merge_floor(b, P: Params):
    W, O, R, S = b["walls"], b["openings"], b["rooms"], b["structure"]
    walls = W["walls"]
    elements = S["elements"]
    ov = wall_structure_overlaps(walls, elements)
    on_concrete = sorted({o["wall"] for o in ov if o["model_space"] and o["overlap_frac"] >= 0.5})
    on_tr = sorted({o["wall"] for o in ov if o["tr_only"] and o["overlap_frac"] >= 0.3} - set(on_concrete))
    HW = None
    if P.heights == "structural" and b.get("floor_no"):
        import masonry_heights as mh
        HW = mh.wall_heights(b["floor_no"], walls, elements)
        if HW.get("_plan") is None:
            HW = None
    conc_len = {}
    if P.str_concrete and HW:
        import masonry_heights as mh
        conc_len = mh.concrete_overlap(HW, walls)
    excl = set(on_concrete) | (set(on_tr) if P.tr_concrete else set())
    mas = masonry_estimate(walls, P, exclude_ids=excl, HW=HW, conc_len=conc_len)
    mas_if_tr = masonry_estimate(walls, P, exclude_ids=set(on_concrete) | set(on_tr), HW=HW, conc_len=conc_len)
    mas_tr_masonry = masonry_estimate(walls, P, exclude_ids=on_concrete, HW=HW, conc_len=conc_len)
    pla = plaster_estimate(R, O, S, W["totals"], P, conc_geom=concrete_faces_on_rooms(b), footprint=b.get("footprint"))

    # ---- cross-checks between readers
    wop = Counter()
    wopw = defaultdict(float)
    for w in walls:
        for o in w["openings"]:
            wop[o["type"]] += 1
            wopw[o["type"]] += o["width"]
    doors = O["doors"]
    win_m = [w for w in O["windows"] if w["kind"] == "window in masonry opening"]
    # doors that cut masonry on their own (not in curved glazing, not a member of a door+glass assembly)
    doors_in_masonry = [d for d in doors if "no masonry" not in (d.get("host_type") or "") and not d.get("in_assembly")]
    asm = O.get("assemblies", [])
    win_own = [w for w in win_m if not w.get("in_assembly")]
    rooms_chk = R["checks"]
    fe = S.get("face_env", {})
    cc = {
        "doors": {"openings_py": len(doors), "openings_py_in_masonry": len(doors_in_masonry),
                  "walls_py_door_gaps": wop["door"], "walls_py_door_width": _r(wopw["door"], 3),
                  "openings_py_width": _r(sum(d.get("width", 0) for d in doors_in_masonry), 3),
                  "rooms_doors_not_two_sided": len(rooms_chk.get("doors_not_two_sided", []))},
        "windows_in_masonry": {"openings_py": len(win_own), "openings_py_width": _r(sum(w["width"] for w in win_own), 3),
                               "openings_py_assemblies": len(asm), "openings_py_assemblies_width": _r(sum(a["width"] for a in asm), 3),
                               "walls_py_window_gaps": wop["window"], "walls_py_window_width": _r(wopw["window"], 3),
                               "rooms_windows_unassigned": len(rooms_chk.get("windows_unassigned", []))},
        # every gap in masonry: openings.py (doors + windows + door+glass assemblies + door-less) vs the
        # gaps walls.py bridged (an assembly may be bridged as 'door' or 'window' there)
        "all_masonry_gaps": {"openings_py": len(doors_in_masonry) + len(win_own) + len(asm) + len(O["openings"]),
                             "openings_py_width": _r(sum(d.get("width", 0) for d in doors_in_masonry)
                                                     + sum(w["width"] for w in win_own) + sum(a["width"] for a in asm)
                                                     + sum(o["width"] for o in O["openings"]), 3),
                             "walls_py": sum(wop.values()), "walls_py_width": _r(sum(wopw.values()), 3)},
        "doorless_openings": {"openings_py": len(O["openings"]),
                              "openings_py_width": _r(sum(o["width"] for o in O["openings"]), 3),
                              "walls_py": wop["opening"], "walls_py_width": _r(wopw["opening"], 3)},
        "footprint_m2": {"rooms_gross_floor_area": R["totals"]["gross_floor_area"],
                         "structure_face_env": fe.get("footprint_area"),
                         **({"try_outline_area": sum(t["area_m2"] for t in b["try_outline"]),
                             "try_outline_perimeter": sum(t["perimeter_m"] for t in b["try_outline"])}
                            if b.get("try_outline") else {})},
        "concrete": {"structure_elements": len(elements),
                     "structure_model_space": sum(1 for e in elements if not e.get("only_in_tr_block")),
                     "structure_tr_only": sum(1 for e in elements if e.get("only_in_tr_block")),
                     "walls_py_concrete_polys": W["diagnostics"].get("concrete_polys"),
                     "walls_on_model_space_concrete": on_concrete},
        "face_length_m": pla["cross_check_face_length"],
    }
    # ---- conflicts / items for the engineer
    conf = []
    for o in ov:
        if o["model_space"] and o["overlap_frac"] >= 0.5:
            conf.append({"type": "wall_on_concrete", "item": o["wall"], "element": o["element"],
                         "detail": f"wall {o['wall']} ({o['family']}, {o['length_gross']} m) lies on {o['element']} "
                                   f"{o['element_size']} ({o['overlap_frac']:.0%}) -> excluded from masonry",
                         "detail_ar": f"الحائط {o['wall']} (سمك {o['family']}، {o['length_gross']} م) يقع على العنصر "
                                      f"الخرساني {o['element']} {o['element_size']} — مستبعد من المباني"})
    for o in ov:
        if o["tr_only"] and o["overlap_frac"] >= 0.3 and o["wall"] not in on_concrete:
            conf.append({"type": "wall_on_tr_element", "item": o["wall"], "element": o["element"],
                         "detail": f"wall {o['wall']} ({o['family']} {o['kind']}, gross {o['length_gross']} m) lies "
                                   f"{o['overlap_frac']:.0%} on ETABS 'tr' element {o['element']} {o['element_size']} - "
                                   f"confirmed concrete (owner 2026-11-26, present in the structural) -> excluded from masonry",
                         "detail_ar": f"الحائط {o['wall']} (سمك {o['family']}، {KIND_AR.get(o['kind'], o['kind'])}، "
                                      f"{o['length_gross']} م) يقع بنسبة {o['overlap_frac']:.0%} على عنصر بلوك tr "
                                      f"{o['element']} {o['element_size']} — خرسانة مؤكدة (موجودة في الإنشائي) — مستبعد من المباني"})
    for x in S.get("openings_on_structure", []):
        conf.append({"type": "opening_is_tr_column", "item": x["opening"], "element": x["element"],
                     "detail": f"door-less opening {x['opening']} ({x['width']} m) = ETABS 'tr' column {x['element']} "
                               f"{x['element_size']}",
                     "detail_ar": f"الفتحة بلا باب {x['opening']} ({x['width']} م) هي بالضبط عمود بلوك tr "
                                  f"{x['element']} {x['element_size']} — فتحة أم عمود؟"})
    for e in elements:
        if e.get("only_in_tr_block") and (e.get("covered_by_walls") or 0) < 0.05 and e["kind"] != "column_xbox":
            conf.append({"type": "tr_element_free_standing", "item": e["id"], "element": e["id"],
                         "detail": f"ETABS 'tr' element {e['id']} {e['size_txt']} has no wall around it",
                         "detail_ar": f"عنصر بلوك tr {e['id']} {e['size_txt']} قائم بلا حوائط حوله (عمود حر؟)"})
    # readers disagree: doors / windows / door-less openings / all gaps (count, or width > 0.05 m)
    for key, lab, a_n, a_w, b_n, b_w in (
            ("doors", "الأبواب", cc["doors"]["openings_py_in_masonry"], cc["doors"]["openings_py_width"],
             cc["doors"]["walls_py_door_gaps"], cc["doors"]["walls_py_door_width"]),
            ("doorless_openings", "الفتحات بلا باب", cc["doorless_openings"]["openings_py"], cc["doorless_openings"]["openings_py_width"],
             cc["doorless_openings"]["walls_py"], cc["doorless_openings"]["walls_py_width"]),
            ("all_masonry_gaps", "كل الفتحات في المباني", cc["all_masonry_gaps"]["openings_py"], cc["all_masonry_gaps"]["openings_py_width"],
             cc["all_masonry_gaps"]["walls_py"], cc["all_masonry_gaps"]["walls_py_width"])):
        if key == "doors" and cc["all_masonry_gaps"]["openings_py"] == cc["all_masonry_gaps"]["walls_py"] and asm:
            continue      # door+glass assemblies are bridged as 'door' or 'window' in walls.py - the totals agree
        if a_n != b_n:
            conf.append({"type": "cross_check_mismatch", "item": key, "element": "-",
                         "detail": f"{key}: openings.py {a_n} ({a_w} m) vs walls.py {b_n} ({b_w} m)",
                         "detail_ar": f"{lab}: openings.py {a_n} ({a_w} م) مقابل walls.py {b_n} ({b_w} م) — راجع الفرق"})
    for key, lab in (("doors_not_two_sided", "أبواب لا تقع بين فراغين"), ("windows_unassigned", "شبابيك غير منسوبة لغرفة")):
        n = len(rooms_chk.get(key, []))
        if n:
            conf.append({"type": "cross_check_mismatch", "item": key, "element": "-",
                         "detail": f"rooms.py {key}: {n}", "detail_ar": f"rooms.py: {lab} = {n}"})
    pp = W["totals"].get("planter_parapet|ALL")
    if pp:
        conf.append({"type": "planter_parapet", "item": f"{pp['n']} دروة", "element": "-",
                     "detail": f"planter parapets (MASS line pairs) {pp['length_gross']} m - masonry or concrete? height? (not in masonry)",
                     "detail_ar": f"دروات أحواض الزرع (أزواج خطوط MASS) {pp['length_gross']} م"
                                  + (f" (منها 0.25: {W['totals']['planter_parapet|0.25']['length_gross']} م"
                                     f"، ورفيعة ≤ 0.12 تكرر زجاج الدور الأسفل: {W['totals']['planter_parapet|thin']['length_gross']} م)"
                                     if 'planter_parapet|thin' in W['totals'] and 'planter_parapet|0.25' in W['totals'] else "")
                                  + " — مباني أم خرسانة؟ الارتفاع؟ (غير محسوبة في المباني)"})
    for g in pla["external"].get("glazing_off_footprint", []):
        conf.append({"type": "glazing_off_footprint", "item": g["id"], "element": "-",
                     "detail": f"full-height glazing {g['id']} ({g['width']} m) is not on the facade line -> not deducted",
                     "detail_ar": f"زجاج كامل الارتفاع {g['id']} ({g['width']} م) ليس على خط الواجهة — لم يُخصم من الواجهات"})
    nc_w = [w for w in walls if w["needs_check"]]
    nc_r = rooms_chk.get("rooms_flagged", [])
    conf.append({"type": "needs_check_counts", "item": "-", "element": "-",
                 "detail": f"walls needs_check {len(nc_w)}, rooms flagged {len(nc_r)}",
                 "detail_ar": f"حوائط تحتاج مراجعة {len(nc_w)} (needs_check)، غرف عليها ملاحظات {len(nc_r)}"})

    by_cat = R["totals"]["by_category"]
    plan = {
        "floor": b["floor"], "floor_no": b["floor_no"], "name_ar": b["name_ar"], "level": b["level"],
        "source": {"file": b["file"], "sheet_index": b["sheet_index"]},
        "frame": "LOCAL (diwan_common): rotation -10 deg removed, origin = min corner of Etabs-col, metres",
        "readers": {"walls": "tools/walls.py", "openings": "tools/openings.py", "rooms": "tools/rooms.py",
                    "structure": "tools/structure.py"},
        "params": P.as_dict(),
        "walls": {"totals": W["totals"], "thickness_histogram_net": W["thickness_histogram_net"],
                  "openings_summary": W.get("openings_summary"),
                  "needs_check": len(nc_w),
                  "records": [_compact_wall(w) | ({"masonry_height": HW[w["id"]]["H_mean"],
                                                   "masonry_height_runs": HW[w["id"]]["runs"]} if HW else {})
                              for w in walls]},
        "openings": {"summary": O["summary"], "doors": [_compact_door(d) for d in doors],
                     "windows": [_compact_window(w) for w in O["windows"]],
                     "openings": [{k: o[k] for k in ("id", "kind", "width", "wall_t", "ends", "side_a", "side_b")
                                   if k in o} for o in O["openings"]],
                     "assemblies": [{k: a[k] for k in ("id", "kind", "members", "width", "ends") if k in a}
                                    for a in O.get("assemblies", [])]},
        "rooms": {"totals": R["totals"], "by_category": by_cat, "flagged": nc_r,
                  "rooms": [_compact_room(r) for r in R["rooms"]]},
        "structure": {"summary": {k: v for k, v in S["summary"].items() if k not in ("dims_by_class", "dash")},
                      "elements": [_compact_element(e) for e in elements],
                      "shafts": [{k: s[k] for k in ("id", "kind", "size_txt", "bbox", "area") if k in s}
                                 for s in S.get("shafts", [])],
                      "stairs": [{k: s[k] for k in ("id", "bbox") if k in s} for s in S.get("stairs", [])],
                      "lift_cars": S.get("lifts", {}).get("count")},
        "cross_checks": cc,
        "conflicts": conf,
        "wall_structure_overlaps": ov,
        "preliminary": {
            "status": "PRELIMINARY / تقديري — heights are assumptions, not read from the plans",
            "masonry": mas,
            "masonry_heights": ({**{k: v for k, v in HW["_meta"].items()},
                                 **__import__("masonry_heights").floor_summary(HW, [w for w in walls if w["id"] not in on_concrete]),
                                 "rule": "H = 3.20 - concrete depth above the wall (slab 0.20/0.35 zone or beam depth); "
                                         "structural sheet = ceiling of this floor"}
                                if HW else {"rule": f"flat H_m = {P.H_m}"}),
            "masonry_excluded_on_concrete": on_concrete,
            "masonry_if_tr_is_real": {"excluded_walls": on_tr, "ALL|ALL": mas_if_tr.get("ALL|ALL")},
            "masonry_if_tr_were_masonry": {"ALL|ALL": mas_tr_masonry.get("ALL|ALL")},
            "masonry_excluded_on_tr": on_tr if P.tr_concrete else [],
            "masonry_length_in_structural_concrete": {k: v for k, v in sorted(conc_len.items())},
            "plaster": pla,
        },
        "timing_s": b.get("timing_s"),
    }
    return plan


# ============================================================================
# 3. combined review drawing
# ============================================================================
def _poly_patch(poly, **kw):
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath
    polys = list(poly.geoms) if hasattr(poly, "geoms") else [poly]
    verts, codes = [], []
    for pg in polys:
        for ring in [pg.exterior] + list(pg.interiors):
            cs = list(ring.coords)
            verts += cs
            codes += [MPath.MOVETO] + [MPath.LINETO] * (len(cs) - 2) + [MPath.CLOSEPOLY]
    return PathPatch(MPath(verts, codes), **kw)


def _arc_points(c, p0, p1, pm=None, sweep=None, n=24):
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    r = math.dist(c, p0)
    d = (a1 - a0) % (2 * math.pi)                 # ccw sweep p0 -> p1
    if pm is not None:
        am = (math.atan2(pm[1] - c[1], pm[0] - c[0]) - a0) % (2 * math.pi)
        if am > d:                                 # the arc passes the other way
            d -= 2 * math.pi
    elif sweep is not None and abs(math.degrees(d) - sweep) > abs(math.degrees(2 * math.pi - d) - sweep):
        d -= 2 * math.pi
    return [(c[0] + r * math.cos(a0 + d * i / n), c[1] + r * math.sin(a0 + d * i / n)) for i in range(n + 1)]


def render_plan(b, plan, out_png, dpi=130, zoom=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.patches import Polygon as MPoly
    from rooms import CAT_COLORS
    from walls import FAM_COLORS, Dir
    plt.rcParams["font.family"] = "Tahoma"
    R = b["rooms"]
    fb = R["totals"]["footprint_bbox"]
    x0, y0, x1, y1 = zoom or (fb[0] - 1.6, fb[1] - 1.6, fb[2] + 1.6, fb[3] + 1.6)
    w_, h_ = x1 - x0, y1 - y0
    k = 0.62 if not zoom else 16.0 / max(w_, h_)          # inch per metre
    fig, ax = plt.subplots(figsize=(w_ * k + 1.5, h_ * k + 1.5))
    # rooms
    polys = b["rooms_polys"]
    cats_present = set()
    for r in R["rooms"]:
        pg = polys.get(r["id"])
        if pg is None or pg.is_empty:
            continue
        col = CAT_COLORS.get(r["category"], "#dddddd")
        cats_present.add(r["category"])
        ax.add_patch(_poly_patch(pg, fc=col, ec="#666666", lw=0.3, alpha=0.45 if not r.get("open_air") else 0.3,
                                 hatch="//" if r.get("open_air") else None, zorder=1))
    # concrete
    for e in b["structure"]["elements"]:
        if not e.get("outline"):
            continue
        pts = e["outline"]
        if e.get("only_in_tr_block"):
            ax.add_patch(MPoly(pts, closed=True, fc="none", ec="#b2182b", lw=0.9, ls="--", hatch="xxxx", zorder=6))
        elif e["kind"] == "column_xbox":
            ax.add_patch(MPoly(pts, closed=True, fc="#8c564b", ec="#3b2416", lw=0.5, alpha=0.6, zorder=6))
        else:
            ax.add_patch(MPoly(pts, closed=True, fc="#3a3a3a", ec="black", lw=0.5, alpha=0.85, zorder=6))
    # walls by thickness
    fams = set()
    for w in b["walls"]["walls"]:
        D = Dir(w["angle"])
        d0, d1 = w["_band"]
        s, e = w["_t"]
        col = FAM_COLORS.get(w["family"], "#000000")
        fams.add(w["family"])
        rect = D.rect(s, e, d0, d1)
        ax.add_patch(MPoly(list(rect.exterior.coords), closed=True, fc=col, ec=col, lw=0.2, alpha=0.9, zorder=4))
        for o in w["openings"]:
            t0, _ = D.td(*o["at"])
            pr = D.rect(t0 - o["width"] / 2, t0 + o["width"] / 2, d0, d1)
            ax.add_patch(MPoly(list(pr.exterior.coords), closed=True, fc="white", ec="none", zorder=5))
        if w["needs_check"]:
            ax.add_patch(MPoly(list(rect.buffer(0.05, join_style=2).exterior.coords), closed=True, fill=False,
                               ec="#ff00ff", lw=0.6, zorder=7))
    # F09-F11 planter parapets (MASS pairs, not masonry): olive with a magenta edge
    for pp in b["walls"].get("planter_parapets", []):
        rect = Dir(pp["angle"]).rect(pp["_t"][0], pp["_t"][1], *pp["_band"])
        ax.add_patch(MPoly(list(rect.exterior.coords), closed=True, fc="#556b2f", ec="#ff00ff", lw=0.4, alpha=0.9, zorder=4))
    O = b["openings"]
    # doors
    for d in O["doors"]:
        ja, jb = d.get("jamb_a"), d.get("jamb_b")
        if ja and jb:
            ax.add_patch(MPoly(ja + jb[::-1], closed=True, fc="#c7e9c0", ec="#1a9641", lw=0.6, zorder=8))
        lg = d.get("leaf_geom")
        if lg:
            c, p0, p1, pm = lg["c"], lg["p0"], lg["p1"], lg.get("pm")
            arc = _arc_points(c, p0, p1, pm=pm)
            ax.plot([p[0] for p in arc], [p[1] for p in arc], color="#1a9641", lw=0.6, zorder=8)
            ax.plot([c[0], p1[0]], [c[1], p1[1]], color="#1a9641", lw=0.9, zorder=8)
        if "width" in d and d.get("center"):
            ax.text(d["center"][0], d["center"][1], f"{d['width']:.2f}".rstrip("0").rstrip("."), fontsize=4.2,
                    color="#0b5d1e", ha="center", va="center", zorder=9)
    # windows
    for wv in O["windows"]:
        if wv["shape"] == "arc" and wv.get("center") and wv.get("ends"):
            pts = _arc_points(wv["center"], wv["ends"][0], wv["ends"][1], sweep=wv.get("sweep_deg"))
        elif wv.get("ends"):
            pts = wv["ends"]
        else:
            continue
        cw = "curtain" in wv["kind"] or wv["shape"] == "arc"
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color="#0077bb" if cw else "#17becf",
                lw=3.2 if cw else 2.6, solid_capstyle="butt", zorder=8)
        if not cw:
            m = wv.get("center") or pts[0]
            ax.text(m[0], m[1], f"{wv['width']:.2f}", fontsize=4.2, color="#003f5c", ha="center", va="center",
                    zorder=9, bbox=dict(boxstyle="round,pad=0.05", fc="white", ec="none", alpha=0.7))
    for o in O["openings"]:
        if o.get("ends"):
            (ax_, ay_), (bx_, by_) = o["ends"]
            ax.plot([ax_, bx_], [ay_, by_], color="#ff7f0e", lw=2.6, solid_capstyle="butt", zorder=8)
    # room labels
    for r in R["rooms"]:
        pg = polys.get(r["id"])
        if pg is None or pg.is_empty or r["category"] in ("shaft",) or r["area"] < 0.8:
            continue
        p = pg.representative_point()
        name = r["name"] or r.get("category_ar") or ""
        fs = 6.5 if r["area"] >= 8 else 5.0
        ax.text(p.x, p.y + 0.18, name, fontsize=fs, ha="center", va="center", color="#111", zorder=10, clip_on=True)
        ax.text(p.x, p.y - 0.22, f"{r['area']:.2f}", fontsize=fs - 0.8, ha="center", va="center", color="#333",
                zorder=10, clip_on=True)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.2, alpha=0.4)
    # legend
    hs = [Patch(fc=FAM_COLORS.get(f, "#000"), label=f"حائط {f}" if f != "other" else "حائط غير قياسي")
          for f in FAMILY_ORDER if f in fams]
    hs += [Patch(fc="#3a3a3a", label="خرسانة Etabs-col"),
           Patch(fc="none", ec="#b2182b", hatch="xxxx", ls="--", label="عنصر بلوك tr فقط (غير مؤكد)"),
           Patch(fc="#c7e9c0", ec="#1a9641", label="باب (العرض م)"),
           Line2D([0], [0], color="#17becf", lw=3, label="شباك في مباني (العرض م)"),
           Line2D([0], [0], color="#0077bb", lw=3, label="حائط ستائري / زجاج منحني"),
           Line2D([0], [0], color="#ff7f0e", lw=3, label="فتحة بلا باب"),
           Patch(fc="none", ec="#ff00ff", label="حائط needs_check")]
    if b["walls"].get("planter_parapets"):
        hs.append(Patch(fc="#556b2f", ec="#ff00ff", label="دروة أحواض زرع (خارج المباني)"))
    from rooms import CATEGORY_AR
    hs += [Patch(fc=CAT_COLORS[c], alpha=0.5, label=CATEGORY_AR.get(c, c)) for c in CAT_COLORS if c in cats_present]
    ax.legend(handles=hs, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7, framealpha=0.95, ncol=1)
    T = plan["walls"]["totals"].get("ALL|ALL", {})
    os_ = O["summary"]
    wm = os_["windows"]["by_kind"].get("window in masonry opening", {})
    t1 = f"المسقط الأفقي — {plan['name_ar']}"            # Arabic alone (no bidi mix with numbers)
    t2 = (f"{plan['floor']}  level {plan['level']:+.2f}  |  "
          f"walls n={T.get('n')} gross {T.get('length_gross', 0):.2f} m / net {T.get('length_net', 0):.2f} m  |  "
          f"doors {os_['doors']['count']} = {os_['doors']['total_width']:.2f} m  |  windows in masonry "
          f"{wm.get('count', 0)} = {wm.get('total_width', 0):.2f} m  |  rooms net {R['totals']['net_indoor_area']:.2f} m2"
          f"  |  concrete {plan['cross_checks']['concrete']['structure_model_space']} (+{plan['cross_checks']['concrete']['structure_tr_only']} tr)")
    ax.set_title(t1 + "\n" + t2 + "\n(local frame, m; room numbers = net area m2)", fontsize=9)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ============================================================================
# 4. Arabic workbook
# ============================================================================
def _xl_styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    thin = Side(style="thin", color="BBBBBB")
    return {
        "title": Font(name="Arial", size=13, bold=True, color="1F3864"),
        "head": Font(name="Arial", size=10, bold=True, color="FFFFFF"),
        "headfill": PatternFill("solid", fgColor="44546A"),
        "sec": Font(name="Arial", size=10, bold=True, color="1F3864"),
        "secfill": PatternFill("solid", fgColor="DDEBF7"),
        "tot": Font(name="Arial", size=10, bold=True),
        "totfill": PatternFill("solid", fgColor="FFF2CC"),
        "warnfill": PatternFill("solid", fgColor="FCE4D6"),
        "body": Font(name="Arial", size=10),
        "note": Font(name="Arial", size=9, italic=True, color="7F7F7F"),
        "border": Border(left=thin, right=thin, top=thin, bottom=thin),
        "center": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "right": Alignment(horizontal="right", vertical="center", wrap_text=True),
    }


class Sheet:
    """Small helper: RTL sheet, row cursor, typed rows."""

    def __init__(self, wb, title, widths=None, first=False):
        self.ws = wb.active if first else wb.create_sheet()
        self.ws.title = title
        self.ws.sheet_view.rightToLeft = True
        self.S = _xl_styles()
        self.row = 1
        for i, w in enumerate(widths or [], 1):
            from openpyxl.utils import get_column_letter
            self.ws.column_dimensions[get_column_letter(i)].width = w

    def _put(self, c, v, font=None, fill=None, fmt=None, align=None, border=True):
        cell = self.ws.cell(row=self.row, column=c, value=v)
        cell.font = font or self.S["body"]
        if fill:
            cell.fill = fill
        if border:
            cell.border = self.S["border"]
        cell.alignment = align or (self.S["center"] if c > 1 else self.S["right"])
        if fmt and isinstance(v, (int, float)) and not isinstance(v, bool):
            cell.number_format = fmt
        return cell

    def title(self, text, sub=None):
        self.ws.cell(row=self.row, column=1, value=text).font = self.S["title"]
        self.row += 1
        if sub:
            for line in ([sub] if isinstance(sub, str) else sub):
                c = self.ws.cell(row=self.row, column=1, value=line)
                c.font = self.S["note"]
                self.row += 1
        self.row += 1

    def header(self, cols):
        for i, v in enumerate(cols, 1):
            self._put(i, v, font=self.S["head"], fill=self.S["headfill"], align=self.S["center"])
        self.ws.row_dimensions[self.row].height = 32
        self.row += 1

    def section(self, text, ncols):
        for i in range(1, ncols + 1):
            self._put(i, text if i == 1 else None, font=self.S["sec"], fill=self.S["secfill"])
        self.row += 1

    def line(self, vals, fmt="0.00", total=False, warn=False):
        fill = self.S["totfill"] if total else (self.S["warnfill"] if warn else None)
        font = self.S["tot"] if total else self.S["body"]
        for i, v in enumerate(vals, 1):
            self._put(i, v, font=font, fill=fill, fmt=fmt)
        self.row += 1

    def blank(self, n=1):
        self.row += n

    def note(self, text):
        c = self.ws.cell(row=self.row, column=1, value=text)
        c.font = self.S["note"]
        self.row += 1


def _get(d, *path, default=None):
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return default
        d = d[p]
    return d


def _fl_header(plans):
    return [f"{p['floor']} ({p['level']:+.2f})" for p in plans]


def write_workbook(plans, P: Params, out_xlsx):
    from openpyxl import Workbook
    wb = Workbook()
    F = _fl_header(plans)
    nF = len(plans)
    sumcol = ["مجموع الأدوار"] if nF > 1 else []
    W_ITEM = 46

    def row_vals(fn, add_sum=True):
        vals = [fn(p) for p in plans]
        if nF > 1 and add_sum:
            nums = [v for v in vals if isinstance(v, (int, float))]
            vals.append(round(sum(nums), 3) if len(nums) == len(vals) else None)
        elif nF > 1:
            vals.append(None)
        return vals

    # ---------------- 1. reading summary
    sh = Sheet(wb, "ملخص القراءة", [W_ITEM] + [15] * (nF + 1), first=True)
    sh.title("قراءة مساقط الديوان — ملخص كل دور (قراءة آلية من اللوحات، ليست حصرًا نهائيًا)",
             ["الأطوال بالمتر (طول المحور للحوائط)، المساحات بالمتر المربع، الإطار المحلي للمبنى (الدوران 10° مُزال).",
              "المصدر: tools/walls.py + openings.py + rooms.py + structure.py عبر tools/read_plan.py"])
    sh.header(["البند"] + F + sumcol)
    nc = 1 + nF + len(sumcol)
    sh.section("الحوائط (مباني)", nc)
    sh.line(["عدد سجلات الحوائط"] + row_vals(lambda p: _get(p, "walls", "totals", "ALL|ALL", "n")), fmt="0")
    sh.line(["طول الحوائط الإجمالي (عبر الفتحات) م"] + row_vals(lambda p: _get(p, "walls", "totals", "ALL|ALL", "length_gross")))
    sh.line(["طول الحوائط الصافي (مصمت فقط) م"] + row_vals(lambda p: _get(p, "walls", "totals", "ALL|ALL", "length_net")), total=True)
    sh.line(["عروض الفتحات داخل الحوائط م"] + row_vals(lambda p: _get(p, "walls", "totals", "ALL|ALL", "openings_width")))
    for k in ("interior", "exterior", "shaft", "stair_lift"):
        sh.line([f"صافي حوائط {KIND_AR[k]} م"] + row_vals(lambda p, k=k: _get(p, "walls", "totals", f"ALL|{k}", "length_net", default=0.0)))
    for f in ("0.12", "0.25"):
        sh.line([f"صافي حوائط {FAMILY_AR[f]} م"] + row_vals(lambda p, f=f: _get(p, "walls", "totals", f"{f}|ALL", "length_net", default=0.0)))
    sh.line(["صافي حوائط بسماكات أخرى م"] + row_vals(lambda p: round(sum(v["length_net"] for k, v in p["walls"]["totals"].items()
                                                                       if k.endswith("|ALL") and not k.startswith(("ALL", "0.12", "0.25", "planter_parapet"))), 2)))
    sh.line(["حوائط تحتاج مراجعة (needs_check)"] + row_vals(lambda p: p["walls"]["needs_check"]), fmt="0", warn=True)
    if any("planter_parapet|ALL" in p["walls"]["totals"] for p in plans):
        sh.line(["دروات أحواض الزرع م (خطوط MASS — خارج المباني، تحتاج قرار)"]
                + row_vals(lambda p: _get(p, "walls", "totals", "planter_parapet|ALL", "length_gross", default=0.0)), warn=True)
    sh.section("الأبواب والشبابيك والفتحات", nc)
    sh.line(["عدد الأبواب"] + row_vals(lambda p: p["openings"]["summary"]["doors"]["count"]), fmt="0")
    sh.line(["مجموع عروض الأبواب م"] + row_vals(lambda p: p["openings"]["summary"]["doors"]["total_width"]))
    sh.line(["عدد الشبابيك في فتحات مباني"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "window in masonry opening", "count", default=0)), fmt="0")
    sh.line(["مجموع عروض الشبابيك في المباني م"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "window in masonry opening", "total_width", default=0.0)))
    sh.line(["الحائط الستائري الغربي م"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "glazed facade / curtain wall", "total_width", default=0.0)))
    sh.line(["الزجاج المنحني بالأركان م"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "curved glazing (corner)", "total_width", default=0.0)))
    sh.line(["فتحات بلا باب (عدد)"] + row_vals(lambda p: p["openings"]["summary"]["openings"]["count"]), fmt="0")
    sh.line(["فتحات بلا باب (العرض م)"] + row_vals(lambda p: p["openings"]["summary"]["openings"]["total_width"]))
    sh.section("الفراغات", nc)
    sh.line(["عدد الفراغات"] + row_vals(lambda p: p["rooms"]["totals"]["n_rooms"]), fmt="0")
    sh.line(["المساحة الصافية الداخلية م²"] + row_vals(lambda p: p["rooms"]["totals"]["net_indoor_area"]))
    sh.line(["المساحة النافعة م² (مكاتب+حمامات+ممر+بهو+خدمات)"] + row_vals(lambda p: p["rooms"]["totals"]["net_usable_area"]))
    sh.line(["مساحة الأسقف م²"] + row_vals(lambda p: p["rooms"]["totals"]["ceiling_area"]), total=True)
    sh.line(["الفراغات المكشوفة م² (تراسات + زرع)"] + row_vals(lambda p: p["rooms"]["totals"]["open_air_area"]))
    sh.line(["المساحة الإجمالية للدور م² (للوجه الخارجي)"] + row_vals(lambda p: p["rooms"]["totals"]["gross_floor_area"]))
    sh.line(["محيط الوجه الخارجي للدور م"] + row_vals(lambda p: p["rooms"]["totals"]["gross_outline_perimeter"]))
    sh.line(["غرف عليها ملاحظات"] + row_vals(lambda p: len(p["rooms"]["flagged"])), fmt="0", warn=True)
    sh.section("الخرسانة (أعمدة / حوائط قص / كور)", nc)
    sh.line(["عناصر خرسانية في المسقط (model space)"] + row_vals(lambda p: p["cross_checks"]["concrete"]["structure_model_space"]), fmt="0")
    sh.line(["عناصر إضافية في بلوك tr فقط (غير مؤكدة)"] + row_vals(lambda p: p["cross_checks"]["concrete"]["structure_tr_only"]), fmt="0", warn=True)
    sh.line(["محيط أوجه الخرسانة الحرة الداخلية م ط (model space)"] + row_vals(lambda p: p["structure"]["summary"].get("plaster_perimeter_model_space_only")))
    sh.line(["محيط أوجه الخرسانة الحرة الداخلية م ط (مع tr)"] + row_vals(lambda p: p["structure"]["summary"].get("plaster_perimeter_all")))
    sh.line(["أوجه خرسانة على الواجهة م ط"] + row_vals(lambda p: p["structure"]["summary"].get("exterior_perimeter_all")))
    sh.line(["أوجه بئر المصعد م ط"] + row_vals(lambda p: p["structure"]["summary"].get("lift_shaft_perimeter")))
    sh.line(["شفتات مؤكدة (عدد)"] + row_vals(lambda p: p["structure"]["summary"].get("shafts_confirmed")), fmt="0")
    sh.line(["شفتات غير مؤكدة (عدد)"] + row_vals(lambda p: p["structure"]["summary"].get("shafts_uncertain")), fmt="0")
    sh.line(["سلالم / كبائن مصاعد"] + row_vals(lambda p: f"{p['structure']['summary'].get('stairs')} / {p['structure'].get('lift_cars')}", add_sum=False))
    sh.ws.freeze_panes = "B5"

    # ---------------- 2. walls by thickness
    sh = Sheet(wb, "الحوائط حسب السمك", [W_ITEM] + [14] * (nF + 1))
    sh.title("أطوال الحوائط حسب السمك والنوع (طول المحور، م)",
             ["الإجمالي = مستمر عبر الأبواب والشبابيك والفتحات؛ الصافي = الأجزاء المصمتة فقط؛ الحوائط تتوقف عند الخرسانة.",
              "الأنواع: خارجي = واجهة، داخلي = قاطوع، حول شفت = أحد وجهيه شفت/منور، سلم/مصعد = حول السلم والمصعد."])
    keys = set()
    for p in plans:
        keys |= set(p["walls"]["totals"])
    fams = [f for f in FAMILY_ORDER if any(k.startswith(f + "|") for k in keys)]
    for metric, lab in (("length_net", "الطول الصافي م"), ("length_gross", "الطول الإجمالي م"), ("n", "عدد السجلات")):
        sh.section(lab, 1 + nF + len(sumcol))
        sh.header(["السمك / النوع"] + F + sumcol)
        for f in fams:
            for k in ("exterior", "interior", "shaft", "stair_lift"):
                key = f"{f}|{k}"
                if not any(key in p["walls"]["totals"] for p in plans):
                    continue
                sh.line([f"{FAMILY_AR[f]} — {KIND_AR[k]}"] + row_vals(lambda p, key=key: _get(p, "walls", "totals", key, metric, default=0)),
                        fmt="0" if metric == "n" else "0.00")
            sh.line([f"{FAMILY_AR[f]} — الكل"] + row_vals(lambda p, f=f: _get(p, "walls", "totals", f"{f}|ALL", metric, default=0)),
                    fmt="0" if metric == "n" else "0.00", total=True)
        sh.line(["كل الحوائط"] + row_vals(lambda p: _get(p, "walls", "totals", "ALL|ALL", metric, default=0)),
                fmt="0" if metric == "n" else "0.00", total=True)
        if any("planter_parapet|ALL" in p["walls"]["totals"] for p in plans):
            sh.line(["دروات أحواض الزرع (خطوط MASS، F09–F11) — غير محسوبة في المباني"]
                    + row_vals(lambda p: _get(p, "walls", "totals", "planter_parapet|ALL", metric, default=0)),
                    fmt="0" if metric == "n" else "0.00", warn=True)
            for key, lab in (("planter_parapet|0.25", "  منها دروات 0.25"),
                             ("planter_parapet|thin", "  منها خطوط رفيعة ≤ 0.12 (تكرار زجاج الدور الأسفل: بردورة/درابزين زجاج/حافة بلاطة؟)")):
                sh.line([lab] + row_vals(lambda p, key=key: _get(p, "walls", "totals", key, metric, default=0)),
                        fmt="0" if metric == "n" else "0.00", warn=True)
        sh.blank()

    # ---------------- 3. doors & windows
    sh = Sheet(wb, "الأبواب والشبابيك", [W_ITEM] + [14] * (nF + 1))
    sh.title("الأبواب والشبابيك والفتحات (العرض بالمتر — الارتفاعات غير موجودة في اللوحات)",
             ["عرض الباب = حلق لحلق من البلوك D<عرض>W<سمك>؛ الشباك = طول الزجاج بين خطّي الإطار على WIN.",
              "الحائط الستائري والزجاج المنحني ليسا داخل مباني (لا يُخصمان من المباني)."])
    sh.header(["البند"] + F + sumcol)
    btypes = sorted({k for p in plans for k in p["openings"]["summary"]["doors"]["by_type"]})
    sh.section("الأبواب (العدد / مجموع العرض م)", 1 + nF + len(sumcol))
    for bt in btypes:
        sh.line([DOOR_TYPE_AR.get(bt, bt) + " — عدد"] + row_vals(lambda p, bt=bt: _get(p, "openings", "summary", "doors", "by_type", bt, "count", default=0)), fmt="0")
        sh.line([DOOR_TYPE_AR.get(bt, bt) + " — العرض م"] + row_vals(lambda p, bt=bt: _get(p, "openings", "summary", "doors", "by_type", bt, "total_width", default=0.0)))
    sh.line(["كل الأبواب — عدد"] + row_vals(lambda p: p["openings"]["summary"]["doors"]["count"]), fmt="0", total=True)
    sh.line(["كل الأبواب — العرض م"] + row_vals(lambda p: p["openings"]["summary"]["doors"]["total_width"]), total=True)
    sh.section("الشبابيك في فتحات مباني حسب العرض (عدد)", 1 + nF + len(sumcol))
    sizes = sorted({round(w["width"], 2) for p in plans for w in p["openings"]["windows"]
                    if w["kind"] == "window in masonry opening"}, reverse=True)
    for s_ in sizes:
        exact = sorted({round(w["width"], 3) for p in plans for w in p["openings"]["windows"]
                        if w["kind"] == "window in masonry opening" and round(w["width"], 2) == s_})
        lab = " / ".join(f"{x:.3f}".rstrip("0").rstrip(".") for x in exact)
        sh.line([f"شباك عرض {lab} م — عدد"] + row_vals(lambda p, s_=s_: sum(1 for w in p["openings"]["windows"]
                                                                             if w["kind"] == "window in masonry opening" and round(w["width"], 2) == s_)), fmt="0")
    sh.line(["كل الشبابيك في المباني — عدد"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "window in masonry opening", "count", default=0)), fmt="0", total=True)
    sh.line(["كل الشبابيك في المباني — العرض م"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "window in masonry opening", "total_width", default=0.0)), total=True)
    sh.section("زجاج بلا مباني وفتحات بلا باب", 1 + nF + len(sumcol))
    sh.line(["الحائط الستائري الغربي م"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "glazed facade / curtain wall", "total_width", default=0.0)))
    sh.line(["الزجاج المنحني بالأركان م"] + row_vals(lambda p: _get(p, "openings", "summary", "windows", "by_kind", "curved glazing (corner)", "total_width", default=0.0)))
    sh.line(["مجموعات باب + زجاج ثابت (F02) — العرض م"] + row_vals(lambda p: _get(p, "openings", "summary", "assemblies", "masonry_width", default=0.0)))
    sh.line(["فتحات بلا باب — عدد"] + row_vals(lambda p: p["openings"]["summary"]["openings"]["count"]), fmt="0")
    sh.line(["فتحات بلا باب — العرض م"] + row_vals(lambda p: p["openings"]["summary"]["openings"]["total_width"]))
    sh.section("ما يُخصم فعلًا من المباني حسب سمك الحائط (العدد / العرض م)", 1 + nF + len(sumcol))
    mkeys = sorted({k for p in plans for k in p["openings"]["summary"].get("masonry_deduction_widths", {})})
    for k in mkeys:
        t, th = k.split("|")
        lab = f"{DED_TYPE_AR.get(t, t)} في حائط {th}"
        sh.line([lab + " — عدد"] + row_vals(lambda p, k=k: _get(p, "openings", "summary", "masonry_deduction_widths", k, "count", default=0)), fmt="0")
        sh.line([lab + " — العرض م"] + row_vals(lambda p, k=k: _get(p, "openings", "summary", "masonry_deduction_widths", k, "width", default=0.0)))

    # ---------------- 4. rooms by category
    from rooms import CAT_ORDER, CATEGORY_AR
    sh = Sheet(wb, "الفراغات", [W_ITEM] + [14] * (nF + 1))
    sh.title("الفراغات حسب الفئة (المساحة الصافية داخل الأوجه المرسومة م²، المحيط = الوجه الداخلي م)",
             ["الأسقف = مكاتب + حمامات + ممر + بهو + خدمات + سلالم؛ بئر المصعد والشفتات والمكشوف خارجها."])
    sh.header(["الفئة / البند"] + F + sumcol)
    cats = [c for c in CAT_ORDER if any(c in p["rooms"]["by_category"] for p in plans)]
    for metric, lab, fmt in (("n", "العدد", "0"), ("area", "المساحة م²", "0.00"), ("perimeter", "المحيط م", "0.00")):
        sh.section(lab, 1 + nF + len(sumcol))
        for c in cats:
            sh.line([CATEGORY_AR.get(c, c)] + row_vals(lambda p, c=c: _get(p, "rooms", "by_category", c, metric, default=0)), fmt=fmt)
    sh.section("مجاميع", 1 + nF + len(sumcol))
    for k, lab in (("net_indoor_area", "الصافي الداخلي م²"), ("net_usable_area", "النافع م²"), ("ceiling_area", "الأسقف م²"),
                   ("open_air_area", "المكشوف م²"), ("gross_floor_area", "الإجمالي (للوجه الخارجي) م²"),
                   ("walls_columns_area", "الحوائط + الأعمدة م²"), ("gross_outline_perimeter", "محيط الوجه الخارجي م")):
        sh.line([lab] + row_vals(lambda p, k=k: p["rooms"]["totals"].get(k)), total=k in ("ceiling_area", "gross_floor_area"))
    sh.section("أطوال حدود الفراغات المسقوفة حسب ما يحدّها (م ط — أساس المحارة الداخلية)", 1 + nF + len(sumcol))
    BK_AR = {"wall": "حائط", "column": "عمود / كور خرساني", "solid_try": "زعانف مباني مهشّرة (try)", "extension": "امتداد افتراضي لحائط قاصر",
             "mass": "خط MASS", "shaft": "شفت", "glazing": "زجاج", "door": "أبواب (العرض × الوجهين)",
             "opening": "فتحات بلا باب", "virtual": "خط افتراضي ممر/بهو (ليس حائطًا)", "unresolved": "غير محدد",
             "slab_edge": "حافة بلاطة"}
    bks = sorted({k for p in plans for k in p["rooms"]["totals"].get("boundary_by_kind_indoor", {})},
                 key=lambda k: list(BK_AR).index(k) if k in BK_AR else 99)
    for k in bks:
        sh.line([BK_AR.get(k, k)] + row_vals(lambda p, k=k: p["rooms"]["totals"]["boundary_by_kind_indoor"].get(k, 0.0)))

    # ---------------- 5. room list
    sh = Sheet(wb, "الغرف تفصيلي", [10, 12, 22, 16, 11, 11, 12, 12, 11, 11, 11, 40])
    sh.title("قائمة الفراغات لكل دور", ["الأطوال م والمساحات م²؛ الأوجه المصمتة = حائط + عمود + زعانف + امتدادات."])
    sh.header(["الدور", "الرقم", "الاسم", "الفئة", "المساحة م²", "المحيط م", "أوجه مصمتة م", "منها خرسانة م",
               "زجاج م", "أبواب م", "فتحات م", "ملاحظات"])
    for p in plans:
        for r in p["rooms"]["rooms"]:
            bd = r.get("boundary", {})
            solid = sum(bd.get(k, 0.0) for k in SOLID_KINDS)
            sh.line([p["floor"], r["id"].split("-")[-1], r["name"], r.get("category_ar") or r["category"], r["area"], r["perimeter"],
                     round(solid, 3), bd.get("column", 0.0), bd.get("glazing", 0.0), bd.get("door", 0.0), bd.get("opening", 0.0),
                     "؛ ".join(r.get("flags", []))[:250] or None], warn=bool(r.get("flags")))
    sh.ws.freeze_panes = "A5"

    # ---------------- 6. concrete
    sh = Sheet(wb, "الأعمدة والخرسانة", [W_ITEM] + [14] * (nF + 1))
    sh.title("الأعمدة وحوائط القص والكور (من Etabs-col + COL + بلوك tr)",
             ["المحيط الحر الداخلي = أوجه تُلبَّس محارة داخلية؛ الواجهة = محارة خارجية أو تكسية؛ بئر المصعد عادةً بلا محارة.",
              "عناصر بلوك tr (Etabs-Slab) غير موجودة في الـ model space — وجودها الفعلي سؤال للمهندس."])
    sh.header(["البند"] + F + sumcol)
    groups = sorted({k for p in plans for k in p["structure"]["summary"].get("totals_by_kind", {})})
    for metric, lab in (("n", "العدد"), ("area", "المساحة م²"), ("perimeter", "المحيط الكلي م"),
                        ("exposed_interior", "المحيط الحر الداخلي م"), ("exposed_exterior", "المحيط على الواجهة م"),
                        ("exposed_lift_shaft", "داخل بئر المصعد م")):
        sh.section(lab, 1 + nF + len(sumcol))
        for g in groups:
            base = g.replace(" (tr block only)", "")
            lab_g = ELEM_KIND_AR.get(base, base) + (" — بلوك tr فقط" if "tr block" in g else "")
            sh.line([lab_g] + row_vals(lambda p, g=g: _get(p, "structure", "summary", "totals_by_kind", g, metric, default=0)),
                    fmt="0" if metric == "n" else "0.00", warn="tr block" in g)

    # ---------------- 7. preliminary masonry
    sh = Sheet(wb, "مباني تقديري", [W_ITEM] + [14] * (nF + 1))
    sh.title("حصر المباني — تقديري أوّلي" + (" (ارتفاع كل حائط من اللوحة الإنشائية)" if P.heights == "structural" else " (ارتفاع ثابت مفترض)"), [
        (f"ارتفاع الدور المنفذ = {P.storey:.2f} م (وش بلاطة لوش بلاطة). ارتفاع المباني لكل حائط = {P.storey:.2f} − عمق الخرسانة فوقه "
         "من سقف نفس الدور في الإنشائي: بلاطة 0.20 ← 3.00، بلاطة 0.35 ← 2.85، كمرة 25×70 ← 2.50، كمرة 25×90 ← 2.30 "
         "(حائط يمر تحت أكثر من عمق = متوسط مرجّح بالطول). التفاصيل: masonry_heights في ملفات output/plan/Fnn.json")
        if P.heights == "structural" else
        (f"ارتفاع الدور = {P.storey:.2f} م؛ سمك البلاطة (افتراض) = {P.slab:.2f} م؛ سقوط الكمرات (افتراض) = {P.beam:.2f} م؛ "
         f"ارتفاع المباني المستخدم = {P.H_m:.2f} م"),
        f"ارتفاع الباب = {P.door_h:.2f} م (عُرف الحصر السابق)؛ جلسة الشباك = {P.window_sill:.2f} م؛ ارتفاع الشباك = "
        + ("ارتفاع المباني عند الشباك − الجلسة؛ " if P.heights == "structural" and P.window_h is None else f"{P.win_h:.2f} م؛ ") +
        f"ارتفاع الفتحات بلا باب (فتحتا المصعد، فتحة 0.80) = {P.open_h:.2f} م",
        "المساحة = الطول الإجمالي (طول المحور عبر الفتحات) × ارتفاع المباني − Σ(عرض الفتحة × ارتفاعها)؛ عرض الفتحة كما قِيس في الحائط (walls.py).",
        "غير مشمول: الحائط الستائري والزجاج المنحني (لا مباني)، الدروات، الأعتاب/الكمرات فوق الفتحات، الحوائط الواقعة على خرسانة "
        "(خرسانة المسقط + عناصر بلوك tr المؤكدة)، وأجزاء الحوائط الداخلة في أعمدة/كور الإنشائي (حوائط القص 0.30 المنفذة، كور Z، الأعمدة غير المرسومة معماريًا).",
        "الأرقام للمراجعة والمقارنة فقط — تتغير بتأكيد المهندس للأبواب والجلسات."])
    sh.header(["البند"] + F + sumcol)
    mfams = [f for f in FAMILY_ORDER if any(f"{f}|ALL" in p["preliminary"]["masonry"] for p in plans)]
    for f in mfams:
        sh.section(FAMILY_AR[f], 1 + nF + len(sumcol))
        key = f"{f}|ALL"
        for m, lab in (("length_gross", "الطول الإجمالي م"), ("area_gross", "المساحة الإجمالية م²"),
                       ("ded_door", "خصم الأبواب م²"), ("ded_window", "خصم الشبابيك م²"), ("ded_opening", "خصم الفتحات بلا باب م²"),
                       ("ded_concrete", "خصم خرسانة الإنشائي داخل الحائط م²"),
                       ("area_net", "صافي المباني م²")):
            sh.line([lab] + row_vals(lambda p, key=key, m=m: _get(p, "preliminary", "masonry", key, m, default=0.0)), total=m == "area_net")
    sh.section("الإجمالي", 1 + nF + len(sumcol))
    for k in ("exterior", "interior", "shaft", "stair_lift"):
        sh.line([f"صافي مباني {KIND_AR[k]} م²"] + row_vals(lambda p, k=k: _get(p, "preliminary", "masonry", f"ALL|{k}", "area_net", default=0.0)))
    sh.line(["صافي المباني — كل السماكات م²"] + row_vals(lambda p: _get(p, "preliminary", "masonry", "ALL|ALL", "area_net", default=0.0)), total=True)
    sh.line(["للمقارنة: لو اعتُبرت عناصر بلوك tr مباني (قبل تأكيد المالك أنها خرسانة) م²"]
            + row_vals(lambda p: _get(p, "preliminary", "masonry_if_tr_were_masonry", "ALL|ALL", "area_net", default=0.0)))
    sh.line(["حوائط مستبعدة لوقوعها على عناصر tr (خرسانة مؤكدة) (عدد)"] + row_vals(lambda p: len(p["preliminary"].get("masonry_excluded_on_tr", []))), fmt="0")
    sh.line(["طول حوائط داخل أعمدة/كور الإنشائي (مخصوم) م"]
            + row_vals(lambda p: round(sum(p["preliminary"].get("masonry_length_in_structural_concrete", {}).values()), 2)))
    sh.line(["حوائط مستبعدة لوقوعها على خرسانة المسقط (عدد)"] + row_vals(lambda p: len(p["preliminary"]["masonry_excluded_on_concrete"])), fmt="0")

    # ---------------- 8. preliminary plaster
    sh = Sheet(wb, "محارة تقديري", [W_ITEM + 6] + [14] * (nF + 1))
    sh.title("حصر المحارة — تقديري أوّلي (الارتفاعات افتراضات، ليست من اللوحات)", [
        f"ارتفاع المحارة الداخلية = {P.H_p:.2f} م (= ارتفاع الدور − البلاطة، حتى بطنية البلاطة؛ لا يوجد سقف معلق في اللوحات)",
        f"الباب {P.door_h:.2f} م (يُضاف شريط فوق الباب على الوجهين)، الشباك من جلسة {P.window_sill:.2f} م بارتفاع {P.win_h:.2f} م (يُضاف شريط الجلسة من الداخل)",
        "الأوجه الداخلية من حدود الفراغات المسقوفة (rooms.py): حائط + عمود/كور + زعانف مهشّرة + امتدادات — كل وجه مرة في كل غرفة (الحائط الداخلي = وجهان).",
        "الأسقف = مساحات الفراغات المسقوفة الصافية. لا تُحسب: الرجوعات (جوانب الفتحات)، أوجه بئر المصعد والشفتات، أوجه عناصر بلوك tr.",
        f"الخارجي (محارة أم تكسية؟ مجهول) = (محيط الوجه الخارجي − الزجاج كامل الارتفاع) × {P.H_f:.2f} م − الشبابيك؛ يشمل حواف البلاطات ولا يشمل الدروات."])
    sh.header(["البند"] + F + sumcol)
    nc = 1 + nF + len(sumcol)
    pl = lambda p, *k: _get(p, "preliminary", "plaster", *k, default=0.0)  # noqa: E731
    sh.section("المحارة الداخلية — الحوائط والأعمدة", nc)
    sh.line(["أطوال الأوجه المصمتة الداخلية م ط"] + row_vals(lambda p: pl(p, "solid_faces_m")))
    sh.line(["  منها أوجه أعمدة/كور خرسانية م ط"] + row_vals(lambda p: pl(p, "of_which_concrete_m")))
    sh.line(["الأوجه × ارتفاع المحارة م²"] + row_vals(lambda p: pl(p, "wall_faces_m2")))
    sh.line(["شرائط فوق الأبواب (الوجهان) م²"] + row_vals(lambda p: pl(p, "strip_above_doors_m2")))
    sh.line(["شرائط فوق الفتحات بلا باب م²"] + row_vals(lambda p: pl(p, "strip_above_openings_m2")))
    sh.line(["شرائط تحت/فوق الشبابيك (من الداخل) م²"] + row_vals(lambda p: pl(p, "strip_windows_m2")))
    sh.line(["شرائط فوق مجموعات باب+زجاج (F02) م²"] + row_vals(lambda p: pl(p, "strip_above_assemblies_m2")))
    sh.line(["محارة الحوائط والأعمدة الداخلية م²"] + row_vals(lambda p: pl(p, "internal_walls_m2")), total=True)
    sh.section("الأسقف", nc)
    sh.line(["محارة الأسقف م²"] + row_vals(lambda p: pl(p, "ceilings_m2")), total=True)
    sh.line(["إجمالي المحارة الداخلية (حوائط + أسقف) م²"] + row_vals(lambda p: pl(p, "internal_total_m2")), total=True)
    sh.section("الخارجي (محارة أو تكسية — مجهول)", nc)
    sh.line(["محيط الوجه الخارجي م"] + row_vals(lambda p: pl(p, "external", "outline_m")))
    sh.line(["زجاج كامل الارتفاع (ستائري + منحني) م"] + row_vals(lambda p: pl(p, "external", "full_height_glazing_m")))
    sh.line(["شبابيك ومجموعات الواجهة (العرض) م"] + row_vals(lambda p: pl(p, "external", "facade_windows_m")))
    sh.line(["الواجهات تقديري م²"] + row_vals(lambda p: pl(p, "external", "area_m2")), total=True)
    sh.section("غير محسوب (للعلم — قرار المهندس)", nc)
    sh.line(["أوجه بئر المصعد م ط"] + row_vals(lambda p: pl(p, "not_included", "lift_shaft_faces_m")), warn=True)
    sh.line(["أوجه الشفتات من الداخل م ط"] + row_vals(lambda p: pl(p, "not_included", "shaft_faces_m")), warn=True)
    sh.line(["أوجه عناصر بلوك tr الداخلية م ط"] + row_vals(lambda p: pl(p, "not_included", "tr_block_concrete_faces_m")), warn=True)
    sh.line(["  × ارتفاع المحارة م²"] + row_vals(lambda p: pl(p, "not_included", "tr_block_concrete_faces_m2")), warn=True)
    sh.line(["أوجه مصمتة حول الفراغات المكشوفة (F02) م ط"] + row_vals(lambda p: pl(p, "not_included", "open_air_solid_faces_m")), warn=True)
    sh.line(["خط افتراضي ممر/بهو (ليس حائطًا) م ط"] + row_vals(lambda p: pl(p, "not_included", "corridor_lobby_virtual_line_m")))
    sh.section("مراجعة: طول الأوجه بطريقتين", nc)
    sh.line(["أوجه مصمتة غير خرسانية (rooms.py) م ط"] + row_vals(lambda p: pl(p, "cross_check_face_length", "rooms_non_concrete_solid_m")))
    sh.line(["2 × صافي الداخلي + صافي الخارجي والشفت (walls.py) م ط"] + row_vals(lambda p: pl(p, "cross_check_face_length", "walls_based_2xinterior_plus_exterior_m")))
    sh.line(["أوجه خرسانة على حدود الغرف (قياس هندسي على حدود Etabs-col) م ط"] + row_vals(lambda p: pl(p, "cross_check_face_length", "rooms_concrete_faces_m")))
    sh.line(["  منها ما صنّفه rooms.py 'عمود' (بلا خط W فوقه) م ط"] + row_vals(lambda p: pl(p, "cross_check_face_length", "rooms_boundary_labelled_column_m")))
    sh.line(["أوجه خرسانة حرة داخلية (structure.py، model space) م ط"] + row_vals(lambda p: pl(p, "cross_check_face_length", "structure_interior_free_faces_model_space_m")))

    # ---------------- 9. conflicts
    sh = Sheet(wb, "تعارضات ومراجعات", [10, 22, 14, 12, 95])
    sh.title("تعارضات بين القرّاء ونقاط تحتاج قرار المهندس", ["مستخرجة آليًا عند دمج القرّاء الأربعة (tools/read_plan.py)."])
    sh.header(["الدور", "النوع", "العنصر", "الخرسانة", "التفاصيل"])
    TYPE_AR = {"wall_on_concrete": "حائط على خرسانة", "wall_on_tr_element": "حائط على عنصر tr",
               "opening_is_tr_column": "فتحة = عمود tr", "tr_element_free_standing": "عنصر tr قائم وحده",
               "needs_check_counts": "عدد المراجعات", "cross_check_mismatch": "عدم تطابق بين القرّاء",
               "planter_parapet": "دروة أحواض زرع", "glazing_off_footprint": "زجاج بعيد عن الواجهة"}
    for p in plans:
        for c in p["conflicts"]:
            sh.line([p["floor"], TYPE_AR.get(c["type"], c["type"]), c["item"], c["element"], c["detail_ar"]],
                    warn=c["type"] != "needs_check_counts")
        cc = p["cross_checks"]
        sh.line([p["floor"], "مطابقة الأبواب", "-", "-",
                 f"openings.py {cc['doors']['openings_py_in_masonry']} باب في مباني ({cc['doors']['openings_py_width']} م) — "
                 f"walls.py {cc['doors']['walls_py_door_gaps']} فجوة باب ({cc['doors']['walls_py_door_width']} م)؛ "
                 f"أبواب لا تقع بين فراغين: {cc['doors']['rooms_doors_not_two_sided']}"])
        cw = cc["windows_in_masonry"]
        asm_txt = (f" + {cw['openings_py_assemblies']} مجموعة باب+زجاج ({cw['openings_py_assemblies_width']} م)"
                   if cw["openings_py_assemblies"] else "")
        sh.line([p["floor"], "مطابقة الشبابيك", "-", "-",
                 f"openings.py {cw['openings_py']} شباك ({cw['openings_py_width']} م زجاج){asm_txt} — walls.py {cw['walls_py_window_gaps']} "
                 f"فجوة شباك ({cw['walls_py_window_width']} م فتحة مباني)"])
        ca = cc["all_masonry_gaps"]
        sh.line([p["floor"], "مطابقة كل الفتحات", "-", "-",
                 f"كل الفتحات في المباني: openings.py {ca['openings_py']} ({ca['openings_py_width']} م) — "
                 f"walls.py {ca['walls_py']} ({ca['walls_py_width']} م)"],
                warn=ca["openings_py"] != ca["walls_py"])
        fp = cc["footprint_m2"]
        sh.line([p["floor"], "مطابقة البصمة", "-", "-",
                 f"rooms.py {fp['rooms_gross_floor_area']} م² (بدون الزعانف الخارجية الرفيعة) — structure.py {fp['structure_face_env']} م²"
                 + (f" — خط الواجهة على طبقة try {fp['try_outline_area']:.2f} م² (محيط {fp['try_outline_perimeter']:.2f} م)"
                    if fp.get("try_outline_area") else "")])

    # ---------------- 10. assumptions & unknowns
    sh = Sheet(wb, "الافتراضات والمجاهيل", [60, 18, 70])
    sh.title("المعاملات المستخدمة وما يجب أن يأتي من المهندس", ["كل قيمة هنا قابلة للتغيير من سطر الأوامر: python tools/read_plan.py --slab 0.22 ..."])
    sh.header(["المعامل", "القيمة", "المصدر / الحالة"])
    for lab, v, src in (
            ("ارتفاع الدور (منسوب لمنسوب)", P.storey, "من علامات المناسيب في اللوحات (+8.90 … +28.10) — مؤكد"),
            *((("ارتفاع المباني لكل حائط", "3.20 − عمق الخرسانة",
                 "من اللوحة الإنشائية (سقف نفس الدور): بلاطة 0.20 ← 3.00، بلاطة 0.35 ← 2.85، كمرة 70 ← 2.50، كمرة 90 ← 2.30 "
                 "(الصافي المنفذ 3.00 تحت بلاطة 20 = المعماري صحيح، مناسيب الإنشائي 3.30 خطأ)"),)
              if P.heights == "structural" else
              (("سمك البلاطة", P.slab, "افتراض (--heights flat)"),
               ("سقوط الكمرات فوق الحوائط", P.beam, "افتراض (--heights flat)"),
               ("ارتفاع المباني", P.H_m, "محسوب"))),
            ("ارتفاع الباب", P.door_h, "مجهول — عُرف الحصر السابق 2.30"),
            ("جلسة الشباك", P.window_sill, "مجهول — حصر الدور الخامس السابق (19 جلسة × 1.00)"),
            ("ارتفاع الشباك", P.win_h if P.heights == "flat" or P.window_h is not None else "ارتفاع المباني عند الشباك − الجلسة",
             "افتراض: حتى أعلى المباني (بلا مباني فوق الشباك)"),
            ("ارتفاع الفتحات بلا باب", P.open_h, "مجهول (فتحتا المصعد 1.25 / فتحة 0.80)"),
            ("ارتفاع المحارة الداخلية", P.H_p, "افتراض: حتى بطنية البلاطة (لا سقف معلق في اللوحات)"),
            ("ارتفاع الواجهة لكل دور", P.H_f, "افتراض: ارتفاع الدور كاملًا (يشمل حافة البلاطة)")):
        sh.line([lab, v, src])
    sh.blank()
    sh.header(["سؤال مفتوح للمهندس", "", "الأثر"])
    for q, eff in OPEN_QUESTIONS:
        sh.line([q, None, eff])

    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_xlsx)
    return out_xlsx


OPEN_QUESTIONS = [
    ("ارتفاع الأبواب (2.20 أم 2.30)، وباب السلم D90W25، ومجموعات التراس في F02", "خصم الأبواب وشرائط المحارة"),
    ("جلسات وعتبات الشبابيك لكل مقاس، وشبابيك الخدمات 0.80", "خصم الشبابيك والجلسات"),
    ("الحائط الستائري الغربي 13 م والزجاج المنحني: بلا مباني تمامًا؟ أم بانيل/دروة أسفله؟", "مباني ومحارة الواجهة الغربية"),
    ("التشطيب الخارجي: محارة أم تكسية (حجر/كلادينج)؟ وخطوط WIN المتقطعة خارج الواجهة؟", "بند المحارة الخارجية كله"),
    ("محارة أوجه الخرسانة: تُحسب على مقاسات الإنشائي المنفذة (حوائط القص 0.30، كور Z، الأعمدة غير المرسومة) لا المعماري؟ وماذا يملأ فرق الـ 0.10 بين حائط القص المعماري 0.40 والمنفذ 0.30؟", "محارة أوجه الخرسانة + مباني بسيطة"),
    ("الواجهة الشمالية الشرقية 0.40 حول الشباك 1.217 (SW01 من tr في نفس المكان)", "مباني الواجهة"),
    ("قواطيع مفقودة في بعض الأدوار (مكتب 2/3 في F05/F08، مكتب 14/15 في F04/F07، F02 مكاتب 6/7/8) — مقصود أم سهو رسم؟", "مباني ومحارة الأدوار المعنية"),
    ("حمامات تظهر وتختفي بين الأدوار — توزيع مقصود لكل مستأجر؟", "مباني 0.12 ومحارة وأبواب D80"),
    ("حائط واجهة المصعد 0.30 بين الفتحتين: مباني أم جزء من الكور؟ وما فوق فتحتي المصعد؟", "مباني 0.30"),
    ("بئر المصعد والشفتات: محارة داخلية أم لا؟", "محارة"),
    ("F02: التراسات وأحواض الزرع والدروات (خطّا MASS 8B1/8B2) والمنطقة 'Waiting For The Update'", "مباني ومحارة F02"),
    ("المحور د: خط X عند x=9.755 أم 1.50 م شرقًا كما في سلسلة الأبعاد؟", "الإسناد للمحاور فقط"),
]


# ============================================================================
# 5. CLI
# ============================================================================
def _short_summary(plan):
    T = plan["walls"]["totals"].get("ALL|ALL", {})
    m = plan["preliminary"]["masonry"].get("ALL|ALL", {})
    pl = plan["preliminary"]["plaster"]
    return {"level": plan["level"], "walls_n": T.get("n"), "walls_gross": T.get("length_gross"), "walls_net": T.get("length_net"),
            "net_0.12": _get(plan, "walls", "totals", "0.12|ALL", "length_net"),
            "net_0.25": _get(plan, "walls", "totals", "0.25|ALL", "length_net"),
            "doors": plan["openings"]["summary"]["doors"]["count"], "doors_width": plan["openings"]["summary"]["doors"]["total_width"],
            "windows_masonry": _get(plan, "openings", "summary", "windows", "by_kind", "window in masonry opening", "count"),
            "windows_masonry_width": _get(plan, "openings", "summary", "windows", "by_kind", "window in masonry opening", "total_width"),
            "rooms": plan["rooms"]["totals"]["n_rooms"], "net_indoor_area": plan["rooms"]["totals"]["net_indoor_area"],
            "ceiling_area": plan["rooms"]["totals"]["ceiling_area"], "gross_floor_area": plan["rooms"]["totals"]["gross_floor_area"],
            "concrete_model_space": plan["cross_checks"]["concrete"]["structure_model_space"],
            "concrete_tr_only": plan["cross_checks"]["concrete"]["structure_tr_only"],
            "concrete_interior_faces_m": plan["structure"]["summary"].get("plaster_perimeter_model_space_only"),
            "masonry_net_m2_prelim": m.get("area_net"), "plaster_internal_m2_prelim": pl["internal_total_m2"],
            "external_m2_prelim": pl["external"]["area_m2"],
            "conflicts": sum(1 for c in plan["conflicts"] if c["type"] != "needs_check_counts")}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read the whole Diwan plan (walls + openings + rooms + structure) -> output/plan/")
    ap.add_argument("floors", nargs="*", type=int, help="floor numbers (default: all 2..8)")
    ap.add_argument("--floor", type=int, action="append", help="a floor number (repeatable)")
    ap.add_argument("--storey", type=float, default=STOREY_HEIGHT, help="floor-to-floor height (m), default 3.20")
    ap.add_argument("--slab", type=float, default=0.20, help="slab thickness (m) - UNKNOWN, default 0.20")
    ap.add_argument("--beam", type=float, default=0.0, help="beam drop below the slab over walls (m) - UNKNOWN, default 0")
    ap.add_argument("--door-h", type=float, default=2.30, help="door height (m), default 2.30 (owner's legacy)")
    ap.add_argument("--window-sill", type=float, default=1.00, help="window sill height (m), default 1.00")
    ap.add_argument("--window-h", type=float, default=None, help="window height (m); default = masonry height - sill")
    ap.add_argument("--opening-h", type=float, default=None, help="door-less opening height (m); default = door height")
    ap.add_argument("--plaster-h", type=float, default=None, help="internal plaster height (m); default = storey - slab")
    ap.add_argument("--facade-h", type=float, default=None, help="external face height per storey (m); default = storey")
    ap.add_argument("--heights", choices=["structural", "flat"], default="structural",
                    help="masonry height per wall: structural (3.20 - slab/beam depth above, default) or flat (storey-slab-beam)")
    ap.add_argument("--no-cache", action="store_true", help="re-run the readers (ignore output/plan/_cache)")
    ap.add_argument("--deep", action="store_true", help="with --no-cache: also drop the walls/rooms DXF geometry caches")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-xlsx", action="store_true")
    ap.add_argument("--dpi", type=int, default=130)
    a = ap.parse_args(argv)
    P = Params(storey=a.storey, slab=a.slab, beam=a.beam, door_h=a.door_h, window_sill=a.window_sill,
               window_h=a.window_h, opening_h=a.opening_h, plaster_h=a.plaster_h, facade_h=a.facade_h,
               heights=a.heights)
    wanted = (a.floors or []) + (a.floor or [])
    fls = [f for f in all_floors() if f.floor_no and (not wanted or f.floor_no in wanted)]
    PLAN_OUT.mkdir(parents=True, exist_ok=True)
    print(f"read_plan: floors {[f.label for f in fls]}  H_m={P.H_m}  H_p={P.H_p}  door={P.door_h} "
          f"sill={P.window_sill} window={P.win_h} opening={P.open_h}", flush=True)
    plans, bundles = [], []
    t0 = time.time()
    for fl in fls:
        b = read_floor(fl, use_cache=not a.no_cache, deep=a.deep)
        plan = merge_floor(b, P)
        plans.append(plan)
        bundles.append(b)
    # same SHnn shaft ids on every floor (structure.harmonize_shaft_ids works on the plain dicts)
    if len(bundles) > 1:
        import structure as stm
        stm.harmonize_shaft_ids([b["structure"] for b in bundles])
        for b, plan in zip(bundles, plans):
            plan["structure"]["shafts"] = [{k: s[k] for k in ("id", "kind", "size_txt", "bbox", "area", "floors") if k in s}
                                           for s in b["structure"]["shafts"]]
    summary = {}
    for b, plan in zip(bundles, plans):
        js = PLAN_OUT / f"{plan['floor']}.json"
        js.write_text(json.dumps(plan, ensure_ascii=False, indent=1, default=_np_default), encoding="utf-8")
        if not a.no_png:
            render_plan(b, plan, PLAN_OUT / f"{plan['floor']}_plan.png", dpi=a.dpi)
        s = _short_summary(plan)
        summary[plan["floor"]] = s
        print(f"{plan['floor']} {plan['level']:+.2f}: walls {s['walls_n']} gross {s['walls_gross']} net {s['walls_net']} | "
              f"doors {s['doors']}={s['doors_width']} | windows {s['windows_masonry']}={s['windows_masonry_width']} | "
              f"rooms {s['rooms']} net {s['net_indoor_area']} ceil {s['ceiling_area']} | concrete {s['concrete_model_space']}"
              f"+{s['concrete_tr_only']}tr | masonry~{s['masonry_net_m2_prelim']} m2 plaster~{s['plaster_internal_m2_prelim']} m2"
              f" ext~{s['external_m2_prelim']} m2 | conflicts {s['conflicts']}", flush=True)
    # a partial run (some floors) must not overwrite the all-floor workbook
    all_labels = [f.label for f in all_floors() if f.floor_no]
    tag = "" if [p["floor"] for p in plans] == all_labels else "_" + "_".join(p["floor"] for p in plans)
    (PLAN_OUT / f"summary{tag}.json").write_text(json.dumps({"params": P.as_dict(), "floors": summary}, ensure_ascii=False,
                                                            indent=1, default=_np_default), encoding="utf-8")
    if not a.no_xlsx:
        x = write_workbook(plans, P, PLAN_OUT / f"summary{tag}.xlsx")
        print("workbook:", x)
    print(f"done in {time.time() - t0:.0f} s -> {PLAN_OUT}")
    return plans


if __name__ == "__main__":
    main()
