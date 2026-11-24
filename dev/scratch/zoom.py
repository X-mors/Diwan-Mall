import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from rooms import *
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"]="Tahoma"
fn=int(sys.argv[1]); x0,y0,x1,y1=map(float,sys.argv[2:6]); out=sys.argv[6]
fl=get_floor(fn); g=load_geometry(fl)
C={"w":"r","zero":"m","win":"c","win_dashed":"c","cols":"g","try_polys":"orange","st":"brown","pr":"purple","dash":"y","mass":"grey","w_hatch":"magenta"}
fig,ax=plt.subplots(figsize=(14,14*(y1-y0)/(x1-x0)))
for k,c in C.items():
    for r in g[k]:
        xs,ys=zip(*r["pts"]); ax.plot(xs,ys,color=c,lw=0.8 if k!="dash" else 0.5, ls="--" if k in("win_dashed","dash") else "-")
for d in g["doors"]:
    for a,b in d["segs"]: ax.plot([a[0],b[0]],[a[1],b[1]],color="blue",lw=0.6)
    for arc in d["arcs"]:
        xs,ys=zip(*arc); ax.plot(xs,ys,color="blue",lw=0.4)
for t in g["texts"]+g["notes"]:
    ax.text(t["x"],t["y"],t["text"],fontsize=9,color="k",clip_on=True)
if len(sys.argv)>7:
    for dm in g["dims"]:
        p2,p3=dm["p2"],dm["p3"]
        if x0<p2[0]<x1 and y0<p2[1]<y1:
            ax.plot([p2[0],p3[0]],[p2[1],p3[1]],"g:",lw=0.5); ax.text((p2[0]+p3[0])/2,(p2[1]+p3[1])/2,f"{dm['value']:.2f}",fontsize=7,color="g",clip_on=True)
ax.set_aspect("equal"); ax.set_xlim(x0,x1); ax.set_ylim(y0,y1); ax.grid(True,lw=0.2)
ax.set_xticks([x0+i*0.5 for i in range(int((x1-x0)/0.5)+1)]); ax.tick_params(labelsize=6)
fig.savefig(out,dpi=80,bbox_inches="tight")
