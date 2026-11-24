import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
JAMB = {'D10W12':0.12,'D80W12':0.12,'D90W12':0.12,'D90W25':0.25}
WID = {'D10W12':1.0,'D80W12':0.8,'D90W12':0.9,'D90W25':0.9}
tot_bad=0
for fl in all_floors():
    js = json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    tool = {d['handle']:d for d in js['doors'] if d.get('source')=='block'}
    mine = {}
    for e in floor_entities(fl, types='INSERT'):
        n=e.dxf.name
        if n not in JAMB: continue
        m = e.matrix44()
        blk = fl.doc.blocks[n]
        jambs=[]
        for be in blk:
            if be.dxftype()=='LINE':
                s,t = be.dxf.start, be.dxf.end
                if abs(math.dist((s.x,s.y),(t.x,t.y))-JAMB[n])<1e-3:
                    a=m.transform(s); b=m.transform(t)
                    jambs.append((fl.to_local(a.x,a.y), fl.to_local(b.x,b.y)))
        # jamb lines: exact wall_t length; D90W25 also has 0.2 lines
        mids=[((p[0]+q[0])/2,(p[1]+q[1])/2) for p,q in jambs]
        # pick the farthest pair
        best=None
        for i in range(len(mids)):
            for j in range(i+1,len(mids)):
                d=math.dist(mids[i],mids[j])
                if best is None or d>best[0]: best=(d,mids[i],mids[j])
        c=((best[1][0]+best[2][0])/2,(best[1][1]+best[2][1])/2)
        mine[e.dxf.handle]=(n,best[0],c)
    miss = set(mine)-set(tool); extra=set(tool)-set(mine)
    bad=[]
    for h,(n,w,c) in mine.items():
        if h not in tool: continue
        t=tool[h]
        if t['block']!=n or abs(t['width']-w)>0.005 or math.dist(t['center'],c)>0.02:
            bad.append((h,n,round(w,3),[round(v,3) for v in c],t['block'],t['width'],t['center']))
    print(fl.label, 'mine',len(mine),'tool',len(tool),'miss',miss,'extra',extra,'bad',len(bad))
    for b in bad: print('   ',b)
    tot_bad+=len(bad)
print('total bad', tot_bad)
