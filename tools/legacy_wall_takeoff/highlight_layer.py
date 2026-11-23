"""
Recolor a DXF layer's real geometry (LINE/LWPOLYLINE) to a distinct color,
while automatically skipping any polyline whose bounding box is as large as
the sheet frame/border (a common drafting mistake where the border ends up
on the same layer as the walls).

Usage:
    python highlight_layer.py <input.dxf> <output.dxf> --layer W --color 1
    (AutoCAD Color Index: 1=red, 2=yellow, 3=green, 4=cyan, 5=blue, 6=magenta)
"""
import argparse

import ezdxf
from ezdxf import colors as ezcolors

ACI_RGB = {
    1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0),
    4: (0, 255, 255), 5: (0, 0, 255), 6: (255, 0, 255), 7: (255, 255, 255),
}


def bbox_size(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def highlight(src: str, dst: str, layer_name: str, color: int, frame_threshold: float = 50.0):
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    rgb = ACI_RGB.get(color, (255, 0, 0))

    count = 0
    skipped = 0
    for e in msp:
        if e.dxf.layer != layer_name:
            continue
        t = e.dxftype()
        if t == "LWPOLYLINE":
            w, h = bbox_size(list(e.get_points()))
            if w > frame_threshold and h > frame_threshold:
                skipped += 1
                continue
        elif t not in ("LINE", "LWPOLYLINE"):
            continue  # skip INSERT/block symbols placed on this layer (doors, windows, fixtures)

        e.dxf.color = color
        try:
            e.dxf.true_color = ezcolors.rgb2int(rgb)
        except Exception:
            pass
        if hasattr(e.dxf, "lineweight"):
            e.dxf.lineweight = 50
        count += 1

    doc.saveas(dst)
    print(f"highlighted: {count}, skipped as frame/border: {skipped}")
    print("saved:", dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dxf")
    ap.add_argument("output_dxf")
    ap.add_argument("--layer", required=True)
    ap.add_argument("--color", type=int, required=True, help="AutoCAD Color Index (1=red,2=yellow,3=green,...)")
    ap.add_argument("--frame-threshold", type=float, default=50.0)
    args = ap.parse_args()
    highlight(args.input_dxf, args.output_dxf, args.layer, args.color, args.frame_threshold)


if __name__ == "__main__":
    main()
