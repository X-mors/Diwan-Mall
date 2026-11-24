import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString
from shapely.ops import unary_union
fl=get_floor(2)
P=None; others=[]
for e in floor_entities(fl, layers=('W',)):
    if e.dxftype() in ('INSERT','TEXT','MTEXT','DIMENSION'): continue
    try: ps=list(ezpath.from_hatch(e)) if e.dxftype()=='HATCH' else [ezpath.make_path(e)]
    except Exception: continue
    for p in ps:
        pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
        if len(pts)<2: continue
        if e.dxf.handle=='1585': P=LineString(pts)
        elif e.dxf.handle not in ('113F',): others.append(LineString(pts))
U=unary_union(others)
B=U.buffer(0.02)
print('1585 len %.2f, overlapping other W within 2cm: %.2f, unique: %.2f'%(P.length, P.intersection(B).length, P.difference(B).length))
raw=sum(l.length for l in others); print('other W raw %.2f union %.2f dup %.2f'%(raw, U.length, raw-U.length))
