import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, Point
from shapely.ops import unary_union
for F in map(int, sys.argv[1:]):
    fl=get_floor(F)
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    segs=[]
    for e in floor_entities(fl, layers=('W','Etabs-col','COL')):
        t=e.dxftype()
        try:
            if t=='LINE': pts=[fl.to_local(e.dxf.start.x,e.dxf.start.y), fl.to_local(e.dxf.end.x,e.dxf.end.y)]
            elif t in ('LWPOLYLINE','ARC','CIRCLE'): pts=[fl.to_local(v.x,v.y) for v in ezpath.make_path(e).flattening(0.01)]
            else: continue
        except Exception: continue
        for p,q in zip(pts,pts[1:]):
            if math.dist(p,q)>1e-4: segs.append(LineString([tuple(map(float,p)),tuple(map(float,q))]))
    G=unary_union(segs)
    wins=[]
    for e in floor_entities(fl, layers='WIN', types='LINE'):
        if e.dxf.get('linetype','BYLAYER').upper()=='DASHED': continue
        a=tuple(map(float,fl.to_local(e.dxf.start.x,e.dxf.start.y))); b=tuple(map(float,fl.to_local(e.dxf.end.x,e.dxf.end.y)))
        wins.append((e.dxf.handle,a,b))
    for w in js['windows']:
        if w.get('shape')!='straight' or w['width']>5: continue
        c=w['center']; ax=math.radians(w['axis_deg']); d=(math.cos(ax),math.sin(ax)); n=(-d[1],d[0])
        res=[]
        for off in (-0.06,0.0,0.06):
            o=(c[0]+n[0]*off,c[1]+n[1]*off)
            hits=[]
            for sgn in (1,-1):
                ray=LineString([o,(o[0]+sgn*d[0]*3.0,o[1]+sgn*d[1]*3.0)])
                X=ray.intersection(G)
                if X.is_empty: hits.append(None); continue
                dist=min(Point(o).distance(g) for g in (getattr(X,'geoms',[X])))
                hits.append(dist)
            if None not in hits: res.append(round(hits[0]+hits[1],3))
        flag='' if res and abs(max(res)-w['width'])<0.02 else '  <-- CHECK'
        print(fl.label,w['id'],'width',w['width'],'my gaps at offsets',res,flag)
