import json, sys
sys.stdout.reconfigure(encoding='utf-8')
B = r'D:\حصر المباني\Diwan-Mall\output\structure'
R = {f: json.load(open(f'{B}\{f}.json', encoding='utf-8')) for f in ['F02','F03','F04','F05','F06','F07','F08']}
r = R['F06']
print('| id | النوع | المقاس (x × y) م | المدى bbox (x0, y0, x1, y1) | المحاور | المحيط | المعرض للمحارة | مغطى بحوائط | مصدر | ملاحظة |')
print('|---|---|---|---|---|---|---|---|---|---|')
kind_ar = {'column':'عمود','shear_wall':'حائط قص','core':'كور مصاعد','column_xbox':'مربع X (COL)'}
for e in sorted(r['elements'], key=lambda e:(e['kind'], e['id'])):
    src = 'tr فقط' if e['only_in_tr_block'] else ('hatch فقط' if e['hatch_only'] else ('COL' if e['kind']=='column_xbox' else 'Etabs-col'))
    notes = []
    if e['outline_on_W'] >= 0.5: notes.append(f"محيطه على W {e['outline_on_W']:.0%}")
    if e['w_inside_len'] > 0.05: notes.append(f"خطوط W داخله {e['w_inside_len']:.2f} م")
    print(f"| {e['id']} | {kind_ar[e['kind']]} | {e['size_txt']} | {e['bbox']} | {e['grid_ref']} | {e['perimeter']:.2f} | {e['exposed_perimeter']:.2f} | {e['covered_by_walls']:.2f} | {src} | {'; '.join(notes)} |")
print()
print('| الدور | أعمدة | حوائط قص | كور | مربعات COL | منها من tr فقط | المحيط المعرض (الكل) | المحيط المعرض (بدون tr) | شفتات | سلالم | كبائن مصاعد | DIM | DASH (خطوط) |')
print('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for f, r in R.items():
    s = r['summary']; k = s['elements_by_kind']
    ntr = sum(1 for e in r['elements'] if e['only_in_tr_block'])
    nd = sum(v['n'] for v in s['dash'].values())
    print(f"| {f} | {k.get('column',0)} | {k.get('shear_wall',0)} | {k.get('core',0)} | {k.get('column_xbox',0)} | {ntr} | {s['plaster_perimeter_all']:.2f} | {s['plaster_perimeter_model_space_only']:.2f} | {s['shafts']} ({s['shaft_area']:.2f} م²) | {s['stairs']} | {s['lift_cars']} | {s['dims']} | {nd} |")
print()
print('shafts F06:')
for x in R['F06']['shafts']:
    print(f"| {x['id']} | {x['kind']} | {x['size_txt']} | {x['bbox']} | {x['grid_ref']} | {x['perimeter']:.2f} | dup={x['duplicates']} |")
print()
for f in R:
    print(f, [ (x['id'], x['kind'][:20], x['size_txt'], x['bbox']) for x in R[f]['shafts'] if x['kind'].startswith('shaft enc') or 'DASH' in x['kind'] or '?' in x['kind']])
print()
print('dash per floor')
for f, r in R.items():
    print(f, {k: (v['n'], v['len']) for k, v in r['summary']['dash'].items()})
print('dims per floor')
for f, r in R.items():
    print(f, r['dims']['by_class'], r['dims']['wall_thickness_values'])
from collections import Counter
c = Counter()
for f, r in R.items():
    for d in r['dims']['dims']:
        if d['class']=='interior': c[d['text']] += 1
print('interior values', c.most_common(25))
c = Counter()
for d in R['F06']['dims']['dims']:
    if d['class'] in ('facade_chain','facade_step'): c[d['text']] += 1
print('facade F06', c.most_common(30))
print([ (d['text'], d['p2'], d['p3']) for d in R['F02']['dims']['dims'] if d['class']=='wall_thickness'])
print('exposed per element across floors:')
for e in R['F03']['elements']:
    print(e['id'], [next(x['exposed_perimeter'] for x in R[f]['elements'] if x['id']==e['id']) for f in R])
