import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
from ezdxf import path as ezpath
bad=0; n=0
for fl in all_floors():
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    tool={d['handle']:d for d in js['doors'] if d.get('source')=='block'}
    for e in floor_entities(fl, types='INSERT'):
        if e.dxf.handle not in tool: continue
        d=tool[e.dxf.handle]
        # leaf arc = biggest radius arc in virtual entities
        arcs=[v for v in e.virtual_entities() if v.dxftype()=='ARC']
        a=max(arcs,key=lambda v:v.dxf.radius)
        pts=[fl.to_local(p.x,p.y) for p in ezpath.make_path(a).flattening(0.01)]
        pm=pts[len(pts)//2]
        c=d['center']
        # which side of the door line is pm ?
        ja=d['jamb_a']; jb=d['jamb_b']
        A=((ja[0][0]+ja[1][0])/2,(ja[0][1]+ja[1][1])/2); B=((jb[0][0]+jb[1][0])/2,(jb[0][1]+jb[1][1])/2)
        cross=(B[0]-A[0])*(pm[1]-A[1])-(B[1]-A[1])*(pm[0]-A[0])
        tpm=d['leaf_geom']['pm']
        n+=1
        if math.dist(pm,tpm)>0.05:
            bad+=1; print(fl.label,d['id'],'my pm',[round(v,3) for v in pm],'tool pm',tpm, 'r', a.dxf.radius)
        # hinge check: arc centre should coincide with tool hinge
        cc=fl.to_local(*ezpath.make_path(a).start.xy) if False else None
print('checked',n,'mismatch',bad)
