import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
fl=get_floor(5)
for e in floor_entities(fl, layers='WIN'):
    if e.dxftype()=='LINE':
        a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
        print(e.dxf.handle, e.dxf.get('linetype','BYLAYER'), [round(v,3) for v in a],[round(v,3) for v in b], round(math.dist(a,b),3))
