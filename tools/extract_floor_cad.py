"""
Cut one floor out of the drawings into NEW CAD files (the originals are never touched):
    architectural sheet of floor N           -> output/cad_extract/floor_NN_architectural.dxf/.dwg
    structural slab UNDER floor N (ceiling N-1) -> floor_NN_structural_slab_under.dxf/.dwg
    structural slab ABOVE floor N (ceiling N)   -> floor_NN_structural_slab_above.dxf/.dwg
Each file is a full copy of its source DXF (layers, blocks, styles kept) with every model-space
entity outside that sheet removed.  DWG via tools/dwg_dxf_convert.py (ODA); the DXF is deleted once
the DWG exists.  A structural sheet frame holds TWO plans (e.g. ceilings of 7 and 8): both are kept.

    python tools/extract_floor_cad.py 9
"""
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diwan_common import OUT_DIR, get_floor  # noqa: E402

OUT = OUT_DIR / "cad_extract"


def _keep_box(src, box, out):
    import ezdxf
    from ezdxf import bbox
    logging.disable(logging.WARNING)
    doc = ezdxf.readfile(str(src))
    logging.disable(logging.NOTSET)
    msp = doc.modelspace()
    x0, y0, x1, y1 = box
    drop = []
    for e in msp:
        try:
            b = bbox.extents([e], fast=True)
        except Exception:
            b = None
        if b is None or not b.has_data:
            drop.append(e)
            continue
        cx, cy = (b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2
        if not (x0 <= cx <= x1 and y0 <= cy <= y1):
            drop.append(e)
    for e in drop:
        msp.delete_entity(e)
    doc.saveas(str(out))
    return len(msp)


_DOCS = {}


def _frame_box(src, plan):
    """The sheet frame around a plan: the smallest entity whose box contains the plan with room for a
    title block (the "Frame" inserts, 128 x 88 m; one sheet can hold two plans, both are kept)."""
    import ezdxf
    from ezdxf import bbox
    if src not in _DOCS:
        logging.disable(logging.WARNING)
        _DOCS[src] = ezdxf.readfile(str(src))
        logging.disable(logging.NOTSET)
    x0, y0, x1, y1 = plan
    best = None
    for e in _DOCS[src].modelspace():
        if e.dxftype() not in ("LWPOLYLINE", "POLYLINE", "INSERT"):
            continue
        try:
            b = bbox.extents([e], fast=True)
        except Exception:
            continue
        if not b.has_data:
            continue
        w, h = b.extmax.x - b.extmin.x, b.extmax.y - b.extmin.y
        if b.extmin.x <= x0 and b.extmin.y <= y0 and b.extmax.x >= x1 and b.extmax.y >= y1 \
                and w > 100 and w < 300:
            if best is None or w * h < best[0]:
                best = (w * h, (b.extmin.x - 1, b.extmin.y - 1, b.extmax.x + 1, b.extmax.y + 1))
    return best[1] if best else None


def _dwg(dxf):
    subprocess.run([sys.executable, str(Path(__file__).parent / "dwg_dxf_convert.py"), str(dxf), str(OUT), "--to", "dwg"],
                   check=False, capture_output=True)
    return dxf.with_suffix(".dwg")


def main(argv=None):
    import str_slabs as ss
    n = int((argv or sys.argv[1:])[0])
    OUT.mkdir(parents=True, exist_ok=True)
    fl = get_floor(n)
    sx0, sy0, sx1, sy1 = fl.sheet_bbox
    out = []
    a = OUT / f"floor_{n:02d}_architectural.dxf"
    out.append((a, _keep_box(fl.file, (sx0, sy0, sx1, sy1), a)))
    S = ss.read_structural()
    for tag, c in (("under", n - 1), ("above", n)):
        p = ss.plan_for_ceiling(S, c)
        x0, y0, x1, y1 = p["bbox_w"]
        box = _frame_box(ss.STR_DXF, (x0, y0, x1, y1)) or (x0 - 6, y0 - 12, x1 + 22, y1 + 6)
        f = OUT / f"floor_{n:02d}_structural_slab_{tag}.dxf"
        out.append((f, _keep_box(ss.STR_DXF, box, f)))
    for f, k in out:
        d = _dwg(f)
        if d.exists():
            f.unlink()          # keep the DWG only (the DXF copy is ~15 MB)
        print(f.name, k, "entities", "| dwg" if d.exists() else "| no dwg, DXF kept")


if __name__ == "__main__":
    main()
