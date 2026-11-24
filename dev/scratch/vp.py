import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import DXF_FILES, open_doc
for p in DXF_FILES:
    doc = open_doc(str(p))
    print("==", p.name, "layouts:", [l.name for l in doc.layouts])
    for lay in doc.layouts:
        if lay.name == 'Model': continue
        n = len(lay)
        vps = lay.query('VIEWPORT')
        print("  ", lay.name, "entities", n, "viewports", len(vps))
        for v in vps:
            fl = v.frozen_layer_names() if hasattr(v,'frozen_layer_names') else None
            print("     vp", v.dxf.get('id'), "center", tuple(round(c,1) for c in v.dxf.view_center_point)[:2], "h", round(v.dxf.view_height,1), "frozen:", fl)
