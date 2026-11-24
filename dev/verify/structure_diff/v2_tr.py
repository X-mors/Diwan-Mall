import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor
from ezdxf import path as ezpath
from shapely.geometry import Polygon
from collections import Counter
n=int(sys.argv[1])
fl = get_floor(n)
ins = [e for e in fl.msp.query('INSERT[layer=="Etabs-Slab"]')]
blk = fl.doc.blocks[ins[0].dxf.name]
print('block entities', Counter((e.dxftype(), e.dxf.layer) for e in blk))
# pick the insert on this sheet
from diwan_common import entity_bbox
e0 = [e for e in ins if (lambda b: fl.contains((b[0]+b[2])/2,(b[1]+b[3])/2))(entity_bbox(e))][0]
print('insert', e0.dxf.handle, 'scale', e0.dxf.xscale, e0.dxf.yscale, 'rot', e0.dxf.rotation)
rows=[]
for v in e0.virtual_entities():
    t=v.dxftype()
    if t=='LWPOLYLINE':
        pts=[fl.to_local(p[0],p[1]) for p in v.get_points('xy')]
    elif t=='HATCH':
        pp=list(ezpath.from_hatch(v))
        pts=[fl.to_local(q.x,q.y) for q in pp[0].flattening(0.005)] if pp else []
    elif t=='LINE':
        pts=[fl.to_local(v.dxf.start.x,v.dxf.start.y), fl.to_local(v.dxf.end.x,v.dxf.end.y)]
    else:
        print('other', t, v.dxf.layer); continue
    xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
    A = Polygon(pts).area if len(pts)>=3 else 0
    rows.append((round(min(ys),2), t, v.dxf.layer, getattr(v,'closed',None), len(pts), '%.3f %.3f %.3f %.3f'%(min(xs),min(ys),max(xs),max(ys)), '%.2fx%.2f'%(max(xs)-min(xs),max(ys)-min(ys)), round(A,3)))
for r in sorted(rows): print(r)
