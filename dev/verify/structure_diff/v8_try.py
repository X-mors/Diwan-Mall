import sys, math, json
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
n=int(sys.argv[1]); fl=get_floor(n)
for e in floor_entities(fl, layers=('try',)):
    t=e.dxftype()
    if t=='HATCH':
        for p in ezpath.from_hatch(e):
            pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.005)]
            xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
            print('try HATCH', e.dxf.handle, '%.3f %.3f %.3f %.3f'%(min(xs),min(ys),max(xs),max(ys)))
    elif t=='LWPOLYLINE':
        pts=[fl.to_local(p[0],p[1]) for p in e.get_points('xy')]
        xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
        print('try LWPOLY', e.dxf.handle, 'closed',e.closed, len(pts), '%.3f %.3f %.3f %.3f  %.2fx%.2f'%(min(xs),min(ys),max(xs),max(ys),max(xs)-min(xs),max(ys)-min(ys)))
    else:
        print('try', t, e.dxf.handle)
r=json.load(open('output/structure/%s.json'%fl.label,encoding='utf-8'))
print('--- tool shafts')
for s in r['shafts']:
    print(s['id'], s['kind'], s['source'], s['bbox'], s['size_txt'], s['area'], s['dash_diagonals'], s['duplicates'])
