import sys
sys.path.insert(0, '.')
import zoom as Z
Z.COL.update({"MASS": "magenta", "0": "orange"})
a = sys.argv
Z.zoom(int(a[1]), *map(float, a[2:6]), a[6], layers=("W", "WIN", "DASH", "try", "MASS"), handles=True)
