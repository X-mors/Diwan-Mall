"""Images for the extra open questions (2026-11-27): single-line walls, office-4 line, axis D."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Ellipse  # noqa: E402
import snap  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output" / "questions"


def mark(ax, x, y, w, h, txt, dx=0.5, dy=0.5):
    ax.add_patch(Ellipse((x, y), w, h, fill=False, ec="red", lw=2.5, zorder=20))
    ax.annotate(txt, (x, y), (x + dx, y + dy), color="red", fontsize=11, fontweight="bold", zorder=21,
                arrowprops=dict(arrowstyle="->", color="red", lw=1.5))


# Q11: walls drawn with ONE line (F07 north-west, F08 north-east) vs F06
z1 = (8.0, 33.0, 18.0, 40.5)
fig, axs = snap.figure(2, z1)
snap.arch_draw(axs[0], 6, z1)
snap.arch_draw(axs[1], 8, z1)
axs[0].set_title("FLOOR 6 (reference): east wall drawn with 2 lines", fontsize=11)
axs[1].set_title("FLOOR 8: north-east wall drawn with ONE line", fontsize=11)
mark(axs[1], 16.75, 37.0, 0.9, 3.8, "single line\n(wall thickness?)", dx=-4.5, dy=1.5)
fig.savefig(OUT / "Q11_single_line_walls_F08.png", dpi=110, bbox_inches="tight")
plt.close(fig)

# Q12: the short single W line inside office 4 (x ~ 5.75), every floor
z3 = (2.0, 34.5, 9.0, 39.8)
fig, axs = snap.figure(1, z3, k=0.9)
snap.arch_draw(axs[0], 6, z3)
axs[0].set_title("FLOOR 6 (same on every floor): short line inside office 4 at x = 5.75", fontsize=11)
mark(axs[0], 5.7, 37.2, 0.7, 1.8, "partial partition? beam edge?\ncladding line?", dx=1.2, dy=1.2)
fig.savefig(OUT / "Q12_office4_line.png", dpi=110, bbox_inches="tight")
plt.close(fig)

# Q13: axis D -- line at x = 9.755, dimension chain puts it 1.50 m east (11.255)
z4 = (5.0, -2.0, 15.0, 40.0)
fig, axs = snap.figure(1, z4, k=0.35)
ax = axs[0]
snap.arch_draw(ax, 6, z4, layers=["W", "Etabs-col", "X"], texts=False, lw=0.5)
ax.axvline(9.755, color="red", lw=2.0, ls="--")
ax.axvline(11.255, color="blue", lw=2.0, ls="--")
ax.text(9.6, 40.3, "axis D line\nx = 9.755", color="red", ha="right", fontsize=11, fontweight="bold")
ax.text(11.4, 40.3, "axis D by the\ndimension chain\n(+1.50 m)", color="blue", ha="left", fontsize=11, fontweight="bold")
ax.set_ylim(-2, 43)
ax.set_title("FLOOR 6: where is axis D?  C-D = 3.15 / D-E = 3.00 in the dimensions, 4.65 / 1.50 on the axis lines",
             fontsize=10)
fig.savefig(OUT / "Q13_axis_D.png", dpi=110, bbox_inches="tight")
plt.close(fig)
print("ok")
