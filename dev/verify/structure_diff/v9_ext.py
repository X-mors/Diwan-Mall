import sys, math, json
sys.path.insert(0, 'tools')
import numpy as np
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import unary_union
n=int(sys.argv[1]); fl=get_floor(n)
L=[]
for e in floor_entities(fl, layers=('W','WIN','Etabs-col')):
    if e.dxftype() in ('INSERT','TEXT','MTEXT','HATCH','DIMENSION'): continue
    try: p=ezpath.make_path(e)
    except Exception: continue
    pts=[fl.to_local(q.x,q.y) for q in p.flattening(0.01)]
    if len(pts)>=2: L.append(LineString(pts))
U = unary_union([l.buffer(0.04) for l in L])
big = max(U.geoms, key=lambda g: g.area) if U.geom_type=='MultiPolygon' else U
FP = Polygon(big.exterior)
print('footprint area %.2f bounds %s'%(FP.area, [round(v,2) for v in FP.bounds]))
r=json.load(open('output/structure/%s.json'%fl.label,encoding='utf-8'))
tot_ext=0
for el in r['elements']:
    if el['kind']=='column_xbox': continue
    P=Polygon(el['outline'])
    ext=0; per=0
    co=list(P.exterior.coords)
    for i in range(len(co)-1):
        a=np.array(co[i]); b=np.array(co[i+1]); Lf=np.hypot(*(b-a))
        if Lf<0.01: continue
        u=(b-a)/Lf; nrm=np.array([-u[1],u[0]])
        if P.contains(Point(*((a+b)/2+nrm*0.01))): nrm=-nrm
        k=max(1,int(round(Lf/0.02)))
        for j in range(k):
            q=a+u*((j+0.5)*Lf/k)+nrm*0.10
            if not FP.contains(Point(*q)): ext+=Lf/k
    if ext>0.01:
        print(el['id'], el['size_txt'], 'faces outside footprint (10cm out): %.2f m'%ext, 'exposed_perimeter', el['exposed_perimeter'])
    tot_ext+=ext
print('TOTAL outward-facing perimeter %.2f'%tot_ext)
