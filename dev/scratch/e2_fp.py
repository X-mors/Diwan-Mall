import sys, math, json
sys.path.insert(0, 'tools')
import numpy as np
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString, Polygon, Point, MultiPolygon
from shapely.ops import unary_union
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
SP = sys.argv[2]
n = int(sys.argv[1]); fl = get_floor(n)
L = []; info = []
for e in floor_entities(fl, layers=('W', 'WIN', 'Etabs-col')):
    if e.dxftype() in ('INSERT', 'TEXT', 'MTEXT', 'HATCH', 'DIMENSION'): continue
    try: p = ezpath.make_path(e)
    except Exception: continue
    pts = [fl.to_local(q.x, q.y) for q in p.flattening(0.01)]
    if len(pts) >= 2:
        ls = LineString(pts); L.append(ls)
        if ls.length > 20: info.append((e.dxf.layer, e.dxf.handle, e.dxftype(), round(ls.length, 2)))
print('long:', info)
for d in (0.04, 0.3):
    U = unary_union([l.buffer(d, cap_style=2, join_style=2) for l in L])
    big = max(U.geoms, key=lambda g: g.area) if U.geom_type == 'MultiPolygon' else U
    FP = Polygon(big.exterior).buffer(-d, join_style=2)
    if FP.geom_type == 'MultiPolygon': FP = max(FP.geoms, key=lambda g: g.area)
    print('d=%.2f area %.2f bounds %s' % (d, FP.area, [round(v, 2) for v in FP.bounds]))
    fig, ax = plt.subplots(figsize=(10, 20))
    for l in L:
        x, y = l.xy; ax.plot(x, y, color='#999', lw=0.4)
    x, y = FP.exterior.xy; ax.fill(x, y, alpha=0.2, color='red'); ax.plot(x, y, color='red', lw=0.8)
    ax.set_aspect('equal'); ax.set_title('%s d=%.2f area %.2f' % (fl.label, d, FP.area))
    fig.savefig(SP + '/fp_%s_%02d.png' % (fl.label, int(d * 100)), dpi=70, bbox_inches='tight'); plt.close(fig)
