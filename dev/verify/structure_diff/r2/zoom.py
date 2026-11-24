import sys, json, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_structure_diff\r2")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from segs import segs
plt.rcParams["font.family"] = "Tahoma"
COL = {"W": "k", "WIN": "c", "DASH": "y", "try": "orange", "MASS": "gray", "Etabs-col": "g", "ST": "brown", "PR": "purple", "X": "pink"}
def zoom(n, x0, y0, x1, y1, out, layers=("W", "WIN", "DASH", "try", "MASS"), handles=False):
    fig, ax = plt.subplots(figsize=(12, 12 * (y1 - y0) / (x1 - x0)))
    for L in layers:
        for a, b, h, t in segs(n, L):
            if (min(a[0], b[0]) > x1 or max(a[0], b[0]) < x0 or min(a[1], b[1]) > y1 or max(a[1], b[1]) < y0):
                continue
            ax.plot([a[0], b[0]], [a[1], b[1]], color=COL.get(L, "r"), lw=1.0)
            if handles and math.hypot(b[0]-a[0], b[1]-a[1]) > 0.08:
                ax.text((a[0]+b[0])/2, (a[1]+b[1])/2, h, fontsize=7, color=COL.get(L, "r"), clip_on=True)
    d = json.load(open(r"D:\حصر المباني\Diwan-Mall\output\structure\F%02d.json" % n, encoding="utf-8"))
    cc = {"interior": "lime", "exterior": "red", "lift_shaft": "purple", "wall": "blue", "concrete": "magenta"}
    for e in d["elements"]:
        o = e.get("outline")
        if o:
            xs, ys = zip(*o); ax.fill(xs, ys, color="g", alpha=0.25)
            ax.text(e["centroid"][0], e["centroid"][1], e["id"], fontsize=9, clip_on=True)
        for f in e.get("faces", []):
            (ax_, ay), (bx, by) = f["a"], f["b"]; L = f["len"]
            if L <= 0: continue
            ux, uy = (bx - ax_) / L, (by - ay) / L; nx, ny = uy, -ux  # outward for CCW? draw both offsets small
            for s, t_, kind in f["runs"]:
                px0, py0 = ax_ + ux * s, ay + uy * s; px1, py1 = ax_ + ux * t_, ay + uy * t_
                ax.plot([px0 + nx * 0.03, px1 + nx * 0.03], [py0 + ny * 0.03, py1 + ny * 0.03], color=cc.get(kind, "k"), lw=3, alpha=0.8)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("equal"); ax.grid(True, lw=0.3)
    ax.set_title(f"F{n:02d} zoom {x0},{y0}-{x1},{y1}  runs: lime int, red ext, blue wall, magenta concrete, purple lift")
    fig.savefig(out, dpi=110, bbox_inches="tight"); plt.close(fig)
if __name__ == "__main__":
    a = sys.argv
    zoom(int(a[1]), *map(float, a[2:6]), a[6], handles=len(a) > 7)
