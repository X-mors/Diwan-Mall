import sys, pickle
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
import rooms
out = {}
for n in map(int, sys.argv[1:]):
    res = rooms.analyze_floor(n)
    out[n] = {"rooms": [{k: v for k, v in r.items()} for r in res["rooms"]], "footprint": res["_footprint"],
              "wall_bodies": res["_wall_bodies"], "P": [(g, k, ref) for g, k, ref in res["_P"]], "checks": res["checks"], "totals": res["totals"]}
pickle.dump(out, open(r"D:\حصر المباني\Diwan-Mall\output\_verify_rooms\toolpolys.pkl", "wb"))
