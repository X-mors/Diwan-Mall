import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, floor_entities
fl = get_floor(3)
doc = fl.doc
ds = doc.dimstyles.get('WWW')
for k in ('dimlfac','dimdec','dimscale','dimtxt','dimasz','dimzin','dimrnd','dimtad','dimlunit','dimdsep'):
    print(k, ds.dxf.get(k))
n=0
for e in floor_entities(fl, layers="DIM", types="DIMENSION"):
    if e.dimtype != 1 and n>3: continue
    blk = e.get_geometry_block()
    txts = [ (x.dxftype(), x.plain_text() if x.dxftype()=='MTEXT' else x.dxf.text) for x in blk if x.dxftype() in ('MTEXT','TEXT')] if blk else None
    ov = e.get_dim_style() if False else None
    print(e.dimtype, e.dxf.dimtype, "act=", e.dxf.get('actual_measurement'), "get=", round(e.get_measurement(),3), "blk", e.dxf.get('geometry'), txts, "ovr:", e.dimstyle_override().dimstyle_attribs if hasattr(e,"dimstyle_override") else None)
    n+=1
    if n>30: break
