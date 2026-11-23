"""
Add "W<n>" text labels at each interior wall's center (from a JSON produced by
wall_schedule_extract.py) onto a DXF, on a dedicated layer.

Usage:
    python wall_schedule_label_dxf.py <in.dxf> <walls.json> <out.dxf> [--layer WALL-NO] [--color 6] [--height 0.30]
"""
import argparse
import json

import ezdxf


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dxf")
    ap.add_argument("walls_json")
    ap.add_argument("output_dxf")
    ap.add_argument("--layer", default="WALL-NO")
    ap.add_argument("--color", type=int, default=6)
    ap.add_argument("--height", type=float, default=0.30)
    args = ap.parse_args()

    with open(args.walls_json, encoding="utf-8") as f:
        data = json.load(f)
    interior = data["interior"]
    rot_deg = data["rot_deg"]

    doc = ezdxf.readfile(args.input_dxf)
    msp = doc.modelspace()
    if args.layer not in doc.layers:
        doc.layers.add(args.layer, color=args.color)

    for w in interior:
        gx, gy = w["global_center"]
        txt = msp.add_text(f"W{w['no']}", dxfattribs={
            "layer": args.layer, "height": args.height, "color": args.color,
            "rotation": rot_deg, "style": "Standard",
        })
        txt.dxf.insert = (gx, gy, 0)
        txt.dxf.halign = 1
        txt.dxf.valign = 2
        txt.dxf.align_point = (gx, gy, 0)

    doc.saveas(args.output_dxf)
    print(f"added {len(interior)} labels -> {args.output_dxf}")


if __name__ == "__main__":
    main()
