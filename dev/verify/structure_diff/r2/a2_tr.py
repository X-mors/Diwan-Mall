import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, all_floors
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ezdxf import path as ezpath
for n in [int(a) for a in sys.argv[1:]] or [3]:
    fl = get_floor(n)
    print("=====", fl.label)
    ins = [e for e in fl.msp.query("INSERT") if e.dxf.name == "tr"]
    for i in ins:
        vs = list(i.virtual_entities())
        # anchor test: geometry on this sheet?
        pts=[]
        for v in vs:
            if v.dxftype()=="LWPOLYLINE":
                pts += [(p[0],p[1]) for p in v.get_points("xy")]
        if not pts: continue
        cx = sum(p[0] for p in pts)/len(pts); cy=sum(p[1] for p in pts)/len(pts)
        on = fl.contains(cx, cy) if hasattr(fl,'contains') else None
        print(" INSERT h=%s layer=%s ins=%s scale=%s rot=%s nvirt=%d centroid_on_sheet=%s" % (i.dxf.handle, i.dxf.layer, tuple(round(c,2) for c in i.dxf.insert), (i.dxf.xscale,i.dxf.yscale), i.dxf.rotation, len(vs), on))
        if not on: continue
        polys=[]
        for v in vs:
            t=v.dxftype()
            if t=="LWPOLYLINE":
                lp=[fl.to_local(p[0],p[1]) for p in v.get_points("xy")]
                if len(lp)>=3:
                    P=Polygon(lp).buffer(0)
                    print("   ",v.dxf.layer,"LWPOLY n=%d closed=%s bbox=%s area=%.3f"%(len(lp),v.closed,[round(b,3) for b in P.bounds],P.area))
            elif t=="HATCH":
                for bp in v.paths:
                    p=ezpath.from_hatch_boundary_path(bp)
                    lp=[fl.to_local(q.x,q.y) for q in p.flattening(0.005)]
                    if len(lp)>=3:
                        P=Polygon(lp).buffer(0)
                        print("   ",v.dxf.layer,"HATCH bbox=%s area=%.4f"%([round(b,3) for b in P.bounds],P.area))
            else:
                print("   ",v.dxf.layer,t)
