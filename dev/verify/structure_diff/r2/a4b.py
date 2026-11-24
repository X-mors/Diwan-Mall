import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor
from sosa_decode import decode
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
fl = get_floor(n)
for e in fl.msp.query("INSERT"):
    if e.dxf.layer not in ("X", "W"): continue
    nm = e.dxf.name
    if nm.startswith("D") and "W" in nm[1:] or nm in ("LP",): continue
    ip = fl.to_local(e.dxf.insert.x, e.dxf.insert.y)
    txt = []; circ = []
    try:
        for v in e.virtual_entities():
            if v.dxftype() == "TEXT":
                txt.append((v.dxf.text, decode(v.dxf.text), fl.to_local(v.dxf.insert.x, v.dxf.insert.y)))
            elif v.dxftype() == "INSERT":
                for w in v.virtual_entities():
                    if w.dxftype() == "CIRCLE":
                        wc = w.ocs().to_wcs(w.dxf.center)
                        circ.append(fl.to_local(wc.x, wc.y))
    except Exception as ex:
        print("ERR", ex)
    pts = [t[2] for t in txt] + circ
    if not pts: continue
    cx = sum(p[0] for p in pts)/len(pts); cy = sum(p[1] for p in pts)/len(pts)
    if not (-30 < cx < 50 and -30 < cy < 70): continue
    print(e.dxf.layer, nm, e.dxf.handle, "txt", [(t[0], t[1], [round(c, 2) for c in t[2]]) for t in txt], "circ", [[round(c, 2) for c in cc] for cc in circ])
