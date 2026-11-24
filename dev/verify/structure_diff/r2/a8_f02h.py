import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_structure_diff\r2")
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from segs import segs
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fl = get_floor(2)
fig, ax = plt.subplots(figsize=(10, 20))
for a, b, h, t in segs(2, "W"):
    if h == "1129": continue
    ax.plot([a[0], b[0]], [a[1], b[1]], color="red" if h == "1585" else "k", lw=0.6 if h != "1585" else 1.5, alpha=0.7)
cols = ["b", "g", "m", "orange", "c"]
for i, e in enumerate([e for e in floor_entities(fl, layers="W") if e.dxftype() == "HATCH"]):
    for j, bp in enumerate(e.paths):
        p = ezpath.from_hatch_boundary_path(bp)
        vs = [fl.to_local(v.x, v.y) for v in p.flattening(0.01)]
        L = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a, b in zip(vs, vs[1:]))
        xs, ys = zip(*vs)
        ax.plot(xs, ys, color=cols[i], lw=2.5, alpha=0.5)
        print(e.dxf.handle, j, "len", round(L, 2), "bbox", [round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2)])
ax.set_aspect("equal"); ax.set_xlim(-2, 21); ax.set_ylim(-3, 41); ax.grid(lw=0.3)
fig.savefig("f02_whatch.png", dpi=80, bbox_inches="tight")
