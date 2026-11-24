# Diwan Mall — حصر المباني والمحارة من اللوحات المعمارية

لوحات المساقط الأفقية المعمارية لمشروع **الديوان** (العاصمة الإدارية – حي وسط البلد، قطعة MU2-71)
من **الدور الثاني حتى الدور الثامن**، مع أدوات بايثون لقراءتها بغرض **حصر المباني (الطوب) والمحارة**.

| الملف | المحتوى | المنسوب |
|---|---|---|
| `drawings/Diwan_-_2nd_Floor_19.8.2026.dwg` | الدور الثاني | +8.90 |
| `drawings/3rd_Floor_22.8.2026.dwg` | الدور الثالث | +12.10 |
| `drawings/4th_Floor_26.8.2026.dwg` | الدور الرابع | +15.30 |
| `drawings/5t_to_8th_Floor_Plan.dwg` | الأدوار 5، 6، 7، 8 (أربع لوحات جنبًا إلى جنب في ملف واحد) | +18.50 / +21.70 / +24.90 / +28.10 |

اللوحات في `drawings/` هي **الملفات الأصلية كما أُرسلت تمامًا** (نفس الاسم والمحتوى، بايت ببايت). نسخ DXF مُحوَّلة (ODA) في `dxf/` لقراءتها مباشرة بـ `ezdxf` دون الحاجة لمحوّل.

**ابدأ من هنا:** [`docs/READING_GUIDE.md`](docs/READING_GUIDE.md) — الدليل الكامل لقراءة هذه اللوحات (الطبقات، البلوكات، الدوران والإطار المحلي، ترميز النص العربي، كيف تُقرأ الحوائط والأبواب والغرف والأعمدة، الفروق بين الأدوار، المزالق، وما ينقص من المهندس).

## الأدوات

كل الأدوات تعمل افتراضيًا على **الأدوار السبعة F02..F08** وتكتب في `output/<الموضوع>/` (خارج git). ما تعلمناه عن كل موضوع في `docs/findings/`.

| الأداة | ماذا تقرأ | المخرجات | التوثيق |
|---|---|---|---|
| `tools/read_plan.py` | **القراءة الكاملة**: يشغّل القرّاء الأربعة معًا، يطابقهم ببعض (أبواب/شبابيك/فتحات/خرسانة/بصمة)، يسجّل التعارضات، ويعطي **حصرًا تقديريًا** للمباني والمحارة بارتفاعات افتراضية قابلة للتغيير | `output/plan/F0x.json` + `F0x_plan.png` (صورة مراجعة مجمّعة) + **`summary.xlsx`** (عربي) + `summary.json` | [`READING_GUIDE.md`](docs/READING_GUIDE.md) |
| `tools/walls.py` | الحوائط: محور كل حائط، السُمك وعائلته، الطول الإجمالي والصافي، الفتحات داخله، النوع (خارجي/داخلي/شفت/سلم-مصعد) | `output/walls/` | [`findings/walls.md`](docs/findings/walls.md) |
| `tools/openings.py` | الأبواب `D<w>W<t>` والشبابيك (WIN) والفتحات بلا أبواب ومجموعات باب+زجاج، وخصومات المباني حسب سُمك الحائط | `output/openings/` | [`findings/openings.md`](docs/findings/openings.md) |
| `tools/rooms.py` | الغرف: المضلعات والأسماء والفئات، المساحة الصافية، المحيط مقسّمًا حسب ما يحدّه (أساس المحارة)، الأسقف، المساحة الإجمالية | `output/rooms/` | [`findings/rooms.md`](docs/findings/rooms.md) |
| `tools/structure.py` | الأعمدة وحوائط القص والكور (+ بلوك `tr`)، أوجهها الحرة (داخلي/واجهة/بئر مصعد)، الشفتات، السلالم، المصاعد، المحاور، DASH، أبعاد المعماري | `output/structure/` | [`findings/structure_diff.md`](docs/findings/structure_diff.md) |
| `tools/floor_compare.py` | مقارنة الأدوار طبقةً طبقة: ما المتكرر وما المختلف وأين | `output/floor_compare/` | [`findings/floors_diff.md`](docs/findings/floors_diff.md) |
| `tools/diwan_common.py` | الأساس المشترك: فصل الأدوار من الملفات، اسم الدور ومنسوبه، الإطار المحلي (إزالة دوران 10°)، فك النص العربي | — | docstring |
| `tools/sosa_decode.py` | فك النص العربي المكتوب بخطوط SOSA/xarb (حروف لاتينية بترتيب لوحة المفاتيح) | — | docstring |
| `tools/render_floor.py` | رسم دور خام بالطبقات (للمراجعة البصرية مقابل الأصل) | `output/render_F0x.png` | docstring |
| `tools/dwg_dxf_convert.py` | تحويل DWG ↔ DXF بمحوّل ODA | — | docstring |
| `tools/legacy_wall_takeoff/` | أدوات وملاحظات الحصر اليدوي السابق للدور الثالث (سبتمبر 2026) — مرجع للمقارنة فقط | — | `NOTES_wall_takeoff.md` |

## البدء السريع

المتطلبات: Python 3.12 + `ezdxf shapely matplotlib openpyxl numpy` (والخط Tahoma للصور). على ويندوز فعّل UTF-8 للطباعة العربية:

```bash
# Git Bash
export PYTHONIOENCODING=utf-8
# PowerShell:  $env:PYTHONIOENCODING = "utf-8"

python tools/read_plan.py                      # كل الأدوار: قراءة كاملة + صور + summary.xlsx  (≈ 4 دقائق أول مرة)
python tools/read_plan.py --floor 3            # دور واحد
python tools/read_plan.py --slab 0.22 --door-h 2.20 --window-sill 0.90   # الحصر التقديري بارتفاعات أخرى (ثوانٍ: نتائج القرّاء في الكاش)

python tools/walls.py 3 --zoom 0 25 10 37      # الحوائط مع صورة مكبّرة لمنطقة (إحداثيات محلية بالمتر)
python tools/openings.py 3 5 --no-png          # الأبواب والشبابيك لأدوار محددة
python tools/rooms.py                          # الغرف لكل الأدوار
python tools/structure.py --no-doc             # الخرسانة والشفتات والمحاور (بدون تحديث جداول findings)
python tools/floor_compare.py                  # مقارنة الأدوار
python tools/render_floor.py 3 --texts --zoom 0 25 10 37   # المسقط الخام للمراجعة
```

من بايثون:
```python
import sys; sys.path.insert(0, "tools")
from read_plan import read_floor, merge_floor, Params
plan = merge_floor(read_floor(3), Params(slab=0.20, door_h=2.30))
plan["walls"]["totals"]["0.12|interior"]      # أطوال القواطيع 0.12
plan["openings"]["summary"]["doors"]          # الأبواب بالنوع
plan["rooms"]["by_category"]                  # المساحات حسب الفئة
plan["preliminary"]["masonry"]["ALL|ALL"]     # مباني تقديري
plan["conflicts"]                             # تعارضات تحتاج المهندس
```

> **تنبيه:** الأرقام **قراءة** للمسقط (أطوال، عروض، مساحات). الارتفاعات (سُمك البلاطة، الكمرات، ارتفاع الأبواب، جلسات الشبابيك) **غير موجودة في اللوحات**؛ ما في ورقتي "مباني تقديري" و"محارة تقديري" بافتراضات معلنة حتى يؤكدها المهندس (القائمة في `READING_GUIDE.md` §15 وفي ورقة "الافتراضات والمجاهيل").
