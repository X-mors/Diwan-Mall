import sys, ezdxf, collections
from ezdxf import bbox
for p in sys.argv[1:]:
    doc = ezdxf.readfile(p)
    msp = doc.modelspace()
    print("="*100); print(p, "units", doc.header.get("$INSUNITS"), "ver", doc.dxfversion)
    cnt = collections.Counter(); lay = collections.defaultdict(collections.Counter)
    for e in msp:
        cnt[e.dxftype()] += 1; lay[e.dxf.layer][e.dxftype()] += 1
    print("types", dict(cnt))
    print("layouts", [l.name for l in doc.layouts])
    for l in sorted(lay, key=lambda k: -sum(lay[k].values())):
        L = doc.layers.get(l) if doc.layers.has_entry(l) else None
        col = L.color if L else None; lt = L.dxf.linetype if L else None
        print(f"  {l!r:30} col={col} lt={lt} {dict(lay[l])}")
    try:
        ext = bbox.extents(msp, fast=True); print("extents", ext.extmin, ext.extmax)
    except Exception as ex: print("bbox err", ex)
    ins = collections.Counter(e.dxf.name for e in msp.query("INSERT"))
    print("top inserts", ins.most_common(40))
