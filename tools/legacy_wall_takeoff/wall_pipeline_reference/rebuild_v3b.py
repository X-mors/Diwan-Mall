import json
from shapely.geometry import box, Point, LinearRing
from shapely.ops import unary_union

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v2_raw.json") as f:
    data = json.load(f)

walls = data["walls"]  # clean 82-wall baseline
h_unpaired = data["h_unpaired"]
v_unpaired = data["v_unpaired"]

# --- classify the CLEAN baseline only ---
polys = [box(w["x0"], w["y0"], w["x1"], w["y1"]) for w in walls]
union = unary_union(polys)
comps = list(union.geoms) if union.geom_type == "MultiPolygon" else [union]
print("baseline components:", len(comps), "areas:", sorted([round(c.area,2) for c in comps], reverse=True)[:6])

def sample_points(w, n=7):
    pts = []
    for i in range(n):
        t = i/(n-1)
        if w["orient"] == "H":
            pts.append((w["x0"]+t*(w["x1"]-w["x0"]), w["cy"]))
        else:
            pts.append((w["cx"], w["y0"]+t*(w["y1"]-w["y0"])))
    return pts

EXT_TOL = 0.22
main_comp = max(comps, key=lambda c: c.area)
main_hull = main_comp.convex_hull

def classify_against(w, comps):
    cx, cy = (w["x0"]+w["x1"])/2, (w["y0"]+w["y1"])/2
    center = Point(cx, cy)
    comp = min(comps, key=lambda c: c.distance(center))
    if comp is not main_comp and main_hull.contains(center):
        # a small component fully inside the main building's silhouette is an
        # isolated interior pocket (e.g. an elevator/stair shaft that failed
        # to bridge-connect to the rest of the network) - never exterior.
        ring = LinearRing(main_comp.exterior.coords)
        dists = [ring.distance(Point(p)) for p in sample_points(w)]
        return False, max(dists), comp.distance(center)
    ring = LinearRing(comp.exterior.coords)
    dists = [ring.distance(Point(p)) for p in sample_points(w)]
    return max(dists) <= EXT_TOL, max(dists), comp.distance(center)

for w in walls:
    is_ext, maxd, complink = classify_against(w, comps)
    w["is_exterior"] = is_ext
    w.setdefault("needs_check", False)

# --- now evaluate the leftover unpaired bands against this SAME clean baseline ring (not mixed into the union) ---
MODE_THICK = 0.12
recovered = []
for b in h_unpaired:
    for a0, a1 in b["intervals"]:
        if a1-a0 >= 0.3:
            recovered.append({"orient":"H","x0":a0,"x1":a1,"y0":b["perp"]-MODE_THICK/2,"y1":b["perp"]+MODE_THICK/2,
                               "len":a1-a0,"thick":MODE_THICK,"cy":b["perp"],"needs_check":True})
for b in v_unpaired:
    for a0, a1 in b["intervals"]:
        if a1-a0 >= 0.3:
            recovered.append({"orient":"V","y0":a0,"y1":a1,"x0":b["perp"]-MODE_THICK/2,"x1":b["perp"]+MODE_THICK/2,
                               "len":a1-a0,"thick":MODE_THICK,"cx":b["perp"],"needs_check":True})

for w in recovered:
    is_ext, maxd, complink = classify_against(w, comps)
    w["is_exterior"] = is_ext
    print(f"  recovered {w['orient']} len={w['len']:.2f} classify: {'EXT' if is_ext else 'INT'}  maxd={maxd:.2f} complink={complink:.2f}")

all_walls = walls + recovered
interior = [w for w in all_walls if not w["is_exterior"]]
exterior = [w for w in all_walls if w["is_exterior"]]
print()
print("interior (pre-split):", len(interior), " exterior:", len(exterior))

# --- now split only the CONFIRMED interior walls across real obstructions
# (columns/shear-walls/shafts) so a wall bridged straight through one (e.g. a
# duct/منور) becomes two separate schedule entries, as requested. Classification
# above already used the well-connected, unsplit geometry, so this doesn't
# disturb it. ---
import math, pickle
from shapely.geometry import Polygon

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\obstruction_union.pkl", "rb") as f:
    obstruction_union = pickle.load(f)

ROT_DEG = 9.999657166117375
PIVOT = (230.0, 785.0)
theta = math.radians(ROT_DEG)  # positive: rotated-frame -> global (inverse of rot())
ct, st = math.cos(theta), math.sin(theta)
def unrot(p):
    x, y = p[0], p[1]
    return (x*ct - y*st + PIVOT[0], x*st + y*ct + PIVOT[1])

def split_interior_across_obstructions(walls, obstruction_union, margin=0.05):
    if obstruction_union is None:
        return walls
    out = []
    split_count = 0
    theta_back = math.radians(-ROT_DEG)
    ctb, stb = math.cos(theta_back), math.sin(theta_back)
    def to_local(p):
        x, y = p[0]-PIVOT[0], p[1]-PIVOT[1]
        return (x*ctb - y*stb, x*stb + y*ctb)
    for w in walls:
        corners = [(w["x0"],w["y0"]), (w["x0"],w["y1"]), (w["x1"],w["y1"]), (w["x1"],w["y0"])]
        gc = [unrot(c) for c in corners]
        rect = Polygon(gc)
        inter = rect.intersection(obstruction_union)
        if inter.is_empty or inter.area / rect.area < 0.05:
            out.append(w)
            continue
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
        axis_vals = [p[0] for p in local_pts] if w["orient"] == "H" else [p[1] for p in local_pts]
        obs_lo, obs_hi = min(axis_vals) - margin, max(axis_vals) + margin
        lo, hi = (w["x0"], w["x1"]) if w["orient"] == "H" else (w["y0"], w["y1"])
        pieces = []
        if obs_lo - lo >= 0.3:
            pieces.append((lo, obs_lo))
        if hi - obs_hi >= 0.3:
            pieces.append((obs_hi, hi))
        if not pieces:
            continue
        split_count += 1
        for p0, p1 in pieces:
            nw = dict(w)
            if w["orient"] == "H":
                nw["x0"], nw["x1"] = p0, p1
            else:
                nw["y0"], nw["y1"] = p0, p1
            nw["len"] = p1 - p0
            nw["needs_check"] = True
            out.append(nw)
    print(f"split {split_count} interior walls that were bridged straight through an obstruction (column/shaft/منور)")
    return out

interior = split_interior_across_obstructions(interior, obstruction_union)

print("FINAL interior:", len(interior), " exterior:", len(exterior))
print("interior needs_check:", sum(1 for w in interior if w["needs_check"]))

all_walls_out = interior + exterior
with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v3b_classified.json", "w") as f:
    json.dump({"walls": all_walls_out}, f)
