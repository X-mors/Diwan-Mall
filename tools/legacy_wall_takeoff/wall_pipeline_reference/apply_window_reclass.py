import json, math
import ezdxf

SRC = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor.dxf"
doc = ezdxf.readfile(SRC)
msp = doc.modelspace()

ROT_DEG = 9.999657166117375
PIVOT = (230.0, 785.0)
theta = math.radians(-ROT_DEG)
ct, st = math.cos(theta), math.sin(theta)
def rot(p):
    x, y = p[0]-PIVOT[0], p[1]-PIVOT[1]
    return (x*ct - y*st, x*st + y*ct)

win_h, win_v = [], []
for e in msp:
    if e.dxf.layer == "WIN" and e.dxftype() == "LINE":
        s = rot((e.dxf.start.x, e.dxf.start.y)); en = rot((e.dxf.end.x, e.dxf.end.y))
        ang = math.degrees(math.atan2(en[1]-s[1], en[0]-s[0])) % 180
        if min(ang, 180-ang) <= 5:
            win_h.append(((s[1]+en[1])/2, min(s[0],en[0]), max(s[0],en[0])))
        elif abs(ang-90) <= 5:
            win_v.append(((s[0]+en[0])/2, min(s[1],en[1]), max(s[1],en[1])))

def win_coverage(w):
    if w["orient"] == "H":
        perp = w["cy"]; a0, a1 = w["x0"], w["x1"]; wins = win_h
    else:
        perp = w["cx"]; a0, a1 = w["y0"], w["y1"]; wins = win_v
    span = a1 - a0
    if span <= 0: return 0.0
    covered = []
    for wp, wa0, wa1 in wins:
        if abs(wp - perp) <= w["thick"] + 0.12:
            lo, hi = max(a0, wa0), min(a1, wa1)
            if hi > lo: covered.append((lo, hi))
    covered.sort(); merged = []
    for lo, hi in covered:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return sum(hi-lo for lo,hi in merged) / span

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v3b_classified.json") as f:
    data = json.load(f)
walls = data["walls"]

FACADE_THRESH = 0.50   # >50% window along it => facade window-wall => exterior
CHECK_THRESH = 0.25    # 25-50% => keep interior but flag
reclassified = 0
for w in walls:
    if w["is_exterior"]:
        w["win_cov"] = win_coverage(w)
        continue
    c = win_coverage(w)
    w["win_cov"] = c
    if c > FACADE_THRESH:
        w["is_exterior"] = True
        w["facade_window_wall"] = True
        reclassified += 1
    elif c > CHECK_THRESH:
        w["needs_check"] = True
        w["window_note"] = True

interior = [w for w in walls if not w["is_exterior"]]
print(f"reclassified {reclassified} window-walls as facade (exterior)")
print(f"remaining interior: {len(interior)}")

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\walls_v3b_classified.json", "w") as f:
    json.dump({"walls": walls}, f)
