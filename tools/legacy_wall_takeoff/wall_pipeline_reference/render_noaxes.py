import ezdxf
from ezdxf.addons.drawing import matplotlib as ezmpl
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy
import matplotlib.pyplot as plt

SRC = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor_walls_numbered_noaxes.dxf"
OUT = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\noaxes_zoom.png"

doc = ezdxf.readfile(SRC)
msp = doc.modelspace()
fig = plt.figure(figsize=(22, 30))
ax = fig.add_axes([0, 0, 1, 1])
ctx = RenderContext(doc)
config = Configuration(background_policy=BackgroundPolicy.WHITE)
out = ezmpl.MatplotlibBackend(ax)
Frontend(ctx, out, config=config).draw_layout(msp, finalize=True)
ax.set_aspect('equal', adjustable='box')
ax.set_xlim(218, 244)
ax.set_ylim(761, 810)
ax.set_autoscale_on(False)
fig.savefig(OUT, dpi=160)
print("saved:", OUT)
