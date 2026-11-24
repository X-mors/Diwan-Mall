import ezdxf, math, collections
doc = ezdxf.readfile(r'dxf/Diwan_3rd_Floor_22.8.2026.dxf')
for name in ['D10W12','D80W12','D90W12','D90W25']:
    b = doc.blocks[name]
    print('=====', name, 'base', b.block.dxf.base_point)
    xs=[];ys=[]
    lines=[]
    for e in b:
        t=e.dxftype()
        if t=='ARC':
            print('  ARC c=(%.3f,%.3f) r=%.3f a=%.1f..%.1f extr=%s layer=%s'%(e.dxf.center.x,e.dxf.center.y,e.dxf.radius,e.dxf.start_angle,e.dxf.end_angle,tuple(e.dxf.extrusion),e.dxf.layer))
        elif t=='LINE':
            s,en=e.dxf.start,e.dxf.end
            L=math.dist((s.x,s.y),(en.x,en.y))
            lines.append((L,s.x,s.y,en.x,en.y,e.dxf.layer))
            xs+= [s.x,en.x]; ys+=[s.y,en.y]
        elif t=='LWPOLYLINE':
            pts=list(e.get_points('xy'))
            xs+=[p[0] for p in pts]; ys+=[p[1] for p in pts]
    print('  bbox lines x %.3f..%.3f y %.3f..%.3f'%(min(xs),max(xs),min(ys),max(ys)))
    lines.sort(reverse=True)
    for l in lines[:12]:
        print('  LINE L=%.3f (%.3f,%.3f)-(%.3f,%.3f) %s'%l)
    c=collections.Counter(round(l[0],3) for l in lines)
    print('  line length hist', sorted(c.items())[:30])
