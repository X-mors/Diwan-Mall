import sys, math
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
from collections import Counter
F={}
for fl in all_floors():
    L=[]
    for e in floor_entities(fl, types='INSERT'):
        p=fl.to_local(e.dxf.insert.x,e.dxf.insert.y)
        L.append((e.dxf.name, p, (e.dxf.rotation-fl.angle)%360, (e.dxf.xscale<0)!=(e.dxf.yscale<0), round(abs(e.dxf.xscale),3), round(abs(e.dxf.yscale),3), e.dxf.layer))
    F[fl.label]=L
    print(fl.label, Counter((x[0][:6] if x[0].startswith('D') else x[0], x[4], x[5]) for x in L if x[0] in ('LP','P','WB','ST-2') or x[0].startswith('D')))
def same(a,b): return a[0]==b[0] and math.dist(a[1],b[1])<=0.02 and abs((a[2]-b[2]+180)%360-180)<0.5 and a[3]==b[3]
for A in F:
    for B in F:
        if A>=B: continue
        for a in F[A]:
            for b in F[B]:
                if same(a,b) and (a[4]!=b[4] or a[5]!=b[5]):
                    print('scale differs', A,B,a[0],[round(v,2) for v in a[1]],a[4:6],b[4:6])
