import sys; sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import rooms
from shapely.strtree import STRtree
n = int(sys.argv[1]); rid = sys.argv[2]
res = rooms.analyze_floor(n)
P = res['_P']; tree = STRtree([p[0] for p in P])
r = [r for r in res['rooms'] if r['id'] == rid][0]
f = r['_poly']
print(rid, r['name'], round(f.area, 3), r['flags'])
print('ext', [tuple(round(c, 3) for c in p) for p in f.exterior.simplify(0.001).coords])
for h in f.interiors: print('hole', [tuple(round(c, 3) for c in p) for p in h.coords][:8])
inner = f.buffer(-0.02)
for j in tree.query(inner):
    geom, kind, ref = P[j]
    if geom.geom_type == 'LineString':
        L = geom.intersection(inner).length
        if L > 0.01: print('inside', kind, ref, round(L, 3), [tuple(round(c, 2) for c in p) for p in geom.coords][:4])
