import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities, entity_bbox
from sosa_decode import decode
n=int(sys.argv[1]); fl=get_floor(n)
print('== X lines')
for e in floor_entities(fl, layers=('X','x1'), types='LINE'):
    a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
    print(e.dxf.layer, e.dxf.handle, '(%.3f,%.3f)-(%.3f,%.3f)'%(a[0],a[1],b[0],b[1]), 'len %.2f'%math.dist(a,b))
print('== inserts with text (X / W layers, incl offsheet)')
for e in fl.msp.query('INSERT'):
    if e.dxf.layer not in ('X','W'): continue
    b = entity_bbox(e)
    if not b or not fl.contains((b[0]+b[2])/2,(b[1]+b[3])/2): continue
    txt=None; circ=None
    def walk(x, d=0):
        for v in x.virtual_entities():
            if v.dxftype()=='INSERT' and d<3: yield from walk(v,d+1)
            else: yield v
    try:
        for v in walk(e):
            if v.dxftype()=='TEXT': txt=v
            if v.dxftype()=='CIRCLE':
                c=v.ocs().to_wcs(v.dxf.center); circ=(fl.to_local(c.x,c.y), v.dxf.radius)
    except Exception as ex: continue
    if txt is None: continue
    tp = txt.dxf.insert
    print(e.dxf.layer, e.dxf.name, e.dxf.handle, 'raw=%r dec=%r'%(txt.dxf.text, decode(txt.dxf.text)), 'circ', circ and ('%.3f,%.3f r%.3f'%(circ[0][0],circ[0][1],circ[1])), 'txtpos %.3f,%.3f'%fl.to_local(tp.x,tp.y))
