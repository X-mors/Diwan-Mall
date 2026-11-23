"""
Convert between .dwg and .dxf using the ODA File Converter (installed at
C:\\Program Files\\ODA\\ODAFileConverter *\\ODAFileConverter.exe).

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


def find_oda_exe() -> str:
    matches = glob.glob(ODA_EXE_GLOB)
    if not matches:
        sys.exit("ODA File Converter not found at " + ODA_EXE_GLOB)
    return matches[0]


def convert(input_file: str, output_dir: str, to: str, version: str) -> Path:
    input_file = Path(input_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_type = "DXF" if to == "dxf" else "DWG"
    in_filter = "*.dwg" if input_file.suffix.lower() == ".dwg" else "*.dxf"

    exe = find_oda_exe()
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        shutil.copy(input_file, tmp_in)
        subprocess.run(
            [exe, tmp_in, tmp_out, version, out_type, "0", "1", in_filter],
            check=True,
            timeout=120,
        )
        produced = list(Path(tmp_out).glob(f"*.{out_type.lower()}"))
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
