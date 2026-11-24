import sys, json, math, collections
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
import ezdxf
from ezdxf import path as ezpath
for fl in all_floors():
    if fl.label not in ('F02','F03','F05','F08'): continue
    lay = fl.doc.layers.get('WIN')
    print('=====', fl.label, 'WIN layer linetype', lay.dxf.linetype)
    ents = floor_entities(fl, layers='WIN')
    cnt = collections.Counter((e.dxftype(), e.dxf.get('linetype','BYLAYER')) for e in ents)
    print(' ', dict(cnt))
    segs=[]
    for e in ents:
        if e.dxftype()=='LINE' and e.dxf.get('linetype','BYLAYER').upper() in ('BYLAYER','CONTINUOUS'):
            a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
            segs.append((e.dxf.handle,a,b,math.dist(a,b)))
    # group: lines parallel, offset 0.05-0.35, overlapping
    used=set(); units=[]
    def dirv(a,b):
        L=math.dist(a,b); return ((b[0]-a[0])/L,(b[1]-a[1])/L)
    for i,(h1,a1,b1,L1) in enumerate(segs):
        for j,(h2,a2,b2,L2) in enumerate(segs):
            if j<=i: continue
            d1=dirv(a1,b1); d2=dirv(a2,b2)
            if abs(abs(d1[0]*d2[0]+d1[1]*d2[1])-1)>1e-4: continue
            n=(-d1[1],d1[0])
            off=abs((a2[0]-a1[0])*n[0]+(a2[1]-a1[1])*n[1])
            if not (0.04<off<0.36): continue
            t=lambda p:(p[0]-a1[0])*d1[0]+(p[1]-a1[1])*d1[1]
            s1=sorted([t(a1),t(b1)]); s2=sorted([t(a2),t(b2)])
            ov=min(s1[1],s2[1])-max(s1[0],s2[0])
            if ov>0.05:
                units.append((round(ov,3),round(off,3),h1,h2,[round(v,2) for v in a1],[round(v,2) for v in b1], L1, L2))
    units.sort(key=lambda u:(u[4][1],u[4][0]))
    tot=0
    for u in units:
        print('   pair ov=%.3f off=%.3f %s %s a=%s b=%s L1=%.3f L2=%.3f'%u)
    arcs=[e for e in ents if e.dxftype()=='ARC']
    for e in arcs:
        c=fl.to_local(e.dxf.center.x,e.dxf.center.y)
        print('   ARC',e.dxf.handle,'c',[round(v,3) for v in c],'r',round(e.dxf.radius,3),'sweep',round((e.dxf.end_angle-e.dxf.start_angle)%360,2),'extr',tuple(e.dxf.extrusion), 'lt',e.dxf.get('linetype','BYLAYER'))
