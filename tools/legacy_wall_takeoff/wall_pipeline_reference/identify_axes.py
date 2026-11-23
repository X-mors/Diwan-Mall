import math
import ezdxf
from collections import Counter

SRC = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor.dxf"
doc = ezdxf.readfile(SRC)
msp = doc.modelspace()

for target in ["X", "x1", "CI", "DASH"]:
    ents = [e for e in msp if e.dxf.layer == target]
    types = Counter(e.dxftype() for e in ents)
    print(f"\n=== layer '{target}': {dict(types)} ===")
    # line length stats
    lines = [e for e in ents if e.dxftype() == "LINE"]
    if lines:
        lens = []
        lts = Counter()
        for e in lines:
            L = math.hypot(e.dxf.end.x-e.dxf.start.x, e.dxf.end.y-e.dxf.start.y)
            lens.append(L)
            lts[e.dxf.linetype] += 1
        lens.sort()
        print(f"   LINE count={len(lines)} len: min={lens[0]:.1f} median={lens[len(lens)//2]:.1f} max={lens[-1]:.1f}")
        print(f"   linetypes: {dict(lts)}")
    inserts = [e for e in ents if e.dxftype() == "INSERT"]
    if inserts:
        blocks = Counter(e.dxf.name for e in inserts)
        print(f"   INSERT blocks: {dict(blocks)}")
