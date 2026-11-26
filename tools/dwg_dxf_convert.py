"""
Convert between .dwg and .dxf using the ODA File Converter.
  Windows: C:\\Program Files\\ODA\\ODAFileConverter *\\ODAFileConverter.exe
  Linux (cloud sessions): /usr/bin/ODAFileConverter from the official .deb
    (opendesign.com/guestfiles/oda_file_converter -> ODAFileConverter_QT6_lnxX64_*dll.deb;
     needs libopengl0 libxkbcommon-x11-0 libxcb-* and xvfb; it runs under `xvfb-run -a`).

Usage:
    python dwg_dxf_convert.py <input_file> <output_dir> [--to dxf|dwg] [--version ACAD2018]

The ODA converter only works folder-to-folder, so this script copies the
single input file into a temp folder, runs the converter, and copies the
result out to <output_dir>.
"""
import argparse
import glob
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ODA_EXE_GLOB = r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe"
ODA_LINUX = "/usr/bin/ODAFileConverter"


def find_oda_exe() -> list:
    """Command prefix that runs the converter (Linux: headless under xvfb-run)."""
    if sys.platform.startswith("win"):
        matches = glob.glob(ODA_EXE_GLOB)
        if not matches:
            sys.exit("ODA File Converter not found at " + ODA_EXE_GLOB)
        return [matches[0]]
    exe = shutil.which("ODAFileConverter") or (ODA_LINUX if Path(ODA_LINUX).exists() else None)
    if not exe:
        sys.exit("ODA File Converter not found (install the Linux .deb, see the docstring)")
    xvfb = shutil.which("xvfb-run")
    return ([xvfb, "-a"] if xvfb else []) + [exe]


def convert(input_file: str, output_dir: str, to: str, version: str) -> Path:
    input_file = Path(input_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_type = "DXF" if to == "dxf" else "DWG"
    in_filter = "*.DWG" if input_file.suffix.lower() == ".dwg" else "*.DXF"

    exe = find_oda_exe()
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        shutil.copy(input_file, tmp_in)
        subprocess.run(
            exe + [tmp_in, tmp_out, version, out_type, "0", "1", in_filter],
            check=True,
            timeout=600,
        )
        produced = [p for p in Path(tmp_out).iterdir() if p.suffix.lower() == "." + out_type.lower()]
        if not produced:
            sys.exit("Conversion failed: no output file produced")
        result = output_dir / produced[0].name
        shutil.copy(produced[0], result)
        return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_file")
    ap.add_argument("output_dir")
    ap.add_argument("--to", choices=["dxf", "dwg"], required=True)
    ap.add_argument("--version", default="ACAD2018")
    args = ap.parse_args()

    result = convert(args.input_file, args.output_dir, args.to, args.version)
    print("saved:", result)


if __name__ == "__main__":
    main()
