"""
Masonry wall heights per floor from the STRUCTURAL drawing (tools/str_slabs.py).

Rule (executed condition, owner 2026-11-26):
    storey (top of slab to top of slab) = 3.20 m on every floor
    masonry height under a point = 3.20 - depth of the concrete above it
        slab 0.20 -> 3.00 | slab 0.35 -> 2.85 | beam 25x70 -> 2.50 | beam 25x90 -> 2.30
The concrete above architectural floor N is the structural sheet "سقف الدور N" (the ceiling of N),
so floor N's walls are run against plan_for_ceiling(S, N), never against a sheet named N.

Frames: the walls are in the architectural LOCAL frame (diwan_common: -10 deg, origin = min corner of
Etabs-col of that floor).  str_slabs.read_structural() is calibrated to it on F06/F09 columns; every
floor is checked again here on its own columns (`floor_shift`) and any residual shift is applied.

Usage (also used by read_plan.py, default --heights structural):
    python tools/masonry_heights.py 6        # per-wall table of F06
    python tools/masonry_heights.py --all    # summary of every floor
"""
import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import str_slabs as ss  # noqa: E402

STOREY = ss.EXEC_STOREY


def _r(v, n=3):
    return None if v is None else round(float(v), n)


def floor_shift(plan, elements, tol=0.6):
    """Residual (dx, dy) to add to an architectural point of this floor to land on the calibrated
    structural plan, voted from the floor's columns / shear walls vs the structural columns."""
    from shapely.geometry import Polygon
    cs = [c["_poly"].centroid for c in plan["columns"]]
    if not cs:
        return (0.0, 0.0), 0
    votes = []
    for e in elements or []:
        if e.get("kind") not in ("column", "column_xbox", "shear_wall") or not e.get("outline"):
            continue
        try:
            c = Polygon(e["outline"]).centroid
        except Exception:
            continue
        best = min(cs, key=lambda q: q.distance(c))
        if best.distance(c) <= tol:
            votes.append((round(best.x - c.x, 2), round(best.y - c.y, 2)))
    if not votes:
        return (0.0, 0.0), 0
    (dx, dy), n = Counter(votes).most_common(1)[0]
    if math.hypot(dx, dy) < 0.02:
        return (0.0, 0.0), len(votes)
    return (dx, dy), n


def wall_heights(floor_no, walls, elements=None, storey=STOREY, S=None):
    """{wall id: {...}} for one architectural floor.  Each record:
        H_mean   length-weighted masonry height along the centre line
        H_min / H_max, runs [(t0, t1, depth, H, source)], at(x, y) -> H at a point (for openings)
    plus a '_meta' entry (plan title, shift, counts)."""
    S = S or ss.read_structural()
    plan = ss.plan_for_ceiling(S, floor_no)
    if plan is None:
        return {"_meta": {"floor_no": floor_no, "plan": None, "note": "no structural ceiling sheet"}}
    (dx, dy), nv = floor_shift(plan, elements)
    out = {}
    for w in walls:
        p0 = (w["x1"] + dx, w["y1"] + dy)
        p1 = (w["x2"] + dx, w["y2"] + dy)
        runs = ss.soffit_profile(plan, p0, p1)
        if not runs:
            d, src = ss.soffit_at(plan, *p0)
            runs = [(0.0, 0.0, d, src)]
        L = sum(b - a for a, b, _, _ in runs)
        Hs = [(b - a, storey - d) for a, b, d, _ in runs]
        H_mean = sum(l * h for l, h in Hs) / L if L > 1e-9 else Hs[0][1]
        out[w["id"]] = {"H_mean": _r(H_mean, 3), "H_min": _r(min(h for _, h in Hs), 3),
                        "H_max": _r(max(h for _, h in Hs), 3),
                        "runs": [(a, b, d, _r(storey - d, 3), s) for a, b, d, s in runs]}
    meta = {"floor_no": floor_no, "plan": plan["title"], "ceiling_of": plan["ceiling_of"],
            "shift": (dx, dy), "shift_votes": nv, "storey": storey,
            "general_thickness": plan.get("general_thickness")}
    out["_meta"] = meta
    out["_plan"] = plan
    out["_shift"] = (dx, dy)
    return out


def height_at(HW, x, y, storey=STOREY):
    """Masonry height at an architectural point (e.g. an opening's 'at')."""
    plan = HW.get("_plan")
    if plan is None:
        return None
    dx, dy = HW["_shift"]
    d, _ = ss.soffit_at(plan, x + dx, y + dy)
    return _r(storey - d, 3)


def in_concrete(HW, x, y, shrink=0.02):
    """True when the architectural point (x, y) lies inside a STRUCTURAL column / shear wall / core of this floor
    (an opening drawn there does not exist: the structural is what was built)."""
    from shapely.geometry import Point
    from shapely.ops import unary_union
    plan = (HW or {}).get("_plan")
    if plan is None:
        return False
    if "_conc_union" not in HW:
        HW["_conc_union"] = unary_union([c["_poly"].buffer(-shrink) for c in plan["columns"]])
    dx, dy = HW["_shift"]
    return HW["_conc_union"].contains(Point(x + dx, y + dy))


def concrete_overlap(HW, walls, shrink=0.02):
    """{wall id: centre-line length (m) inside the STRUCTURAL columns / shear walls / cores of this floor}.
    The structural is what was built (owner, 2026-11-26): shear walls 0.30 (not the 0.40 drawn), the Z core
    between SW04 and SW02, and columns missing from the architectural plan.  Masonry is deducted there."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    plan = HW.get("_plan")
    if plan is None:
        return {}
    dx, dy = HW["_shift"]
    U = unary_union([c["_poly"].buffer(-shrink) for c in plan["columns"]])
    out = {}
    for w in walls:
        L = LineString([(w["x1"] + dx, w["y1"] + dy), (w["x2"] + dx, w["y2"] + dy)])
        ln = L.intersection(U).length
        if ln > 0.05:
            out[w["id"]] = _r(ln, 3)
    return out


def floor_summary(HW, walls):
    by_h = defaultdict(float)
    by_src = defaultdict(float)
    for w in walls:
        r = HW.get(w["id"])
        if not r:
            continue
        L = sum(b - a for a, b, *_ in r["runs"]) or 1e-9
        k = w["length_gross"] / L
        for a, b, d, h, s in r["runs"]:
            by_h[h] += (b - a) * k
            by_src[s.split(" (")[0] if s.startswith("beam") else s] += (b - a) * k
    return {"length_by_height": {f"{h:.2f}": _r(v, 2) for h, v in sorted(by_h.items(), reverse=True)},
            "length_by_source": {k: _r(v, 2) for k, v in sorted(by_src.items(), key=lambda kv: -kv[1])}}


def _load_floor(n):
    from diwan_common import all_floors
    import read_plan as rp
    fl = next(f for f in all_floors() if f.floor_no == n)
    b = rp.read_floor(fl, use_cache=True, log=lambda *a, **k: None)
    return fl, b


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("floors", nargs="*", type=int)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    from diwan_common import all_floors
    fls = [f.floor_no for f in all_floors() if f.floor_no] if a.all or not a.floors else a.floors
    S = ss.read_structural()
    for n in fls:
        fl, b = _load_floor(n)
        walls = b["walls"]["walls"]
        HW = wall_heights(n, walls, b["structure"]["elements"], S=S)
        m = HW["_meta"]
        fs = floor_summary(HW, walls)
        print(f"F{n:02d}: ceiling sheet '{m['plan']}' shift {m['shift']} ({m['shift_votes']} votes) | "
              f"length by masonry height {fs['length_by_height']}")
        if len(fls) == 1 or not a.all and len(a.floors) == 1:
            for w in walls:
                r = HW[w["id"]]
                det = "; ".join(f"{a_:.2f}-{b_:.2f} m: {h:.2f} ({s})" for a_, b_, d, h, s in r["runs"])
                print(f"  {w['id']:6} {w['family']:5} {w['length_gross']:6.2f} m  H={r['H_mean']:.2f}  {det}")


if __name__ == "__main__":
    main()
