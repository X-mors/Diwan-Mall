import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\output\_verify_structure_diff\r2")
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from a6_diff import geoms, uncovered, total
from diwan_common import get_floor, floor_entities
from ezdxf import path as ezpath
from shapely.geometry import LineString
from shapely.ops import unary_union, linemerge
fl = get_floor(2)
H = []
for e in floor_entities(fl, layers="W"):
    if e.dxftype() == "HATCH":
        for bp in e.paths:
            p = ezpath.from_hatch_boundary_path(bp)
            vs = [fl.to_local(v.x, v.y) for v in p.flattening(0.01)]
            for a, b in zip(vs, vs[1:]):
                if math.hypot(b[0]-a[0], b[1]-a[1]) > 1e-6:
                    H.append((LineString([a, b]), "hatch:" + e.dxf.handle))
print("hatch boundary total", round(sum(g.length for g, _ in H), 2))
L = geoms(2, "W", maxlen=50)          # plain lines, no 1585
P1585 = [(g, h) for g, h in geoms(2, "W", maxlen=200) if h == "1585"]
print("1585 len", round(sum(g.length for g, _ in P1585), 2))
# hatch covered by plain lines?
uH = uncovered(H, L); print("hatch not covered by F02 plain W lines", round(total(uH), 2))
uH2 = uncovered(uH, P1585); print("... nor by 1585", round(total(uH2), 2))
u1585 = uncovered(P1585, L); print("1585 not covered by plain W lines", round(total(u1585), 2))
u1585b = uncovered(u1585, H); print("1585 not covered by plain W nor hatch", round(total(u1585b), 2))
F6 = geoms(6, "W", maxlen=50)
print("F02 plain lines not in F06:", round(total(uncovered(L, F6)), 2))
print("F02 hatch not in F06:", round(total(uncovered(H, F6)), 2))
print("F02 hatch not in F06 and not dup of own lines:", round(total(uncovered(uncovered(H, F6), L)), 2))
print("F02 1585 not in F06:", round(total(uncovered(P1585, F6)), 2), " and not dup of own lines/hatch:", round(total(uncovered(uncovered(uncovered(P1585, F6), L), H)), 2))
# unique geometry of F02 not in F06 (dedupe)
allg = L + H + P1585
u = uncovered(allg, F6)
geo = unary_union([g for g, _ in u])
print("UNIQUE (deduped via union) F02 W geometry not in F06 ~", round(geo.length, 2))
