import sys, math, json, pickle
sys.path.insert(0, 'tools')
import numpy as np
from diwan_common import all_floors, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, MultiLineString
from shapely.strtree import STRtree
LAYS = sys.argv[1].split(',') if len(sys.argv)>1 else ['W']
data = {}
for fl in all_floors():
    segs = {l: [] for l in LAYS}
    for e in floor_entities(fl, layers=tuple(LAYS)):
        if e.dxftype() == 'INSERT' or e.dxftype() in ('TEXT','MTEXT','DIMENSION'): continue
        try:
            if e.dxftype()=='HATCH':
                ps = list(ezpath.from_hatch(e))
            else:
                ps = [ezpath.make_path(e)]
        except Exception: continue
        for p in ps:
            pts = [fl.to_local(q.x, q.y) for q in p.flattening(0.01)]
            for i in range(len(pts)-1):
                if math.dist(pts[i], pts[i+1])>1e-6:
                    segs[e.dxf.layer].append((pts[i], pts[i+1]))
    data[fl.label] = segs
pickle.dump(data, open('output/_verify_structure_diff/segs_%s.pkl'%'_'.join(LAYS),'wb'))
def sample(segs, step=0.01):
    P=[]
    for a,b in segs:
        L=math.dist(a,b); k=max(1,int(L/step))
        for i in range(k):
            t=(i+0.5)/k; P.append((a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, L/k))
    return np.array(P)
labs = sorted(data)
for lay in LAYS:
    print('layer', lay, 'n segs', {l: len(data[l][lay]) for l in labs}, 'len', {l: round(sum(math.dist(a,b) for a,b in data[l][lay]),2) for l in labs})
    trees = {l: STRtree([LineString(s) for s in data[l][lay]]) if data[l][lay] else None for l in labs}
    geoms = {l: [LineString(s) for s in data[l][lay]] for l in labs}
    samples = {l: sample(data[l][lay]) for l in labs}
    M = {}
    for A in labs:
        row = []
        for B in labs:
            if A==B or len(samples[A])==0: row.append(0); continue
            S = samples[A]
            if trees[B] is None: row.append(round(S[:,2].sum(),2)); continue
            from shapely import points
            pts = points(S[:,0], S[:,1])
            idx = trees[B].query_nearest(pts, max_distance=0.02, return_distance=False, all_matches=False)
            matched = np.zeros(len(S), bool); matched[idx[0]] = True
            row.append(round(S[~matched,2].sum(),2))
        M[A]=row
        print(A, row)
