import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import DXF_FILES, open_doc
from sosa_decode import decode, is_arabic_style
doc = open_doc(str(DXF_FILES[1]))
names = ['rt5hrt6','67yjh6y','t6uyh','6yh','5rt6hr','56y','567hu6','565r6','r6th5r6','rhrt','56hr','rtg','67yu','D10W12','D80W12','D90W12','D90W25','LP','WB','P','ST-2']
for n in names:
    b = doc.blocks.get(n)
    if b is None: print(n,'MISSING'); continue
    c = Counter((e.dxftype(), e.dxf.layer) for e in b)
    print('==', n, 'base', tuple(round(v,3) for v in b.block.dxf.base_point), dict(c))
    for e in b:
        t = e.dxftype()
        if t in ('TEXT','MTEXT','ATTDEF'):
            raw = e.dxf.text if t!='MTEXT' else e.plain_text()
            st = e.dxf.get('style','Standard')
            print('    TEXT', repr(raw), st, is_arabic_style(doc, st), decode(raw) if is_arabic_style(doc, st) else '', tuple(round(v,2) for v in e.dxf.insert))
        elif t=='INSERT':
            print('    INS', e.dxf.name, tuple(round(v,2) for v in e.dxf.insert), e.dxf.xscale, e.dxf.rotation)
        elif t=='ARC':
            print('    ARC c', tuple(round(v,3) for v in e.dxf.center), 'r', round(e.dxf.radius,3), round(e.dxf.start_angle,1), round(e.dxf.end_angle,1))
        elif t=='LINE':
            print('    LINE', tuple(round(v,3) for v in e.dxf.start)[:2], tuple(round(v,3) for v in e.dxf.end)[:2])
        elif t=='LWPOLYLINE':
            print('    LWP', [tuple(round(v,3) for v in p) for p in e.get_points('xy')], e.closed)
        elif t=='CIRCLE':
            print('    CIRCLE', tuple(round(v,3) for v in e.dxf.center), round(e.dxf.radius,3))
