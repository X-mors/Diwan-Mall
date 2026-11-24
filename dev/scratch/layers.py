import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import DXF_FILES, open_doc
import hashlib
for p in DXF_FILES:
    doc = open_doc(str(p))
    print("==", p.name)
    for l in doc.layers:
        n = l.dxf.name
        st = []
        if l.is_off(): st.append("OFF")
        if l.is_frozen(): st.append("FROZEN")
        if l.is_locked(): st.append("locked")
        if not l.dxf.get('plot', 1): st.append("noplot")
        if st or n in ('Etabs-Slab','Etabs-col','COL','try','DASH','HAT','MASS','-MASS','sidewalk','PR1','FUR','X','x1','CI','TEXT-DIM','W-100','DIM'):
            print(f"   {n:14} color={l.dxf.color} lt={l.dxf.linetype} {st}")
    b = doc.blocks.get('tr')
    sig = sorted((e.dxftype(), e.dxf.layer, round(sum(v[0]+v[1] for v in e.get_points('xy')),3) if e.dxftype()=='LWPOLYLINE' else 0) for e in b)
    print("   tr signature", hashlib.md5(str(sig).encode()).hexdigest()[:10], len(b))
