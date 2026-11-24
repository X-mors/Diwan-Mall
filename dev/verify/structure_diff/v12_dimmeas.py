import sys, math
sys.path.insert(0, 'tools')
from diwan_common import get_floor, floor_entities
fl=get_floor(6)
n=0; bad=0; tot=0
for e in floor_entities(fl, layers='DIM', types='DIMENSION'):
    tot+=1
    txt=None
    for x in e.get_geometry_block() or []:
        if x.dxftype() in ('MTEXT','TEXT'):
            txt=(x.plain_text() if x.dxftype()=='MTEXT' else x.dxf.text).strip(); break
    act=e.dxf.get('actual_measurement')
    try: gm=e.get_measurement()
    except Exception as ex: gm=None
    p2=e.dxf.defpoint2; p3=e.dxf.defpoint3
    d=math.dist((p2.x,p2.y),(p3.x,p3.y))
    if e.dimtype==1:
        n+=1
        if n<=6: print('aligned', e.dxf.handle, 'txt',txt,'act',act and round(act,4),'get_meas',gm if gm is None else round(float(gm),4),'p2p3 dist',round(d,4))
    if txt and act is not None and abs(float(txt)-act)>0.006: bad+=1
print('aligned', n, 'total', tot, 'txt!=act', bad)
