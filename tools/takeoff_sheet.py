"""
Masonry takeoff of one floor for REVIEW: a plan image with every counted wall numbered, and an Excel
with one row per wall in the same numbering (owner's request 2026-11-27: "لوحة مرقم عليها الحوائط
وتسلسلها على الإكسيل").

Reads output/plan/Fnn.json (written by `python tools/read_plan.py`, which holds the owner's rules):
    preliminary.masonry_walls     one row per counted wall (height, gross, door / window / concrete deductions, net)
    preliminary.masonry_excluded  walls left out (on concrete, on tr elements, lift front wall under the beam)

    python tools/takeoff_sheet.py 6            # -> output/takeoff/F06_masonry.png + F06_masonry.xlsx
    python tools/takeoff_sheet.py 2 3 4 5      # several floors
    python tools/takeoff_sheet.py 6 --rerun    # re-run read_plan for the floor first

Numbering: north to south in 1.5 m bands, west to east inside a band (the same order in the image and the Excel).
The Excel total equals preliminary.masonry["ALL|ALL"].area_net (checked, the script stops if not).
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diwan_common import OUT_DIR, all_floors  # noqa: E402

OUT = OUT_DIR / "takeoff"
PLAN = OUT_DIR / "plan"
KIND_AR = {"exterior": "خارجي (واجهة)", "interior": "داخلي", "shaft": "حول شفت", "stair_lift": "سلم / مصعد"}
FAM_COL = {"0.10": "#8c564b", "0.12": "#1f77b4", "0.15": "#17becf", "0.20": "#bcbd22", "0.25": "#d62728",
           "0.30": "#9467bd", "0.40": "#ff7f0e", "0.50": "#e377c2", "0.60": "#7f7f7f", "other": "#2ca02c"}
BAND = 1.5


def _order(rows):
    def key(r):
        mx, my = (r["x1"] + r["x2"]) / 2, (r["y1"] + r["y2"]) / 2
        return (-math.floor(my / BAND), mx, -my)
    return sorted(rows, key=key)


def _load(n):
    p = PLAN / f"F{n:02d}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    pre = d["preliminary"]
    if "masonry_walls" not in pre:
        raise SystemExit(f"{p.name} has no per-wall rows: run  python tools/read_plan.py {n}")
    return d


def _note(r):
    parts = []
    if r.get("ded_concrete"):
        parts.append(f"خُصم {r['ded_concrete'] / (r['height'] or 1):.2f} م طول داخل عمود/حائط خرساني بالإنشائي")
    for o in r.get("openings_in_concrete") or []:
        parts.append(f"{'شباك' if o['type'] == 'window' else 'باب' if o['type'] == 'door' else 'فتحة'} {o['width']:.2f} بالمعماري "
                     "مكانه عمود بالإنشائي (لم يُخصم مرتين)")
    return "؛ ".join(parts)


def image(n, d, rows, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import snap
    pre = d["preliminary"]
    recs = {w["id"]: w for w in d["walls"]["records"]}
    xs = [v for w in d["walls"]["records"] for v in (w["x1"], w["x2"])]
    ys = [v for w in d["walls"]["records"] for v in (w["y1"], w["y2"])]
    z = (min(xs) - 1.0, min(ys) - 1.0, max(xs) + 1.0, max(ys) + 1.0)
    W, H = z[2] - z[0], z[3] - z[1]
    fig, ax = plt.subplots(figsize=(W * 1.15 + 4, H * 1.15))
    snap.arch_draw(ax, n, z, layers=["W", "WIN", "Etabs-col", "ST"], texts=False, lw=0.35)
    for ln in ax.get_lines():
        ln.set_alpha(0.35)
    # structural columns / shear walls / cores of this floor (what was built): masonry is deducted inside them
    try:
        import str_slabs as ss
        from matplotlib.patches import Polygon as MPoly
        mh_meta = pre.get("masonry_heights") or {}
        plan = ss.plan_for_ceiling(ss.read_structural(), n)
        sdx, sdy = mh_meta.get("shift") or (0.0, 0.0)
        for c in (plan or {}).get("columns", []):
            g = c["_poly"]
            for gg in getattr(g, "geoms", [g]):
                xy = [(x - sdx, y - sdy) for x, y in gg.exterior.coords]
                ax.add_patch(MPoly(xy, closed=True, fc="#9b59b6", ec="#6c3483", alpha=0.35, hatch="////", lw=0.6, zorder=7))
    except Exception as e:  # structural not available -> plan without columns
        print("structural columns not drawn:", e)
    ex = pre.get("masonry_excluded", {})
    exl = [(i, "on concrete") for i in ex.get("on_concrete", [])] + [(i, "on tr concrete") for i in ex.get("on_tr", [])] + \
          [(i, "lift front wall (later)") for i in ex.get("lift_front_later", [])]
    for wid, _ in exl:
        w = recs.get(wid)
        if w:
            ax.plot([w["x1"], w["x2"]], [w["y1"], w["y2"]], color="#555555", lw=2.5, ls=(0, (2, 1.5)), zorder=5)
    for r in rows:
        col = FAM_COL.get(r["family"], "#2ca02c")
        # draw only the masonry: cut the door / window / opening gaps out of the centre line
        Lw = math.hypot(r["x2"] - r["x1"], r["y2"] - r["y1"]) or 1e-9
        ux, uy = (r["x2"] - r["x1"]) / Lw, (r["y2"] - r["y1"]) / Lw
        cuts = []
        for o in r["openings"]:
            if o.get("at"):
                t = (o["at"][0] - r["x1"]) * ux + (o["at"][1] - r["y1"]) * uy
                cuts.append((t - o["width"] / 2, t + o["width"] / 2, o["type"]))
        t0 = 0.0
        for a, b_, typ in sorted(cuts):
            if a > t0:
                ax.plot([r["x1"] + ux * t0, r["x1"] + ux * a], [r["y1"] + uy * t0, r["y1"] + uy * a], color=col, lw=3.2,
                        solid_capstyle="butt", zorder=6, alpha=0.85)
            ax.plot([r["x1"] + ux * max(a, 0), r["x1"] + ux * min(b_, Lw)], [r["y1"] + uy * max(a, 0), r["y1"] + uy * min(b_, Lw)],
                    color="#00bcd4" if typ == "window" else "#ffffff", lw=1.0, ls=":", zorder=6)
            t0 = max(t0, b_)
        if t0 < Lw:
            ax.plot([r["x1"] + ux * t0, r["x2"]], [r["y1"] + uy * t0, r["y2"]], color=col, lw=3.2, solid_capstyle="butt",
                    zorder=6, alpha=0.85)
        mx, my = (r["x1"] + r["x2"]) / 2, (r["y1"] + r["y2"]) / 2
        L = math.hypot(r["x2"] - r["x1"], r["y2"] - r["y1"]) or 1
        nx, ny = -(r["y2"] - r["y1"]) / L, (r["x2"] - r["x1"]) / L
        off = 0.0 if L > 1.2 else 0.28
        ax.text(mx + nx * off, my + ny * off, str(r["no"]), fontsize=7.5, ha="center", va="center", color=col,
                fontweight="bold", zorder=8,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec=col, lw=0.6, alpha=0.95))
    fams = sorted({r["family"] for r in rows}, key=lambda f: (f == "other", f))
    hs = [Line2D([0], [0], color=FAM_COL.get(f, "#2ca02c"), lw=4, label=f"wall {f} m" if f != "other" else "non-standard")
          for f in fams]
    hs.append(Line2D([0], [0], color="#00bcd4", lw=1, ls=":", label="window opening"))
    from matplotlib.patches import Patch
    hs.append(Patch(fc="#9b59b6", ec="#6c3483", alpha=0.35, hatch="////", label="structural concrete (deducted from the wall)"))
    hs.append(Line2D([0], [0], color="#555555", lw=2.5, ls=(0, (2, 1.5)), label="NOT counted (concrete / lift front later)"))
    ax.legend(handles=hs, loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=11, frameon=False)
    tot = sum(r["area_net"] for r in rows)
    ax.set_title(f"FLOOR {n}  ({d['level']:+.2f})  -  masonry takeoff: {len(rows)} walls numbered 1..{len(rows)} "
                 f"(same order as the Excel)  -  net {tot:.2f} m2", fontsize=14)
    ax.set_xlim(z[0], z[2])
    ax.set_ylim(z[1], z[3])
    ax.set_aspect("equal")
    fig.savefig(out_png, dpi=110, bbox_inches="tight")
    plt.close(fig)


def workbook(n, d, rows, out_xlsx):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    pre = d["preliminary"]
    wb = Workbook()
    ws = wb.active
    ws.title = f"حصر مباني الدور {n}"
    ws.sheet_view.rightToLeft = True
    thin = Side(style="thin", color="999999")
    B = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor="DDEBF7")
    tot_fill = PatternFill("solid", fgColor="FFF2CC")
    ws["A1"] = f"حصر مباني الدور {n} (منسوب {d['level']:+.2f}) — كل حائط برقمه على الصورة F{n:02d}_masonry.png"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = ("الارتفاع = 3.20 − عمق الخرسانة فوق الحائط (بلاطة 0.20 ← 3.00، 0.35 ← 2.85، كمرة 70 ← 2.50، كمرة 90 ← 2.30)؛ "
                "الأبواب 2.30 وعرض اللوحة + 5 سم؛ شبابيك الخدمات 85×65؛ " + ("باقي الشبابيك جلسة 1.00 (مباني تحت الشباك)؛ " if d["params"].get("window_sill") else "باقي الشبابيك فراغ بالارتفاع كله؛ ") +
                "خصم الخرسانة = طول الحائط داخل أعمدة/حوائط قص الإنشائي × الارتفاع")
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A2:N2")
    ws.row_dimensions[2].height = 45
    cols = ["م", "رقم الحائط في القراءة", "السمك (م)", "النوع", "الطول الإجمالي (م)", "الارتفاع (م)",
            "المساحة الإجمالية (م²)", "خصم الأبواب (م²)", "خصم الشبابيك (م²)", "خصم فتحات بلا باب (م²)",
            "خصم الخرسانة (م²)", "الصافي (م²)", "الفتحات", "ملاحظة"]
    r0 = 4
    for j, c in enumerate(cols, 1):
        cell = ws.cell(r0, j, c)
        cell.font = Font(bold=True)
        cell.fill = hdr_fill
        cell.border = B
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[r0].height = 32
    for i, r in enumerate(rows, 1):
        rr = r0 + i
        ops = "، ".join(f"{'باب' if o['type'] == 'door' else 'شباك' if o['type'] == 'window' else 'فتحة'} {o['width']:.2f}"
                        for o in r["openings"])
        vals = [r["no"], r["id"], float(r["family"]) if r["family"] != "other" else (r.get("thickness") or "غير قياسي"),
                KIND_AR.get(r["kind"], r["kind"]), r["length_gross"], r["height"], None,
                r["ded_door"], r["ded_window"], r["ded_opening"], r["ded_concrete"], None, ops,
                "مباني بقرار المالك (ضلع C للمصعد)" if r["id"] == "LIFT-C" else _note(r)]
        for j, v in enumerate(vals, 1):
            c = ws.cell(rr, j, v)
            c.border = B
            if j in (5, 6, 7, 8, 9, 10, 11, 12):
                c.number_format = "0.00"
        ws.cell(rr, 7, f"=E{rr}*F{rr}").number_format = "0.00"
        ws.cell(rr, 12, f"=G{rr}-H{rr}-I{rr}-J{rr}-K{rr}").number_format = "0.00"
    last = r0 + len(rows)
    rt = last + 1
    ws.cell(rt, 1, "الإجمالي").font = Font(bold=True)
    for j, L in ((5, "E"), (7, "G"), (8, "H"), (9, "I"), (10, "J"), (11, "K"), (12, "L")):
        c = ws.cell(rt, j, f"=SUM({L}{r0 + 1}:{L}{last})")
        c.number_format = "0.00"
        c.font = Font(bold=True)
    for j in range(1, 15):
        ws.cell(rt, j).fill = tot_fill
        ws.cell(rt, j).border = B
    for j, w in enumerate([5, 12, 9, 13, 11, 9, 12, 11, 11, 11, 11, 11, 26, 26], 1):
        ws.column_dimensions[chr(64 + j)].width = w
    ws.freeze_panes = ws.cell(r0 + 1, 1)

    # summary by thickness / kind (formulas on the wall sheet)
    s2 = wb.create_sheet("ملخص")
    s2.sheet_view.rightToLeft = True
    s2["A1"] = f"ملخص حصر مباني الدور {n}"
    s2["A1"].font = Font(bold=True, size=13)
    sh = ws.title
    row = 3
    for title, col_letter, keys in (("حسب السمك", "C", sorted({ws.cell(i, 3).value for i in range(r0 + 1, last + 1)}, key=str)),
                                    ("حسب النوع", "D", sorted({ws.cell(i, 4).value for i in range(r0 + 1, last + 1)}))):
        s2.cell(row, 1, title).font = Font(bold=True)
        for j, h in enumerate(["البند", "عدد الحوائط", "الطول الإجمالي (م)", "الصافي (م²)"], 1):
            c = s2.cell(row + 1, j, h)
            c.font = Font(bold=True)
            c.fill = hdr_fill
            c.border = B
        row += 2
        for k in keys:
            q = f'"{k}"' if isinstance(k, str) else k
            s2.cell(row, 1, k).border = B
            s2.cell(row, 2, f"=COUNTIF('{sh}'!{col_letter}{r0 + 1}:{col_letter}{last},{q})").border = B
            for j, L in ((3, "E"), (4, "L")):
                c = s2.cell(row, j, f"=SUMIF('{sh}'!{col_letter}{r0 + 1}:{col_letter}{last},{q},'{sh}'!{L}{r0 + 1}:{L}{last})")
                c.number_format = "0.00"
                c.border = B
            row += 1
        row += 1
    s2.cell(row, 1, "الإجمالي").font = Font(bold=True)
    c = s2.cell(row, 4, f"='{sh}'!L{rt}")
    c.number_format = "0.00"
    c.font = Font(bold=True)
    row += 2
    ex = pre.get("masonry_excluded", {})
    s2.cell(row, 1, "حوائط غير محسوبة (مرسومة رمادي متقطع على الصورة)").font = Font(bold=True)
    row += 1
    recs = {w["id"]: w for w in d["walls"]["records"]}
    for key, lab in (("on_concrete", "على خرسانة المسقط"), ("on_tr", "على عنصر خرسانة tr"),
                     ("lift_front_later", "حائط واجهة المصعد تحت الكمرة — مباني لاحقًا (المالك)")):
        for wid in ex.get(key, []):
            w = recs.get(wid, {})
            s2.cell(row, 1, wid)
            s2.cell(row, 2, lab)
            s2.cell(row, 3, w.get("length_gross"))
            row += 1
    s2.column_dimensions["A"].width = 22
    s2.column_dimensions["B"].width = 40
    s2.column_dimensions["C"].width = 18
    s2.column_dimensions["D"].width = 14
    wb.save(out_xlsx)


def run(n, rerun=False):
    if rerun:
        subprocess.run([sys.executable, str(Path(__file__).parent / "read_plan.py"), str(n), "--no-png", "--no-xlsx"], check=True)
    d = _load(n)
    pre = d["preliminary"]
    rows = _order([dict(r) for r in pre["masonry_walls"]])
    for i, r in enumerate(rows, 1):
        r["no"] = i
    tot = round(sum(r["area_net"] for r in rows), 2)
    ref = pre["masonry"]["ALL|ALL"]["area_net"]
    if abs(tot - ref) > 0.05:
        raise SystemExit(f"F{n:02d}: per-wall total {tot} != floor total {ref}")
    OUT.mkdir(parents=True, exist_ok=True)
    png, xlsx = OUT / f"F{n:02d}_masonry.png", OUT / f"F{n:02d}_masonry.xlsx"
    image(n, d, rows, png)
    workbook(n, d, rows, xlsx)
    (OUT / f"F{n:02d}_masonry_order.json").write_text(
        json.dumps([{"no": r["no"], "id": r["id"], "area_net": r["area_net"]} for r in rows], ensure_ascii=False), encoding="utf-8")
    print(f"F{n:02d}: {len(rows)} walls, net {tot} m2 -> {png.name}, {xlsx.name}")
    return png, xlsx, tot


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("floors", nargs="*", type=int)
    ap.add_argument("--rerun", action="store_true")
    a = ap.parse_args(argv)
    fls = a.floors or [f.floor_no for f in all_floors() if f.floor_no]
    for n in fls:
        run(n, a.rerun)


if __name__ == "__main__":
    main()
