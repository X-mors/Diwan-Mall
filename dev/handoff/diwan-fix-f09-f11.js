export const meta = {
  name: 'diwan-fix-f09-f11',
  description: 'Fix the verified defects of the Diwan readers on floors F09-F11 (one agent per tool file), integrate in read_plan, then re-verify incl. F02-F08 regression',
  phases: [
    { title: 'Fix', detail: 'openings / rooms / walls / structure fixed in parallel (separate files)' },
    { title: 'Integrate', detail: 'read_plan.py fixes + full run + regression vs baseline' },
    { title: 'Verify', detail: 'adversarial re-verification F09-F11 + F02-F08 regression' },
  ],
}
const REPO = 'D:\\حصر المباني\\Diwan-Mall'
const DEFECTS_FILE = REPO + '\\output\\_state\\verify_f09_11.json'
const CTX = `
CONTEXT: Repo ${REPO}. DO NOT git commit/push (the orchestrator does). Run python with PYTHONIOENCODING=utf-8; quote paths (Arabic). Python 3.12, ezdxf, shapely, matplotlib (font Tahoma, raw Arabic, no reshaper), openpyxl.
Readers: tools/walls.py, openings.py, rooms.py, structure.py; integrator tools/read_plan.py (output/plan/F0x.json, F0x_plan.png, summary.xlsx/json). Shared lib tools/diwan_common.py (floors F02..F11, local frame, is_try_outline()). Read docs/READING_GUIDE.md (esp. §5-§9, §11-ب) before changing code.
Floors F09 (+31.30), F10 (+34.50), F11 (+37.70) come from dxf/Diwan_9th_to_11th_Floor.dxf and have a different design (16 offices, glazed facades, planters outside with MASS parapets, try floor outline + plot boundary). An adversarial verifier found defects on F09-F11; the full list with evidence (handles, local coords) and suggested fixes is in ${DEFECTS_FILE} (JSON journal; the 'result' entries hold {verdict, defects[]}).
HARD RULES:
 - Edit ONLY the files assigned to you (other agents edit the other tools at the same time).
 - NO REGRESSION on F02-F08: before editing, run your tool on all floors and save its F02-F08 key numbers; after fixing, re-run and confirm F02-F08 numbers are unchanged (or explain each change as a genuine improvement with evidence). Baseline of the integrated numbers: output/_state/baseline_summary_before_f911_fix.json.
 - Tools must still run on ALL floors (default = all F02..F11). Bump any geometry/cache version key in your file if extraction changes.
 - Update the relevant docs/findings/<topic>.md section for F09-F11 (Arabic prose) describing what changed. Do not edit READING_GUIDE.md (the orchestrator does).
Return a concise report: what you fixed (per defect), what you rejected and why (with evidence), per-floor numbers before/after for F09-F11, and F02-F08 regression result.`

phase('Fix')
const FIXERS = [
  { key: 'openings', files: 'tools/openings.py (+ docs/findings/openings.md)', task: `Fix in openings.py: (1) WIN entities inside a stair zone (F11 stair eyes / break line drawn on WIN) must not become glazing — skip WIN fully inside the buffered hull of each ST-line cluster, report them in checks; (2) WIN double lines 0.03-0.06 m apart (F11 curtain-wall frames) must be merged into one glazing line before pairing; test 'not paired' before 'width>=4' so a lone line is not a curtain wall when a parallel twin exists; dedupe glazing items overlapping >80% with offset <0.10; (3) door blocks D<w>W<t> must be collected from ANY layer (F10 D80W12 handle 44B0 on layer DIM) — then F10 = 31 doors = 28.80 and the false opening F10-O03 disappears; (4) deduction_table / masonry_deduction_widths: deduct only real masonry windows, put unpaired single-line glazing in a separate 'unresolved glazing' bucket; accept corner-return pairs up to 0.40 m when both lines end on the same masonry cap; (5) curved corner glazing width = union of angular sweeps of both radii x r_mid, flag when sweeps differ >10 deg. Also handle the other openings.py minors in the defects file if cheap.` },
  { key: 'rooms', files: 'tools/rooms.py (+ docs/findings/rooms.md)', task: `Fix in rooms.py: (1) WIN lines inside a stair hull (F11 stair eyes on WIN) must be skipped like MASS lines inside stairs (flag them) — F11 stairs should come back to ~14.6 / ~15.8-ish like F09/F10 when the geometry is the same; (2) corridor/lobby split must still work when an extra 'ممر' label lies on the lobby side (F10/F11): retry dropping corridor labels on the lobby side, accept when corridor_like(), flag it; (3) the try floor outline must not cut indoor rooms short of curved glazing — use it only to delimit open-air planters / add it last and drop it wherever W/WIN lies within 0.15 m; prefer glazing within 0.12 m over slab_edge in boundary_breakdown; flag planter faces whose only label is snapped from far; (4) MASS line parallel 0.03-0.16 m to a continuous WIN line over >=80% length = glazing frame on wrong layer -> tag as glazing, not mass (F09 west glazing at office 10 / south stair); (5) do not extend a dangling W stub whose end lies inside a try shaft polygon; create solid_try primitives from try HATCHes with no matching LWPOLYLINE (curtain-wall post at office 7/8 on F09-F11). Plus cheap minors.` },
  { key: 'walls', files: 'tools/walls.py (+ docs/findings/walls.md)', task: `Fix in walls.py: (1) planter parapets on F09-F11 are drawn as MASS line pairs (0.25 on F09; 0.08-0.12 on F10/F11) along planter AR-CONC hatches / outside the try floor outline — add a reader that emits them as records kind='planter_parapet', needs_check=True, with thickness and length, kept OUT of the masonry totals by default but present in a separate totals key 'planter_parapet|ALL' (read_plan will show it); (2) the double record for one wall+door beside SW06 on x=7.00 (F09 W73/W80, F10 W69/W76): treat a one-face break <=0.15 m covered by the other face with nothing abutting as contiguous, and refuse a bridge to concrete when another run already covers it; (3) F11: two D10W12 door gaps missed (stub read only in the crossing direction) — fallback pass for unmatched door blocks so every D..W.. block yields a bridged door gap; (4) planter AR-CONC hatches must not act as concrete jambs in bridge_to_concrete / classify_gap (structural concrete only), keep them for exterior classification. Plus cheap minors.` },
  { key: 'structure', files: 'tools/structure.py (+ docs/findings/structure_diff.md)', task: `Fix in structure.py: (1) element ids must be stable across floors: assign ids from a canonical F06 table by footprint IoU (like harmonize_shaft_ids), new elements (e.g. the F09-F11 column 0.5x1.2 at local 8.96,12.28) get the next free id; key doc tables on those ids; (2) shafts: report try boxes without DASH X as shafts_uncertain (or confirmed if confirmed on other floors via harmonize_shaft_ids) so counts agree with rooms; (3) build boxes also from try HATCHes with no matching LWPOLYLINE (curtain-wall post at office 7/8 on F09-F11); call it post_at_curtain_wall only within ~0.7 m of curtain-wall glazing and inside the footprint, else 'stray hatched try object' (F10 has one outside SW); (4) WIN closed polylines/lines inside a stair box on F11 are the stair eye (read them as eye, not glazing). Plus cheap minors.` },
]
const fixes = await parallel(FIXERS.map(f => () =>
  agent(`${CTX}\n\nYOU OWN: ${f.files}. Defects to fix are those whose 'tool' mentions ${f.key} in ${DEFECTS_FILE}.\n${f.task}`, { label: `fix:${f.key}`, phase: 'Fix' })))

phase('Integrate')
const integ = await agent(`${CTX}

YOU OWN: tools/read_plan.py and the comment in tools/diwan_common.py about is_try_outline (do not change its logic). Four agents just fixed openings.py, rooms.py, walls.py, structure.py. Their reports:
${fixes.map((r, i) => `--- ${FIXERS[i].key} ---\n${String(r).slice(0, 5000)}`).join('\n')}

Do: (1) read_plan merge_floor: append conflicts of type 'cross_check_mismatch' when doors / windows / door-less openings / all gaps differ between walls and openings in count or by >0.05 m width, and when rooms doors_not_two_sided or windows_unassigned is non-zero; (2) plaster_estimate external: count a glazing item as full-height facade glazing only if it lies within ~0.3 m of the exterior of the rooms footprint (drops stair eyes), dedupe parallel glazing lines 0.03-0.06 apart; count unresolved single-line glazing that is on the footprint edge once; (3) add 'try_outline_area' (bulge-aware via ezdxf.path) to cross_checks footprint for F09-F11 and fix the diwan_common comment: the try outline is the FACADE line, planters + their MASS parapets lie outside it; (4) show walls 'planter_parapet' totals (if present) as their own row in the workbook walls sheet and in conflicts ('دروة أحواض الزرع: مباني أم خرسانة؟ الارتفاع؟'), not inside masonry; (5) run python tools/read_plan.py --no-cache --deep on ALL floors (F02..F11), fix crashes, compare F02-F08 numbers against output/_state/baseline_summary_before_f911_fix.json and list every change with its cause; Read output/plan/F11_plan.png and F10_plan.png to check visually. Return the final per-floor table (all 10 floors: walls gross/net, doors n=w, windows n=w, rooms n & net area, masonry~, plaster~, facade~), the regression list, and remaining issues.`, { label: 'integrate:read_plan', phase: 'Integrate' })

phase('Verify')
const VERDICT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['pass', 'fix'] },
    defects: { type: 'array', items: { type: 'object', properties: {
      severity: { type: 'string', enum: ['major', 'minor'] }, floor: { type: 'string' }, tool: { type: 'string' },
      description: { type: 'string' }, evidence: { type: 'string' }, suggested_fix: { type: 'string' } },
      required: ['severity', 'tool', 'description', 'evidence'] } },
    checks_passed: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'defects', 'checks_passed'],
}
const ver = await agent(`${CTX}

You are an ADVERSARIAL RE-VERIFIER (report only, do NOT edit tools/ or docs/; scratch under output/_verify_f09_11_r2/). The defects in ${DEFECTS_FILE} were supposedly fixed. Integration report:
${String(integ).slice(0, 8000)}
Check: (a) every MAJOR defect of the defects file is really fixed on the raw DXF evidence it cites; (b) no new defects on F09-F11 (sample >= 10 items, Read F09/F10/F11 plan PNGs, zoom on stairs, facades/planters, curved glazing, north offices); (c) NO REGRESSION on F02-F08 vs output/_state/baseline_summary_before_f911_fix.json — any changed number must be a justified improvement; (d) all tools run cleanly on all 10 floors. verdict='pass' only if no MAJOR defect remains.`, { label: 'verify:r2', phase: 'Verify', schema: VERDICT })

return { fixes: fixes.map((r, i) => ({ key: FIXERS[i].key, report: r })), integration: integ, verdict: ver }