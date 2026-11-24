import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_texts
for fl in all_floors():
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    doors=[(d['id'],d['center'],d.get('block'),d.get('opens_into'),d.get('other_side')) for d in js['doors']]
    labs=[t for t in floor_texts(fl) if t['layer'] in ('TEXT','-A-TEXT')]
    out=[]
    for t in labs:
        txt=t['text'].strip()
        if not txt: continue
        p=t['local']
        # rooms named by a door
        named=[d[0] for d in doors if txt in ((d[3] or ''),(d[4] or ''))]
        near=min(doors,key=lambda d:math.dist(d[1],p))
        dn=math.dist(near[1],p)
        if txt=='حمام' or dn>3.5:
            out.append((txt,[round(float(v),2) for v in p],'nearest',near[0],near[2],round(dn,2)))
    print(fl.label, len(labs))
    for o in out:
        if o[0]=='حمام' and o[5]<2.6: continue
        print('   ',o)
