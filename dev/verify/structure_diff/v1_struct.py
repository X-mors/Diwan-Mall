import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities, entity_bbox
from ezdxf import path as ezpath
from shapely.geometry import Polygon
for n in [int(a) for a in sys.argv[1:]]:
    fl = get_floor(n)
    print('=====', fl.label, fl.file.name, fl.sheet_index)
    ents = floor_entities(fl, layers=('Etabs-col','COL','Etabs-Slab'))
    for e in ents:
        t = e.dxftype()
        if t == 'LWPOLYLINE':
            pts = [fl.to_local(p[0], p[1]) for p in e.get_points('xy')]
            xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
            print(e.dxf.layer, t, e.dxf.handle, 'closed', e.closed, 'n', len(pts), 'bbox %.3f %.3f %.3f %.3f' % (min(xs),min(ys),max(xs),max(ys)), 'size %.3f x %.3f'%(max(xs)-min(xs), max(ys)-min(ys)))
        elif t == 'HATCH':
            for p in ezpath.from_hatch(e):
                pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.005)]
                xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
                print(e.dxf.layer, t, e.dxf.handle, e.dxf.pattern_name, 'bbox %.3f %.3f %.3f %.3f' % (min(xs),min(ys),max(xs),max(ys)), 'area %.3f'%Polygon(pts).area)
        else:
            print(e.dxf.layer, t, e.dxf.handle, getattr(e.dxf,'name',''))
    # all inserts on Etabs-Slab in whole msp
    for e in fl.msp.query('INSERT[layer=="Etabs-Slab"]'):
        b = entity_bbox(e)
        print('Etabs-Slab INSERT', e.dxf.handle, e.dxf.name, 'ins', fl.to_local(e.dxf.insert.x, e.dxf.insert.y), 'bbox', b and [round(v,1) for v in b], 'contains-centre', b and fl.contains((b[0]+b[2])/2,(b[1]+b[3])/2))
