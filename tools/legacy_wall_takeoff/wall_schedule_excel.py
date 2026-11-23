"""
Build an Arabic/RTL Excel wall schedule from a JSON produced by
wall_schedule_extract.py (the "interior" list: each wall's no/len/thick).

Usage:
    python wall_schedule_excel.py <walls.json> <out.xlsx> --height 3.0 --title "حصر الحوائط الداخلية"
"""
import argparse
import json

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def build(walls_json, out_xlsx, height, title, subtitle):
    with open(walls_json, encoding="utf-8") as f:
        data = json.load(f)
    walls = data["interior"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "حصر الحوائط"
    ws.sheet_view.rightToLeft = True

    FONT = "Arial"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(name=FONT, bold=True, color="FFFFFF", size=11)
    title_font = Font(name=FONT, bold=True, size=14)
    sub_font = Font(name=FONT, italic=True, size=10, color="555555")
    normal_font = Font(name=FONT, size=11)
    total_font = Font(name=FONT, bold=True, size=11)
    total_fill = PatternFill("solid", fgColor="D9E1F2")
    thin = Side(style="thin", color="B7B7B7")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("A1:F1")
    ws["A1"] = title
    ws["A1"].font = title_font
    ws["A1"].alignment = center

    ws.merge_cells("A2:F2")
    ws["A2"] = subtitle
    ws["A2"].font = sub_font
    ws["A2"].alignment = center

    HEADER_ROW = 4
    headers = ["م", "رقم الحائط", "الطول (م.ط)", "السُمك (م)", "الارتفاع (م)", "المساحة (م²)"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=HEADER_ROW, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    first_data_row = HEADER_ROW + 1
    for i, w in enumerate(walls):
        r = first_data_row + i
        ws.cell(row=r, column=1, value=i + 1).alignment = center
        ws.cell(row=r, column=2, value=f"W{w['no']}").alignment = center
        ws.cell(row=r, column=3, value=round(w["len"], 2)).alignment = center
        ws.cell(row=r, column=4, value=round(w["thick"], 2)).alignment = center
        ws.cell(row=r, column=5, value=height).alignment = center
        area_cell = ws.cell(row=r, column=6, value=f"=C{r}*E{r}")
        area_cell.alignment = center
        for c in (3, 4, 5, 6):
            ws.cell(row=r, column=c).number_format = "0.00"
        for c in range(1, 7):
            cell = ws.cell(row=r, column=c)
            cell.font = normal_font
            cell.border = border

    last_data_row = first_data_row + len(walls) - 1
    total_row = last_data_row + 1

    ws.cell(row=total_row, column=1, value=f"=COUNT(A{first_data_row}:A{last_data_row})")
    ws.cell(row=total_row, column=2, value="الإجمالي")
    ws.cell(row=total_row, column=3, value=f"=SUM(C{first_data_row}:C{last_data_row})").number_format = "0.00"
    ws.cell(row=total_row, column=6, value=f"=SUM(F{first_data_row}:F{last_data_row})").number_format = "0.00"
    for c in range(1, 7):
        cell = ws.cell(row=total_row, column=c)
        cell.font = total_font
        cell.fill = total_fill
        cell.border = border
        cell.alignment = center

    note_row = total_row + 2
    notes = [
        "ملاحظات:",
        f"١- الارتفاع مفترض بمقدار {height:.2f} م لكل الحوائط لحساب المساحة (م² = الطول × الارتفاع).",
        "٢- الأطوال مقاسة كخط منتصف الحائط (Centerline)، متضمنة فتحات الأبواب/الشبابيك دون خصم (طول إجمالي وليس صافي).",
        f"٣- الأرقام (W1...W{len(walls)}) تظهر نفس الترقيم على لوحة الأوتوكاد المرفقة.",
        "٤- استخراج آلي من الرسم؛ يُنصح بالمراجعة قبل الاعتماد النهائي.",
    ]
    for i, n in enumerate(notes):
        cell = ws.cell(row=note_row + i, column=1, value=n)
        cell.font = Font(name=FONT, size=9, italic=(i > 0), bold=(i == 0))
        ws.merge_cells(start_row=note_row + i, start_column=1, end_row=note_row + i, end_column=6)

    for i, w in enumerate([6, 12, 14, 12, 14, 14], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{first_data_row}"

    wb.save(out_xlsx)
    print(f"saved {out_xlsx}  ({len(walls)} walls)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("walls_json")
    ap.add_argument("output_xlsx")
    ap.add_argument("--height", type=float, default=3.0)
    ap.add_argument("--title", default="حصر كميات الحوائط الداخلية")
    ap.add_argument("--subtitle", default="(بدون الواجهة الخارجية) - مستخرج آليًا من ملف الأوتوكاد")
    args = ap.parse_args()
    build(args.walls_json, args.output_xlsx, args.height, args.title, args.subtitle)


if __name__ == "__main__":
    main()
