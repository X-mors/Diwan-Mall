import sys
sys.path.insert(0, 'tools')
from diwan_common import get_floor, entity_bbox
from ezdxf import path as ezpath
fl = get_floor(3)
ins = [e for e in fl.msp.query('INSERT[layer=="Etabs-Slab"]')][0]
for v in ins.virtual_entities():
    if v.dxftype()=='HATCH':
        paths=list(ezpath.from_hatch(v))
        if len(paths)>1 or True:
            for i,p in enumerate(paths):
                pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.005)]
                xs=[q[0] for q in pts]; ys=[q[1] for q in pts]
                if min(ys)>35.6 and min(xs)<6:
                    print(v.dxf.handle if v.dxf.hasattr('handle') else '', 'path',i,len(pts),'%.3f %.3f %.3f %.3f'%(min(xs),min(ys),max(xs),max(ys)))
                    print('   ', [(round(a,3),round(b,3)) for a,b in pts])
    if v.dxftype() in ('LWPOLYLINE','LINE'):
        if v.dxftype()=='LINE': pts=[fl.to_local(v.dxf.start.x,v.dxf.start.y),fl.to_local(v.dxf.end.x,v.dxf.end.y)]
        else: pts=[fl.to_local(p[0],p[1]) for p in v.get_points('xy')]
        if min(p[1] for p in pts)>35.6 and min(p[0] for p in pts)<6:
            print(v.dxftype(), [(round(a,3),round(b,3)) for a,b in pts])
