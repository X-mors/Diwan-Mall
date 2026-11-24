export const meta = {
  name: 'diwan-plan-reading',
  description: 'Learn to read the Diwan architectural plans (floors 2-8) for masonry & plaster takeoff: build, adversarially verify and fix one reader tool per aspect, then integrate',
  phases: [
    { title: 'Build', detail: 'one agent per aspect: walls, openings, rooms, structure+floor-diff' },
    { title: 'Verify', detail: 'adversarial verifier per tool (raw-geometry spot checks + visual review)' },
    { title: 'Fix', detail: 'fix verified defects, re-verify (max 2 rounds)' },
    { title: 'Integrate', detail: 'read_plan orchestrator + READING_GUIDE + preliminary quantities' },
    { title: 'Critique', detail: 'completeness critic vs masonry/plaster takeoff readiness' },
  ],
}

const REPO = 'D:\\حصر المباني\\Diwan-Mall'
const CONTEXT = `
PROJECT CONTEXT (read carefully — this is shared by every agent):
- Repo: ${REPO}  (git repo; DO NOT git commit/push — the orchestrator does that). Work in Git Bash or PowerShell; quote paths (they contain Arabic). Run python with env PYTHONIOENCODING=utf-8.
- Python 3.12, ezdxf 1.4.4, shapely 2.1.2, matplotlib 3.11.2, openpyxl 3.1.5, numpy. matplotlib: font Tahoma, pass RAW Arabic strings (NO arabic_reshaper/bidi — it garbles).
- Drawings: drawings/*.dwg (originals) and dxf/*.dxf (ODA-converted, read these). 4 files, 7 floors:
    F02 الدور الثاني +8.90 (Diwan_2nd_Floor_19.8.2026.dxf), F03 الثالث +12.10, F04 الرابع +15.30 (one sheet per file),
    F05 +18.50, F06 +21.70, F07 +24.90, F08 +28.10 = FOUR sheets side by side in Diwan_5th_to_8th_Floor.dxf.
  Storey height = 3.20 m (floor-to-floor, from the level marks). Building = office floors (مكاتب) of "Diwan" mall, New Administrative Capital.
- Shared library tools/diwan_common.py (DO NOT EDIT it, nor sosa_decode.py / render_floor.py; if you need a change, put a helper in your own module and mention it in your result):
    all_floors() -> list[Floor] sorted F02..F08; get_floor(n); floors_in_file(path)
    Floor fields: file, sheet_index, sheet_bbox (world), floor_no, name_ar, level, angle (=10.0 deg), origin, plan_bbox, label ('F03'), doc, msp
    Floor.to_local(x,y) / to_world(lx,ly): LOCAL frame = building rotation (10 deg) removed and translated so the structural columns' min corner is (0,0) -> identical local coordinates on every floor (building ~17 m wide (x) x 43 m long (y) in local frame).
    floor_entities(fl, layers=None|str|tuple, types=None|'LINE LWPOLYLINE') -> model-space entities whose anchor lies on that floor's sheet
    floor_texts(fl, layers=None) -> dicts {layer, style, raw, text (Arabic decoded), arabic, x, y, local, height, handle}
  tools/sosa_decode.py: Arabic text is stored as LATIN keystrokes of the Arabic keyboard rendered by SOSA.shx/xarb.shx (e.g. 'l:jF 5' -> 'مكتب 5', 'plhL' -> 'حمام', 'jvHS slh,D' -> 'تراس سماوي', '>vU' -> 'زرع', 'fi, Hglwu]' -> 'بهو المصعد', '\`,D HgilL' -> 'ذوي الهمم'). decode()/is_arabic_style(doc, style).
  tools/render_floor.py: base_axes(floor_no, layers=[...], zoom=(x0,y0,x1,y1) local, texts=bool) -> (fig, ax, fl) to draw overlays in LOCAL coords; CLI: python tools/render_floor.py 3 --texts --zoom 0 0 10 10 --out output/x.png. Use the Read tool on PNGs to LOOK at them (zoom into regions; the whole plan at low dpi hides detail).
- Units = metres. Sheet = A0 at 1:100. Each floor ~700 LINEs on layer W.
- Layer inventory (per floor; F05-F08 file has 4x): W (col 7: ~700 LINE wall faces, 37 INSERT, ~11 LWPOLYLINE, a few HATCH/ARC on F02), WIN (cyan 4: ~56 LINE + 4 ARC; F02 has 68 LINE + 12 ARC), DIM (~231-241 architect DIMENSIONs, dimstyle WWW), DASH (DASHED ~143 LINE + 6 LWPOLYLINE), PR (col 41: 34 LINE, 6 LWPOLY, 25 INSERT, door-leaf geometry inside blocks), X (axis grid: 25 LINE at exactly 10/100 deg + 30 bubble INSERTs with odd internal offsets), x1 (1 stray axis), TEXT (room names, ARA style), -A-TEXT (English room names: 'IT room','FTR room','DAS/GSM','electric room'), TEXT-D (titles + blank level tags '+ 0.00'), ST (stairs, 50 LINE), MASS (col 130, outline masses), Etabs-col (col 1: 14 LWPOLYLINE + 15 HATCH = structural columns/cores), COL (6 LWPOLYLINE), try (18 LWPOLYLINE + 6 HATCH, X-crossed boxes = shafts/ducts?), FUR (furniture blocks WB=wash basin, P=WC?), HAT, Outer BORDER/LOGO-L1 (title block), Etabs-Slab (block 'tr' 15x39 m slab/column outline from ETABS), PR1, -MASS, sidewalk, 0.
- Blocks: door blocks are named D<width cm>W<wall thickness cm>: D10W12 (=100 cm door in 12 cm wall, ~21-22 per floor), D80W12 (~11), D90W12 (3), D90W25 (1). Inserted on layers W or PR, often mirrored (xscale=-1). Their geometry is on layer PR (5 ARC, 20 LINE, 18 LWPOLY). LP (on W, scale 0.65 / 2.37), WB, P (FUR). Many randomly-named blocks ('rt5hrt6','67yjh6y','t6uyh',...) inserted on W contain an INSERT on CI + a TEXT on TEXT-DIM (tags?); the axis bubbles also have random names ('rhrt','56hr',...).
- Building drawn rotated +10.0 deg; local frame handles it.
- PRIOR KNOWLEDGE (same building, 3rd floor, Sept 2026 — see tools/legacy_wall_takeoff/NOTES_wall_takeoff.md): the user (a quantity surveyor, Arabic speaker) previously measured INTERIOR walls himself as AutoCAD dimensions: 3rd floor 161 wall runs = 291.42 m (x3.00 m), 37 doors = 34.23 m width (x2.30 m, deducted); 4th: 149 walls 825.24 m2, 60 doors+windows 200.20 m2; 5th: 154 walls 835.74 m2 + 19 facade window sills x1.00 m. Pitfalls the user caught before: columns mistaken for walls; facade window-walls counted as interior; axes confused with walls; duplicate parallel lines double-counted; bridging through shafts/columns; rotation. Those runs were face-runs, so they are a loose sanity reference, not ground truth for your method.
- GOAL of the whole effort: be able to READ these plans for حصر المباني (masonry/blockwork: wall length x height by wall thickness, minus openings) and المحارة (plaster: internal wall faces both sides, inner face of external walls, columns/cores faces, ceilings; external plaster on facades). Accuracy matters a lot; the user checks everything against the drawing. Every tool must run on ALL 7 floors (F02..F08) and write outputs under output/<topic>/ (gitignored) — JSON per floor + review PNG(s). Write a findings doc docs/findings/<topic>.md in ARABIC prose (English identifiers/layer names OK) explaining conventions learned, numbers per floor, method, limitations, open questions for the engineer. Keep tools as importable modules with a CLI (argparse; default = all floors) and a clear top docstring.
- Do NOT use the Workflow or Agent tools yourself.
`

const BUILD_RESULT = {
  type: 'object',
  properties: {
    tool_files: { type: 'array', items: { type: 'string' } },
    output_files: { type: 'array', items: { type: 'string' } },
    findings_doc: { type: 'string' },
    per_floor_summary: { type: 'string', description: 'compact table text: floor -> key counts/quantities' },
    conventions_learned: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
    known_limitations: { type: 'array', items: { type: 'string' } },
    api: { type: 'string', description: 'how other code should call the module (function names, return structure)' },
  },
  required: ['tool_files', 'findings_doc', 'per_floor_summary', 'conventions_learned', 'open_questions', 'known_limitations', 'api'],
}

const VERDICT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['pass', 'fix'] },
    defects: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['major', 'minor'] },
          floor: { type: 'string' },
          description: { type: 'string' },
          evidence: { type: 'string', description: 'handles / local coords / numbers proving it' },
          suggested_fix: { type: 'string' },
        },
        required: ['severity', 'description', 'evidence'],
      },
    },
    checks_passed: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'defects', 'checks_passed'],
}

const WPS = [
  {
    key: 'walls',
    prompt: `TASK: build tools/walls.py — the wall reader (masonry basis).
From layer W (LINEs, LWPOLYLINEs; also check the HATCH/ARC on W and what they are) on each floor, reconstruct WALL SEGMENTS: pair parallel faces into walls with a THICKNESS and a centerline, in the LOCAL frame. Discover the real thickness families from the data (expect ~0.12 and ~0.25 m given door blocks D..W12/W25; verify, also 0.20/0.10/0.15 etc.) and report a thickness histogram per floor. Walls are typically measured CONTINUOUS through door/window openings for masonry gross length, but ALSO record the solid (net) pieces — store both: gross runs (bridging gaps that host a door block / window) and net solid pieces. Classify each wall: exterior/facade (on the building perimeter; note many facade bays are glazing on WIN), interior partition, shaft/duct enclosure, around stairs/lifts. EXCLUDE concrete: anything coinciding with structural columns/cores (Etabs-col, COL polygons) — columns sit inside wall lines; split walls at columns so lengths are net of columns, and report column-face info separately is NOT your job (structure agent) but do not count column outlines as walls. Do not double count duplicate/overlapping lines. Handle curved walls (arcs) if any. Output per floor: output/walls/<F>.json {walls:[{id, x1,y1,x2,y2 (local), thickness, length_gross, length_net, kind, needs_check, reason}], totals by thickness x kind} + PNG review (walls coloured by thickness, numbered) — look at it and zoom to check. Cross-check thicknesses/lengths against architect DIMENSIONs on layer DIM (actual_measurement + defpoints) where they dimension walls/rooms, and compare F03 interior total with the legacy 291.42 m (loose). Report differences between floors.`,
  },
  {
    key: 'openings',
    prompt: `TASK: build tools/openings.py — doors, windows and openings reader (deductions for masonry & plaster).
DOORS: every door block (D<w>W<t> family, any other door-like blocks — inspect ALL block definitions inserted on W/PR/FUR/0 and decide what each is: e.g. LP, the random-named blocks containing CI insert + TEXT-DIM text — decode/print their texts, maybe door/window TAGS; the axis bubble blocks are X layer). For each door: local insertion point, rotation, mirror, nominal width from name vs measured width from block geometry/wall gap, host wall thickness, which wall it sits in (gap in W lines), single/double/sliding, swing arc. Also find door-less OPENINGS (gaps in walls with no block) and doors drawn without blocks (raw arcs/lines on PR or W). WINDOWS: layer WIN — group lines into window units (glazing lines in wall thickness, curtain walls along facade, curved glazing arcs at corners), measure each window's width along the wall, note sill info if any (none in plan? say so). Report counts & total widths per floor, by type. Output output/openings/<F>.json + PNG review (doors green with width labels, windows cyan, openings orange) — Read the PNGs, zoom, verify. Cross-check: door count per floor vs legacy (3rd floor 37 doors / 34.23 m width measured by the user) and explain any difference; check door widths against architect DIMs (DIM layer) near the doors. Heights are NOT in plan: state default assumptions (doors 2.20-2.30? windows?) as open questions.`,
  },
  {
    key: 'rooms',
    prompt: `TASK: build tools/rooms.py — spaces/rooms reader (plaster, ceilings, floor areas).
Build closed ROOM polygons per floor from the wall geometry (layer W lines + structural column polygons Etabs-col/COL + WIN glazing lines as the facade boundary + stair/lift/shaft enclosures), closing door gaps (door blocks D..W.. on W/PR give the gap) so each room is a closed polygon. Use shapely (polygonize/unary_union of buffered lines then interior rings, or line noding + polygonize — choose what works robustly; inspect results visually). Assign each room its decoded name from TEXT/-A-TEXT labels (point-in-polygon; labels are sometimes slightly outside - handle nearest), e.g. مكتب 1..19, حمام, ممر, بهو المصعد, تراس سماوي, زرع, ذوي الهمم, IT room, FTR room, DAS/GSM, electric room, stairs (ST), lifts, shafts ('try' X-boxes). For each room: name, category (office/wc/corridor/lobby/stair/lift/shaft/terrace/planter/service), net area m2, perimeter m (inner face), number of door/window gaps on its boundary if easy, and flag rooms with no label or multiple labels. Totals per floor: net area by category, gross floor area (outer facade outline). Output output/rooms/<F>.json + PNG (rooms filled by category with name+area) — Read it, zoom, verify against the drawing. Validate a few rooms' dimensions against architect DIMENSIONs on layer DIM. Note which spaces are open-air (terraces/planters) since they affect internal vs external plaster and ceilings.`,
  },
  {
    key: 'structure_diff',
    prompt: `TASK: build tools/structure.py and tools/floor_compare.py — structure/annotation layers + cross-floor differences.
(1) structure.py: per floor, read structural columns and cores (Etabs-col LWPOLYLINE+HATCH, COL), classify each (rectangular column WxH, shear wall/core), give local position, size, perimeter (plaster on column faces) — and the Etabs-Slab 'tr' block content; stairs (ST), lifts, shafts ('try' boxes); axis grid (X lines; try to read the axis LABELS from the bubble blocks / their TEXT entities — decode if needed) to give a grid reference system (e.g. axis A..,1..) that later takeoff sheets can cite; DASH lines meaning (beams/slab edges above? drop ceilings?), HAT, MASS, -MASS, sidewalk, PR1, FUR, TEXT-D level tags ('+ 0.00' blanks), architect DIMENSIONs (style WWW: what they dimension; extract them with local coordinates; histogram of values; which are wall thicknesses). Output output/structure/<F>.json + PNG.
(2) floor_compare.py: overlay all 7 floors in the LOCAL frame and diff layer by layer (W, WIN, door blocks, Etabs-col, ST, TEXT room names, DIM): identify which floors are identical (typical) and list every difference with local coords and a short description (e.g. F02 has extra curved glazing / different terrace; F05-F08 identical to F04?). Use tolerance matching of segment endpoints (~2 cm). Output docs/findings/floors_diff.md section + output/floor_compare/*.png difference plots (Read them). This tells the takeoff which floors can be computed once and multiplied.`,
  },
]

const RESUME = {
  walls: `RESUME NOTE: a previous build agent for this exact task was INTERRUPTED (usage limit) near the end. Its partial work is on disk: tools/walls.py (~1875 lines, already runs on all 7 floors - outputs in output/walls/*.json + PNGs, output/walls/run_log.txt, summary.json) and docs/findings/walls.md (INCOMPLETE: it still has a <!--TABLES--> placeholder and lacks per-floor numbers, conventions, limitations, open questions). Start by reading tools/walls.py and the doc, re-run the tool, LOOK at the PNGs, then finish and repair what is missing. Do NOT rewrite from scratch unless it is broken. Also available (finished by another agent; you may import or compare with it): tools/openings.py (doors/windows reader, see its docstring/API; docs/findings/openings.md).`,
  rooms: `RESUME NOTE: previous build agents for this exact task were INTERRUPTED twice (usage limit), the last one LATE. Its work is on disk: tools/rooms.py (~1414 lines, already produced output/rooms/F02..F08 .json + PNGs) - but docs/findings/rooms.md was NOT written yet. Start by reading tools/rooms.py, re-run it on all floors, LOOK at the PNGs (zoom), fix what is wrong, and write the findings doc. Do NOT rewrite from scratch unless it is broken. Finished readers you may import: tools/openings.py (doors/windows) and tools/walls.py (walls) - see their docstrings and docs/findings/openings.md, walls.md.`,
  structure_diff: `RESUME NOTE: a previous build agent for this exact task was INTERRUPTED (usage limit) LATE. Its work is on disk: tools/structure.py (~1455 lines), tools/floor_compare.py (~767 lines), docs/findings/structure_diff.md and docs/findings/floors_diff.md, outputs in output/structure/ and output/floor_compare/. Start by reading them, re-run both tools on all floors, LOOK at the PNGs, finish and repair what is missing (check the docs are complete and consistent with the latest outputs). Do NOT rewrite from scratch unless broken. Finished readers you may import: tools/openings.py, tools/walls.py (tools/rooms.py may still be edited by another agent).`,
}
const buildPrompt = (wp) => `${CONTEXT}\n${wp.prompt}\n\nWrite your findings doc at docs/findings/${wp.key}.md. Run your tool on ALL floors before finishing and LOOK at your review PNGs. Return the structured result.` + (RESUME[wp.key] ? `\n\n${RESUME[wp.key]}` : '')

const verifyPrompt = (wp, built, round) => `${CONTEXT}
You are an ADVERSARIAL VERIFIER (round ${round}) of the '${wp.key}' reader built by another agent. Original task given to it:
---
${wp.prompt}
---
Its report: ${JSON.stringify(built).slice(0, 6000)}

Your job: try hard to find where its outputs are WRONG or INCOMPLETE versus the raw DXF. Do not trust its summary. Steps:
1. Re-run its tool on all floors (CLI) — must run cleanly.
2. Independently, with your own small scripts (scratch files under output/_verify_${wp.key}/), sample >= 12 items across at least 3 floors (incl. one of F05-F08) and check each against the raw entities (handles, coordinates, lengths, block names). Also hunt for MISSES: raw entities that should have produced an item but did not (e.g. W line pairs not in any wall, door blocks not reported, unlabelled/unclosed rooms, columns counted as walls, double counting, facade glazing treated as wall, axis lines picked up).
3. Look at the review PNGs with the Read tool, zooming into dense areas (stairs/lift core, bathrooms, facade corners, curved glazing).
4. Check totals for plausibility (e.g. building ~17x43 m, 19 offices; F03 legacy reference) and cross-floor consistency.
Report concrete defects with evidence (handles/local coords/numbers) and a suggested fix. verdict='pass' only if no MAJOR defects remain. Do not edit the tool's code yourself.`

const fixPrompt = (wp, built, verdict) => `${CONTEXT}
You are fixing the '${wp.key}' reader. Original task:
---
${wp.prompt}
---
Previous build report: ${JSON.stringify(built).slice(0, 5000)}
An adversarial verifier found these defects (fix every MAJOR one; fix minors where cheap; if you believe a defect is not real, prove it with evidence in known_limitations):
${JSON.stringify(verdict.defects, null, 1).slice(0, 9000)}
Edit the tool files in place, re-run on ALL floors, LOOK at the PNGs again, update docs/findings/${wp.key}.md, and return the updated structured result (same schema).
NOTE: an earlier fix attempt for these same defects may have been interrupted (usage limit) mid-way, so the tool files may already be partly edited (check 'git diff HEAD~1 -- tools/ docs/' and the current code before changing anything; keep good partial fixes).`

phase('Build')
const results = await pipeline(
  WPS,
  (wp) => agent(buildPrompt(wp), { label: `build:${wp.key}`, phase: 'Build', schema: BUILD_RESULT }),
  async (built, wp) => {
    if (!built) return { wp: wp.key, built: null, verdicts: [] }
    let cur = built
    const verdicts = []
    for (let round = 1; round <= 2; round++) {
      const v = await agent(verifyPrompt(wp, cur, round), { label: `verify:${wp.key}#${round}`, phase: 'Verify', schema: VERDICT })
      if (!v) break
      verdicts.push(v)
      const majors = (v.defects || []).filter(d => d.severity === 'major')
      log(`${wp.key} round ${round}: ${v.verdict}, ${majors.length} major / ${(v.defects || []).length} total defects`)
      if (v.verdict === 'pass' && majors.length === 0) break
      const fixed = await agent(fixPrompt(wp, cur, v), { label: `fix:${wp.key}#${round}`, phase: 'Fix', schema: BUILD_RESULT })
      if (fixed) cur = fixed
    }
    return { wp: wp.key, built: cur, verdicts }
  }
)

phase('Integrate')
const summaries = results.filter(Boolean).map(r => ({
  wp: r.wp,
  report: r.built,
  last_verdict: r.verdicts.length ? r.verdicts[r.verdicts.length - 1] : null,
}))
const integ = await agent(`${CONTEXT}
TASK: INTEGRATE the four readers that were built and verified (walls, openings, rooms, structure+floor_compare). Their final reports and last verifier verdicts:
${JSON.stringify(summaries).slice(0, 30000)}

Do:
1. Build tools/read_plan.py: one CLI that, for all floors (or --floor N), runs walls/openings/rooms/structure readers (import their modules; do not duplicate logic) and writes output/plan/<F>.json (merged) + one combined review PNG per floor (walls by thickness, doors/windows, room names) + output/plan/summary.xlsx (Arabic-only sheet labels & headers, RTL, values not formulas): per floor — wall length by thickness (gross/net, interior/exterior), door count & widths by type, window widths, room areas/perimeters by category, columns count & perimeter. This is a READING summary, not yet the final takeoff: heights are unknown parameters (storey 3.20 m floor-to-floor; slab/beam depth unknown) — expose them as CLI parameters with defaults and compute PRELIMINARY masonry m2 (net length x (storey height - slab thickness param) - openings) and plaster m2 (both faces of interior walls, inner face of exterior walls, column faces, ceilings = room net areas) in a separate sheet clearly titled as preliminary/تقديري with the assumptions listed.
2. Write docs/READING_GUIDE.md in ARABIC: the complete guide to reading these Diwan plans (files & floors & levels, sheet layout, rotation & local frame, Arabic SOSA encoding, every layer's meaning, block naming D<w>W<t>, wall thickness families, how walls/openings/rooms/columns are recognized, floor-to-floor differences / typical floors, pitfalls, how to run each tool, what is still unknown and must come from the engineer: heights, slab thickness, external finish (cladding vs plaster), parapets, etc.). Link docs/findings/*.md.
3. Update README.md (Arabic): add a tools table + quick-start commands; keep the existing drawings table.
4. Run read_plan.py on all floors, Read the combined PNG of F03 and F06 to check, fix integration bugs.
Return: files written, per-floor key numbers table, list of open questions for the engineer, any remaining defects.`, { label: 'integrate', phase: 'Integrate' })

phase('Critique')
const critique = await agent(`${CONTEXT}
You are a COMPLETENESS CRITIC. The team built readers for walls/openings/rooms/structure + read_plan.py + docs/READING_GUIDE.md in ${REPO}. Integration report:
${String(integ).slice(0, 12000)}
Check, against the goal (reliably reading these plans for masonry حصر المباني and plaster محارة takeoff on F02..F08): run python tools/read_plan.py; open output/plan/summary.xlsx with openpyxl; Read 2 combined PNGs. What is missing or wrong? (aspect not covered, floor not handled, number implausible, doc claim unverified, tool crash, Arabic garbled in PNG/Excel, decoding gaps in sosa table). Fix SMALL issues directly (docs typos, crashes, labels); list larger gaps. Return a concise report: fixed items, remaining gaps (with severity), and the final per-floor numbers table.`, { label: 'critic', phase: 'Critique' })

return { results: summaries.map(s => ({ wp: s.wp, report: s.report, last_verdict: s.last_verdict })), integration: integ, critique }
