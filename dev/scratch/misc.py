import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, entity_bbox, floor_entities, floor_texts
fl = get_floor(int(sys.argv[1]) if len(sys.argv)>1 else 3)
doc = fl.doc
def L(p): return fl.to_local(p.x, p.y)
for lay in sys.argv[2].split(','):
    print("==", lay, "layer linetype:", doc.layers.get(lay).dxf.linetype if lay in doc.layers else None, "color", doc.layers.get(lay).dxf.color if lay in doc.layers else None)
    for e in floor_entities(fl, layers=lay):
        t = e.dxftype()
        if t == 'LINE':
            a, b = L(e.dxf.start), L(e.dxf.end)
            ang = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 180
            print(f"  LINE ({a[0]:.3f},{a[1]:.3f})-({b[0]:.3f},{b[1]:.3f}) len={math.dist(a,b):.3f} ang={ang:.1f} lt={e.dxf.get('linetype')} ltsc={e.dxf.get('ltscale',1)} col={e.dxf.get('color')}")
        elif t == 'LWPOLYLINE':
            pts = [fl.to_local(e.ocs().to_wcs((p[0],p[1],e.dxf.elevation)).x, e.ocs().to_wcs((p[0],p[1],e.dxf.elevation)).y) for p in e.get_points("xy")]
            print(f"  LWPOLY n={len(pts)} closed={e.closed} lt={e.dxf.get('linetype')}", [(round(x,2),round(y,2)) for x,y in pts][:12])
        elif t == 'INSERT':
            p = L(e.dxf.insert)
            print(f"  INSERT {e.dxf.name} at ({p[0]:.2f},{p[1]:.2f}) sc=({e.dxf.xscale:.2f},{e.dxf.yscale:.2f}) rot={e.dxf.rotation:.1f}")
        elif t in ('TEXT','MTEXT'):
            pass
        elif t == 'ARC':
            c = e.ocs().to_wcs(e.dxf.center); c = fl.to_local(c.x,c.y)
            print(f"  ARC c=({c[0]:.2f},{c[1]:.2f}) r={e.dxf.radius:.3f} {e.dxf.start_angle:.1f}->{e.dxf.end_angle:.1f}")
        else:
            b = entity_bbox(e); 
            print(f"  {t} bbox local", fl.to_local(b[0],b[1]), fl.to_local(b[2],b[3]), e.dxf.get('pattern_name',''))
    for t in floor_texts(fl, layers=lay):
        print(f"  TEXT {t['raw']!r} -> {t['text']!r} at ({t['local'][0]:.2f},{t['local'][1]:.2f}) h={t['height']:.2f} style={t['style']}")
