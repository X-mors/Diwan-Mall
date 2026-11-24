import sys, math, random
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from rooms import *
from shapely.geometry import LineString, Polygon, box, Point
from shapely.ops import unary_union
import shapely
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"]="Tahoma"
fn = int(sys.argv[1]); EPS=float(sys.argv[2]) if len(sys.argv)>2 else 0.015
fl = get_floor(fn); g = load_geometry(fl)
geoms=[]
for k in ("w","zero","win"):
    for r in g[k]:
        geoms.append(LineString(r["pts"]).buffer(EPS))
for k in ("cols","try_polys"):
    for r in g[k]:
        pg=Polygon(r["pts"]).buffer(0)
        geoms.append(pg.buffer(EPS))
# doors: jamb lines (length ~ nominal_t) -> closure
for d in g["doors"]:
    t=d["nominal_t"]
    jam=[s for s in d["segs"] if abs(math.dist(*s)-t)<0.003]
    best=None
    for i in range(len(jam)):
        for j in range(i+1,len(jam)):
            a,b=jam[i],jam[j]
            sep=math.dist(((a[0][0]+a[1][0])/2,(a[0][1]+a[1][1])/2),((b[0][0]+b[1][0])/2,(b[0][1]+b[1][1])/2))
            sc=abs(sep-d["nominal_w"])
            if best is None or sc<best[0]: best=(sc,a,b)
    if best is None or best[0]>0.05:
        print("door no jambs", d["name"], d["insert"]); continue
    _,a,b=best
    # pair endpoints
    if math.dist(a[0],b[0])+math.dist(a[1],b[1]) > math.dist(a[0],b[1])+math.dist(a[1],b[0]):
        b=(b[1],b[0])
    poly=Polygon([a[0],a[1],b[1],b[0]]).buffer(0)
    geoms.append(poly.buffer(EPS))
mass=unary_union(geoms)
env=box(-4,-5,25,45)
free=env.difference(mass)
faces=[p for p in getattr(free,"geoms",[free])]
faces=[p for p in faces if not p.exterior.coords or not p.touches(env.exterior) and not p.intersects(env.exterior)]
print(len(faces))
fig,ax=plt.subplots(figsize=(16,30))
for r in g["w"]+g["win"]:
    xs,ys=zip(*r["pts"]); ax.plot(xs,ys,color="k",lw=0.3)
random.seed(1)
for p in faces:
    q=p.buffer(EPS,join_style=2)
    mic=shapely.maximum_inscribed_circle(q).length
    c=(random.random(),random.random(),random.random(),0.5)
    xs,ys=q.exterior.xy; ax.fill(xs,ys,color=c)
    rp=q.representative_point()
    if q.area>0.3: ax.text(rp.x,rp.y,f"{q.area:.2f}\nw{mic:.2f}",fontsize=6,ha="center")
for t in g["texts"]:
    ax.text(t["x"],t["y"],t["text"],fontsize=7,color="b")
ax.set_aspect("equal"); ax.set_xlim(-2,20); ax.set_ylim(-3,41)
fig.savefig(sys.argv[3] if len(sys.argv)>3 else rf"D:\حصر المباني\Diwan-Mall\output\rooms\_scratch\proto_F{fn:02d}.png",dpi=90,bbox_inches="tight")
