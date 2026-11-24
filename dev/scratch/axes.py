import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, entity_bbox, floor_entities
from sosa_decode import decode, is_arabic_style
fl = get_floor(int(sys.argv[1]) if len(sys.argv)>1 else 3)
doc = fl.doc; msp = fl.msp
print("X lines:")
for e in floor_entities(fl, layers=("X","x1"), types="LINE"):
    a = fl.to_local(e.dxf.start.x, e.dxf.start.y); b = fl.to_local(e.dxf.end.x, e.dxf.end.y)
    print(f"  {e.dxf.layer} ({a[0]:.3f},{a[1]:.3f})-({b[0]:.3f},{b[1]:.3f}) lt={e.dxf.get('linetype','')} col={e.dxf.get('color')}")
print("bubbles:")
def walk(e, depth=0):
    for v in e.virtual_entities():
        t = v.dxftype()
        if t == 'INSERT':
            yield from walk(v, depth+1)
        else:
            yield v
for e in msp.query('INSERT'):
    if e.dxf.layer not in ('X','W'): continue
    bb = entity_bbox(e)
    if not bb: continue
    cx, cy = (bb[0]+bb[2])/2, (bb[1]+bb[3])/2
    if not fl.contains(cx, cy): continue
    if e.dxf.name.startswith('D') or e.dxf.name in ('LP',): continue
    circ = None; txt = None
    for v in walk(e):
        if v.dxftype()=="CIRCLE": circ = (v.ocs().to_wcs(v.dxf.center), v.dxf.radius)
        if v.dxftype()=='TEXT': txt = v
    if circ is None: 
        print("  no circle", e.dxf.name, e.dxf.layer); continue
    c = fl.to_local(circ[0].x, circ[0].y); tp = txt.ocs().to_wcs(txt.dxf.insert) if txt else None; tl = fl.to_local(tp.x,tp.y) if tp else None
    raw = txt.dxf.text if txt else None
    st = txt.dxf.get('style') if txt else None
    print(f"  {e.dxf.layer:2} {e.dxf.name:12} c=({c[0]:8.3f},{c[1]:8.3f}) r={circ[1]:.3f} raw={raw!r} dec={decode(raw) if raw and is_arabic_style(doc,st) else raw!r} style={st} t=({tl[0]:.2f},{tl[1]:.2f}) ext={tuple(txt.dxf.extrusion)} rot={txt.dxf.rotation:.1f}")
