"""
Render a DXF's modelspace to a PNG for a quick visual check (no AutoCAD needed).

Usage:
    python render_dxf.py <input.dxf> <output.png> [--dpi 150]
"""
import argparse

import ezdxf
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing import matplotlib as ezmpl
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration


def render(src: str, dst: str, dpi: int = 150):
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()

    fig = plt.figure(figsize=(16, 16))
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    config = Configuration(background_policy=BackgroundPolicy.WHITE)
    out = ezmpl.MatplotlibBackend(ax)
    Frontend(ctx, out, config=config).draw_layout(msp, finalize=True)
    fig.savefig(dst, dpi=dpi)
    print("saved:", dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_dxf")
    ap.add_argument("output_png")
    ap.add_argument("--dpi", type=int, default=150)
    args = ap.parse_args()
    render(args.input_dxf, args.output_png, args.dpi)


if __name__ == "__main__":
    main()
