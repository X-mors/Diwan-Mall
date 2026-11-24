import sys, collections, math
sys.path.insert(0, 'tools')
import ezdxf
from diwan_common import get_floor
from sosa_decode import decode
fl=get_floor(3)
doc=fl.doc; msp=doc.modelspace()
rows=[]
for e in msp.query('INSERT[layer=="W"]'):
    n=e.dxf.name
    if n.startswith('D') and 'W' in n[1:] or n=='LP': continue
    ents=list(e.virtual_entities())
    types=collections.Counter(v.dxftype() for v in ents)
    txt=[v.dxf.text for v in ents if v.dxftype()=='TEXT']
    # bbox of virtual entities in local
    pts=[]
    for v in ents:
        if v.dxftype()=='CIRCLE': pts.append(fl.to_local(v.dxf.center.x,v.dxf.center.y))
        if v.dxftype()=='TEXT': pts.append(fl.to_local(v.dxf.insert.x,v.dxf.insert.y))
    ip=fl.to_local(e.dxf.insert.x,e.dxf.insert.y)
    rows.append((n,dict(types),txt,[decode(t) for t in txt],[round(float(x),1) for x in ip],[ [round(float(c),1) for c in p] for p in pts[:2]]))
print(len(rows))
for r in rows: print(r)
