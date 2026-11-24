import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
for F in (3,5):
    fl=get_floor(F)
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    jpts=[]
    for d in js['doors']:
        for j in (d['jamb_a'],d['jamb_b']):
            jpts += [tuple(j[0]),tuple(j[1]),((j[0][0]+j[1][0])/2,(j[0][1]+j[1][1])/2)]
    hits=[]; small=[]
    for e in floor_entities(fl, layers='DIM', types='DIMENSION'):
        try:
            p2=fl.to_local(e.dxf.defpoint2.x,e.dxf.defpoint2.y); p3=fl.to_local(e.dxf.defpoint3.x,e.dxf.defpoint3.y)
        except Exception: continue
        m=e.get_measurement() if hasattr(e,'get_measurement') else None
        for p in (p2,p3):
            dmin=min(math.dist(p,q) for q in jpts)
            if dmin<0.06: hits.append((e.dxf.handle,round(m,3) if m else None,[round(v,3) for v in p],round(dmin,3)))
        if m and 0.6<m<1.3: small.append((e.dxf.handle,round(m,3),[round(v,3) for v in p2],[round(v,3) for v in p3]))
    print(fl.label,'dims near door jambs:',hits)
    print(fl.label,'dims 0.6-1.3:',small)
