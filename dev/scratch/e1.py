import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
for n in (2,3,6):
    fl=get_floor(n)
    print("== F0%d"%n)
    for e in floor_entities(fl, layers=('W',)):
        t=e.dxftype()
        if t in ('ARC','CIRCLE'):
            c=e.ocs().to_wcs(e.dxf.center); lc=fl.to_local(c.x,c.y)
            sa=e.dxf.get('start_angle',0); ea=e.dxf.get('end_angle',360)
            sw=(ea-sa)%360 if t=='ARC' else 360
            print(t, e.dxf.handle, 'c', [round(v,3) for v in lc], 'r %.3f'%e.dxf.radius, 'sweep %.1f'%sw, 'extr', tuple(e.dxf.extrusion))
        if t=='LWPOLYLINE':
            p=ezpath.make_path(e); pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
            L=sum(math.dist(pts[i],pts[i+1]) for i in range(len(pts)-1))
            if L>5: print('LWP', e.dxf.handle, 'len %.2f'%L, 'closed', e.closed, 'nv', len(e))
    for e in floor_entities(fl, layers=('MASS',)):
        t=e.dxftype()
        if t=='LWPOLYLINE':
            p=ezpath.make_path(e); pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
            L=sum(math.dist(pts[i],pts[i+1]) for i in range(len(pts)-1))
            xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
            print('MASS LWP', e.dxf.handle, 'len %.2f'%L, 'closed', e.closed, 'nv', len(e), '%.2f %.2f %.2f %.2f'%(min(xs),min(ys),max(xs),max(ys)))
