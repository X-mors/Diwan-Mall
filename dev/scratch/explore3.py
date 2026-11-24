import sys, math, collections
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
fl = get_floor(3)
c = collections.Counter()
for e in floor_entities(fl, types="INSERT"):
    c[(e.dxf.layer, e.dxf.name)] += 1
for k,v in sorted(c.items()): print(k, v)
doc = fl.doc
for name in ["D10W12","D80W12","D90W12","D90W25","LP","WB","P"]:
    if name in doc.blocks:
        blk = doc.blocks[name]
        ents = [(e.dxftype(), e.dxf.layer) for e in blk]
        bb = None
        from ezdxf import bbox
        b = bbox.extents(blk)
        print(name, collections.Counter(ents), "bbox", b.extmin, b.extmax, "base", blk.block.dxf.base_point)
# random-named blocks
for k in c:
    if k[1] not in ("D10W12","D80W12","D90W12","D90W25","LP","WB","P"):
        blk = doc.blocks[k[1]]
        print(k, [(e.dxftype(), e.dxf.layer, (e.dxf.text if e.dxftype()=="TEXT" else e.dxf.get("name",""))) for e in blk][:6])
