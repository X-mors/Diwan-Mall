import json, sys
from pathlib import Path
R = Path(r"D:\حصر المباني\Diwan-Mall")
rows = []
hdr = ("| الدور | المنسوب | حوائط إجمالي / صافي (م) | صافي 0.12 / 0.25 (م) | داخلي / خارجي صافي (م) | أبواب عدد = عرض (م) | شبابيك في مباني عدد = عرض (م) | "
       "فراغات | صافي داخلي / أسقف (م²) | إجمالي الدور (م²) | خرسانة (+tr) | أوجه خرسانة داخلية (م ط) | **مباني تقديري (م²)** | **محارة داخلية تقديري (م²)** | واجهات تقديري (م²) |")
sep = "|" + "---|" * 15
out = [hdr, sep]
for F in ["F02", "F03", "F04", "F05", "F06", "F07", "F08"]:
    p = json.loads((R / "output" / "plan" / f"{F}.json").read_text(encoding="utf-8"))
    T = p["walls"]["totals"]; g = lambda k, m: T.get(k, {}).get(m, 0)
    os_ = p["openings"]["summary"]; wm = os_["windows"]["by_kind"].get("window in masonry opening", {})
    rt = p["rooms"]["totals"]; cc = p["cross_checks"]["concrete"]; pl = p["preliminary"]["plaster"]
    m = p["preliminary"]["masonry"]["ALL|ALL"]
    out.append(f"| {F} | {p['level']:+.2f} | {g('ALL|ALL','length_gross'):.2f} / {g('ALL|ALL','length_net'):.2f} | "
               f"{g('0.12|ALL','length_net'):.2f} / {g('0.25|ALL','length_net'):.2f} | {g('ALL|interior','length_net'):.2f} / {g('ALL|exterior','length_net'):.2f} | "
               f"{os_['doors']['count']} = {os_['doors']['total_width']:.2f} | {wm.get('count',0)} = {wm.get('total_width',0):.2f} | "
               f"{rt['n_rooms']} | {rt['net_indoor_area']:.2f} / {rt['ceiling_area']:.2f} | {rt['gross_floor_area']:.2f} | "
               f"{cc['structure_model_space']} (+{cc['structure_tr_only']}) | {p['structure']['summary']['plaster_perimeter_model_space_only']:.2f} | "
               f"**{m['area_net']:.2f}** | **{pl['internal_total_m2']:.2f}** | {pl['external']['area_m2']:.2f} |")
print("\n".join(out))
