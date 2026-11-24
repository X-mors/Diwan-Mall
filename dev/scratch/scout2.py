import sys, ezdxf, collections, math
p = sys.argv[1]
doc = ezdxf.readfile(p); msp = doc.modelspace()
print("== TEXT (layer, text, pos, height)")
for e in msp.query("TEXT MTEXT"):
    t = e.dxf.text if e.dxftype()=="TEXT" else e.plain_text()
    print(f"  {e.dxf.layer:14} {t[:60]!r:64} ({e.dxf.insert.x:.2f},{e.dxf.insert.y:.2f}) h={getattr(e.dxf,'height',getattr(e.dxf,'char_height',0)):.2f}")
print("== block defs with W-layer inserts")
for name in ["D10W12","D80W12","D90W12","D90W25","WB","P","LP","ST-2","rt5hrt6","tr"]:
    if name in doc.blocks:
        b = doc.blocks[name]; c = collections.Counter((e.dxftype(), e.dxf.layer) for e in b)
        try:
            from ezdxf import bbox; ex = bbox.extents(b); sz=(ex.size.x, ex.size.y)
        except Exception: sz=None
        layers = collections.Counter(i.dxf.layer for i in msp.query(f'INSERT[name=="{name}"]'))
        sc = collections.Counter((round(i.dxf.xscale,2), round(i.dxf.yscale,2)) for i in msp.query(f'INSERT[name=="{name}"]'))
        print(f"  {name}: {dict(c)} size={sz} insert-layers={dict(layers)} scales={dict(sc)}")
print("== DIM sample")
for i,e in enumerate(msp.query("DIMENSION")):
    if i>15: break
    print("  ", e.dxf.layer, e.dxf.dimstyle, e.dimtype, round(e.dxf.actual_measurement,4) if e.dxf.hasattr('actual_measurement') else None, e.dxf.get('text',''))
ds = collections.Counter(e.dxf.dimstyle for e in msp.query("DIMENSION")); print("dimstyles", ds)
print("== W line length & angle histogram")
ang = collections.Counter(); lens=[]
for e in msp.query('LINE[layer=="W"]'):
    d = e.dxf.end - e.dxf.start; L = math.hypot(d.x,d.y); lens.append(L)
    a = math.degrees(math.atan2(d.y,d.x)) % 180; ang[round(a)] += 1
print("angles", ang.most_common(12)); 
import statistics; print("len count", len(lens), "median", statistics.median(lens), "max", max(lens))
