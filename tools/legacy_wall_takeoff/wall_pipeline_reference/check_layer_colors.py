import ezdxf
SRC = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\dxf_out\3rd_Floor.dxf"
doc = ezdxf.readfile(SRC)
ACI = {1:"RED",2:"YELLOW",3:"GREEN",4:"CYAN(سماوي)",5:"BLUE",6:"MAGENTA",7:"WHITE/BLACK"}
for layer in doc.layers:
    c = layer.dxf.color
    name = ACI.get(abs(c), f"ACI{abs(c)}")
    print(f"  layer '{layer.dxf.name:15s}'  color={c:4d}  = {name}")
