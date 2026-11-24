# Verifier scratch: raw inventory of W / blocks per floor (independent of walls.py)
import sys, math, json
from collections import Counter, defaultdict
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import all_floors, floor_entities

for fl in all_floors():
    c = Counter()
    ins = Counter()
    blkgeo = Counter()
    for e in floor_entities(fl, layers="W"):
        c[e.dxftype()] += 1
        if e.dxftype() == "INSERT":
            ins[e.dxf.name] += 1
    # every INSERT on floor: does its block contain LINE/LWPOLY geometry on layer W (or layer 0 inherited W)?
    wblk = Counter()
    for e in floor_entities(fl, types="INSERT"):
        try:
            for v in e.virtual_entities():
                lay = v.dxf.layer
                if lay == "W" or (lay == "0" and e.dxf.layer == "W"):
                    if v.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
                        wblk[(e.dxf.name, e.dxf.layer, v.dxftype())] += 1
        except Exception as ex:
            pass
    print(fl.label, dict(c))
    print("   W inserts:", dict(ins))
    print("   block geometry landing on W:", dict(wblk))
