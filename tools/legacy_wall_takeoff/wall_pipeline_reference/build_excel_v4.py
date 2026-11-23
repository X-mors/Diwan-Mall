import json
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

with open(r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\interior_walls_v4_final.json") as f:
    walls = json.load(f)

OUT = r"C:\Users\hp\AppData\Local\Temp\claude\D-------------\08d10124-4af8-4a54-9322-07ffbccda861\scratchpad\حصر_الحوائط_الداخلية_v2.xlsx"

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
check_font = Font(name=FONT, size=11, color="9C5700")
check_fill = PatternFill("solid", fgColor="FFEB9C")
total_font = Font(name=FONT, bold=True, size=11)
total_fill = PatternFill("solid", fgColor="D9E1F2")
thin = Side(style="thin", color="B7B7B7")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center")

ws.merge_cells("A1:G1")
ws["A1"] = "حصر كميات الحوائط الداخلية - الدور الثالث"
ws["A1"].font = title_font
ws["A1"].alignment = center

ws.merge_cells("A2:G2")
ws["A2"] = "(بدون الواجهة الخارجية) - مستخرج آليًا من ملف الأوتوكاد بتاريخ 22.8.2026 - نسخة مُراجَعة"
ws["A2"].font = sub_font
ws["A2"].alignment = center

HEADER_ROW = 4
headers = ["م", "رقم الحائط", "الطول (م.ط)", "السُمك (م)", "الارتفاع (م)", "المساحة (م²)", "ملاحظة"]
for c, h in enumerate(headers, start=1):
    cell = ws.cell(row=HEADER_ROW, column=c, value=h)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = center
    cell.border = border

first_data_row = HEADER_ROW + 1
for i, w in enumerate(walls):
    r = first_data_row + i
    flagged = w["needs_check"]
    f_font = check_font if flagged else normal_font
    f_fill = check_fill if flagged else None

    ws.cell(row=r, column=1, value=i + 1).alignment = center
    label = f"W{w['no']}"
    ws.cell(row=r, column=2, value=label).alignment = center
    ws.cell(row=r, column=3, value=round(w["len"], 2)).alignment = center
    ws.cell(row=r, column=4, value=round(w["thick"], 2)).alignment = center
    ws.cell(row=r, column=5, value=3.00).alignment = center
    area_cell = ws.cell(row=r, column=6, value=f"=C{r}*E{r}")
    area_cell.alignment = center
    note = "يُنصح بالمراجعة الميدانية - وجه واحد فقط ظاهر بالرسم، السُمك تقديري (12 سم)" if flagged else ""
    ws.cell(row=r, column=7, value=note).alignment = Alignment(horizontal="right", vertical="center", wrap_text=True)

    for c in (3, 4, 5, 6):
        ws.cell(row=r, column=c).number_format = "0.00"
    for c in range(1, 8):
        cell = ws.cell(row=r, column=c)
        cell.font = f_font
        cell.border = border
        if f_fill:
            cell.fill = f_fill

last_data_row = first_data_row + len(walls) - 1
total_row = last_data_row + 1

ws.cell(row=total_row, column=1, value=f"=COUNT(A{first_data_row}:A{last_data_row})")
ws.cell(row=total_row, column=2, value="الإجمالي")
ws.cell(row=total_row, column=3, value=f"=SUM(C{first_data_row}:C{last_data_row})").number_format = "0.00"
ws.cell(row=total_row, column=6, value=f"=SUM(F{first_data_row}:F{last_data_row})").number_format = "0.00"
for c in range(1, 8):
    cell = ws.cell(row=total_row, column=c)
    cell.font = total_font
    cell.fill = total_fill
    cell.border = border
    cell.alignment = center

n_flagged = sum(1 for w in walls if w["needs_check"])
note_row = total_row + 2
notes = [
    "ملاحظات هامة:",
    "١- الارتفاع مفترض بمقدار 3.00 م لكل الحوائط لحساب المساحة (م² = الطول × الارتفاع).",
    "٢- الأطوال مقاسة كخط منتصف الحائط (Centerline)، متضمنة فتحات الأبواب/الشبابيك دون خصم (طول إجمالي وليس صافي).",
    "٣- تم استبعاد حوائط الواجهة الخارجية، وتم استبعاد الأعمدة الخرسانية بمطابقتها مع طبقة الأعمدة (COL/Etabs-col) بالرسم.",
    f"٤- الصفوف المظلَّلة (باللون الأصفر) وعددها {n_flagged} حائطًا: تم رصد هذه الحوائط من وجه واحد فقط بالرسم (الوجه المقابل غير واضح أو غير مطابق لحائط آخر قريب)، فتم افتراض سُمك قياسي (12 سم) لحساب مساحتها - يُنصح بمراجعتها على الطبيعة/اللوحة قبل الاعتماد.",
    "٥- الأرقام (W1..." + f"W{len(walls)}" + ") تظهر بنفس الترقيم على لوحة الأوتوكاد المرفقة (باللون الوردي = مؤكد، والبرتقالي مع علامة ? = يحتاج مراجعة).",
    "٦- استخراج آلي من هندسة الرسم؛ برجاء المراجعة النهائية قبل الاعتماد في التسعير أو التنفيذ.",
]
for i, n in enumerate(notes):
    cell = ws.cell(row=note_row + i, column=1, value=n)
    cell.font = Font(name=FONT, size=9, italic=(i > 0), bold=(i == 0))
    ws.merge_cells(start_row=note_row + i, start_column=1, end_row=note_row + i, end_column=7)

widths = [6, 12, 14, 12, 14, 14, 45]
for i, w in enumerate(widths, start=1):
    ws.column_dimensions[get_column_letter(i)].width = w
ws.freeze_panes = f"A{first_data_row}"

wb.save(OUT)
print("saved:", OUT, " rows:", len(walls), " flagged:", n_flagged)
