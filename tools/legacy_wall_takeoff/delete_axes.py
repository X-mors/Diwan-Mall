"""
Delete the axis/grid (المحاور) from a DXF: the long grid centerlines and their
circular grid-head bubbles. In this project's drawings the grid lives on layer
"X" (long 45-68m dash-dot lines + bubble-head INSERT blocks) and a stray line on
"x1". Pass the layer names to match other drawings.

It deliberately does NOT touch layer "DASH" (short 0.7-2.3m hidden/detail dashes)
which are not axes.

Usage:
    python delete_axes.py <in.dxf> <out.dxf> [--layers X x1]
"""
import argparse
from collections import Counter

import ezdxf


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dxf")
    ap.add_argument("output_dxf")
    ap.add_argument("--layers", nargs="+", default=["X", "x1"],
                    help="layer names holding the axis grid (default: X x1)")
    args = ap.parse_args()

    doc = ezdxf.readfile(args.input_dxf)
    msp = doc.modelspace()
    targets = set(args.layers)

    to_delete = [e for e in msp if e.dxf.layer in targets]
    print("removing:", dict(Counter((e.dxf.layer, e.dxftype()) for e in to_delete)))
    for e in to_delete:
        msp.delete_entity(e)
    for lname in targets:
        if lname in doc.layers:
            try:
                doc.layers.remove(lname)
            except Exception:
                pass

    doc.saveas(args.output_dxf)
    print(f"deleted {len(to_delete)} axis entities -> {args.output_dxf}")


if __name__ == "__main__":
    main()
