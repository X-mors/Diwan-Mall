"""
Reconstruct wall centerline runs from a double-line CAD wall layer, classify
each as exterior (building envelope) or interior (partition), and number the
interior ones for a quantity-survey schedule.

Pipeline:
  1. Read all LINE entities on the given layer.
  2. Auto-detect the building's rotation angle (dominant line direction) and
     rotate everything to axis-aligned so walls become purely H/V.
  3. Cluster lines into "face bands" (parallel lines at the same offset),
     merging duplicates and dropping short hatch/detail fragments.
  4. Pair adjacent bands at typical wall-thickness apart into wall runs,
     bridging door/window-sized gaps so each run is one continuous wall.
  5. Union all wall run rectangles (shapely) and classify each run as
     exterior/interior by testing multiple points along it against the
     boundary of its own connected component (handles disconnected wings).
  6. Number the interior runs in reading order (top-to-bottom, left-to-right)
     and write everything to a JSON file for downstream labeling/Excel export.

Usage:
    python wall_schedule_extract.py <input.dxf> <output.json> --layer W [options]

Notes / tunables (defaults tuned on a typical Egyptian residential floor plan,
units = meters):
    --min-face-len   0.08   min band total length to count as a real wall face
                             (was 1.0 in the reference session; lower here so
                             thin/short walls in other buildings aren't lost -
                             raise it back to ~1.0 if a drawing has heavy hatch
                             noise on the wall layer, inspect band_classification
                             first, see the render_bands helper below)
    --min-thick      0.08   min wall thickness to pair two bands
    --max-thick      0.48   max wall thickness to pair two bands
    --bridge-gap     3.2    max gap (door/window) to bridge into one wall run
    --ext-tol        0.22   max distance from boundary to call a run "exterior"

ALWAYS visually verify the result (render with render_dxf.py or a custom
matplotlib plot colored by is_exterior) before trusting the numbers - this
is a heuristic reconstruction, not exact CAD wall recognition, and drawings
vary a lot in how "clean" the double-line geometry is.
"""
import argparse
import json
import math

import ezdxf
from shapely.geometry import box, Point, LinearRing
from shapely.ops import unary_union


def _weighted_mean_base_angle(lines, center, window):
    """Circular mean (mod 90 deg) of angles within `window` deg of `center`, length-weighted."""
    sx = sy = 0.0
    for s, e, length in lines:
        ang = math.atan2(e[1] - s[1], e[0] - s[0]) % math.pi
        deg = math.degrees(ang)
        base = deg % 90
        # distance from center on the mod-90 circle
        d = min(abs(base - center), 90 - abs(base - center))
        if d > window:
            continue
        a2 = math.radians(base * 4)
        sx += length * math.cos(a2)
        sy += length * math.sin(a2)
    if sx == 0 and sy == 0:
        return None
    return (math.degrees(math.atan2(sy, sx)) / 4) % 90


def dominant_angle_deg(lines):
    """Histogram (1-deg bins, mod 90, length-weighted) to find the coarse mode,
    then refine with a tight-window circular mean so short diagonal noise
    (door swings, hatch ticks) doesn't bias the final angle."""
    bins = [0.0] * 90
    for s, e, length in lines:
        ang = math.atan2(e[1] - s[1], e[0] - s[0]) % math.pi
        base = math.degrees(ang) % 90
        bins[int(base)] += length
    mode_bin = max(range(90), key=lambda i: bins[i])
    coarse = mode_bin + 0.5
    for _ in range(4):
        refined = _weighted_mean_base_angle(lines, center=coarse, window=3.0)
        if refined is None:
            break
        coarse = refined
    return coarse


def load_lines(doc, layer):
    msp = doc.modelspace()
    out = []
    for e in msp:
        if e.dxftype() == "LINE" and e.dxf.layer == layer:
            s = (e.dxf.start.x, e.dxf.start.y)
            en = (e.dxf.end.x, e.dxf.end.y)
            length = math.hypot(en[0] - s[0], en[1] - s[1])
            if length > 0.01:
                out.append((s, en, length))
    return out


def rotate_point(p, pivot, cos_t, sin_t):
    x, y = p[0] - pivot[0], p[1] - pivot[1]
    return (x * cos_t - y * sin_t, x * sin_t + y * cos_t)


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
            if abs(b["perp_sum"] / b["n"] - it["perp"]) <= tol:
                b["items"].append(it)
                b["perp_sum"] += it["perp"]
                b["n"] += 1
                placed = True
                break
        if not placed:
            bands.append({"items": [it], "perp_sum": it["perp"], "n": 1})
    result = []
    for b in bands:
        perp = b["perp_sum"] / b["n"]
        intervals = merge_intervals([(it["a0"], it["a1"]) for it in b["items"]], 0.08)
        result.append({"perp": perp, "intervals": intervals})
    result.sort(key=lambda b: b["perp"])
    return result


def consolidate(bands, min_face_len, dup_tol=0.10):
    kept = [b for b in bands if sum(a1 - a0 for a0, a1 in b["intervals"]) >= min_face_len]
    kept.sort(key=lambda b: b["perp"])
    out = []
    for b in kept:
        if out and abs(b["perp"] - out[-1]["perp_avg"]) <= dup_tol:
            prev = out[-1]
            prev["intervals"] = merge_intervals(prev["intervals"] + b["intervals"], 0.08)
            prev["perp_avg"] = (prev["perp_avg"] * prev["n"] + b["perp"]) / (prev["n"] + 1)
            prev["n"] += 1
        else:
            out.append({"perp_avg": b["perp"], "n": 1, "intervals": list(b["intervals"])})
    for b in out:
        b["perp"] = b["perp_avg"]
    return out


def pair_bands(bands, min_thick, max_thick, bridge_gap):
    bands = sorted(bands, key=lambda b: b["perp"])
    used = [False] * len(bands)
    walls = []
    for i in range(len(bands) - 1):
        if used[i] or used[i + 1]:
            continue
        gap = bands[i + 1]["perp"] - bands[i]["perp"]
        if min_thick <= gap <= max_thick:
            combined = bands[i]["intervals"] + bands[i + 1]["intervals"]
            for a0, a1 in merge_intervals(combined, bridge_gap):
                if a1 - a0 >= 0.3:
                    walls.append({"perp": (bands[i]["perp"] + bands[i + 1]["perp"]) / 2,
                                  "thick": gap, "a0": a0, "a1": a1, "len": a1 - a0})
            used[i] = used[i + 1] = True
    return walls


def build_wall_dicts(h_walls, v_walls):
    walls = []
    for w in h_walls:
        walls.append({"orient": "H", "x0": w["a0"], "x1": w["a1"],
                       "y0": w["perp"] - w["thick"] / 2, "y1": w["perp"] + w["thick"] / 2,
                       "len": w["len"], "thick": w["thick"], "cy": w["perp"]})
    for w in v_walls:
        walls.append({"orient": "V", "y0": w["a0"], "y1": w["a1"],
                       "x0": w["perp"] - w["thick"] / 2, "x1": w["perp"] + w["thick"] / 2,
                       "len": w["len"], "thick": w["thick"], "cx": w["perp"]})
    return walls


def classify(walls, ext_tol):
    polys = [box(w["x0"], w["y0"], w["x1"], w["y1"]) for w in walls]
    union = unary_union(polys)
    comps = list(union.geoms) if union.geom_type == "MultiPolygon" else [union]

    def sample_points(w, n=7):
        pts = []
        for i in range(n):
            t = i / (n - 1)
            if w["orient"] == "H":
                pts.append((w["x0"] + t * (w["x1"] - w["x0"]), w["cy"]))
            else:
                pts.append((w["cx"], w["y0"] + t * (w["y1"] - w["y0"])))
        return pts

    for w in walls:
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2
        comp = min(comps, key=lambda c: c.distance(Point(cx, cy)))
        ring = LinearRing(comp.exterior.coords)
        dists = [ring.distance(Point(p)) for p in sample_points(w)]
        w["max_dist_to_ext"] = max(dists)
        w["is_exterior"] = w["max_dist_to_ext"] <= ext_tol
    return walls


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_dxf")
    ap.add_argument("output_json")
    ap.add_argument("--layer", required=True)
    ap.add_argument("--min-face-len", type=float, default=0.08)
    ap.add_argument("--min-thick", type=float, default=0.08)
    ap.add_argument("--max-thick", type=float, default=0.48)
    ap.add_argument("--bridge-gap", type=float, default=3.2)
    ap.add_argument("--ext-tol", type=float, default=0.22)
    args = ap.parse_args()

    doc = ezdxf.readfile(args.input_dxf)
    raw_lines = load_lines(doc, args.layer)
    if not raw_lines:
        raise SystemExit(f"no LINE entities found on layer {args.layer!r}")

    rot_deg = dominant_angle_deg(raw_lines)
    xs = [p[0] for s, e, _ in raw_lines for p in (s, e)]
    ys = [p[1] for s, e, _ in raw_lines for p in (s, e)]
    pivot = (sum(xs) / len(xs), sum(ys) / len(ys))
    theta = math.radians(-rot_deg)
    ct, st = math.cos(theta), math.sin(theta)

    h_in, v_in = [], []
    for s, e, length in raw_lines:
        rs = rotate_point(s, pivot, ct, st)
        re = rotate_point(e, pivot, ct, st)
        ang = math.degrees(math.atan2(re[1] - rs[1], re[0] - rs[0])) % 180
        if min(ang, 180 - ang) <= 3.0:
            h_in.append({"perp": (rs[1] + re[1]) / 2, "a0": min(rs[0], re[0]), "a1": max(rs[0], re[0])})
        elif abs(ang - 90) <= 3.0:
            v_in.append({"perp": (rs[0] + re[0]) / 2, "a0": min(rs[1], re[1]), "a1": max(rs[1], re[1])})

    h_bands = consolidate(cluster_bands(h_in), args.min_face_len)
    v_bands = consolidate(cluster_bands(v_in), args.min_face_len)

    h_walls = pair_bands(h_bands, args.min_thick, args.max_thick, args.bridge_gap)
    v_walls = pair_bands(v_bands, args.min_thick, args.max_thick, args.bridge_gap)

    walls = build_wall_dicts(h_walls, v_walls)
    classify(walls, args.ext_tol)

    theta_inv = math.radians(rot_deg)
    ct2, st2 = math.cos(theta_inv), math.sin(theta_inv)

    def unrot(p):
        x, y = p
        return (x * ct2 - y * st2 + pivot[0], x * st2 + y * ct2 + pivot[1])

    for w in walls:
        if w["orient"] == "H":
            cx, cy = (w["x0"] + w["x1"]) / 2, w["cy"]
        else:
            cx, cy = w["cx"], (w["y0"] + w["y1"]) / 2
        w["global_center"] = unrot((cx, cy))

    interior = [w for w in walls if not w["is_exterior"]]
    interior.sort(key=lambda w: (-round(w["global_center"][1] / 2), w["global_center"][0]))
    for i, w in enumerate(interior, start=1):
        w["no"] = i

    exterior = [w for w in walls if w["is_exterior"]]

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump({
            "rot_deg": rot_deg, "pivot": pivot,
            "interior": interior, "exterior": exterior,
        }, f, ensure_ascii=False)

    total_len = sum(w["len"] for w in interior)
    print(f"interior walls: {len(interior)}   exterior walls: {len(exterior)}")
    print(f"total interior length: {total_len:.2f} m")
    print("saved:", args.output_json)
    print()
    print("IMPORTANT: visually verify exterior/interior split before using these numbers -")
    print("render the walls colored by is_exterior and compare against the drawing.")


if __name__ == "__main__":
    main()
