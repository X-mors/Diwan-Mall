import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, entity_bbox, floor_entities
fl = get_floor(int(sys.argv[1]) if len(sys.argv)>1 else 3)
c = Counter(); styles=Counter(); vals=Counter(); ovr=Counter()
rows=[]
for e in floor_entities(fl, layers="DIM", types="DIMENSION"):
    dt = e.dimtype
    c[dt]+=1; styles[e.dxf.dimstyle]+=1
    try: m = e.get_measurement()
    except Exception as ex: m = None
    t = e.dxf.get('text','')
    ovr[t]+=1
    p2 = e.dxf.get('defpoint2'); p3 = e.dxf.get('defpoint3'); p1=e.dxf.defpoint
    a = fl.to_local(p2.x,p2.y) if p2 else None; b = fl.to_local(p3.x,p3.y) if p3 else None
    rows.append((dt, m, t, a, b, e.dxf.get('angle',0), e.dxf.handle))
print(c, styles)
print("text overrides:", ovr.most_common(10))
for r in sorted(rows, key=lambda r:(r[3][1] if r[3] else 0)):
    dt,m,t,a,b,ang,h = r
    if isinstance(m,(int,float)):
        ms = f"{m:.3f}"
    else: ms=str(m)
    d = math.dist(a,b) if a and b else None
    print(f"  t={dt} m={ms} txt={t!r} ang={ang:.1f} p2=({a[0]:.3f},{a[1]:.3f}) p3=({b[0]:.3f},{b[1]:.3f}) dist={d:.3f}")
