# حالة شغل الأدوار 9/10/11 (يُحدَّث بعد كل خطوة)
> الملف المعتمد: drawings/9th__10th__11th_-1.dwg (الملف الأول 9th__10th__11th_.dwg أُلغي بطلب المستخدم وحُذف هو ومخرجاته)
- [x] 1. نسخ اللوحة الأصلية إلى drawings/9th__10th__11th_-1.dwg (بايت ببايت)
- [x] 2. تحويل DXF (dxf/Diwan_9th_to_11th_Floor.dxf) + diwan_common: F09 +31.30 / F10 +34.50 / F11 +37.70، 'الحادي عشر' مدعوم، الأعمدة متطابقة مع F08 (+2: SW06 polyline، عمود 0.5×1.2 عند 8.96,12.28) — 16 مكتب + أحواض زرع
- [x] 4. إصلاح: حدود الدور وحدود الأرض على طبقة try في F09-F11 كانت تُقرأ شفتات (السلالم والمصعد صُنّفت شفت) — diwan_common.is_try_outline + walls/rooms/structure/openings؛ rooms يعتبر حدود الدور slab_edge
- [x] 5. read_plan على الأدوار العشرة (summary.xlsx شامل F02-F11) — السلالم/المصعد صحيحة الآن؛ F10 مكتب 2+3 بلا قاطوع (حقيقي في الرسم)
- [x] 6. تحديث READING_GUIDE (§1، §11-ب جديد، §12، §14، §15) و README
- [x] 7. structure.py + floor_compare.py على الأدوار العشرة (findings محدثة) — مرفوع. التالي: تحقق عدائي من F09-F11 (workflow صغير)
- [ ] 8. تحقق عدائي F09-F11: workflow wf_da1f4b8f-0ce (task w9qsa1dhi) شغال — لو اتقطع: Workflow({scriptPath: 'C:/Users/hp/.claude/projects/D-------------/d3b44a19-989c-4f10-9b51-d237f635d5e6/workflows/scripts/diwan-verify-f09-f11-wf_da1f4b8f-0ce.js', resumeFromRunId: 'wf_da1f4b8f-0ce'}) ثم أصلح العيوب الكبيرة، أعد read_plan، ارفع، بلّغ المستخدم
- [x] 8. التحقق العدائي خلص: 7 عيوب كبيرة (openings: عين السلم على WIN في F11، خطوط زجاج مزدوجة 4 سم، باب على طبقة DIM في F10؛ walls: دروات أحواض الزرع MASS؛ rooms: عين السلم، ممر/بهو F10-F11؛ read_plan: واجهة F11) + صغرى — التفاصيل output/_state/verify_f09_11.json؛ baseline: output/_state/baseline_summary_before_f911_fix.json
- [ ] 9. workflow إصلاح wf_3a34bf5e-c0f (task wpf03xd7f) شغال — لو اتقطع بالحد: Workflow({scriptPath: "C:/Users/hp/.claude/projects/D-------------/d3b44a19-989c-4f10-9b51-d237f635d5e6/workflows/scripts/diwan-fix-f09-f11-wf_3a34bf5e-c0f.js", resumeFromRunId: "wf_3a34bf5e-c0f"}) (الملفات الجزئية على القرص؛ ممكن تضيف ملاحظة RESUME للبرومبت). بعده: commit+push، تحديث READING_GUIDE §11-ب (حدود try = خط الواجهة والزرع خارجه، دروات MASS، ممر إضافي F10/F11، أرقام §14)، ثم بلاغ المستخدم ثم سطر DONE
  - 2026-11-24 20:50 المحاولة الأولى للإصلاح اتقطعت بالحد قبل أي تعديل (git نظيف) — أُعيد التشغيل (task w1xnwd4oi، نفس run wf_3a34bf5e-c0f)
- [x] 9a. إصلاح openings + rooms خلص ومرفوع. walls/structure/read_plan/verify اتقطعوا بالحد الأسبوعي — أُعيد التشغيل بـ resume
- [ ] 10. الشغل اتوقف على الجهاز واتنقل لجلسة سحابية — شوف HANDOFF.md
