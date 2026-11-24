import sys, pickle, glob
sys.path.insert(0, 'tools')
from shapely.geometry import Polygon
from rooms import INDOOR_CEILING
F = sys.argv[1]
b = pickle.load(open(glob.glob(f'output/plan/_cache/{F}_*.pkl')[0], 'rb'))
rooms = {r['id']: r for r in b['rooms']['rooms']}
ind = [b['rooms_polys'][i] for i, r in rooms.items() if r.get('indoor') and r['category'] in INDOOR_CEILING and i in b['rooms_polys']]
allr = [(r['category'], b['rooms_polys'][i]) for i, r in rooms.items() if i in b['rooms_polys']]
tot_s = tot_r = 0
for e in b['structure']['elements']:
    if e['only_in_tr_block'] or e['kind'] == 'column_xbox':
        continue
    P = Polygon(e['outline']).buffer(0)
    zone = P.buffer(0.03, join_style=2).difference(P.buffer(-0.03, join_style=2))
    L = sum(pg.exterior.intersection(zone).length + sum(h.intersection(zone).length for h in pg.interiors) for pg in ind)
    other = {}
    for c, pg in allr:
        if c in INDOOR_CEILING: continue
        l = pg.boundary.intersection(zone).length
        if l > 0.05: other[c] = other.get(c, 0) + round(l, 2)
    tot_s += e['exposed_interior']; tot_r += L
    print(e['id'], e['kind'], e['size_txt'], 'struct_int', e['exposed_interior'], 'rooms', round(L, 2), 'diff', round(e['exposed_interior'] - L, 2), other)
print('tot', round(tot_s, 2), round(tot_r, 2))
