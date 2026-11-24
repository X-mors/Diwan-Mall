import sys
sys.path.insert(0, r"D:\حصر المباني\Diwan-Mall\tools")
from diwan_common import get_floor, floor_entities
from shapely.geometry import Polygon, Point, box
fl = get_floor(3)
area = box(9.8, 18.0, 13.5, 23.2)
for e in floor_entities(fl, layers=("Etabs-col","COL","try","W","MASS","Etabs-Slab"), types="LWPOLYLINE HATCH"):
    if e.dxftype()=="LWPOLYLINE":
        pts=[fl.to_local(p[0],p[1]) for p in e.get_points("xy")]
        pg = Polygon(pts) if len(pts)>=3 else None
        if pg is not None and pg.buffer(0).intersects(area):
            print(e.dxf.layer, e.dxftype(), "closed", e.closed, [(round(x,3),round(y,3)) for x,y in pts])
for e in floor_entities(fl, layers=("W","0"), types="LINE"):
    a=fl.to_local(e.dxf.start.x,e.dxf.start.y); b=fl.to_local(e.dxf.end.x,e.dxf.end.y)
    if area.contains(Point(a)) and area.contains(Point(b)) and 10.2<min(a[0],b[0])<10.8:
        print("W", (round(a[0],3),round(a[1],3)),(round(b[0],3),round(b[1],3)))
