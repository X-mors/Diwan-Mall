# independent raw dump of the entities per floor in LOCAL frame
import sys, pickle, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import all_floors, floor_entities, floor_texts
from ezdxf import path as ezpath
out = {}
for fl in all_floors():
    L = fl.to_local
    d = {"W": [], "WIN": [], "cols": [], "try": [], "inserts": [], "texts": [], "mass": [], "st": [], "dims": [], "pr": [], "dash": [], "zero": [], "hatch": []}
    for e in floor_entities(fl):
        lay, t = e.dxf.layer, e.dxftype()
        if t == "INSERT":
            d["inserts"].append(dict(name=e.dxf.name, layer=lay, ins=L(e.dxf.insert.x, e.dxf.insert.y), h=e.dxf.handle,
                                     xs=e.dxf.xscale, ys=e.dxf.yscale, rot=e.dxf.rotation))
            continue
        if t == "DIMENSION":
            try:
                d["dims"].append(dict(h=e.dxf.handle, p2=L(e.dxf.defpoint2.x, e.dxf.defpoint2.y), p3=L(e.dxf.defpoint3.x, e.dxf.defpoint3.y), val=e.get_measurement(), layer=lay))
            except Exception:
                pass
            continue
        if t == "HATCH":
            d["hatch"].append(dict(h=e.dxf.handle, layer=lay, pat=e.dxf.pattern_name))
            continue
        if t in ("TEXT", "MTEXT"):
            continue
        try:
            p = ezpath.make_path(e)
            pts = [L(v.x, v.y) for v in p.flattening(0.01)]
        except Exception:
            continue
        rec = dict(h=e.dxf.handle, t=t, pts=pts, layer=lay, lt=e.dxf.get("linetype", "BYLAYER"))
        key = {"W": "W", "WIN": "WIN", "Etabs-col": "cols", "COL": "cols", "try": "try", "MASS": "mass", "ST": "st", "PR": "pr", "DASH": "dash", "0": "zero"}.get(lay)
        if key:
            d[key].append(rec)
    for tx in floor_texts(fl):
        d["texts"].append(dict(layer=tx["layer"], text=tx["text"], raw=tx["raw"], local=tx["local"], h=tx["handle"], height=tx["height"]))
    out[fl.label] = d
    print(fl.label, {k: len(v) for k, v in d.items()})
pickle.dump(out, open(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\raw.pkl", "wb"))
