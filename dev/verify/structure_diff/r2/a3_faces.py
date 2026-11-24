import sys, json, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_structure_diff\r2")
from segs import segs
J = r"D:\حصر المباني\Diwan-Mall\output\structure\F%02d.json"
def touching(n, x0, y0, x1, y1, layers=("W","WIN","DASH","try","MASS"), tol=0.03):
    """for an axis-aligned rect, list segments perpendicular to each face with an endpoint on it"""
    faces = {"S": ((x0,y0),(x1,y0)), "N": ((x0,y1),(x1,y1)), "W": ((x0,y0),(x0,y1)), "E": ((x1,y0),(x1,y1))}
    res = {}
    for L in layers:
        for a, b, h, t in segs(n, L):
            dx, dy = b[0]-a[0], b[1]-a[1]; ln = math.hypot(dx, dy)
            if ln < 0.005: continue
            for side, ((ax, ay), (bx, by)) in faces.items():
                horiz = side in "SN"
                for p, q in ((a, b), (b, a)):
                    if horiz:
                        if abs(p[1]-ay) <= tol and ax-0.01 <= p[0] <= bx+0.01:
                            perp = abs(dx)/ln < 0.06
                            along = abs(dy)/ln < 0.06
                            out = (q[1]-ay) * (1 if side=="N" else -1)
                            if perp and out > 0.005:
                                res.setdefault(side, []).append((round(p[0],3), L, h, t, round(ln,3), "perp-out"))
                            elif along:
                                res.setdefault(side, []).append((round(min(p[0],q[0]),3), L, h, t, round(ln,3), "along %.3f-%.3f"%(min(p[0],q[0]),max(p[0],q[0]))))
                    else:
                        if abs(p[0]-ax) <= tol and ay-0.01 <= p[1] <= by+0.01:
                            perp = abs(dy)/ln < 0.06
                            along = abs(dx)/ln < 0.06
                            out = (q[0]-ax) * (1 if side=="E" else -1)
                            if perp and out > 0.005:
                                res.setdefault(side, []).append((round(p[1],3), L, h, t, round(ln,3), "perp-out"))
                            elif along:
                                res.setdefault(side, []).append((round(min(p[1],q[1]),3), L, h, t, round(ln,3), "along %.3f-%.3f"%(min(p[1],q[1]),max(p[1],q[1]))))
    return res
if __name__ == "__main__":
    n = int(sys.argv[1]); ids = sys.argv[2:]
    d = json.load(open(J % n, encoding="utf-8"))
    for e in d["elements"]:
        if ids and e["id"] not in ids: continue
        x0, y0, x1, y1 = e["bbox"]
        print("==", e["id"], e["kind"], e["bbox"], "cov_w", e["covered_by_walls"], "cov_c", e["covered_by_concrete_or_shaft"], "int", e["exposed_interior"], "ext", e["exposed_exterior"], "lift", e["exposed_lift_shaft"])
        for f in e["faces"]:
            print("   face", f["a"], "->", f["b"], "runs", f["runs"])
        r = touching(n, x0, y0, x1, y1)
        for side in "SNWE":
            for it in sorted(set(r.get(side, []))):
                print("   ", side, it)
