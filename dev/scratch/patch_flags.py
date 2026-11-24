p = r"D:\حصر المباني\Diwan-Mall\tools\walls.py"
s = open(p, encoding="utf-8").read()
old = '''        reasons = []
        fam = family(thk)
        if fam == "other":
            reasons.append(f"thickness {thk:.3f} m is not a standard family")
        if gross < 0.30:
            reasons.append("very short piece (<0.30 m) - nib/return/fragment?")
        if any(gp["type"] == "opening" for gp in r["openings"]):
            reasons.append("bridged a jamb-capped gap with no door block/window")
        if r.get("mixed"):
            reasons.append("one side is partly outside/void - classification mixed")
        if r["kind"] == "exterior" and any(gp["type"] == "window" for gp in r["openings"]):
            reasons.append("facade line with glazing bays: gross includes windows")
'''
new = '''        reasons, notes = [], []
        fam = family(thk)
        if fam == "other":
            reasons.append(f"thickness {thk:.3f} m is not a standard family (composite pier / nib / drafting?)")
        if gross < 0.10:
            reasons.append("tiny fragment (<0.10 m)")
        elif gross < 0.30:
            notes.append("short piece (<0.30 m): nib / stub / pier return")
        if thk >= 0.35 and r["kind"] != "exterior" and fam != "other":
            reasons.append("thick wall (>=0.35) like the shear walls - concrete or masonry?")
        if any(gp["type"] == "opening" for gp in r["openings"]):
            reasons.append("bridged a jamb-capped gap with no door block/window")
        if r.get("mixed"):
            reasons.append("one side is partly outside/void - classification mixed")
        if r["kind"] == "exterior" and any(gp["type"] == "window" for gp in r["openings"]):
            notes.append("facade line with glazing bays: gross includes the windows")
        if r["ext"][0] > 1e-6 or r["ext"][1] > 1e-6:
            notes.append("L-corner: extended to the centre-line crossing")
'''
assert old in s
s = s.replace(old, new)
old = '''            "needs_check": bool(reasons) and not (len(reasons) == 1 and reasons[0].startswith("facade line")),
            "reason": "; ".join(reasons),'''
new = '''            "needs_check": bool(reasons),
            "reason": "; ".join(reasons),
            "notes": "; ".join(notes),'''
assert old in s
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("ok")
