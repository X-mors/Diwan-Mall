import json
import math
import ezdxf
from shapely.geometry import box, Point, LinearRing
from shapely.ops import unary_union

SRC = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor.dxf"
doc = ezdxf.readfile(SRC)
msp = doc.modelspace()

ROT_DEG = 9.999657166117375
PIVOT = (230.0, 785.0)
theta = math.radians(-ROT_DEG)
ct, st = math.cos(theta), math.sin(theta)

def rot(p):
    x, y = p[0] - PIVOT[0], p[1] - PIVOT[1]
    return (x * ct - y * st, x * st + y * ct)

theta2 = math.radians(ROT_DEG)
ct2, st2 = math.cos(theta2), math.sin(theta2)
def unrot(p):
    x, y = p
    return (x * ct2 - y * st2 + PIVOT[0], x * st2 + y * ct2 + PIVOT[1])

# --- structural footprints (global coords) on COL/Etabs-col layers ---
# Two different uses need two different sets:
#  - col_union_small: genuine COLUMNS (both dims small, <=0.8m) - used to drop
#    a wall-candidate that is mostly just a column's own outline.
#  - col_union_all: EVERY such element regardless of size (columns, shear
#    walls, stair/shaft cores - some of these are large, e.g. a 3x4.5m stair
#    core) - used only to stop wall-run BRIDGING across a real obstruction
#    (never to delete a wall candidate: a long wall merely passing near/along
#    a big shear-wall core is still a real wall).
col_polys_small = []
col_polys_all = []
for e in msp:
    if e.dxf.layer in ("COL", "Etabs-col") and e.dxftype() == "LWPOLYLINE":
        pts = [(p[0], p[1]) for p in e.get_points()]
        if len(pts) >= 3:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            w, h = max(xs)-min(xs), max(ys)-min(ys)
            poly = box(min(xs) - 0.03, min(ys) - 0.03, max(xs) + 0.03, max(ys) + 0.03)
            col_polys_all.append(poly)
            # genuine column/pier: short side <=0.85m and long side <=2.6m.
            # Bigger elongated "Etabs-col" entries (e.g. 3-4.5m) are shaft/
            # stair-core outlines, not columns - excluding a real partition
            # wall just because it coincides with one of those fragments the
            # interior wall network and misclassifies whole rooms as exterior.
            if min(w, h) <= 0.85 and max(w, h) <= 2.6:
                col_polys_small.append(poly)
col_union = unary_union(col_polys_small) if col_polys_small else None  # used only to drop a wall-candidate that IS a column
# obstruction_union (bridging-block + later splitting) uses the SAME small/
# medium-sized set (columns AND duct/شفت openings up to ~2.6m, e.g. the
# منور case) - NOT the large 3-4.5m elevator/stair-core outlines. Blocking
# bridging across those big cores breaks the surrounding walls' connectivity
# to the rest of the building and misclassifies whole rooms as exterior.
obstruction_union = col_union
print("structural footprints used (columns + duct/shaft-sized, <=2.6m):", len(col_polys_small), " / excluded from this (large cores):", len(col_polys_all) - len(col_polys_small))

# --- raw wall lines (layer W) rotated ---
raw = []
for e in msp:
    if e.dxftype() == "LINE" and e.dxf.layer == "W":
        s = rot((e.dxf.start.x, e.dxf.start.y))
        en = rot((e.dxf.end.x, e.dxf.end.y))
        length = math.hypot(en[0]-s[0], en[1]-s[1])
        if length < 0.01:
            continue
        raw.append((s, en, length))

TOL_ANG = 3.0
h_in, v_in = [], []
for s, e, length in raw:
    ang = math.degrees(math.atan2(e[1]-s[1], e[0]-s[0])) % 180
    if min(ang, 180-ang) <= TOL_ANG:
        h_in.append({"perp": (s[1]+e[1])/2, "a0": min(s[0],e[0]), "a1": max(s[0],e[0])})
    elif abs(ang-90) <= TOL_ANG:
        v_in.append({"perp": (s[0]+e[0])/2, "a0": min(s[1],e[1]), "a1": max(s[1],e[1])})

def merge_intervals(intervals, gap_tol):
    intervals = sorted(intervals)
    merged = []
    for a0, a1 in intervals:
        if merged and a0 <= merged[-1][1] + gap_tol:
            merged[-1] = (merged[-1][0], max(merged[-1][1], a1))
        else:
            merged.append((a0, a1))
    return merged

def cluster_bands(lines, tol=0.03):
    items = sorted(lines, key=lambda it: it["perp"])
    bands = []
    for it in items:
        placed = False
        for b in bands:
            if abs(b["perp_sum"]/b["n"] - it["perp"]) <= tol:
                b["items"].append(it); b["perp_sum"] += it["perp"]; b["n"] += 1
                placed = True; break
        if not placed:
            bands.append({"items": [it], "perp_sum": it["perp"], "n": 1})
    result = []
    for b in bands:
        perp = b["perp_sum"]/b["n"]
        intervals = merge_intervals([(it["a0"], it["a1"]) for it in b["items"]], 0.08)
        result.append({"perp": perp, "intervals": intervals})
    result.sort(key=lambda b: b["perp"])
    return result

MIN_FACE_LEN = 1.0   # keep at 1.0 for a CLEAN baseline union/classification; recovery of smaller real walls is handled separately, classified against this clean baseline ring rather than mixed into it
def consolidate(bands, min_face_len, dup_tol=0.10):
    kept = [b for b in bands if sum(a1-a0 for a0,a1 in b["intervals"]) >= min_face_len]
    kept.sort(key=lambda b: b["perp"])
    out = []
    for b in kept:
        if out and abs(b["perp"] - out[-1]["perp_avg"]) <= dup_tol:
            prev = out[-1]
            prev["intervals"] = merge_intervals(prev["intervals"] + b["intervals"], 0.08)
            prev["perp_avg"] = (prev["perp_avg"]*prev["n"] + b["perp"]) / (prev["n"]+1)
            prev["n"] += 1
        else:
            out.append({"perp_avg": b["perp"], "n": 1, "intervals": list(b["intervals"])})
    for b in out:
        b["perp"] = b["perp_avg"]
    return out

h_bands = consolidate(cluster_bands(h_in), MIN_FACE_LEN)
v_bands = consolidate(cluster_bands(v_in), MIN_FACE_LEN)
print("h_bands:", len(h_bands), " v_bands:", len(v_bands))

MIN_THICK, MAX_THICK, BRIDGE_GAP = 0.08, 0.32, 3.2  # tightened max thickness (was 0.48) to stop pairing column-sized gaps

def gap_hits_obstruction(orient, perp_lo, perp_hi, a0, a1, obstruction_union):
    """Does the rectangle spanning this candidate bridge-gap overlap a known
    column/shaft (Etabs-col/COL) footprint? If so, this is not a door/window
    opening to silently bridge across - it's a real break (e.g. a light well /
    منور, or a column), so the two sides must stay separate walls."""
    if obstruction_union is None:
        return False
    if orient == "H":
        corners = [(a0, perp_lo), (a0, perp_hi), (a1, perp_hi), (a1, perp_lo)]
    else:
        corners = [(perp_lo, a0), (perp_hi, a0), (perp_hi, a1), (perp_lo, a1)]
    gc = [unrot(c) for c in corners]
    from shapely.geometry import Polygon
    rect = Polygon(gc)
    if not rect.is_valid or rect.area <= 0:
        return False
    return rect.intersection(obstruction_union).area / rect.area > 0.5

def merge_intervals_avoid_obstruction(intervals, gap_tol, orient, perp_lo, perp_hi, obstruction_union):
    intervals = sorted(intervals)
    merged = []
    for a0, a1 in intervals:
        if merged and a0 <= merged[-1][1] + gap_tol:
            if gap_hits_obstruction(orient, perp_lo, perp_hi, merged[-1][1], a0, obstruction_union):
                merged.append((a0, a1))  # keep separate - real obstruction in the gap
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], a1))
        else:
            merged.append((a0, a1))
    return merged

def pair_bands_wide(bands, min_thick, max_thick, bridge_gap, orient, obstruction_union, max_lookahead=3):
    bands = sorted(bands, key=lambda b: b["perp"])
    n = len(bands)
    used = [False]*n
    walls = []
    for i in range(n):
        if used[i]:
            continue
        for k in range(1, max_lookahead+1):
            j = i + k
            if j >= n or used[j]:
                continue
            gap = bands[j]["perp"] - bands[i]["perp"]
            if gap > max_thick:
                break
            if gap < min_thick:
                continue
            combined = bands[i]["intervals"] + bands[j]["intervals"]
            perp_lo, perp_hi = bands[i]["perp"], bands[j]["perp"]
            for a0, a1 in merge_intervals_avoid_obstruction(combined, bridge_gap, orient, perp_lo, perp_hi, obstruction_union):
                if a1 - a0 >= 0.3:
                    walls.append({"perp": (bands[i]["perp"]+bands[j]["perp"])/2, "thick": gap, "a0": a0, "a1": a1, "len": a1-a0})
            used[i] = used[j] = True
            break
    unpaired = [bands[i] for i in range(n) if not used[i]]
    return walls, unpaired

h_walls, h_unpaired = pair_bands_wide(h_bands, MIN_THICK, MAX_THICK, BRIDGE_GAP, "H", obstruction_union)
v_walls, v_unpaired = pair_bands_wide(v_bands, MIN_THICK, MAX_THICK, BRIDGE_GAP, "V", obstruction_union)
print("h_walls:", len(h_walls), " unpaired h:", len(h_unpaired))
print("v_walls:", len(v_walls), " unpaired v:", len(v_unpaired))

print()
print("unpaired h-bands (these did NOT become walls - review):")
for b in h_unpaired:
    tot = sum(a1-a0 for a0,a1 in b["intervals"])
    print(f"  y={b['perp']:.3f}  total_len={tot:.2f}  n_seg={len(b['intervals'])}")
print("unpaired v-bands:")
for b in v_unpaired:
    tot = sum(a1-a0 for a0,a1 in b["intervals"])
    print(f"  x={b['perp']:.3f}  total_len={tot:.2f}  n_seg={len(b['intervals'])}")

def build_walls(h_walls, v_walls):
    walls = []
    for w in h_walls:
        walls.append({"orient":"H","x0":w["a0"],"x1":w["a1"],"y0":w["perp"]-w["thick"]/2,"y1":w["perp"]+w["thick"]/2,"len":w["len"],"thick":w["thick"],"cy":w["perp"]})
    for w in v_walls:
        walls.append({"orient":"V","y0":w["a0"],"y1":w["a1"],"x0":w["perp"]-w["thick"]/2,"x1":w["perp"]+w["thick"]/2,"len":w["len"],"thick":w["thick"],"cx":w["perp"]})
    return walls

walls = build_walls(h_walls, v_walls)

# exclude walls that are MOSTLY a column footprint (a short stub that IS a
# column), not walls that merely pass through/beside an embedded column.
if col_union is not None:
    kept = []
    dropped = []
    for w in walls:
        # build the wall rectangle in GLOBAL coords (rotate the 4 corners)
        corners = [(w["x0"],w["y0"]), (w["x0"],w["y1"]), (w["x1"],w["y1"]), (w["x1"],w["y0"])]
        gc = [unrot(c) for c in corners]
        from shapely.geometry import Polygon
        rect = Polygon(gc)
        inter = rect.intersection(col_union)
        ratio = inter.area / rect.area if rect.area > 0 else 0
        if ratio > 0.90:
            dropped.append((w, ratio))
        else:
            kept.append(w)
    print(f"\ndropped {len(dropped)} wall-candidates that are MOSTLY a column footprint (ratio>0.5)")
    for w, ratio in dropped:
        print("  DROPPED (column):", w["orient"], "len=", round(w["len"],2), "thick=", round(w["thick"],2), "overlap_ratio=", round(ratio,2))
    walls = kept

def dedupe_overlapping_walls(walls):
    """Two same-orientation walls whose centerlines are close (< 0.35m, i.e.
    closer than any real corridor) AND whose along-extent overlaps heavily are
    the same physical wall picked up twice via two different close band-pairs
    (e.g. 4 closely-stacked bands paired as (1,2) and (3,4) instead of being
    recognized as one face). Merge them: keep the union of extents, and the
    OUTER perp span (min low, max high) as the true thickness."""
    walls = list(walls)
    changed = True
    while changed:
        changed = False
        for i in range(len(walls)):
            for j in range(i+1, len(walls)):
                a, b = walls[i], walls[j]
                if a["orient"] != b["orient"]:
                    continue
                if a["orient"] == "H":
                    perp_gap = abs(a["cy"] - b["cy"])
                    ov = max(0, min(a["x1"],b["x1"]) - max(a["x0"],b["x0"]))
                    along_len = min(a["x1"]-a["x0"], b["x1"]-b["x0"])
                else:
                    perp_gap = abs(a["cx"] - b["cx"])
                    ov = max(0, min(a["y1"],b["y1"]) - max(a["y0"],b["y0"]))
                    along_len = min(a["y1"]-a["y0"], b["y1"]-b["y0"])
                if perp_gap <= 0.35 and along_len > 0 and ov/along_len > 0.3:
                    y0 = min(a["y0"], b["y0"]); y1 = max(a["y1"], b["y1"])
                    x0 = min(a["x0"], b["x0"]); x1 = max(a["x1"], b["x1"])
                    merged = {"orient": a["orient"], "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                              "thick": (y1-y0) if a["orient"]=="H" else (x1-x0)}
                    if a["orient"] == "H":
                        merged["len"] = x1 - x0
                        merged["cy"] = (y0+y1)/2
                    else:
                        merged["len"] = y1 - y0
                        merged["cx"] = (x0+x1)/2
                    new_walls = [w for k, w in enumerate(walls) if k not in (i, j)]
                    new_walls.append(merged)
                    walls = new_walls
                    changed = True
                    break
            if changed:
                break
    return walls

before_n = len(walls)
walls = dedupe_overlapping_walls(walls)
print(f"\nde-duplication: {before_n} -> {len(walls)} walls")

def split_walls_crossing_obstructions(walls, obstruction_union, margin=0.05):
    """A wall whose span was bridged straight through a column/shear-wall/
    shaft core (because only ONE of its two face-lines was actually broken
    there) still needs splitting: cut it at the obstruction's near/far edge
    along the wall's own axis, dropping the portion actually inside it."""
    if obstruction_union is None:
        return walls
    from shapely.geometry import Polygon
    out = []
    split_count = 0
    for w in walls:
        corners = [(w["x0"],w["y0"]), (w["x0"],w["y1"]), (w["x1"],w["y1"]), (w["x1"],w["y0"])]
        gc = [unrot(c) for c in corners]
        rect = Polygon(gc)
        inter = rect.intersection(obstruction_union)
        if inter.is_empty or inter.area / rect.area < 0.05:
            out.append(w)
            continue
        # project the obstruction intersection back onto the wall's own axis
        # by rotating its coords back into the wall's local (rotated) frame
        theta_back = math.radians(-ROT_DEG)
        ctb, stb = math.cos(theta_back), math.sin(theta_back)
        def to_local(p):
            x, y = p[0]-PIVOT[0], p[1]-PIVOT[1]
            return (x*ctb - y*stb, x*stb + y*ctb)
        geoms = list(inter.geoms) if hasattr(inter, "geoms") else [inter]
        local_pts = []
        for g in geoms:
            if g.is_empty:
                continue
            for p in g.exterior.coords:
                local_pts.append(to_local(p))
        if not local_pts:
            out.append(w)
            continue
        if w["orient"] == "H":
            axis_vals = [p[0] for p in local_pts]
        else:
            axis_vals = [p[1] for p in local_pts]
        obs_lo, obs_hi = min(axis_vals) - margin, max(axis_vals) + margin
        if w["orient"] == "H":
            lo, hi = w["x0"], w["x1"]
        else:
            lo, hi = w["y0"], w["y1"]
        pieces = []
        if obs_lo - lo >= 0.3:
            pieces.append((lo, obs_lo))
        if hi - obs_hi >= 0.3:
            pieces.append((obs_hi, hi))
        if not pieces:
            continue  # the whole wall was essentially just the obstruction itself
        split_count += 1
        for p0, p1 in pieces:
            nw = dict(w)
            if w["orient"] == "H":
                nw["x0"], nw["x1"] = p0, p1
                nw["len"] = p1 - p0
            else:
                nw["y0"], nw["y1"] = p0, p1
                nw["len"] = p1 - p0
            nw["needs_check"] = True  # cut point is approximate (obstruction bbox, not exact wall corner)
            out.append(nw)
    print(f"split {split_count} walls that were bridged straight through an obstruction")
    return out

# NOTE: do NOT split here - splitting fragments the wall network's topology,
# which the exterior/interior classifier (rebuild_v3b.py) relies on for good
# connectivity. Save the UNSPLIT (bridged) walls for classification, and save
# the split function's obstruction data separately so v3b can split only the
# final INTERIOR list, after classification is already decided.
with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v2_raw.json", "w") as f:
    json.dump({"walls": walls, "h_unpaired": h_unpaired, "v_unpaired": v_unpaired}, f)
print("\ntotal walls (bridged, unsplit) after column exclusion:", len(walls))

import pickle
with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\obstruction_union.pkl", "wb") as f:
    pickle.dump(obstruction_union, f)
