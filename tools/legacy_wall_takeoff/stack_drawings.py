"""
Combine two DXF drawings into a single file, stacking the second one
(placed on top / at a higher Y) above the first, so both appear together
in one CAD file for comparison.

Usage:
    python stack_drawings.py <base.dxf> <top.dxf> <output.dxf> [--gap 15]

<base.dxf> stays where it is; <top.dxf>'s entities are imported and
translated upward (and left-aligned with base) so they sit directly above
<base.dxf> with a vertical gap between them, in the same modelspace.
"""
import argparse

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.addons.importer import Importer


def stack(base_path: str, top_path: str, out_path: str, gap: float = 15.0):
    base_doc = ezdxf.readfile(base_path)
    base_msp = base_doc.modelspace()
    top_doc = ezdxf.readfile(top_path)
    top_msp = top_doc.modelspace()

    base_ext = ezbbox.extents(base_msp)
    top_ext = ezbbox.extents(top_msp)

    dy = base_ext.extmax.y - top_ext.extmin.y + gap
    dx = base_ext.extmin.x - top_ext.extmin.x  # left-align with base

    before_handles = {e.dxf.handle for e in base_msp}

    importer = Importer(top_doc, base_doc)
    importer.import_modelspace()
    importer.finalize()

    new_entities = [e for e in base_msp if e.dxf.handle not in before_handles]
    failed = 0
    for e in new_entities:
        try:
            e.translate(dx, dy, 0)
        except Exception:
            failed += 1

    base_doc.saveas(out_path)
    print(f"imported {len(new_entities)} entities from top drawing ({failed} could not be translated)")
    print(f"offset applied: dx={dx:.2f} dy={dy:.2f}")
    print("saved:", out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_dxf", help="bottom drawing (stays in place)")
    ap.add_argument("top_dxf", help="drawing placed above the base")
    ap.add_argument("output_dxf")
    ap.add_argument("--gap", type=float, default=15.0, help="vertical gap between the two drawings (meters)")
    args = ap.parse_args()
    stack(args.base_dxf, args.top_dxf, args.output_dxf, args.gap)


if __name__ == "__main__":
    main()
