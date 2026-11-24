# Verifier scratch: collinear wall records separated by an unbridged gap; big openings; classification oddities.
import sys, math, json
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_walls")
from diwan_common import get_floor
from v_check import load, wall_geoms, OUT, rect
from shapely.ops import unary_union


def run(n):
    fl = get_floor(n)
    res = json.load(open(f"{OUT}/walls/{fl.label}.json", encoding="utf-8"))
    raw = load(fl)
    CU = unary_union([c[0] for c in raw["cols"]]).buffer(0.02)
    TU = unary_union([t[0] for t in raw["try"]]).buffer(0.02)
    W = res["walls"]
    print("=" * 20, fl.label)
    gaps = []
    for i, a in enumerate(W):
        for b in W:
            if a is b or abs(a["angle"] - b["angle"]) > 0.5: continue
            if abs(a["_band"][0] - b["_band"][0]) > 0.02 or abs(a["_band"][1] - b["_band"][1]) > 0.02: continue
            g = b["_t"][0] - a["_t"][1]
            if 0.05 < g <= 2.5:
                R = rect(a["angle"], a["_t"][1] + 0.01, b["_t"][0] - 0.01, *a["_band"])
                fc = R.intersection(CU).area / R.area
                fv = R.intersection(TU).area / R.area
                if fc < 0.3 and fv < 0.3:
                    c = R.centroid
                    gaps.append((a["id"], b["id"], round(g, 3), a["thickness"], a["kind"], (round(c.x, 2), round(c.y, 2))))
    print("unbridged collinear gaps (no concrete/void):")
    for x in gaps: print("   ", x)
    print("openings: type 'opening' or width>2.4:")
    for w in W:
        for o in w["openings"]:
            if o["type"] == "opening" or o["width"] > 2.4:
                print("   ", w["id"], w["kind"], w["thickness"], o["type"], o["width"], o["at"])
    print("classification oddities:")
    for w in W:
        sh = [s["share"] for s in w["sides"]]
        outs = [s.get("out", 0) for s in sh]
        if w["kind"] == "exterior" and max(outs) < 0.5:
            print("    exterior w/o out side:", w["id"], w["thickness"], w["length_gross"], sh, [s["labels"] for s in w["sides"]])
        if w["kind"] != "exterior" and max(outs) >= 0.5:
            print("    non-exterior with out side:", w["id"], w["kind"], w["thickness"], w["length_gross"], sh)
        if w["kind"] == "exterior" and min(outs) >= 0.5:
            print("    out on both sides:", w["id"], w["thickness"], w["length_gross"], (w["x1"], w["y1"]))
    # windows per floor
    wins = sorted(round(o["width"], 3) for w in W for o in w["openings"] if o["type"] == "window")
    print("windows", len(wins), sum(wins), wins)


if __name__ == "__main__":
    for a in sys.argv[1:]:
        run(int(a))
