import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, Polygon
for n in (2,3):
    fl=get_floor(n)
    for e in floor_entities(fl, layers=('MASS','W'), types='LWPOLYLINE'):
        p=ezpath.make_path(e); pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
        L=LineString(pts).length
        if L>20:
            xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
            A = Polygon(pts).area if e.closed else None
            print(fl.label, e.dxf.layer, e.dxf.handle, 'closed',e.closed, 'len %.2f'%L, 'area', A and round(A,2), '%.2f %.2f %.2f %.2f'%(min(xs),min(ys),max(xs),max(ys)), 'lineweight', e.dxf.get('lineweight'), 'color', e.dxf.get('color'))
