import sys, math, argparse
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf import path as ezpath
from diwan_common import get_floor, floor_entities, floor_texts
plt.rcParams["font.family"]="Tahoma"
COL={"W":"#d62728","WIN":"#17becf","Etabs-col":"#2ca02c","COL":"#006400","DASH":"#bcbd22","ST":"#8c564b","PR":"#9467bd","try":"#ff7f0e","FUR":"#c7c7c7","DIM":"#98df8a","MASS":"#7f7f7f","HAT":"#aaaaaa","0":"#000000","TEXT-D":"#555"}
def paths(e, depth=0):
    t=e.dxftype()
    if t=="INSERT":
        if depth<3:
            for v in e.virtual_entities():
                yield from paths(v, depth+1)
        return
    if t in ("TEXT","MTEXT","DIMENSION","ATTDEF","ATTRIB","POINT","SOLID","TRACE"): 
        if t=="DIMENSION":
            for v in e.virtual_entities(): yield from paths(v, depth+1)
        return
    if t=="HATCH":
        try:
            for p in ezpath.from_hatch(e): yield p
        except Exception: pass
        return
    try:
        yield ezpath.make_path(e)
    except Exception:
        return
ap=argparse.ArgumentParser(); ap.add_argument("floor",type=int); ap.add_argument("x0",type=float); ap.add_argument("y0",type=float); ap.add_argument("x1",type=float); ap.add_argument("y1",type=float)
ap.add_argument("--out"); ap.add_argument("--layers",nargs="*",default=["W","WIN","Etabs-col","COL","ST","DASH","PR","try","FUR"]); ap.add_argument("--dpi",type=int,default=80); ap.add_argument("--texts",action="store_true"); ap.add_argument("--names",action="store_true")
a=ap.parse_args()
fl=get_floor(a.floor)
w=a.x1-a.x0; h=a.y1-a.y0; sc=12/max(w,h)
fig,ax=plt.subplots(figsize=(w*sc+1,h*sc+1))
for e in floor_entities(fl, layers=tuple(a.layers)):
    c=COL.get(e.dxf.layer,"k")
    for p in paths(e):
        try:
            pts=[fl.to_local(v.x,v.y) for v in p.flattening(0.01)]
        except Exception: continue
        if len(pts)>=2:
            xs,ys=zip(*pts)
            if max(xs)<a.x0-1 or min(xs)>a.x1+1 or max(ys)<a.y0-1 or min(ys)>a.y1+1: continue
            ax.plot(xs,ys,color=c,lw=0.7)
    if a.names and e.dxftype()=="INSERT":
        p=e.dxf.insert; lx,ly=fl.to_local(p.x,p.y)
        ax.text(lx,ly,f"{e.dxf.name}\n{e.dxf.xscale:g} r{(e.dxf.rotation-fl.angle)%360:.0f}",fontsize=6,color="m",clip_on=True)
if a.texts:
    for t in floor_texts(fl, layers=("TEXT","-A-TEXT","DIM","PR","TEXT-D")):
        lx,ly=t["local"]; ax.text(lx,ly,t["text"],fontsize=7,clip_on=True)
ax.set_xlim(a.x0,a.x1); ax.set_ylim(a.y0,a.y1); ax.set_aspect("equal"); ax.grid(True,lw=0.2)
import matplotlib.ticker as mt
ax.xaxis.set_major_locator(mt.MultipleLocator(1)); ax.yaxis.set_major_locator(mt.MultipleLocator(1))
fig.savefig(a.out,dpi=a.dpi,bbox_inches="tight"); print("saved",a.out)
