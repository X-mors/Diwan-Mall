import json, sys
sys.path.insert(0, 'tools')
from shapely.geometry import Polygon
from walls import Dir
for F in sys.argv[1:]:
    W = json.load(open(f'output/walls/{F}.json', encoding='utf-8'))
    S = json.load(open(f'output/structure/{F}.json', encoding='utf-8'))
    els = [(e['id'], e['kind'], e['sources'], e['only_in_tr_block'], e.get('hatch_only'), Polygon(e['outline']).buffer(0)) for e in S['elements']]
    for w in W['walls']:
        D = Dir(w['angle']); d0, d1 = w['_band']; s, e = w['_t']
        R = D.rect(s, e, d0, d1)
        for eid, k, src, tr, ho, P in els:
            a = R.intersection(P).area
            if a > 0.01:
                print(F, w['id'], w['family'], w['kind'], round(w['length_gross'],3), round(w['length_net'],3), '->', eid, k, src, 'tr' if tr else '', 'hatch_only' if ho else '', round(a,3), round(a/R.area,2))
