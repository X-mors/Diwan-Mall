import sys, math, collections, pickle
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import walls as W
from shapely.geometry import Polygon
from shapely.ops import unary_union
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"]="Tahoma"
from diwan_common import get_floor
F = int(sys.argv[1]) if len(sys.argv)>1 else 3
zoom = tuple(map(float, sys.argv[2:6])) if len(sys.argv)>5 else None
fl = get_floor(F)
g = W.load_geometry(fl)
conc = W.concrete_polys(g); shafts = W.shaft_polys(g)
CU = unary_union([c["poly"] for c in conc]); SU = unary_union([s["poly"] for s in shafts])
fig, ax = plt.subplots(figsize=((16,30) if not zoom else (14,14)))
for s in g["wsegs"]:
    ax.plot([s[0],s[2]],[s[1],s[3]], color="#000", lw=0.5)
for w in g["win"]:
    ax.plot([w[0],w[2]],[w[1],w[3]], color="#17becf", lw=0.4)
for c in conc:
    x,y = c["poly"].exterior.xy; ax.fill(x,y, color="#2ca02c", alpha=0.3)
for s in shafts:
    x,y = s["poly"].exterior.xy; ax.fill(x,y, color="#ff7f0e", alpha=0.3)
cmap = {0.12:"#d62728",0.25:"#1f77b4",0.20:"#9467bd",0.30:"#8c564b",0.40:"#e377c2"}
hist = collections.Counter()
for D, segs in W.cluster_directions(g["wsegs"]):
    faces = W.build_faces(D, segs)
    cells = W.pair_cells(faces)
    for c in cells:
        r = D.rect(c["s"], c["e"], c["d0"], c["d1"])
        th = round(c["d1"]-c["d0"],2)
        inter_c = r.intersection(CU).area/r.area if r.area>0 else 0
        inter_s = r.intersection(SU).area/r.area if r.area>0 else 0
        if inter_c > 0.5: col = "#00ff00"
        elif inter_s > 0.5: col = "#ffaa00"
        else:
            col = cmap.get(th, "#000000"); hist[th]+= c["e"]-c["s"]
        x,y = r.exterior.xy; ax.fill(x,y,color=col, alpha=0.8, lw=0)
        if col=="#000000":
            ax.text((c["s"]*D.u[0]+(c["d0"]+c["d1"])/2*D.n[0]), (c["s"]*D.u[1]+(c["d0"]+c["d1"])/2*D.n[1]), f"{th:.2f}", fontsize=6, clip_on=True)
ax.set_aspect("equal")
if zoom: ax.set_xlim(zoom[0],zoom[2]); ax.set_ylim(zoom[1],zoom[3])
else: ax.set_xlim(-2,21); ax.set_ylim(-3,41)
fig.savefig(rf"D:\حصر المباني\Diwan-Mall\output\walls\explore\cells_F{F:02d}{'_z' if zoom else ''}.png", dpi=110 if not zoom else 130, bbox_inches="tight")
for k,v in sorted(hist.items()):
    if v>0.2: print("t=%.2f L=%.2f"%(k,v))
