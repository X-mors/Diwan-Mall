import sys; sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Tahoma"
import rooms
from diwan_common import get_floor
n = int(sys.argv[1]); z = list(map(float, sys.argv[2:6])); out = sys.argv[6]
hand = len(sys.argv) > 7
g = rooms.load_geometry(get_floor(n))
fig, ax = plt.subplots(figsize=(12, 12 * (z[3]-z[1])/(z[2]-z[0])))
C = {"w": "#d62728", "zero": "k", "win": "#17becf", "win_dashed": "#9edae5", "st": "#8c564b", "pr": "#9467bd",
     "dash": "#bcbd22", "mass": "#7f7f7f", "cols": "#2ca02c", "try_polys": "#ff7f0e", "w_hatch": "#e377c2"}
def inz(pts):
    return any(z[0]-0.5 <= p[0] <= z[2]+0.5 and z[1]-0.5 <= p[1] <= z[3]+0.5 for p in pts)
for k, c in C.items():
    for r in g[k]:
        pts = r["pts"]
        if not inz(pts): continue
        if k in ("cols", "try_polys", "w_hatch"): pts = list(pts) + [pts[0]]
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=c, lw=0.9 if k in ("w","win") else 0.6, ls="--" if k in ("dash","win_dashed") else "-")
        if hand and k in ("w", "zero", "mass"):
            ax.text(sum(xs)/len(xs), sum(ys)/len(ys), r["handle"], fontsize=5, color=c)
for d in g["doors"]:
    for a, b in d["segs"]:
        if inz([a]): ax.plot([a[0], b[0]], [a[1], b[1]], color="#1f77b4", lw=0.7)
    for arc in d["arcs"]:
        if inz(arc): xs, ys = zip(*arc); ax.plot(xs, ys, color="#1f77b4", lw=0.5)
for t in g["texts"] + g["notes"]:
    if z[0] <= t["x"] <= z[2] and z[1] <= t["y"] <= z[3]:
        ax.text(t["x"], t["y"], t["text"], fontsize=8, color="navy"); ax.plot(t["x"], t["y"], "b+", ms=4)
ax.set_xlim(z[0], z[2]); ax.set_ylim(z[1], z[3]); ax.set_aspect("equal"); ax.grid(True, lw=0.2)
import numpy as np
ax.set_xticks(np.arange(np.floor(z[0]), z[2], 0.5 if z[2]-z[0] < 8 else 1)); ax.set_yticks(np.arange(np.floor(z[1]), z[3], 0.5 if z[3]-z[1] < 8 else 1))
ax.tick_params(labelsize=6)
fig.savefig(out, dpi=110, bbox_inches="tight")
print("saved", out)
