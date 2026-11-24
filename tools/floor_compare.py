# -*- coding: utf-8 -*-
"""
floor_compare — مقارنة الأدوار السبعة (F02..F08) طبقةً طبقة في الإطار المحلي المشترك
لتحديد الأدوار المتكررة (النموذجية) وكل اختلاف بإحداثياته.

Method (all in the LOCAL frame of diwan_common, metres):
  LINE LAYERS  W, WIN, ST, DASH, PR, MASS, X, COL, try, Etabs-col, HAT, 0:
               every LINE / LWPOLYLINE / ARC / CIRCLE / HATCH boundary -> local polylines
               (OCS-safe, arcs flattened at 1 cm; INSERTs are compared separately).
               Floor A vs floor B: A_union.difference(B_union.buffer(TOL)) -> the pieces
               of A that have no B geometry within TOL (2 cm).  This is independent of how
               the lines are split into segments.  Pieces shorter than MIN_PIECE (5 cm)
               are ignored (snapping noise).
  BLOCKS       every INSERT on the floor (doors D<w>W<t>, LP, FUR 'P'/'WB', PR1 'ST-2'):
               same block + insertion point within TOL + same rotation & mirror.
  TEXTS        TEXT / -A-TEXT room names (SOSA decoded): same text within 5 cm; same text
               within 1.5 m = 'moved'.
  DIMS         architect DIMENSIONs: same extension points (unordered, TOL) + same text.
  STRUCTURE    structural polygons from tools/structure.py (Etabs-col + 'tr' + COL).
  -> pairwise difference matrix per layer (length of non-matching geometry, both ways),
     groups of identical floors, a REFERENCE floor (medoid), and CHANGE REGIONS:
     the pieces of every floor that differ from the reference, clustered (0.6 m), each
     region described per floor (which floors share which variant).

Outputs (output/floor_compare/, gitignored) + docs/findings/floors_diff.md (generated):
  summary.json            matrices, groups, regions, block/text/dim differences
  overlay_W.png           W of all floors overlaid (common = grey, floor-specific = colour)
  diff_F0x.png            each floor vs the reference (red = only on this floor, blue = only
                          on the reference), numbered change regions
  regions_map.png         all change regions numbered on the reference plan
  region_RNN.png          zoom on each region, one small panel per floor

CLI:  python tools/floor_compare.py            # all floors
      python tools/floor_compare.py --ref 5    # force the reference floor
API:  from floor_compare import compare_floors ; res = compare_floors()
      res["identical_groups"], res["regions"], res["matrix"]["W"]
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
from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diwan_common import OUT_DIR, REPO, all_floors, floor_entities, floor_texts  # noqa: E402

OUT = OUT_DIR / "floor_compare"
DOC = REPO / "docs" / "findings" / "floors_diff.md"
TOL = 0.02
MIN_PIECE = 0.05
REGION_GAP = 0.35   # m: differences closer than this form one region
LINE_LAYERS = ["W", "WIN", "ST", "DASH", "PR", "MASS", "X", "COL", "try", "Etabs-col", "HAT", "0", "FUR"]
FLOOR_COLORS = {"F02": "#d62728", "F03": "#1f77b4", "F04": "#2ca02c", "F05": "#ff7f0e",
                "F06": "#9467bd", "F07": "#8c564b", "F08": "#e377c2"}


def _r(v, n=3):
    if isinstance(v, (list, tuple)):
        return [_r(x, n) for x in v]
    if isinstance(v, (float, np.floating)):
        return round(float(v), n)
    return v


# ----------------------------------------------------------------------------- extraction
def _local_paths(e, fl):
    t = e.dxftype()
    out = []
    try:
        if t == "HATCH":
            for p in ezpath.from_hatch(e):
                pts = [fl.to_local(q.x, q.y) for q in p.flattening(0.01)]
                if len(pts) >= 2:
                    out.append(pts)
        elif t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE", "ELLIPSE"):
            p = ezpath.make_path(e)
            pts = [fl.to_local(q.x, q.y) for q in p.flattening(0.01)]
            if len(pts) >= 2:
                out.append(pts)
    except Exception:
        pass
    return out


def extract(fl):
    """All comparable features of one floor in local coordinates."""
    lines = defaultdict(list)
    inserts = []
    for e in floor_entities(fl):
        lay = e.dxf.layer
        t = e.dxftype()
        if t == "INSERT":
            p = e.dxf.insert
            lp = fl.to_local(p.x, p.y)
            rot = (e.dxf.rotation - fl.angle) % 360.0
            mir = (e.dxf.xscale < 0) != (e.dxf.yscale < 0)
            inserts.append({"block": e.dxf.name, "layer": lay, "at": lp, "rot": rot, "mirror": mir,
                            "scale": abs(e.dxf.xscale)})
            continue
        if t in ("TEXT", "MTEXT", "DIMENSION"):
            continue
        if lay in LINE_LAYERS:
            for pts in _local_paths(e, fl):
                if len(pts) == 2 and math.dist(*pts) < 1e-6:
                    continue
                lines[lay].append(LineString(pts))
    texts = [{"layer": t["layer"], "text": t["text"], "at": t["local"]}
             for t in floor_texts(fl, layers=("TEXT", "-A-TEXT", "TEXT-D", "PR", "0"))]
    dims = []
    for e in floor_entities(fl, layers="DIM", types="DIMENSION"):
        p2, p3 = e.dxf.get("defpoint2"), e.dxf.get("defpoint3")
        if p2 is None or p3 is None:
            continue
        txt = None
        try:
            blk = e.get_geometry_block()
            for x in blk or []:
                if x.dxftype() in ("MTEXT", "TEXT"):
                    txt = (x.plain_text() if x.dxftype() == "MTEXT" else x.dxf.text).strip()
                    break
        except Exception:
            pass
        dims.append({"a": fl.to_local(p2.x, p2.y), "b": fl.to_local(p3.x, p3.y), "text": txt,
                     "dimline": fl.to_local(e.dxf.defpoint.x, e.dxf.defpoint.y)})
    # structural polygons (incl. the ETABS 'tr' block) via structure.py
    struct = []
    try:
        from structure import FloorData, _collect_struct_polys
        D = FloorData(fl)
        els, _ = _collect_struct_polys(fl, D)
        struct = [{"poly": el["poly"], "sources": el["sources"]} for el in els]
    except Exception as ex:  # pragma: no cover
        print("  structure polygons unavailable:", ex)
    return {"label": fl.label, "lines": dict(lines), "inserts": inserts, "texts": texts, "dims": dims,
            "struct": struct}


# ----------------------------------------------------------------------------- geometry diff
_UNION_CACHE = {}


def _union(F, lay):
    key = (F["label"], lay)
    if key not in _UNION_CACHE:
        L = F["lines"].get(lay, [])
        g = unary_union(L) if L else MultiLineString()
        _UNION_CACHE[key] = (g, g.buffer(TOL, cap_style=2, join_style=2) if not g.is_empty else Polygon())
    return _UNION_CACHE[key]


def _pieces(geom, min_len=MIN_PIECE):
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        gs = [geom]
    elif hasattr(geom, "geoms"):
        gs = [g for g in geom.geoms if g.geom_type == "LineString"]
    else:
        gs = []
    # merge touching pieces
    if gs:
        from shapely.ops import linemerge
        m = linemerge(gs) if len(gs) > 1 else gs[0]
        gs = [m] if m.geom_type == "LineString" else list(m.geoms)
    return [g for g in gs if g.length >= min_len]


def only_in(A, B, lay, clip=None):
    """pieces of layer `lay` of floor A that are not within TOL of floor B."""
    ga, _ = _union(A, lay)
    _, gb_buf = _union(B, lay)
    if ga.is_empty:
        return []
    if clip is not None:
        ga = ga.intersection(clip)
        if ga.is_empty:
            return []
    d = ga.difference(gb_buf) if not gb_buf.is_empty else ga
    return _pieces(d)


def _same_insert(a, b):
    if a["block"] != b["block"] or math.dist(a["at"], b["at"]) > TOL:
        return False
    dr = abs((a["rot"] - b["rot"] + 180) % 360 - 180)
    return dr < 0.5 and a["mirror"] == b["mirror"]


def insert_diff(A, B):
    onlyA = [a for a in A["inserts"] if not any(_same_insert(a, b) for b in B["inserts"])]
    return onlyA


def text_diff(A, B, layers=("TEXT", "-A-TEXT")):
    res = []
    for a in A["texts"]:
        if a["layer"] not in layers:
            continue
        same = [b for b in B["texts"] if b["layer"] == a["layer"] and b["text"] == a["text"]]
        if any(math.dist(a["at"], b["at"]) <= 0.05 for b in same):
            continue
        near = [b for b in same if math.dist(a["at"], b["at"]) <= 1.5]
        if near:
            b = min(near, key=lambda b: math.dist(a["at"], b["at"]))
            res.append({"kind": "moved", "text": a["text"], "at": _r(list(a["at"])),
                        "from": _r(list(b["at"])), "dist": _r(math.dist(a["at"], b["at"]))})
        else:
            other = [b for b in B["texts"] if b["layer"] == a["layer"] and math.dist(a["at"], b["at"]) <= 0.3]
            res.append({"kind": "only here" if not other else "text changed", "text": a["text"],
                        "at": _r(list(a["at"])), "other_text_there": other[0]["text"] if other else None})
    return res


def dim_diff(A, B):
    res = []
    for a in A["dims"]:
        ok = False
        for b in B["dims"]:
            if ((math.dist(a["a"], b["a"]) <= TOL and math.dist(a["b"], b["b"]) <= TOL) or
                    (math.dist(a["a"], b["b"]) <= TOL and math.dist(a["b"], b["a"]) <= TOL)):
                if a["text"] == b["text"]:
                    ok = True
                    break
        if not ok:
            res.append({"text": a["text"], "a": _r(list(a["a"])), "b": _r(list(a["b"])), "dimline": _r(list(a["dimline"]))})
    return res


def struct_diff(A, B):
    res = []
    for a in A["struct"]:
        if not any(a["poly"].symmetric_difference(b["poly"]).area < 0.01 for b in B["struct"]):
            x0, y0, x1, y1 = a["poly"].bounds
            res.append({"bbox": _r([x0, y0, x1, y1]), "size": f"{x1 - x0:.2f} x {y1 - y0:.2f}", "sources": a["sources"]})
    return res


# ----------------------------------------------------------------------------- regions
def _cluster(items, gap=0.6):
    """items: list of (bbox, payload) -> clusters of overlapping (bbox expanded by gap)."""
    n = len(items)
    parent = list(range(n))

    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    bbs = [it[0] for it in items]
    for i in range(n):
        for j in range(i + 1, n):
            a, b = bbs[i], bbs[j]
            if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                ra, rb = f(i), f(j)
                if ra != rb:
                    parent[ra] = rb
    cl = defaultdict(list)
    for i in range(n):
        cl[f(i)].append(items[i])
    return list(cl.values())


def _region_signature(F, R, layers):
    """geometry of floor F clipped to region polygon R (for variant grouping)."""
    return {lay: _union(F, lay)[0].intersection(R) for lay in layers}


def _sig_equal(F1, F2, R, layers):
    for lay in layers:
        for X, Y in ((F1, F2), (F2, F1)):
            if only_in(X, Y, lay, clip=R):
                return False
    return True


def _nearest_rooms(Fref, x, y, k=2, maxd=4.0):
    T = [t for t in Fref["texts"] if t["layer"] in ("TEXT", "-A-TEXT") and t["text"]
         and not re.match(r"^[+\-]?\s*[\d.]+$", t["text"])]
    T.sort(key=lambda t: math.dist(t["at"], (x, y)))
    out = []
    for t in T:
        if math.dist(t["at"], (x, y)) > maxd:
            break
        if t["text"] not in out:
            out.append(t["text"])
        if len(out) >= k:
            break
    return out


def _build_regions(items, prefix, gap, F, labels, R):
    clusters = _cluster(items, gap=gap)
    regions = []
    for cl in clusters:
        bbs = [it[0] for it in cl]
        x0 = min(b[0] for b in bbs); y0 = min(b[1] for b in bbs)
        x1 = max(b[2] for b in bbs); y1 = max(b[3] for b in bbs)
        floors = sorted({it[1]["floor"] for it in cl})
        lay_len = defaultdict(float)
        for it in cl:
            lay_len[it[1]["layer"]] += it[1]["len"]
        geo_len = sum(it[1]["len"] for it in cl if not it[1]["layer"].startswith(("BLOCK", "TEXT", "DIM")))
        regions.append({"bbox": [x0, y0, x1, y1], "items": cl, "floors_differing_from_ref": floors,
                        "layers": dict(lay_len), "geo_len": geo_len})
    regions.sort(key=lambda r: (-(r["bbox"][1] + r["bbox"][3]) / 2, r["bbox"][0]))
    out_regions = []
    for i, rg in enumerate(regions, 1):
        x0, y0, x1, y1 = rg["bbox"]
        Rbox = box(x0 - 0.1, y0 - 0.1, x1 + 0.1, y1 + 0.1)
        geo_lays = sorted({it[1]["layer"] for it in rg["items"] if not it[1]["layer"].startswith(("BLOCK", "TEXT", "DIM"))})
        variants = []
        for a in labels:
            for v in variants:
                if _sig_equal(F[a], F[v[0]], Rbox, geo_lays) and _ann_equal(F[a], F[v[0]], Rbox):
                    v.append(a)
                    break
            else:
                variants.append([a])
        desc = []
        for lay in sorted(rg["layers"]):
            per = defaultdict(lambda: [0.0, 0.0, 0, 0])
            for it in rg["items"]:
                if it[1]["layer"] == lay:
                    here = it[1]["side"].endswith("here")
                    per[it[1]["floor"]][0 if here else 1] += it[1]["len"]
                    per[it[1]["floor"]][2 if here else 3] += 1
            parts = []
            for f_, (h, rr, nh, nr) in sorted(per.items()):
                if lay.startswith(("BLOCK", "TEXT", "DIM")):
                    parts.append(f"{f_}:+{nh}/-{nr}")
                else:
                    parts.append(f"{f_}:+{h:.2f}/-{rr:.2f}")
            desc.append(f"{lay} [" + ", ".join(parts) + "]")
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inside = -1.0 <= cx <= 20.5 and -2.5 <= cy <= 40.5
        out_regions.append({
            "id": f"{prefix}{i:02d}", "bbox": _r([x0, y0, x1, y1], 2), "center": _r([cx, cy], 2),
            "in_building": inside, "rooms_near": _nearest_rooms(R, cx, cy) if inside else [],
            "floors_differing_from_ref": rg["floors_differing_from_ref"],
            "variants": variants, "geometry_len": _r(rg["geo_len"], 2),
            "changes": desc,
        })
    return out_regions


# ----------------------------------------------------------------------------- main compare
def compare_floors(ref=None, png=True, features=None):
    t0 = time.time()
    fls = all_floors()
    F = features or {}
    for fl in fls:
        if fl.label not in F:
            F[fl.label] = extract(fl)
            print(f"  extracted {fl.label} ({time.time() - t0:.0f}s)")
    labels = [fl.label for fl in fls]
    lays = [l for l in LINE_LAYERS if any(F[x]["lines"].get(l) for x in labels)]
    # pairwise matrices
    matrix = {lay: {} for lay in lays}
    for lay in lays:
        for a in labels:
            matrix[lay][a] = {}
            for b in labels:
                if a == b:
                    matrix[lay][a][b] = 0.0
                    continue
                matrix[lay][a][b] = _r(sum(p.length for p in only_in(F[a], F[b], lay)), 2)
        print(f"  matrix {lay} ({time.time() - t0:.0f}s)")
    blk_m = {a: {b: len(insert_diff(F[a], F[b])) for b in labels} for a in labels}
    txt_m = {a: {b: len(text_diff(F[a], F[b])) for b in labels} for a in labels}
    dim_m = {a: {b: len(dim_diff(F[a], F[b])) for b in labels} for a in labels}
    st_m = {a: {b: len(struct_diff(F[a], F[b])) for b in labels} for a in labels}

    def total(a, b):
        return (sum(matrix[l][a][b] + matrix[l][b][a] for l in lays) + blk_m[a][b] + blk_m[b][a]
                + txt_m[a][b] + txt_m[b][a] + dim_m[a][b] + dim_m[b][a] + st_m[a][b] + st_m[b][a])
    tot = {a: {b: _r(total(a, b), 2) for b in labels} for a in labels}
    # identical groups (all layers zero, no block/text/dim/struct difference)
    groups, seen = [], set()
    for a in labels:
        if a in seen:
            continue
        g = [a] + [b for b in labels if b != a and b not in seen and tot[a][b] == 0]
        seen.update(g)
        groups.append(g)
    # reference = medoid on W + WIN + blocks
    def wscore(a):
        return sum(matrix["W"][a][b] + matrix["W"][b][a] + (matrix.get("WIN", {}).get(a, {}).get(b, 0) +
                                                            matrix.get("WIN", {}).get(b, {}).get(a, 0)) +
                   blk_m[a][b] + blk_m[b][a] for b in labels)
    ref = ref or min(labels, key=wscore)
    R = F[ref]
    print(f"  reference floor = {ref}")
    # pieces vs reference, then regions
    items = []
    per_floor = {}
    for a in labels:
        if a == ref:
            continue
        pf = {"only_here": {}, "only_ref": {}, "blocks_only_here": [], "blocks_only_ref": [],
              "texts_only_here": text_diff(F[a], R), "texts_only_ref": text_diff(R, F[a]),
              "dims_only_here": dim_diff(F[a], R), "dims_only_ref": dim_diff(R, F[a]),
              "struct_only_here": struct_diff(F[a], R), "struct_only_ref": struct_diff(R, F[a])}
        for lay in lays:
            for side, X, Y in (("only_here", F[a], R), ("only_ref", R, F[a])):
                ps = only_in(X, Y, lay)
                if ps:
                    pf[side][lay] = [{"len": _r(p.length, 3), "coords": _r([list(c) for c in p.coords], 3)} for p in ps]
                    for p in ps:
                        items.append((p.bounds, {"floor": a, "side": side, "layer": lay, "len": p.length}))
        for side, X, Y in (("blocks_only_here", F[a], R), ("blocks_only_ref", R, F[a])):
            for ins in insert_diff(X, Y):
                pf[side].append({"block": ins["block"], "layer": ins["layer"], "at": _r(list(ins["at"])),
                                 "rot": _r(ins["rot"], 1), "mirror": ins["mirror"]})
                x, y = ins["at"]
                items.append(((x - 0.3, y - 0.3, x + 0.3, y + 0.3),
                              {"floor": a, "side": side, "layer": "BLOCK " + ins["block"], "len": 0}))
        for side in ("texts_only_here", "texts_only_ref"):
            for t in pf[side]:
                x, y = t["at"]
                items.append(((x - 0.2, y - 0.2, x + 0.2, y + 0.2),
                              {"floor": a, "side": side, "layer": "TEXT " + t["text"], "len": 0}))
        per_floor[a] = pf
    # atypical floors (W difference far above the others, e.g. F02 with its terraces) get their
    # own region set; otherwise their widespread changes chain every region into one.
    wmean = {a: np.mean([matrix["W"][a][b] + matrix["W"][b][a] for b in labels if b != a]) for a in labels}
    med = float(np.median(list(wmean.values())))
    atypical = [a for a in labels if a != ref and wmean[a] > 2.5 * med]
    typical = [a for a in labels if a not in atypical]
    out_regions = []
    out_regions += _build_regions([it for it in items if it[1]["floor"] in typical], "R", REGION_GAP, F, labels, R)
    for a in atypical:
        # outline layers (MASS / 0) of an atypical floor = one region per layer; the rest
        # clustered with a tight gap
        sub = [it for it in items if it[1]["floor"] == a]
        regs = _build_regions([it for it in sub if it[1]["layer"] not in ("MASS", "0")], a + "-R", 0.05, F, labels, R)
        for lay in ("MASS", "0"):
            li = [it for it in sub if it[1]["layer"] == lay]
            if li:
                regs += _build_regions(li, f"{a}-{lay}-", 1e9, F, labels, R)
        out_regions += regs
    res = {"reference": ref, "floors": labels, "typical_floors": typical, "atypical_floors": atypical,
           "w_mean_diff": {a: _r(v, 2) for a, v in wmean.items()}, "tolerance_m": TOL, "min_piece_m": MIN_PIECE,
           "layers_compared": lays, "identical_groups": groups,
           "matrix": matrix, "blocks_matrix": blk_m, "texts_matrix": txt_m, "dims_matrix": dim_m,
           "struct_matrix": st_m, "total_matrix": tot,
           "per_floor_vs_ref": per_floor, "regions": out_regions,
           "elapsed_s": round(time.time() - t0)}
    if png:
        render_all(res, F, fls)
    return res


def _ann_equal(F1, F2, Rbox):
    def ins(F):
        return sorted((i["block"], round(i["at"][0], 2), round(i["at"][1], 2), round(i["rot"]) % 360, i["mirror"])
                      for i in F["inserts"] if Rbox.contains(Point(i["at"])))
    def txt(F):
        return sorted((t["text"], round(t["at"][0], 1), round(t["at"][1], 1))
                      for t in F["texts"] if t["layer"] in ("TEXT", "-A-TEXT") and Rbox.contains(Point(t["at"])))
    def dm(F):
        return sorted((d["text"], round(d["a"][0], 2), round(d["a"][1], 2), round(d["b"][0], 2), round(d["b"][1], 2))
                      for d in F["dims"] if Rbox.contains(Point(d["a"])) and Rbox.contains(Point(d["b"])))
    a = (ins(F1), txt(F1), dm(F1)); b = (ins(F2), txt(F2), dm(F2))
    if a == b:
        return True
    # tolerance compare for inserts
    i1, i2 = ins(F1), ins(F2)
    if len(i1) != len(i2) or a[1] != b[1] or a[2] != b[2]:
        return False
    return all(x[0] == y[0] and abs(x[1] - y[1]) <= 0.03 and abs(x[2] - y[2]) <= 0.03 and x[3] == y[3] and x[4] == y[4]
               for x, y in zip(i1, i2))


# ----------------------------------------------------------------------------- rendering
def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Tahoma"
    return plt


def _draw_lines(ax, geoms, **kw):
    for g in geoms:
        if g.is_empty:
            continue
        gs = [g] if g.geom_type == "LineString" else list(getattr(g, "geoms", []))
        for s in gs:
            if s.geom_type != "LineString":
                continue
            xs, ys = s.xy
            ax.plot(xs, ys, **kw)


def render_all(res, F, fls):
    plt = _plt()
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D
    OUT.mkdir(parents=True, exist_ok=True)
    ref = res["reference"]
    R = F[ref]
    labels = res["floors"]
    XL, YL = (-1.8, 20.5), (-2.8, 41.0)
    # 1) overlay of W: common geometry grey, floor-specific coloured
    fig, ax = plt.subplots(figsize=(14, 28))
    common = _union(R, "W")[0]
    for a in labels:
        if a == ref:
            continue
        common = common.intersection(_union(F[a], "W")[1])
    _draw_lines(ax, [common], color="#9a9a9a", lw=0.6)
    for a in labels:
        others = [b for b in labels if b != a]
        mine = _union(F[a], "W")[0]
        # pieces of this floor that are missing on at least one other floor
        diff_any = [p for b in others for p in only_in(F[a], F[b], "W")]
        _draw_lines(ax, diff_any, color=FLOOR_COLORS[a], lw=1.6, alpha=0.8)
    ax.legend(handles=[Line2D([], [], color="#9a9a9a", lw=1, label="مشترك في كل الأدوار")] +
              [Line2D([], [], color=c, lw=2, label=f"{k}: غير موجود في دور آخر على الأقل") for k, c in FLOOR_COLORS.items()],
              loc="upper right", fontsize=8)
    ax.set_aspect("equal"); ax.set_xlim(*XL); ax.set_ylim(*YL); ax.grid(True, lw=0.2)
    ax.set_title("تراكب طبقة W لكل الأدوار في الإطار المحلي — الملوّن = خطوط ليست في كل الأدوار", fontsize=12)
    fig.savefig(OUT / "overlay_W.png", dpi=100, bbox_inches="tight"); plt.close(fig)

    # 2) per-floor diff vs reference
    reg_by_floor = defaultdict(list)
    for rg in res["regions"]:
        for f_ in rg["floors_differing_from_ref"]:
            reg_by_floor[f_].append(rg)
    for a in labels:
        if a == ref:
            continue
        fig, ax = plt.subplots(figsize=(14, 28))
        for lay, col in (("W", "#c8c8c8"), ("WIN", "#bfe8ef"), ("ST", "#e0d0c8"), ("Etabs-col", "#bfe5bf")):
            _draw_lines(ax, [_union(R, lay)[0]], color=col, lw=0.5)
        pf = res["per_floor_vs_ref"][a]
        for side, col in (("only_here", "#d62728"), ("only_ref", "#1f77b4")):
            for lay, ps in pf[side].items():
                for p in ps:
                    xs, ys = zip(*p["coords"])
                    ax.plot(xs, ys, color=col, lw=1.8 if lay in ("W", "WIN", "Etabs-col") else 1.0,
                            ls="-" if lay in ("W", "WIN", "Etabs-col", "COL") else "--", alpha=0.9)
        for side, col, mk in (("blocks_only_here", "#d62728", "s"), ("blocks_only_ref", "#1f77b4", "s")):
            for b in pf[side]:
                ax.plot(*b["at"], marker=mk, ms=7, mfc="none", mec=col, mew=1.5)
                ax.text(b["at"][0] + 0.15, b["at"][1] + 0.1, b["block"], fontsize=6, color=col)
        for side, col in (("texts_only_here", "#d62728"), ("texts_only_ref", "#1f77b4")):
            for t in pf[side]:
                ax.text(t["at"][0], t["at"][1], t["text"], fontsize=6, color=col,
                        bbox=dict(boxstyle="round,pad=0.1", fc="white", ec=col, lw=0.5))
        for rg in reg_by_floor.get(a, []):
            x0, y0, x1, y1 = rg["bbox"]
            if not rg["in_building"]:
                continue
            ax.add_patch(Rectangle((x0 - 0.15, y0 - 0.15), x1 - x0 + 0.3, y1 - y0 + 0.3, fill=False, ec="#ff00ff", lw=1.0))
            ax.text(x1 + 0.2, y1 + 0.1, rg["id"], fontsize=8, color="#ff00ff", fontweight="bold")
        ax.legend(handles=[Line2D([], [], color="#d62728", lw=2, label=f"موجود في {a} فقط (ليس في {ref})"),
                           Line2D([], [], color="#1f77b4", lw=2, label=f"موجود في {ref} وغير موجود في {a}"),
                           Line2D([], [], color="#d62728", lw=1, ls="--", label="طبقات ثانوية (DASH/PR/ST/MASS...) — متقطع"),
                           Line2D([], [], color="#ff00ff", lw=1, label="منطقة اختلاف (R..)")],
                  loc="upper right", fontsize=8)
        ax.set_aspect("equal"); ax.set_xlim(*XL); ax.set_ylim(*YL); ax.grid(True, lw=0.2)
        ax.set_title(f"{a} مقارنةً بالدور المرجعي {ref} — أحمر = في {a} فقط، أزرق = في {ref} فقط", fontsize=12)
        fig.savefig(OUT / f"diff_{a}.png", dpi=100, bbox_inches="tight"); plt.close(fig)

    # 3) regions map on the reference
    fig, ax = plt.subplots(figsize=(14, 28))
    for lay, col in (("W", "#9a9a9a"), ("WIN", "#9fd8e3"), ("Etabs-col", "#7fc97f"), ("ST", "#c49c94")):
        _draw_lines(ax, [_union(R, lay)[0]], color=col, lw=0.6)
    for rg in res["regions"]:
        if not rg["in_building"] or "-" in rg["id"]:
            continue
        x0, y0, x1, y1 = rg["bbox"]
        n = len(rg["floors_differing_from_ref"])
        col = "#d62728" if n >= 3 else "#ff7f0e"
        ax.add_patch(Rectangle((x0 - 0.15, y0 - 0.15), x1 - x0 + 0.3, y1 - y0 + 0.3, fill=True, fc=col, alpha=0.15, ec=col, lw=1.2))
        var = " | ".join("".join(v_[1:] for v_ in v) for v in rg["variants"])
        ax.text(x1 + 0.2, (y0 + y1) / 2, f"{rg['id']}  {var}", fontsize=6.5, color=col, fontweight="bold")
    ax.set_aspect("equal"); ax.set_xlim(*XL); ax.set_ylim(*YL); ax.grid(True, lw=0.2)
    ax.set_title(f"مناطق الاختلاف بين الأدوار على مسقط {ref} — بجانب كل منطقة: مجموعات الأدوار المتطابقة فيها "
                 f"(02|0345678 = F02 مختلف والباقي متطابق)", fontsize=10)
    fig.savefig(OUT / "regions_map.png", dpi=100, bbox_inches="tight"); plt.close(fig)

    # 4) per-region panels (one panel per floor)
    for rg in res["regions"]:
        if not rg["in_building"] or rg["geometry_len"] < 0.05 and not any(c.startswith(("BLOCK", "TEXT")) for c in rg["changes"]):
            continue
        if "-" in rg["id"] and (rg["geometry_len"] < 3.0 or rg["geometry_len"] > 60):   # atypical floor: big ones only
            continue
        x0, y0, x1, y1 = rg["bbox"]
        pad = 1.0
        w = max(x1 - x0, 1.5) + 2 * pad; h = max(y1 - y0, 1.5) + 2 * pad
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        Z = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        ncol = 4
        nrow = int(math.ceil(len(labels) / ncol))
        pw = 4.0
        fig, axs = plt.subplots(nrow, ncol, figsize=(pw * ncol, nrow * pw * min(max(h / w, 0.35), 2.2) + 0.9))
        axs = np.atleast_1d(axs).ravel()
        for ax in axs[len(labels):]:
            ax.axis("off")
        var_txt = "   ".join("=".join(v) for v in rg["variants"])
        NL = chr(10)
        axs[-1].text(0.02, 0.45, "مجموعات متطابقة داخل المنطقة:" + NL + var_txt.replace("   ", NL), fontsize=9,
                     transform=axs[-1].transAxes, va="top")
        axs[-1].text(0.02, 0.98, NL.join(rg["changes"])[:600], fontsize=6, transform=axs[-1].transAxes, va="top",
                     wrap=True)
        for ax, a in zip(axs, labels):
            for lay, col, lw in (("W", "#d62728", 0.9), ("WIN", "#17becf", 0.8), ("Etabs-col", "#2ca02c", 0.9),
                                 ("DASH", "#bcbd22", 0.5), ("ST", "#8c564b", 0.5), ("PR", "#9467bd", 0.5),
                                 ("try", "#ff7f0e", 0.6), ("COL", "#006400", 0.6)):
                g = _union(F[a], lay)[0]
                if not g.is_empty:
                    _draw_lines(ax, [g.intersection(box(*Z))], color=col, lw=lw)
            for i_ in F[a]["inserts"]:
                if Z[0] <= i_["at"][0] <= Z[2] and Z[1] <= i_["at"][1] <= Z[3] and re.match(r"^D\d+W\d+$", i_["block"]):
                    ax.plot(*i_["at"], marker="o", ms=3, color="#2ca02c")
                    ax.text(i_["at"][0], i_["at"][1], i_["block"], fontsize=6, color="#2ca02c")
            for t in F[a]["texts"]:
                if t["layer"] in ("TEXT", "-A-TEXT") and Z[0] <= t["at"][0] <= Z[2] and Z[1] <= t["at"][1] <= Z[3]:
                    ax.text(t["at"][0], t["at"][1], t["text"], fontsize=7, color="#333")
            ax.add_patch(Rectangle((x0 - 0.1, y0 - 0.1), x1 - x0 + 0.2, y1 - y0 + 0.2, fill=False, ec="#ff00ff", lw=0.6, ls=":"))
            same_as_ref = a == ref or a not in rg["floors_differing_from_ref"]
            ax.set_title(f"{a}" + (" (=المرجع)" if same_as_ref else " ≠ المرجع"), fontsize=10,
                         color="#333" if same_as_ref else "#d62728")
            ax.set_xlim(Z[0], Z[2]); ax.set_ylim(Z[1], Z[3]); ax.set_aspect("equal")
            ax.set_xticks([]); ax.set_yticks([])
        fig.suptitle(f"{rg['id']}  مركز ({cx:.2f}, {cy:.2f})  {' / '.join(rg['rooms_near'])}   — المرجع {ref}", fontsize=11)
        fig.savefig(OUT / f"region_{rg['id']}.png", dpi=110, bbox_inches="tight"); plt.close(fig)


# ----------------------------------------------------------------------------- doc
def write_doc(res, path=DOC):
    L = []
    ref = res["reference"]
    labels = res["floors"]
    L.append("# مقارنة الأدوار (F02–F08) — ما الذي يتكرر وما الذي يختلف")
    L.append("")
    L.append("> **ملف مُولَّد آليًا** بواسطة `python tools/floor_compare.py` (لا تعدّله يدويًا — التفسير والأسئلة في "
             "`docs/findings/structure_diff.md`). الإحداثيات في الإطار المحلي لـ `diwan_common` بالمتر، "
             f"وسماحية المطابقة {res['tolerance_m'] * 100:.0f} سم، وتُهمل القطع الأقصر من {res['min_piece_m'] * 100:.0f} سم.")
    L.append("")
    L.append(f"**الدور المرجعي** (الأقل اختلافًا عن الباقي في W + WIN + البلوكات): **{ref}**.")
    L.append("")
    L.append("## 1) مجموعات الأدوار المتطابقة تمامًا (كل الطبقات + البلوكات + النصوص + الأبعاد)")
    L.append("")
    for g in res["identical_groups"]:
        L.append(f"- {' = '.join(g)}" + ("" if len(g) > 1 else " (لا يطابقه أي دور آخر تمامًا)"))
    L.append("")
    L.append("## 2) مصفوفة الاختلاف — طبقة W (طول الخطوط بالمتر الموجودة في دور الصف وغير الموجودة في دور العمود)")
    L.append("")
    L.append("| | " + " | ".join(labels) + " |")
    L.append("|---|" + "---|" * len(labels))
    for a in labels:
        L.append(f"| **{a}** | " + " | ".join(f"{res['matrix']['W'][a][b]:.2f}" if a != b else "—" for b in labels) + " |")
    L.append("")
    L.append(f"### الاختلاف عن المرجع {ref} لكل طبقة (م: في الدور وليس في المرجع / في المرجع وليس في الدور) + البلوكات/النصوص/الأبعاد")
    L.append("")
    lays = res["layers_compared"]
    L.append("| الدور | " + " | ".join(lays) + " | بلوكات | نصوص الغرف | أبعاد | إنشائي |")
    L.append("|---|" + "---|" * (len(lays) + 4))
    for a in labels:
        if a == ref:
            continue
        cells = []
        for lay in lays:
            x, y = res["matrix"][lay][a][ref], res["matrix"][lay][ref][a]
            cells.append("0" if x == 0 and y == 0 else f"+{x:.2f}/−{y:.2f}")
        cells.append(f"+{res['blocks_matrix'][a][ref]}/−{res['blocks_matrix'][ref][a]}")
        cells.append(f"+{res['texts_matrix'][a][ref]}/−{res['texts_matrix'][ref][a]}")
        cells.append(f"+{res['dims_matrix'][a][ref]}/−{res['dims_matrix'][ref][a]}")
        cells.append(f"+{res['struct_matrix'][a][ref]}/−{res['struct_matrix'][ref][a]}")
        L.append(f"| {a} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## 3) مناطق الاختلاف (داخل المبنى)")
    L.append("")
    L.append("`variants` = مجموعات الأدوار المتطابقة داخل حدود المنطقة. الصور: `output/floor_compare/region_RNN.png` "
             "(لوحة لكل دور) و`regions_map.png` و`diff_F0x.png`.")
    L.append("")
    L.append("| المنطقة | المركز (x, y) | المدى bbox | قرب | الأدوار المختلفة عن المرجع | المجموعات المتطابقة | التغييرات (طبقة [دور:+في الدور/−في المرجع]) |")
    L.append("|---|---|---|---|---|---|---|")
    for rg in res["regions"]:
        if not rg["in_building"]:
            continue
        var = " · ".join("=".join(v) for v in rg["variants"])
        L.append(f"| {rg['id']} | {rg['center'][0]:.2f}, {rg['center'][1]:.2f} | {rg['bbox']} | {' / '.join(rg['rooms_near'])} | "
                 f"{', '.join(rg['floors_differing_from_ref'])} | {var} | {'; '.join(rg['changes'])} |")
    L.append("")
    outside = [rg for rg in res["regions"] if not rg["in_building"]]
    if outside:
        L.append("## 4) اختلافات خارج المبنى (إطار اللوحة / العنوان / الأبعاد الخارجية)")
        L.append("")
        for rg in outside:
            L.append(f"- {rg['id']} عند ({rg['center'][0]:.1f}, {rg['center'][1]:.1f}): أدوار {', '.join(rg['floors_differing_from_ref'])} — "
                     f"{'; '.join(rg['changes'])}")
        L.append("")
    L.append("## 5) البلوكات والنصوص المختلفة عن المرجع (تفصيل)")
    L.append("")
    for a in labels:
        if a == ref:
            continue
        pf = res["per_floor_vs_ref"][a]
        rows = []
        for b in pf["blocks_only_here"]:
            rows.append(f"+ بلوك {b['block']} عند ({b['at'][0]:.2f}, {b['at'][1]:.2f}) دوران {b['rot']}° {'معكوس' if b['mirror'] else ''}")
        for b in pf["blocks_only_ref"]:
            rows.append(f"− بلوك {b['block']} (موجود في {ref}) عند ({b['at'][0]:.2f}, {b['at'][1]:.2f})")
        for t in pf["texts_only_here"]:
            rows.append(f"+ نص «{t['text']}» ({t['kind']}) عند ({t['at'][0]:.2f}, {t['at'][1]:.2f})")
        for t in pf["texts_only_ref"]:
            rows.append(f"− نص «{t['text']}» (في {ref}) عند ({t['at'][0]:.2f}, {t['at'][1]:.2f})")
        for s in pf["struct_only_here"]:
            rows.append(f"+ عنصر إنشائي {s['size']} عند {s['bbox']}")
        for s in pf["struct_only_ref"]:
            rows.append(f"− عنصر إنشائي {s['size']} (في {ref}) عند {s['bbox']}")
        L.append(f"**{a}**: " + ("لا شيء" if not rows else ""))
        for r_ in rows:
            L.append(f"  - {r_}")
        L.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer, np.bool_)):
        return o.item()
    return o


def main():
    ap = argparse.ArgumentParser(description="compare all floors layer by layer in the local frame")
    ap.add_argument("--ref", help="reference floor label, e.g. F05 (default: medoid)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--no-doc", action="store_true")
    a = ap.parse_args()
    ref = a.ref if not a.ref or a.ref.startswith("F") else f"F{int(a.ref):02d}"
    res = compare_floors(ref=ref, png=not a.no_png)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(_jsonable(res), ensure_ascii=False, indent=1), encoding="utf-8")
    if not a.no_doc:
        print("doc:", write_doc(res))
    print("identical groups:", res["identical_groups"], " reference:", res["reference"])
    for rg in res["regions"]:
        print(f"  {rg['id']} {rg['center']} {rg['rooms_near']} differ={rg['floors_differing_from_ref']} variants={rg['variants']} :: {'; '.join(rg['changes'])[:200]}")
    print(f"elapsed {res['elapsed_s']} s")


if __name__ == "__main__":
    main()
