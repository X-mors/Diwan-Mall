"""Independent hunt for door-less gaps: collinear W face-line gaps where the parallel face also has a gap."""
import sys, json, math
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

def segs_of(fl, layers):
    out=[]
    for e in floor_entities(fl, layers=layers):
        t=e.dxftype()
        try:
            if t=='LINE':
                a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
                out.append((tuple(map(float,a)),tuple(map(float,b)),e.dxf.handle,e.dxf.layer))
            elif t in ('LWPOLYLINE','POLYLINE','ARC','CIRCLE'):
                pts=[tuple(map(float,fl.to_local(v.x,v.y))) for v in ezpath.make_path(e).flattening(0.01)]
                for p,q in zip(pts,pts[1:]):
                    out.append((p,q,e.dxf.handle,e.dxf.layer))
        except Exception: pass
    return out

floors=[int(a) for a in sys.argv[1:]] or [2,3,4,5,6,7,8]
for fl in all_floors():
    if fl.floor_no not in floors: continue
    js=json.load(open(f'output/openings/{fl.label}.json',encoding='utf-8'))
    W=[s for s in segs_of(fl,('W',)) if math.dist(s[0],s[1])>1e-4]
    obst=segs_of(fl,('Etabs-col','COL','try','WIN'))
    allg=unary_union([LineString([s[0],s[1]]) for s in W+obst])
    # explained spans: doors/windows/openings/candidates/frames/assemblies
    expl=[]
    for key in ('doors','windows','openings','opening_candidates','window_frame_pieces','assemblies'):
        for it in js.get(key,[]):
            if 'jamb_a' in it:
                pa=[(it['jamb_a'][0][0]+it['jamb_a'][1][0])/2,(it['jamb_a'][0][1]+it['jamb_a'][1][1])/2]
                pb=[(it['jamb_b'][0][0]+it['jamb_b'][1][0])/2,(it['jamb_b'][0][1]+it['jamb_b'][1][1])/2]
                expl.append(LineString([pa,pb]).buffer(0.25))
            elif it.get('ends'):
                e=it['ends']
                if len(e)==2: expl.append(LineString(e).buffer(0.3))
            if it.get('center') and it.get('width'):
                expl.append(Point(it['center']).buffer(max(0.3,it['width']/2+0.1)))
    E=unary_union(expl)
    # axis-aligned only (local frame); also handle slanted later
    found=[]
    for orient in ('H','V'):
        lines=[]
        for (a,b,h,l) in W:
            if orient=='H' and abs(a[1]-b[1])<0.003 and abs(a[0]-b[0])>0.02:
                lines.append((round((a[1]+b[1])/2,3),min(a[0],b[0]),max(a[0],b[0]),h))
            if orient=='V' and abs(a[0]-b[0])<0.003 and abs(a[1]-b[1])>0.02:
                lines.append((round((a[0]+b[0])/2,3),min(a[1],b[1]),max(a[1],b[1]),h))
        # group by offset
        byoff={}
        for off,s,e,h in lines:
            k=None
            for kk in byoff:
                if abs(kk-off)<0.004: k=kk;break
            byoff.setdefault(k if k is not None else off,[]).append((s,e,h))
        # merge intervals per offset, find gaps 0.5..3.0
        gaps=[]
        for off,iv in byoff.items():
            iv.sort()
            merged=[]
            for s,e,h in iv:
                if merged and s<=merged[-1][1]+0.003: merged[-1][1]=max(merged[-1][1],e)
                else: merged.append([s,e])
            for (s1,e1),(s2,e2) in zip(merged,merged[1:]):
                g=s2-e1
                if 0.45<=g<=3.2: gaps.append((off,e1,s2))
        # need a parallel face 0.08..0.32 away with a gap at about the same place
        for off,g0,g1 in gaps:
            for off2,h0,h1 in gaps:
                d=off2-off
                if 0.32<d<=0.65 and abs(g0-h0)<0.2 and abs(g1-h1)<0.2:
                    lo=max(g0,h0); hi=min(g1,h1)
                    if hi-lo<0.4: continue
                    mid=(off+off2)/2
                    if orient=='H':
                        probe=LineString([(lo+0.02,mid),(hi-0.02,mid)]); c=((lo+hi)/2,mid)
                    else:
                        probe=LineString([(mid,lo+0.02),(mid,hi-0.02)]); c=(mid,(lo+hi)/2)
                    blocked = probe.intersects(allg)
                    explained = E.contains(Point(c))
                    found.append((orient,round(mid,3),round(lo,3),round(hi,3),round(hi-lo,3),round(d,3),'BLOCKED' if blocked else 'empty','expl' if explained else 'UNEXPLAINED',c))
    print('=====',fl.label)
    for f in sorted(found,key=lambda f:(f[7],f[0],f[1])):
        if f[7]=='UNEXPLAINED': print('  ',f)
    print('   explained:',sum(1 for f in found if f[7]=='expl'),'unexplained:',sum(1 for f in found if f[7]!='expl'))
