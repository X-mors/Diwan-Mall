import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from collections import Counter
for n in (2,3,6):
    fl=get_floor(n)
    c=Counter((e.dxf.layer,e.dxftype()) for e in floor_entities(fl) if e.dxftype() in ('CIRCLE','ARC','ELLIPSE','HATCH','SPLINE'))
    print(fl.label, dict(c))
    for e in floor_entities(fl, layers=('W','0','MASS','COL','Etabs-col','HAT','FUR'), types='CIRCLE'):
        c0=e.ocs().to_wcs(e.dxf.center); p=fl.to_local(c0.x,c0.y)
        print('  CIRCLE', e.dxf.layer, e.dxf.handle, 'c=(%.3f,%.3f) r=%.3f'%(p[0],p[1],e.dxf.radius))
    for e in floor_entities(fl, layers=('W',), types='HATCH'):
        from ezdxf import path as ezpath
        for pth in ezpath.from_hatch(e):
            pts=[fl.to_local(q.x,q.y) for q in pth.flattening(0.01)]
            xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
            print('  W HATCH', e.dxf.handle, e.dxf.pattern_name, '%.2f %.2f %.2f %.2f'%(min(xs),min(ys),max(xs),max(ys)))
