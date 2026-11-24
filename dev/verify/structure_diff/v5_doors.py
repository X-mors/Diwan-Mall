import sys, math, re
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities, entity_bbox
from collections import Counter
D = {}
for fl in all_floors():
    L = []
    for e in fl.msp.query('INSERT'):
        if not re.match(r'^D\d+W\d+$', e.dxf.name): continue
        p = e.dxf.insert
        on = fl.contains(p.x, p.y)
        b = entity_bbox(e)
        onb = b and fl.contains((b[0]+b[2])/2, (b[1]+b[3])/2)
        if on or onb:
            lp = fl.to_local(p.x, p.y)
            L.append((e.dxf.name, round(lp[0],3), round(lp[1],3), round((e.dxf.rotation-fl.angle)%360,1), e.dxf.xscale<0, e.dxf.yscale<0, e.dxf.handle, on))
    D[fl.label] = L
    print(fl.label, len(L), Counter(x[0] for x in L), 'offsheet-insert', sum(1 for x in L if not x[7]))
def same(a,b):
    return a[0]==b[0] and math.dist(a[1:3], b[1:3])<=0.02 and abs((a[3]-b[3]+180)%360-180)<0.5 and (a[4]!=a[5])==(b[4]!=b[5])
labs=sorted(D)
for A in labs:
    print(A, [sum(1 for a in D[A] if not any(same(a,b) for b in D[B])) for B in labs])
# also print what differs F04 vs F07 and F06
for A,B in [('F04','F07'),('F07','F04'),('F06','F04'),('F04','F06'),('F05','F04')]:
    print(A,'not in',B,[a for a in D[A] if not any(same(a,b) for b in D[B])])
