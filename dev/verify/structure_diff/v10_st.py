import sys, math, json
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from collections import Counter, defaultdict
n=int(sys.argv[1]); fl=get_floor(n)
segs=[]
for e in floor_entities(fl, layers=('ST',)):
    if e.dxftype()=='LINE':
        a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
        segs.append((a,b))
    else: print('ST other', e.dxftype())
print('n ST lines', len(segs))
for region,(x0,y0,x1,y1) in {'ST1':(9.5,25,15,30),'ST2':(2.5,9,8,13)}.items():
    S=[s for s in segs if all(x0<=p[0]<=x1 and y0<=p[1]<=y1 for p in s)]
    groups=defaultdict(list)
    for a,b in S:
        L=math.dist(a,b)
        if abs(a[0]-b[0])<0.01: groups[('v',round(min(a[1],b[1]),2),round(max(a[1],b[1]),2))].append(round(a[0],3))
        elif abs(a[1]-b[1])<0.01: groups[('h',round(min(a[0],b[0]),2),round(max(a[0],b[0]),2))].append(round(a[1],3))
        else: groups[('d',)].append((a,b))
    print(region, len(S))
    for k,v in sorted(groups.items(), key=lambda kv:-len(kv[1])):
        vv=sorted(v) if k[0]!='d' else v
        print('  ',k, len(v), vv if len(v)<25 else '')
r=json.load(open('output/structure/%s.json'%fl.label,encoding='utf-8'))
for s in r['stairs']:
    print(s['id'], s['bbox'], s['size_txt'], s['st_lines'], [(f['orientation'],f['tread_lines'],f['width'],f['going_median'],f['extent']) for f in s['flights_ST']])
