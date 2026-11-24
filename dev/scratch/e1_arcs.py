import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
for n in (2, 3, 6):
    fl = get_floor(n)
    print('==', fl.label)
    for e in floor_entities(fl, layers=('W',)):
        t = e.dxftype()
        if t in ('ARC', 'CIRCLE'):
            c = e.ocs().to_wcs(e.dxf.center)
            lc = fl.to_local(c.x, c.y)
            r = e.dxf.radius
            if t == 'ARC':
                sw = (e.dxf.end_angle - e.dxf.start_angle) % 360
            else:
                sw = 360
            print(t, e.dxf.handle, 'c=(%.3f,%.3f) r=%.3f sweep=%.1f extr=%s' % (lc[0], lc[1], r, sw, tuple(e.dxf.extrusion)))
