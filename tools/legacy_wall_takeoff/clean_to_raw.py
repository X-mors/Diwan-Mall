"""
Clean a cluttered floor-plan DXF down to the office's "raw" measurement-ready
state. Two removal mechanisms:

A) LAYER rules (from tools/raw_layers.json, derived from the raw 3rd-floor template):
   - empty_layers    : layers empty in the raw template (axes X/x1, furniture FUR,
                       hatches HAT, -A-TEXT, ...) -> delete their content
   - clutter_layers  : detail layers the owner strips for measuring (try = منور/
                       fixture markers, PR = door-leaf/detail lines) -> delete
   - foreign layers  : any layer in neither content_layers nor the above -> delete

B) ENTITY rules (the specific clutter the owner named):
   - all DIMENSION entities                              (old measurements)
   - INSERT door/window symbol blocks  name ~ D<digits>W<digits>  (رسمة الأبواب)
   - WIN lines with DASHED linetype                      (الداش لاين السماوي)

Walls (W), windows outline (WIN solid), columns (COL/Etabs-col), stairs (ST),
room text (TEXT) and the border are KEPT.

NOTE: on the 3rd floor this reproduces the owner's hand-cleaned template except
for a few per-entity manual deletions inside kept layers (some DASH/MASS/W lines)
which cannot be rule-targeted; those do not affect wall/door measuring. When the
exact template for a floor is available, use diff_clean (geometric match) instead.

Usage:
    python clean_to_raw.py <input.dxf> <output.dxf> [--raw-layers raw_layers.json] [--keep-dims]
"""
import argparse, json, os, re
from collections import Counter

import ezdxf

HERE=os.path.dirname(os.path.abspath(__file__))
DOOR_BLOCK=re.compile(r'^D\d+W\d+', re.IGNORECASE)   # D10W12, D80W12, D90W25 ...
CLUTTER_LAYERS={"try","PR"}                           # منور fixtures + door-leaf/detail

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dxf"); ap.add_argument("output_dxf")
    ap.add_argument("--raw-layers", default=os.path.join(HERE,"raw_layers.json"))
    ap.add_argument("--keep-dims", action="store_true")
    args=ap.parse_args()

    with open(args.raw_layers, encoding="utf-8") as f:
        cfg=json.load(f)
    content=set(cfg["content_layers"]); empty=set(cfg["empty_layers"])
    known=content|empty|CLUTTER_LAYERS

    doc=ezdxf.readfile(args.input_dxf); msp=doc.modelspace()
    removed=Counter(); to_del=[]
    for e in msp:
        lay=e.dxf.layer; t=e.dxftype()
        reason=None
        if lay in empty:                    reason=("empty-layer",lay)
        elif lay in CLUTTER_LAYERS:         reason=("clutter-layer",lay)
        elif lay not in known:              reason=("foreign-layer",lay)
        elif t=="DIMENSION" and not args.keep_dims: reason=("dimension",lay)
        elif t=="INSERT" and lay=="W": reason=("wall-layer-insert",lay)  # walls are lines; any block on W is a door/window symbol
        elif t=="INSERT" and DOOR_BLOCK.match(str(e.dxf.name)): reason=("door-block",e.dxf.name)
        elif t=="LINE" and lay=="WIN" and str(e.dxf.linetype).upper()=="DASHED": reason=("win-dashed",lay)
        if reason: to_del.append(e); removed[reason]+=1
    for e in to_del: msp.delete_entity(e)

    purged=0
    for l in list(doc.layers):
        n=l.dxf.name
        if n in ("0","DEFPOINTS"): continue
        if (n in empty or n in CLUTTER_LAYERS or n not in known):
            try: doc.layers.remove(n); purged+=1
            except Exception: pass

    doc.saveas(args.output_dxf)
    print(f"removed {len(to_del)} entities:")
    for k,v in removed.most_common(): print(f"   {k}: {v}")
    print(f"purged {purged} layers -> {args.output_dxf}")

if __name__=="__main__":
    main()
