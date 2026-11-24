import sys
sys.path.insert(0, 'tools')
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
fl=get_floor(2)
fig,axs=plt.subplots(1,2,figsize=(16,18))
for ax,zoom in zip(axs,[(-1.5,-2.5,20.5,41),(-1.2,-2.4,6,6)]):
    for e in floor_entities(fl, layers=('W','WIN','MASS')):
        if e.dxftype() in ('INSERT','TEXT','MTEXT','HATCH','DIMENSION'): continue
        try: p=ezpath.make_path(e)
        except Exception: continue
        pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
        xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
        h=e.dxf.handle
        if h=='1585': ax.plot(xs,ys,color='red',lw=2.0,zorder=5)
        elif h in ('8B1',): ax.plot(xs,ys,color='blue',lw=1.5,zorder=6)
        elif h in ('8B2',): ax.plot(xs,ys,color='green',lw=1.5,zorder=6)
        elif e.dxf.layer=='WIN': ax.plot(xs,ys,color='cyan',lw=0.5)
        elif e.dxf.layer=='W': ax.plot(xs,ys,color='#999',lw=0.4)
    ax.set_xlim(zoom[0],zoom[2]); ax.set_ylim(zoom[1],zoom[3]); ax.set_aspect('equal')
axs[0].set_title('F02: red=W LWPOLY 1585, blue=MASS 8B1, green=MASS 8B2')
plt.savefig('output/_verify_structure_diff/f02_outlines.png',dpi=80,bbox_inches='tight')
