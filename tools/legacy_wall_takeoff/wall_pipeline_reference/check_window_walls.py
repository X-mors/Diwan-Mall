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

# collect WIN-layer line segments in local frame, split H/V
win_h = []   # (perp=y, a0, a1)
win_v = []   # (perp=x, a0, a1)
for e in msp:
    if e.dxf.layer == "WIN" and e.dxftype() == "LINE":
        s = rot((e.dxf.start.x, e.dxf.start.y)); en = rot((e.dxf.end.x, e.dxf.end.y))
        ang = math.degrees(math.atan2(en[1]-s[1], en[0]-s[0])) % 180
        if min(ang, 180-ang) <= 5:
            win_h.append((( s[1]+en[1])/2, min(s[0],en[0]), max(s[0],en[0])))
        elif abs(ang-90) <= 5:
            win_v.append(((s[0]+en[0])/2, min(s[1],en[1]), max(s[1],en[1])))

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\interior_walls_v4_final.json") as f:
    interior = json.load(f)

def win_coverage(w):
    """fraction of wall length that has a WIN line running parallel within
    thickness+0.1m and overlapping in the along direction."""
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
            if hi > lo:
                covered.append((lo, hi))
    covered.sort()
    merged = []
    for lo, hi in covered:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    cov = sum(hi-lo for lo,hi in merged)
    return cov / span

flagged = []
for w in interior:
    c = win_coverage(w)
    w["win_cov"] = c
    if c > 0.30:
        flagged.append(w)

print(f"walls with >30% window (cyan) coverage along them: {len(flagged)} of {len(interior)}")
for w in sorted(flagged, key=lambda w: -w["win_cov"]):
    print(f"  W{w['no']:<3d} len={w['len']:5.2f} win_cov={w['win_cov']*100:4.0f}%  is_ext={w['is_exterior']} needs_check={w['needs_check']}")
