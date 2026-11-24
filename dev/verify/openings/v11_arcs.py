import sys, json, math, collections
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
for fl in all_floors():
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    dc=[d['hinge'] for d in js['doors']]
    out=[]
    cnt=collections.Counter()
    for e in floor_entities(fl, types=('ARC','CIRCLE','ELLIPSE','SPLINE')):
        t=e.dxftype(); cnt[(e.dxf.layer,t)]+=1
        if t in ('ARC','CIRCLE'):
            r=e.dxf.radius
            c=fl.to_local(e.dxf.center.x,e.dxf.center.y) if tuple(e.dxf.extrusion)==(0,0,1) else None
            if 0.4<r<1.6:
                near=min((math.dist(c,h) for h in dc),default=9) if c else None
                out.append((e.dxf.layer,t,e.dxf.handle,round(r,3),[round(v,2) for v in c] if c else 'OCS',round(near,2) if near is not None else None))
    print(fl.label, dict(cnt))
    for o in out: print('   ',o)
