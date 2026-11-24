import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, Polygon
for fl in all_floors():
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    segs=[]
    for e in floor_entities(fl, layers=('W','Etabs-col','COL','try')):
        t=e.dxftype()
        try:
            if t=='LINE': pts=[fl.to_local(e.dxf.start.x,e.dxf.start.y), fl.to_local(e.dxf.end.x,e.dxf.end.y)]
            elif t in ('LWPOLYLINE','ARC','CIRCLE'): pts=[fl.to_local(v.x,v.y) for v in ezpath.make_path(e).flattening(0.01)]
            else: continue
        except Exception: continue
        for p,q in zip(pts,pts[1:]):
            if math.dist(p,q)>1e-4: segs.append((LineString([tuple(map(float,p)),tuple(map(float,q))]),e.dxf.layer,e.dxf.handle))
    items=[(d['id'],d['jamb_a'],d['jamb_b']) for d in js['doors'] if d.get('source')=='block']
    bad=[]
    for i,ja,jb in items:
        A=[(ja[0][0]+ja[1][0])/2,(ja[0][1]+ja[1][1])/2]; B=[(jb[0][0]+jb[1][0])/2,(jb[0][1]+jb[1][1])/2]
        L=math.dist(A,B); d=((B[0]-A[0])/L,(B[1]-A[1])/L); n=(-d[1],d[0])
        s=0.04; h=0.20
        P=[(A[0]+d[0]*s+n[0]*h,A[1]+d[1]*s+n[1]*h),(B[0]-d[0]*s+n[0]*h,B[1]-d[1]*s+n[1]*h),(B[0]-d[0]*s-n[0]*h,B[1]-d[1]*s-n[1]*h),(A[0]+d[0]*s-n[0]*h,A[1]+d[1]*s-n[1]*h)]
        poly=Polygon(P)
        hits=[(l,hd,round(g.intersection(poly).length,3)) for g,l,hd in segs if g.intersects(poly) and g.intersection(poly).length>0.05]
        if hits: bad.append((i,hits))
    print(fl.label,'doors with W/col inside opening band (+-0.20):',len(bad))
    for b in bad: print('   ',b)
