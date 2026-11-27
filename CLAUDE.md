# CLAUDE.md — Diwan Mall takeoff (حصر المباني والمحارة)

Answer the owner's questions **from this repo**: the tools in `tools/` and their saved outputs in `output/`.
Start with `README.md` (tool table, quick start) and `docs/READING_GUIDE.md` (how the drawings are read,
pitfalls, open questions). Findings per topic are in `docs/findings/`.

## Rules from the owner
- **Original drawings in `drawings/` are never modified** (byte-identical). Converted DXF goes in `dxf/`.
- **Everything is committed and pushed to `main`** (no feature branches unless the owner asks).
- **Commit the generated outputs** (`output/**`) so nothing has to be rebuilt; only `output/**/_cache/` is ignored.
- Work through all tasks without stopping; collect questions for the owner at the end of the report. Reply in Arabic.

## Facts that are easy to get wrong
- Architectural floors F02..F11, finish levels +8.90 .. +37.70, storey **3.20** (finish to finish, finish 10 cm).
- Plans are rotated 10°. All tools work in the LOCAL frame (`diwan_common`): rotation removed,
  origin = min corner of Etabs-col, metres. Arabic text is SOSA-encoded (`sosa_decode`).
- Structural drawing `drawings/Dewan STR-UPDATED-REV01.dwg` (reader `tools/str_slabs.py`):
  - sheet names after the 7th are shifted: "السابع متكرر" = 8th, "الثامن" = 9th, "التاسع" = 10th, "العاشر" = 11th;
  - "سقف الدور X" is the slab **above** floor X — floor N's walls are measured under the sheet "سقف الدور N";
  - slab top is one level per floor; thickness 20 (general) / 35 (zones) varies downward only; beams `ك n (b*h)` in cm;
  - executed: clear 3.00 m under a 20 cm slab ⇒ storey 3.20 is right, the structural +3.30 level marks are **wrong**.
- **Masonry height = 3.20 − concrete depth above the wall**: 0.20 → 3.00, 0.35 → 2.85, beam 70 → 2.50, beam 90 → 2.30.
  `read_plan.py` uses this by default (`--heights structural`); `--heights flat --slab ..` for a fixed height.

## Owner answers (binding, applied in the tools) — log in `docs/owner_answers.md`
- Unlabelled slab band = 20 cm; walls on a 20/35 edge are under 20.
- Shear walls were built 0.30 as in the structural (not 0.40); the Z between SW04/SW02 is a concrete core.
- ETABS `tr`-block elements are real concrete (walls on them are not masonry); columns that exist only in the
  structural exist on site. `read_plan.py` therefore excludes walls on tr elements and deducts wall lengths inside
  structural columns/cores (`Params.tr_concrete`, `Params.str_concrete`).
- 2026-11-27: door 2.30, masonry door opening = drawn width + 5 cm; service windows 80x60, masonry opening +5 cm;
  facades = plaster + paint, no masonry/parapet under curtain walls; planters, planter parapets, F02 terraces and the
  decorative slab projections are OUT of the takeoff; partitions differing between floors are intentional.
  Internal plaster per room = clear height under the slab − 10 cm (offices/shops/rooms/stairs) or − 50 cm (corridor +
  lift lobby: suspended ceiling); bathrooms have NO internal plaster; corridor/wc ceilings not plastered.
  Lift core: the front wall under beam 25x90 is masonry LATER (out now); the long leg of the C core is MASONRY (`lift_core_rules`).
- The owner speaks in ACTUAL floor numbers (8, 9, 10, 11): never use the structural sheet names in replies.
- When asking the owner a question, attach a screenshot of the drawing (`tools/snap.py`, images in `output/questions/`).

## Tools (all default to every floor)
| question | run | read |
|---|---|---|
| quantities, conflicts, Excel | `python tools/read_plan.py` | `output/plan/summary.xlsx`, `output/plan/Fnn.json` |
| masonry height of each wall | `python tools/masonry_heights.py 6` | `Fnn.json` → `walls.records[].masonry_height`, `preliminary.masonry_heights` |
| slab zones / beams / columns of the structural sheets | `python tools/str_slabs.py --json` | `output/structure_str/slabs.json` |
| overlay structural on architectural / floors on each other | `python tools/str_arch_compare.py 6`, `--arch 9 8`, `--str 8 9` | `output/compare/*.png/json` |
| walls, openings, rooms, concrete separately | `tools/walls.py`, `openings.py`, `rooms.py`, `structure.py` | `output/<topic>/` |
| drawing screenshots (arch + structural side by side) | `python tools/snap.py both 6 x0 y0 x1 y1 out.png` | — |
| floor on the slab under it / planters vs slab | `python tools/slab_boards.py`, `python tools/planter_sections.py 8 9 10 11` (plan + sections AA north, BB west, CC south) | `output/compare/slab_board_Fnn.png`, `plan_Fnn_slab_planters.png`, `section_Fnn_AA/BB/CC.png` |
| one floor as separate CAD files (arch + structural slab under / above) | `python tools/extract_floor_cad.py 9` | `output/cad_extract/floor_NN_*.dwg` |
| layer-by-layer floor differences | `tools/floor_compare.py` | `output/floor_compare/` |
| DWG ↔ DXF | `tools/dwg_dxf_convert.py` (Linux: ODA .deb + xvfb-run, see docstring) | — |

Python deps: `ezdxf shapely matplotlib openpyxl numpy scipy`. On Windows set `PYTHONIOENCODING=utf-8`.
