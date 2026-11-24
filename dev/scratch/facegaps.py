import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import openings as O
res = O.analyze_floor(3)
G = res["_G"]
tot_min = tot_max = tot_blk = 0
for d in res["doors"]:
    c, u, n = d["_c"], d["_u"], d["_n"]
    t = d["wall_t_block"]
    fg = []
    for side in (-1, 1):
        off = side * t / 2
        lo, hi = -9, 9
        for a, b, _ in G.wall_segs:
            v = O._sub(b, a)
            if O._len(v) < 0.02 or abs(O._cross(O._unit(v), u)) > 0.01: continue
            oa = O._dot(O._sub(a, c), n)
            if abs(oa - off) > 0.006: continue
            s0, s1 = sorted((O._dot(O._sub(a, c), u), O._dot(O._sub(b, c), u)))
            if s1 <= 0.001 and s1 > lo: lo = s1
            if s0 >= -0.001 and s0 < hi: hi = s0
            if s0 < 0 < s1: lo, hi = 0, 0
        fg.append(round(hi - lo, 3) if hi < 9 and lo > -9 else None)
    w = d["width"]
    g = [x for x in fg if x is not None]
    if any(abs(x - w) > 0.004 for x in g) or len(g) < 2:
        print(d["id"], d["block"], w, "face gaps", fg, "host gap", d["host"]["gap"])
    tot_blk += w
    tot_min += min(g) if g else w
    tot_max += max(g) if g else w
print("block", round(tot_blk,3), "min-face", round(tot_min,3), "max-face", round(tot_max,3))
