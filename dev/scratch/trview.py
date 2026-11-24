import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, entity_bbox
from render_floor import base_axes
from ezdxf import path as ezpath
n = int(sys.argv[1]); zoom = tuple(map(float, sys.argv[2:6])); out = sys.argv[6]
fig, ax, fl = base_axes(n, layers=["W","WIN","Etabs-col","COL","try","DASH","ST","PR","MASS"], zoom=zoom, figsize=(14,14), texts=True)
for e in fl.msp.query('INSERT[layer=="Etabs-Slab"]'):
    b = entity_bbox(e)
    if not (b and fl.contains((b[0]+b[2])/2,(b[1]+b[3])/2)): continue
    for v in e.virtual_entities():
        if v.dxftype() in ('LWPOLYLINE','LINE','HATCH'):
            paths = ezpath.from_hatch(v) if v.dxftype()=='HATCH' else [ezpath.make_path(v)]
            for pp in paths:
                pts = [fl.to_local(q.x,q.y) for q in pp.flattening(0.01)]
                if len(pts)>=2:
                    xs, ys = zip(*pts)
                    ax.plot(xs, ys, color='magenta', lw=1.5, ls='--')
    break
fig.savefig(out, dpi=100, bbox_inches='tight')
