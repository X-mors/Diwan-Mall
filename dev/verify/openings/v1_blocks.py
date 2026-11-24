import sys, collections
sys.path.insert(0, 'tools')
import ezdxf
from diwan_common import all_floors, floor_entities
fls = all_floors()
files = sorted(set(f.file for f in fls))
for fp in files:
    doc = ezdxf.readfile(fp)
    msp = doc.modelspace()
    cnt = collections.Counter()
    for e in msp.query('INSERT'):
        cnt[(e.dxf.name, e.dxf.layer)] += 1
    print('FILE', fp)
    for (n,l),c in sorted(cnt.items()):
        if n.startswith('D') or n in ('LP','WB','P','ST-2'):
            print('  ', n, l, c)
    # block defs containing ARC  (door-like) and nested inserts
    for b in doc.blocks:
        if b.name.startswith('*'): continue
        types = collections.Counter(e.dxftype() for e in b)
        nested = [e.dxf.name for e in b if e.dxftype()=='INSERT']
        arcs = types.get('ARC',0)
        if arcs or nested and any(n.startswith('D') for n in nested):
            print('  BLOCKDEF', b.name, dict(types), 'nested=', nested[:6])
