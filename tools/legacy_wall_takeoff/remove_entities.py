"""
Delete DIMENSION entities and/or TEXT/MTEXT entities of a given resolved
color from a DXF, optionally restricted to entities located inside the
bounding box of a reference layer (e.g. only delete text drawn inside the
building outline, leaving schedule/legend text outside it untouched).

Usage:
    python remove_entities.py <input.dxf> <output.dxf> --dimensions
    python remove_entities.py <input.dxf> <output.dxf> --text-color 2
    python remove_entities.py <input.dxf> <output.dxf> --text-color 2 --inside-layer W --pad 3
"""
import argparse

import ezdxf


def resolved_color(e, layer_colors):
    c = e.dxf.color
    if c == 256:
        return layer_colors.get(e.dxf.layer, 7)
    return c


def compute_bbox(msp, layer_name: str, frame_threshold: float = 50.0):
    xs, ys = [], []
    for e in msp:
        if e.dxf.layer != layer_name:
            continue
        if e.dxftype() == "LINE":
            xs += [e.dxf.start.x, e.dxf.end.x]
            ys += [e.dxf.start.y, e.dxf.end.y]
        elif e.dxftype() == "LWPOLYLINE":
            pts = list(e.get_points())
            pxs = [p[0] for p in pts]
            pys = [p[1] for p in pts]
            if max(pxs) - min(pxs) > frame_threshold and max(pys) - min(pys) > frame_threshold:
                continue  # skip frame/border polyline
            xs += pxs
            ys += pys
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dxf")
    ap.add_argument("output_dxf")
    ap.add_argument("--dimensions", action="store_true", help="delete all DIMENSION entities")
    ap.add_argument("--text-color", type=int, help="delete TEXT/MTEXT with this resolved ACI color")
    ap.add_argument("--inside-layer", help="restrict text deletion to inside this layer's bbox")
    ap.add_argument("--pad", type=float, default=3.0)
    args = ap.parse_args()

    doc = ezdxf.readfile(args.input_dxf)
    msp = doc.modelspace()
    layer_colors = {l.dxf.name: l.dxf.color for l in doc.layers}

    bbox = None
    if args.text_color is not None and args.inside_layer:
        bbox = compute_bbox(msp, args.inside_layer)
        if bbox:
            bx0, by0, bx1, by1 = bbox
            bx0 -= args.pad; by0 -= args.pad; bx1 += args.pad; by1 += args.pad

    def inside(e):
        if bbox is None:
            return True
        ip = e.dxf.insert
        return bx0 <= ip.x <= bx1 and by0 <= ip.y <= by1

    to_delete = []
    for e in msp:
        t = e.dxftype()
        if args.dimensions and t == "DIMENSION":
            to_delete.append(e)
        elif args.text_color is not None and t in ("TEXT", "MTEXT"):
            if resolved_color(e, layer_colors) == args.text_color and inside(e):
                to_delete.append(e)

    for e in to_delete:
        msp.delete_entity(e)

    doc.saveas(args.output_dxf)
    print("deleted entities:", len(to_delete))
    print("saved:", args.output_dxf)


if __name__ == "__main__":
    main()
