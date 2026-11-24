"""dump W / Etabs-col / COL / WIN / try segments in a local window"""
import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
F=int(sys.argv[1]); x0,y0,x1,y1=map(float,sys.argv[2:6])
layers=tuple(sys.argv[6].split(',')) if len(sys.argv)>6 else ('W','Etabs-col','COL','WIN','try','0','PR')
fl=get_floor(F)
def inside(p): return x0<=p[0]<=x1 and y0<=p[1]<=y1
for e in floor_entities(fl, layers=layers):
    t=e.dxftype()
    if t=='LINE':
        a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
        if inside(a) or inside(b):
            print(e.dxf.layer, t, e.dxf.handle, '(%.3f,%.3f)-(%.3f,%.3f) L=%.3f'%(a[0],a[1],b[0],b[1],math.dist(a,b)))
    elif t in ('LWPOLYLINE','ARC','CIRCLE','HATCH','INSERT'):
        try:
            if t=='HATCH':
                continue
            if t=='INSERT':
                p=fl.to_local(e.dxf.insert.x,e.dxf.insert.y)
                if inside(p): print(e.dxf.layer,t,e.dxf.handle,e.dxf.name,'(%.3f,%.3f)'%p)
                continue
            pts=[fl.to_local(v.x,v.y) for v in ezpath.make_path(e).flattening(0.01)]
        except Exception as ex:
            continue
        if any(inside(p) for p in pts):
            s=' '.join('(%.3f,%.3f)'%p for p in pts[:14])
            print(e.dxf.layer, t, e.dxf.handle, 'closed' if getattr(e,'closed',False) else '', s, '...' if len(pts)>14 else '')
