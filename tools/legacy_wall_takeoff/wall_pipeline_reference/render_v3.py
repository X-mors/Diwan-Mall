import json
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v3b_classified.json") as f:
    data = json.load(f)
walls = data["walls"]

fig, ax = plt.subplots(figsize=(18, 30))
for i, w in enumerate(walls):
    if w["is_exterior"]:
        color = "red"
    elif w["needs_check"]:
        color = "orange"
    else:
        color = "steelblue"
    ax.add_patch(Rectangle((w["x0"], w["y0"]), w["x1"]-w["x0"], w["y1"]-w["y0"], facecolor=color, edgecolor="black", linewidth=0.3, alpha=0.9))

xs = [w["x0"] for w in walls] + [w["x1"] for w in walls]
ys = [w["y0"] for w in walls] + [w["y1"] for w in walls]
ax.set_xlim(min(xs)-1, max(xs)+1)
ax.set_ylim(min(ys)-1, max(ys)+1)
ax.set_aspect("equal")
ax.set_title("red=exterior, blue=interior(confident), orange=interior(needs thickness check)")
fig.savefig(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\v3b_full.png", dpi=140)
print("saved")
