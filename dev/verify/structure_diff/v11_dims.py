import sys
sys.path.insert(0, 'tools')
from diwan_common import all_floors, floor_entities, entity_bbox
from collections import Counter
import json
for fl in all_floors():
    c = Counter()
    styles=Counter()
    for e in fl.msp.query('DIMENSION'):
        p = e.dxf.get('defpoint2') or e.dxf.defpoint
        if fl.contains(p.x, p.y) or fl.contains(e.dxf.defpoint.x, e.dxf.defpoint.y):
            c[e.dxf.layer]+=1; styles[e.dxf.get('dimstyle')]+=1
    fe = Counter(e.dxf.layer for e in floor_entities(fl, types='DIMENSION'))
    r=json.load(open('output/structure/%s.json'%fl.label,encoding='utf-8'))
    print(fl.label, 'raw by layer', dict(c), 'styles', dict(styles), '| floor_entities', dict(fe), '| tool', r['dims']['n'])
