import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import matplotlib; matplotlib.use("Agg")
from render_floor import base_axes
for n in [2,4,5,6,7,8]:
    fig, ax, fl = base_axes(n, texts=True, zoom=(-1.5,-2.5,21,41), figsize=(12,22))
    fig.savefig(rf"D:\حصر المباني\Diwan-Mall\output\walls\explore\full_F{n:02d}.png", dpi=90, bbox_inches="tight")
    print(n)
