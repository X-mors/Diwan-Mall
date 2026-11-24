import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from sosa_decode import decode
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
fl = get_floor(n)
print("== X lines")
for L in ("X", "x1"):
    for e in floor_entities(fl, layers=L):
        if e.dxftype() == "LINE":
            a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
            v = "V" if abs(a[0]-b[0]) < 0.01 else ("H" if abs(a[1]-b[1]) < 0.01 else "?")
            print(L, e.dxf.handle, v, [round(c, 3) for c in a], [round(c, 3) for c in b])
print("== bubble/tag inserts (layers X and W, non-door)")
for e in floor_entities(fl, layers=("X", "W"), types="INSERT"):
    nm = e.dxf.name
    if nm.startswith("D") and "W" in nm[1:]: continue
    if nm in ("LP",): continue
    txt = []; circ = []
    for v in e.virtual_entities():
        if v.dxftype() == "TEXT":
            txt.append((v.dxf.text, decode(v.dxf.text), fl.to_local(v.dxf.insert.x, v.dxf.insert.y)))
        elif v.dxftype() == "INSERT":
            for w in v.virtual_entities():
                if w.dxftype() == "CIRCLE":
                    c = w.dxf.center
                    # OCS->WCS
                    ocs = w.ocs(); wc = ocs.to_wcs(c)
                    circ.append((fl.to_local(wc.x, wc.y), round(w.dxf.radius, 3)))
    ip = fl.to_local(e.dxf.insert.x, e.dxf.insert.y)
    print(e.dxf.layer, nm, e.dxf.handle, "ins", [round(c, 2) for c in ip], "txt", [(t[0], t[1], [round(c, 2) for c in t[2]]) for t in txt], "circ", [([round(c, 2) for c in cc[0]], cc[1]) for cc in circ])
