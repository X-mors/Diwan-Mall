import sys, math
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_texts
fl=get_floor(int(sys.argv[1]))
for t in floor_texts(fl, layers=("TEXT","-A-TEXT","TEXT-D")):
    x,y=t['local']
    if -3<x<22 and -3<y<42: print(t['layer'], repr(t['raw']), t['text'], round(x,1), round(y,1))
