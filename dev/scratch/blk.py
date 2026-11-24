import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from collections import Counter
from diwan_common import get_floor, entity_bbox
from sosa_decode import decode, is_arabic_style
fl = get_floor(3)
doc = fl.doc; msp = fl.msp
def desc(name, depth=0):
    b = doc.blocks[name]
    c = Counter((e.dxf.layer, e.dxftype()) for e in b)
    print("  "*depth + f"BLOCK {name} base={tuple(b.block.dxf.base_point)[:2]} n={len(b)} {dict(c)}")
    for e in b:
        if e.dxftype()=='INSERT' and depth<2:
            print("  "*depth+f"   INSERT {e.dxf.name} at {tuple(round(v,2) for v in e.dxf.insert)[:2]} sc=({e.dxf.xscale},{e.dxf.yscale}) rot={e.dxf.rotation} layer={e.dxf.layer}")
            desc(e.dxf.name, depth+1)
        if e.dxftype() in ('TEXT','MTEXT'):
            raw = e.dxf.text if e.dxftype()=='TEXT' else e.plain_text()
            st = e.dxf.get('style','')
            print("  "*depth+f"   TEXT {raw!r} style={st} ar={is_arabic_style(doc,st)} dec={decode(raw)!r} at {tuple(round(v,2) for v in e.dxf.insert)[:2]} h={e.dxf.get('height',0)}")
for name in ['tr','rfbf','ferfsrtfgser','ererererer','rt5hrt6','rhrt']:
    desc(name)
