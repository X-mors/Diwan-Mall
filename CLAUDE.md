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

## Tools (all default to every floor)
| question | run | read |
|---|---|---|
| quantities, conflicts, Excel | `python tools/read_plan.py` | `output/plan/summary.xlsx`, `output/plan/Fnn.json` |
| masonry height of each wall | `python tools/masonry_heights.py 6` | `Fnn.json` → `walls.records[].masonry_height`, `preliminary.masonry_heights` |
| slab zones / beams / columns of the structural sheets | `python tools/str_slabs.py --json` | `output/structure_str/slabs.json` |
| overlay structural on architectural / floors on each other | `python tools/str_arch_compare.py 6`, `--arch 9 8`, `--str 8 9` | `output/compare/*.png/json` |
| walls, openings, rooms, concrete separately | `tools/walls.py`, `openings.py`, `rooms.py`, `structure.py` | `output/<topic>/` |
| layer-by-layer floor differences | `tools/floor_compare.py` | `output/floor_compare/` |
| DWG ↔ DXF | `tools/dwg_dxf_convert.py` (Linux: ODA .deb + xvfb-run, see docstring) | — |

Python deps: `ezdxf shapely matplotlib openpyxl numpy scipy`. On Windows set `PYTHONIOENCODING=utf-8`.
