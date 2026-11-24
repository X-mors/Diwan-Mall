# -*- coding: utf-8 -*-
"""
diwan_common — الأساس المشترك لقراءة لوحات الديوان (Diwan Mall architectural plans).

Facts this module encodes (verified on all 4 files / 7 floors):
  * Units = metres ($INSUNITS=6). Each floor is one A0 sheet (~122 x 84 m model
    space at 1:100). The 2nd/3rd/4th files hold ONE sheet each; the 5th-8th file
    holds FOUR sheets side by side along +X (irregular spacing).
  * The building is drawn ROTATED +10.0 deg (axis grid on layer X is exactly
    10.0 / 100.0 deg). Work in a LOCAL frame: rotate by -10 deg, then translate
    so the structural columns (layer Etabs-col) start at (0,0) -> the same
    local coordinates on every floor => floors can be compared/overlaid.
  * Floor identity comes from the decoded title 'للدور <ordinal>' (layer TEXT-D)
    and the level from the PR-layer text ' +8.90' next to 'منسوب الدور ...'.
  * Arabic text is keyboard-encoded (SOSA.shx/xarb.shx) -> sosa_decode.

Usage:
    from diwan_common import all_floors, floor_entities, floor_texts
    for fl in all_floors():
        print(fl.floor_no, fl.name_ar, fl.level, fl.sheet_bbox)
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import ezdxf
from ezdxf import bbox as ezbbox

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sosa_decode import decode, is_arabic_style  # noqa: E402

for _s in (sys.stdout, sys.stderr):  # Arabic paths/text on a cp1252 Windows console
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO = Path(__file__).resolve().parent.parent
DXF_DIR = REPO / "dxf"
DWG_DIR = REPO / "drawings"
OUT_DIR = REPO / "output"

DXF_FILES = [
    DXF_DIR / "Diwan_2nd_Floor_19.8.2026.dxf",
    DXF_DIR / "Diwan_3rd_Floor_22.8.2026.dxf",
    DXF_DIR / "Diwan_4th_Floor_26.8.2026.dxf",
    DXF_DIR / "Diwan_5th_to_8th_Floor.dxf",
    DXF_DIR / "Diwan_9th_to_11th_Floor.dxf",   # 3 sheets: F09 +31.30, F10 +34.50, F11 +37.70
]

ORDINALS = {
    "الاول": 1, "الأول": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5,
    "السادس": 6, "السابع": 7, "الثامن": 8, "التاسع": 9, "العاشر": 10,
    "الحادي عشر": 11, "الثاني عشر": 12, "الثالث عشر": 13,
}
STOREY_HEIGHT = 3.20  # m, from the level marks (+8.90, +12.10, ... +28.10)

# ---- layer semantics (see docs/READING_GUIDE.md) ----
LAYER_WALL = "W"
LAYER_WINDOW = "WIN"
LAYER_AXIS = ("X", "x1")
LAYER_COLUMNS = ("Etabs-col", "COL")


# --------------------------------------------------------------------------
@lru_cache(maxsize=8)
def open_doc(path: str | Path):
    return ezdxf.readfile(str(path))


def entity_bbox(e):
    try:
        b = ezbbox.extents([e], fast=True)
        if b.has_data:
            return (b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y)
    except Exception:
        pass
    return None


def sheet_clusters(msp, gap: float = 2.0):
    """Cluster model-space entities by X-extent -> one cluster per drawing sheet."""
    iv = []
    for e in msp:
        b = entity_bbox(e)
        if b:
            iv.append(b)
    iv.sort()
    cl = []
    for x0, y0, x1, y1 in iv:
        if cl and x0 <= cl[-1][2] + gap:
            c = cl[-1]
            cl[-1] = (c[0], min(c[1], y0), max(c[2], x1), max(c[3], y1), c[4] + 1)
        else:
            cl.append((x0, y0, x1, y1, 1))
    # drop tiny clusters (stray entities)
    return [c[:4] for c in cl if c[4] > 50]


def detect_angle(msp, bbox=None) -> float:
    """Building rotation in degrees from the axis grid (layer X), fallback W-line mode."""
    from collections import Counter
    cnt = Counter()
    for lay in ("X", "W"):
        for e in msp.query(f'LINE[layer=="{lay}"]'):
            s, t = e.dxf.start, e.dxf.end
            if bbox and not _inside(((s.x + t.x) / 2, (s.y + t.y) / 2), bbox):
                continue
            L = math.hypot(t.x - s.x, t.y - s.y)
            if L < 0.5:
                continue
            a = math.degrees(math.atan2(t.y - s.y, t.x - s.x)) % 90.0
            cnt[round(a, 1)] += L
        if cnt:
            break
    if not cnt:
        return 10.0
    return cnt.most_common(1)[0][0]


def _inside(pt, bb, pad=0.0):
    return bb[0] - pad <= pt[0] <= bb[2] + pad and bb[1] - pad <= pt[1] <= bb[3] + pad


def rot(pt, ang_deg):
    a = math.radians(ang_deg)
    c, s = math.cos(a), math.sin(a)
    return (pt[0] * c - pt[1] * s, pt[0] * s + pt[1] * c)


# --------------------------------------------------------------------------
@dataclass
class Floor:
    file: Path
    sheet_index: int          # 0..n-1 inside the file (left -> right)
    sheet_bbox: tuple         # world (x0,y0,x1,y1) of the whole A0 sheet
    floor_no: int | None = None
    name_ar: str = ""
    level: float | None = None
    angle: float = 10.0       # building rotation (deg)
    origin: tuple = (0.0, 0.0)  # local-frame translation (columns min corner)
    plan_bbox: tuple | None = None  # world bbox of the building (columns/windows/stairs)
    notes: list = field(default_factory=list)

    @property
    def doc(self):
        return open_doc(str(self.file))

    @property
    def msp(self):
        return self.doc.modelspace()

    @property
    def label(self):
        return f"F{self.floor_no:02d}" if self.floor_no else f"S{self.sheet_index}"

    # world <-> local (floor-independent, axis-aligned) frame
    def to_local(self, x, y=None):
        if y is None:
            x, y = x[0], x[1]
        lx, ly = rot((x, y), -self.angle)
        return (lx - self.origin[0], ly - self.origin[1])

    def to_world(self, lx, ly=None):
        if ly is None:
            lx, ly = lx[0], lx[1]
        return rot((lx + self.origin[0], ly + self.origin[1]), self.angle)

    def contains(self, x, y, pad=0.0):
        return _inside((x, y), self.sheet_bbox, pad)


def _entity_anchor(e):
    t = e.dxftype()
    try:
        if t == "LINE":
            s, u = e.dxf.start, e.dxf.end
            return ((s.x + u.x) / 2, (s.y + u.y) / 2)
        if t in ("TEXT", "MTEXT", "INSERT"):
            p = e.dxf.insert
            return (p.x, p.y)
        if t in ("ARC", "CIRCLE"):
            p = e.dxf.center
            return (p.x, p.y)
    except Exception:
        pass
    b = entity_bbox(e)
    if b:
        return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    return None


def floor_entities(fl: Floor, layers=None, types=None):
    """Model-space entities whose anchor lies on this floor's sheet."""
    q = types if isinstance(types, str) else (" ".join(types) if types else "*")
    for e in fl.msp.query(q):
        if layers is not None:
            lay = e.dxf.layer
            if (isinstance(layers, str) and lay != layers) or (not isinstance(layers, str) and lay not in layers):
                continue
        a = _entity_anchor(e)
        if a and fl.contains(*a, pad=0.5):
            yield e


def text_value(e) -> str:
    return e.dxf.text if e.dxftype() == "TEXT" else e.plain_text()


def floor_texts(fl: Floor, layers=None):
    """All TEXT/MTEXT on the floor with Arabic decoded. Returns list of dicts."""
    doc = fl.doc
    out = []
    for e in floor_entities(fl, layers=layers, types="TEXT MTEXT"):
        raw = text_value(e)
        style = e.dxf.get("style", "Standard")
        arabic = is_arabic_style(doc, style)
        p = e.dxf.insert
        out.append({
            "layer": e.dxf.layer, "style": style, "raw": raw,
            "text": decode(raw).strip() if arabic else raw.strip(),
            "arabic": arabic, "x": p.x, "y": p.y,
            "local": fl.to_local(p.x, p.y),
            "height": e.dxf.get("height", 0.0) if e.dxftype() == "TEXT" else e.dxf.get("char_height", 0.0),
            "handle": e.dxf.handle,
        })
    return out


_LEVEL_RE = re.compile(r"^\s*([+-])\s*(\d+\.\d+)\s*$")


def _identify(fl: Floor):
    msp = fl.msp
    fl.angle = detect_angle(msp, fl.sheet_bbox)
    # floor name + level
    texts = floor_texts(fl)
    def _norm(w):
        return w.replace("أ", "ا").replace("ا", "")

    for t in texts:
        m = re.search(r"للدور\s+(\S+)(?:\s+(\S+))?", t["text"])
        if m and fl.floor_no is None:
            one = m.group(1)
            two = f"{one} {m.group(2)}" if m.group(2) else None
            # two-word ordinals first ('الحادي عشر' = 11), then one word
            for cand in ([two] if two else []) + [one]:
                for k, v in ORDINALS.items():
                    if _norm(cand) == _norm(k):
                        fl.floor_no, fl.name_ar = v, "الدور " + k
                        break
                if fl.floor_no is not None:
                    break
    lv = [t for t in texts if t["layer"] == "PR" and _LEVEL_RE.match(t["raw"])]
    if lv:
        m = _LEVEL_RE.match(lv[0]["raw"])
        fl.level = float(m.group(2)) * (1 if m.group(1) == "+" else -1)
    # local origin from structural columns (identical on every floor)
    pts = []
    for e in floor_entities(fl, layers="Etabs-col", types="LWPOLYLINE"):
        vs = [rot((p[0], p[1]), -fl.angle) for p in e.get_points("xy")]
        pts.extend(vs)
    if pts:
        fl.origin = (min(p[0] for p in pts), min(p[1] for p in pts))
    else:
        fl.notes.append("no Etabs-col columns found; local origin = sheet corner")
        fl.origin = rot((fl.sheet_bbox[0], fl.sheet_bbox[1]), -fl.angle)
    # building bbox (world) from columns/windows/stairs
    bbs = [entity_bbox(e) for e in floor_entities(fl, layers=("Etabs-col", "COL", "WIN", "ST"))]
    bbs = [b for b in bbs if b]
    if bbs:
        fl.plan_bbox = (min(b[0] for b in bbs), min(b[1] for b in bbs),
                        max(b[2] for b in bbs), max(b[3] for b in bbs))


@lru_cache(maxsize=8)
def floors_in_file(path: str | Path):
    path = Path(path)
    msp = open_doc(str(path)).modelspace()
    fls = []
    for i, bb in enumerate(sheet_clusters(msp)):
        fl = Floor(file=path, sheet_index=i, sheet_bbox=bb)
        _identify(fl)
        fls.append(fl)
    return tuple(fls)


def all_floors():
    fls = []
    for p in DXF_FILES:
        fls.extend(floors_in_file(str(p)))
    return sorted(fls, key=lambda f: (f.floor_no or 99, str(f.file), f.sheet_index))


def get_floor(floor_no: int) -> Floor:
    for f in all_floors():
        if f.floor_no == floor_no:
            return f
    raise KeyError(floor_no)


if __name__ == "__main__":
    for f in all_floors():
        print(f"{f.label}  {f.name_ar:14} level={f.level}  file={f.file.name} sheet={f.sheet_index} "
              f"angle={f.angle} origin=({f.origin[0]:.3f},{f.origin[1]:.3f}) "
              f"sheet=({f.sheet_bbox[0]:.1f},{f.sheet_bbox[1]:.1f})-({f.sheet_bbox[2]:.1f},{f.sheet_bbox[3]:.1f}) "
              f"plan={tuple(round(v, 1) for v in f.plan_bbox) if f.plan_bbox else None} {f.notes}")
