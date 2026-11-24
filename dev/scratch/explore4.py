import pickle, math, collections
D = pickle.load(open("wdata.pkl","rb"))
for F in ["F03"]:
    d = D[F]
    angs = collections.Counter()
    for a,b,h,lt in d["lines"]:
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        ang = math.degrees(math.atan2(b[1]-a[1], b[0]-a[0])) % 180
        if abs(ang-0)>0.05 and abs(ang-90)>0.05 and abs(ang-180)>0.05:
            print(round(ang,3), round(L,3), tuple(round(v,2) for v in a), tuple(round(v,2) for v in b), lt)
    lts = collections.Counter(l[3] for l in d["lines"]); print(lts)
    Ls = sorted(math.hypot(b[0]-a[0], b[1]-a[1]) for a,b,h,lt in d["lines"])
    print("n", len(Ls), "len<0.02:", sum(1 for L in Ls if L<0.02), "<0.05", sum(1 for L in Ls if L<0.05))
