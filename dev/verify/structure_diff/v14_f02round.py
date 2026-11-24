import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
fl=get_floor(2)
for e in floor_entities(fl, layers=('W',)):
    t=e.dxftype()
    if t in ('ARC','LWPOLYLINE','CIRCLE','INSERT'):
        if t=='INSERT':
            p=fl.to_local(e.dxf.insert.x,e.dxf.insert.y); print('INSERT', e.dxf.name, e.dxf.handle, [round(v,2) for v in p]); continue
        p=ezpath.make_path(e); pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
        xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
        bul = t=='LWPOLYLINE' and any(abs(b)>1e-6 for *_,b in e.get_points('xyb'))
        print(t, e.dxf.handle, 'n',len(pts), 'bulge' if bul else '', 'closed' if getattr(e,'closed',False) else '', '%.2f %.2f %.2f %.2f'%(min(xs),min(ys),max(xs),max(ys)))
