import pickle, math
D = pickle.load(open("wdata.pkl","rb"))
d = D["F03"]
box = (-0.5, 28.0, 1.5, 37)
def inb(p): return box[0]<=p[0]<=box[2] and box[1]<=p[1]<=box[3]
print("W lines:")
for a,b,h,lt in d["lines"]:
    if inb(a) or inb(b):
        print("  ", tuple(round(v,3) for v in a), tuple(round(v,3) for v in b), h)
print("WIN lines:")
for w in d["win"]:
    if len(w)==3 and (inb(w[0]) or inb(w[1])):
        print("  ", tuple(round(v,3) for v in w[0]), tuple(round(v,3) for v in w[1]), w[2])
