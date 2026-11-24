import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor
from sosa_decode import decode
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
fl = get_floor(n)
def walk(e, depth=0, path=""):
    try:
        for v in e.virtual_entities():
            if v.dxftype() in ("TEXT", "MTEXT"):
                yield v, path
            elif v.dxftype() == "INSERT" and depth < 3:
                yield from walk(v, depth+1, path + "/" + v.dxf.name)
    except Exception:
        return
for e in fl.msp.query("INSERT TEXT MTEXT"):
    if e.dxftype() == "INSERT":
        for v, p in walk(e, 0, e.dxf.name):
            t = v.dxf.text if v.dxftype() == "TEXT" else v.text
            if t.strip() in ("7", "&"):
                lp = fl.to_local(v.dxf.insert.x, v.dxf.insert.y)
                if -40 < lp[0] < 60 and -40 < lp[1] < 80:
                    print("INSERT", e.dxf.layer, e.dxf.handle, p, repr(t), [round(c, 2) for c in lp])
    else:
        t = e.dxf.text if e.dxftype() == "TEXT" else e.text
        if t.strip() == "7":
            lp = fl.to_local(e.dxf.insert.x, e.dxf.insert.y)
            if -40 < lp[0] < 60 and -40 < lp[1] < 80:
                print(e.dxftype(), e.dxf.layer, e.dxf.handle, repr(t), [round(c, 2) for c in lp])
