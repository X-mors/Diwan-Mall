import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import walls as W
from diwan_common import get_floor
F=int(sys.argv[1]); box=tuple(map(float,sys.argv[2:6]))
g = W.load_geometry(get_floor(F))
def inb(x,y): return box[0]<=x<=box[2] and box[1]<=y<=box[3]
print("W:")
for s in g["wsegs"]:
    if inb(s[0],s[1]) or inb(s[2],s[3]):
        print("  (%.3f,%.3f)-(%.3f,%.3f) %s %s"%(s[0],s[1],s[2],s[3],s[4],s[5]))
print("WIN:")
for s in g["win"]:
    if inb(s[0],s[1]) or inb(s[2],s[3]):
        print("  (%.3f,%.3f)-(%.3f,%.3f) %s"%s)
print("doors:")
for d in g["doors"]:
    if inb(d["x"],d["y"]): print("  ", d["name"], d["layer"], round(d["x"],3), round(d["y"],3), d["rot"], [round(v,3) for v in d["bbox"]])
print("cols:")
for c in g["columns"]:
    if any(inb(*p) for p in c["pts"]): print("  ", c["layer"], [(round(p[0],3),round(p[1],3)) for p in c["pts"]])
print("texts:")
for t in g["texts"]:
    if inb(t["x"],t["y"]): print("  ", t["text"], round(t["x"],2), round(t["y"],2))
