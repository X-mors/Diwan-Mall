import json, math

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v3b_classified.json") as f:
    data = json.load(f)

walls = data["walls"]
interior = [w for w in walls if not w["is_exterior"]]

ROT_DEG = 9.999657166117375
PIVOT = (230.0, 785.0)
theta = math.radians(ROT_DEG)
ct, st = math.cos(theta), math.sin(theta)
def unrot(p):
    x, y = p
    return (x*ct - y*st + PIVOT[0], x*st + y*ct + PIVOT[1])

for w in interior:
    if w["orient"] == "H":
        cx, cy = (w["x0"]+w["x1"])/2, w["cy"]
    else:
        cx, cy = w["cx"], (w["y0"]+w["y1"])/2
    w["global_center"] = unrot((cx, cy))

interior.sort(key=lambda w: (-round(w["global_center"][1]/2), w["global_center"][0]))
for i, w in enumerate(interior, start=1):
    w["no"] = i

total_len = sum(w["len"] for w in interior)
confirmed = [w for w in interior if not w["needs_check"]]
flagged = [w for w in interior if w["needs_check"]]
print(f"interior walls: {len(interior)}  (confirmed: {len(confirmed)}, needs_check: {len(flagged)})")
print(f"total length: {total_len:.2f} m   total area @3m: {total_len*3:.2f} m2")

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\interior_walls_v4_final.json", "w") as f:
    json.dump(interior, f)
