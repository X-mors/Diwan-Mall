import pickle, math
from shapely.geometry import LineString
from shapely.ops import unary_union
d = pickle.load(open('output/_verify_structure_diff/segs_W.pkl','rb'))
for f in sorted(d):
    S = d[f]['W']
    raw = sum(math.dist(a,b) for a,b in S)
    u = unary_union([LineString(s) for s in S])
    print(f, 'raw', round(raw,2), 'union', round(u.length,2), 'dup', round(raw-u.length,2))
