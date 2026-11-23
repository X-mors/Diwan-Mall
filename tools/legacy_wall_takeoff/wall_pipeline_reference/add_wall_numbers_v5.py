import json
import math
import ezdxf

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\interior_walls_v4_final.json") as f:
    interior = json.load(f)

SRC = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor_walls_highlighted_clean.dxf"
DST = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor_walls_numbered_v5.dxf"

doc = ezdxf.readfile(SRC)
msp = doc.modelspace()

if "WALL-NO" not in doc.layers:
    doc.layers.add("WALL-NO", color=6)       # magenta - confirmed
if "WALL-NO-CHECK" not in doc.layers:
    doc.layers.add("WALL-NO-CHECK", color=30)  # orange - needs verification

ROT_DEG = 9.999657166117375
PIVOT = (230.0, 785.0)
theta = math.radians(ROT_DEG)
ct, st = math.cos(theta), math.sin(theta)
def rot_vec(vx, vy):
    return (vx*ct - vy*st, vx*st + vy*ct)

CIRCLE_R = 0.42     # radius of the bubble
TEXT_HEIGHT = 0.38  # text height
MIN_SEP = 2 * CIRCLE_R + 0.12  # min distance between two bubble centers

def candidate_centers(w):
    """Yield candidate bubble centers (global) for wall w, in preference order:
    both perpendicular sides at increasing offset distances."""
    wc = w["global_center"]
    for dist in (1.3, 1.9, 2.5, 3.1, 3.7):
        for sign in (+1, -1):
            if w["orient"] == "H":
                local = (0, sign * dist)
            else:
                local = (sign * dist, 0)
            gx, gy = rot_vec(*local)
            yield (wc[0] + gx, wc[1] + gy)

placed_centers = []
def choose_center(w):
    """Pick the first candidate center that doesn't collide with an already
    placed bubble; fall back to the furthest candidate if all collide."""
    last = None
    for c in candidate_centers(w):
        last = c
        if all(math.hypot(c[0]-p[0], c[1]-p[1]) >= MIN_SEP for p in placed_centers):
            placed_centers.append(c)
            return c
    placed_centers.append(last)
    return last

# place larger walls first so their bubbles get the preferred near positions
for w in sorted(interior, key=lambda w: -w["len"]):
    wall_center = w["global_center"]
    circle_center = choose_center(w)
    layer = "WALL-NO-CHECK" if w["needs_check"] else "WALL-NO"
    color = 30 if w["needs_check"] else 6
    label = f"W{w['no']}"

    # leader line from wall center to edge of circle
    dx = circle_center[0] - wall_center[0]
    dy = circle_center[1] - wall_center[1]
    d = math.hypot(dx, dy)
    if d > 0:
        ux, uy = dx / d, dy / d
        end_x = circle_center[0] - ux * CIRCLE_R
        end_y = circle_center[1] - uy * CIRCLE_R
    else:
        end_x, end_y = circle_center

    msp.add_line(wall_center, (end_x, end_y), dxfattribs={"layer": layer, "color": color})

    # circle
    msp.add_circle(circle_center, CIRCLE_R, dxfattribs={"layer": layer, "color": color})

    # text centered in circle
    txt = msp.add_text(label, dxfattribs={
        "layer": layer, "height": TEXT_HEIGHT, "color": color,
        "rotation": ROT_DEG, "style": "Standard",
    })
    txt.dxf.insert = circle_center
    txt.dxf.halign = 1
    txt.dxf.valign = 2
    txt.dxf.align_point = circle_center

    # --- length measurement written ALONG the wall centerline ---
    # H wall: text reads along local X (rotation = ROT_DEG)
    # V wall: text reads along local Y (rotation = ROT_DEG + 90)
    length_txt = f"{w['len']:.2f}"
    if w["orient"] == "H":
        text_rot = ROT_DEG
        off_local = (0, 0.22)   # nudge just above the wall line
    else:
        text_rot = ROT_DEG + 90
        off_local = (0.22, 0)   # nudge just beside the wall line
    ogx, ogy = rot_vec(*off_local)
    len_pos = (wall_center[0] + ogx, wall_center[1] + ogy)
    dtxt = msp.add_text(length_txt, dxfattribs={
        "layer": layer, "height": 0.30, "color": color,
        "rotation": text_rot, "style": "Standard",
    })
    dtxt.dxf.insert = len_pos
    dtxt.dxf.halign = 1   # center
    dtxt.dxf.valign = 2   # middle
    dtxt.dxf.align_point = len_pos

doc.saveas(DST)
print("added", len(interior), "labels + length measurements ->", DST)
