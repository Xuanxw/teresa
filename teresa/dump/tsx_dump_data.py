#!/usr/bin/env python3

import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def _resolve_gdal_translate() -> str:
    env_bin = os.getenv("DORIS_GDAL_BIN")
    if env_bin:
        candidate = Path(env_bin) / "gdal_translate"
        if candidate.exists():
            return str(candidate)

    found = shutil.which("gdal_translate")
    if found:
        return found

    raise FileNotFoundError("Cannot find gdal_translate. Set DORIS_GDAL_BIN or add gdal_translate to PATH.")


def _parse_original_size(res_file: Path) -> Tuple[int, int]:
    text = res_file.read_text(encoding="utf-8", errors="ignore")
    line_match = re.search(r"Number_of_lines_original:\s*(\d+)", text)
    pixel_match = re.search(r"Number_of_pixels_original:\s*(\d+)", text)
    if not line_match or not pixel_match:
        raise ValueError(f"Cannot parse original TSX dimensions from {res_file}")
    return int(line_match.group(1)), int(pixel_match.group(1))


def _replace_crop_flag(res_file: Path) -> None:
    text = res_file.read_text(encoding="utf-8", errors="ignore")
    text = text.replace("crop:\t\t0", "crop:\t\t1")
    text = text.replace("crop:\t\t\t0", "crop:\t\t\t1")
    res_file.write_text(text, encoding="utf-8")


def tsx_to_data(
    filein: str,
    fileout: str,
    res_file: str,
    l0: Optional[int] = None,
    lN: Optional[int] = None,
    p0: Optional[int] = None,
    pN: Optional[int] = None,
) -> Tuple[int, int, int, int]:
    """Convert TSX COSAR data to Doris complex_short raw data."""
    input_file = Path(filein)
    output_file = Path(fileout)
    res_path = Path(res_file)

    if not input_file.exists():
        raise FileNotFoundError(f"File {input_file} not found!")
    if not res_path.exists():
        raise FileNotFoundError(f"Result file {res_path} not found!")

    nlines, npixels = _parse_original_size(res_path)
    l0 = 1 if l0 is None else int(l0)
    lN = nlines if lN is None else int(lN)
    p0 = 1 if p0 is None else int(p0)
    pN = npixels if pN is None else int(pN)

    if l0 < 1 or p0 < 1 or lN < l0 or pN < p0:
        raise ValueError(f"Invalid TSX crop window: l0={l0}, lN={lN}, p0={p0}, pN={pN}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    gdal_translate = _resolve_gdal_translate()
    cmd = [
        gdal_translate,
        "-ot",
        "CInt16",
        "-of",
        "MFF",
        "-srcwin",
        str(p0 - 1),
        str(l0 - 1),
        str(pN - p0 + 1),
        str(lN - l0 + 1),
        str(input_file),
        str(output_file),
    ]
    subprocess.run(cmd, check=True)

    mff_data = output_file.with_suffix(".j00")
    if mff_data.exists():
        if output_file.exists():
            output_file.unlink()
        mff_data.rename(output_file)

    return l0, lN, p0, pN


def tsx_to_res(res_file: str, l0: int, lN: int, p0: int, pN: int) -> bool:
    """Append TSX crop information to Doris result file."""
    res_path = Path(res_file)
    fileout = "image.raw"

    with res_path.open("a", encoding="utf-8") as out_stream:
        out_stream.write("\n")
        out_stream.write("*******************************************************************\n")
        out_stream.write("*_Start_crop:\t\t\tcosar\n")
        out_stream.write("*******************************************************************\n")
        out_stream.write(f"Data_output_file: \t{fileout}\n")
        out_stream.write("Data_output_format: \t\t\tcomplex_short\n")
        out_stream.write(f"First_line (w.r.t. original_image): \t{l0}\n")
        out_stream.write(f"Last_line (w.r.t. original_image): \t{lN}\n")
        out_stream.write(f"First_pixel (w.r.t. original_image): \t{p0}\n")
        out_stream.write(f"Last_pixel (w.r.t. original_image): \t{pN}\n")
        out_stream.write("*******************************************************************\n")
        out_stream.write("* End_crop:_NORMAL\n")
        out_stream.write("*******************************************************************\n")
        out_stream.write(f"\n    Current time: {datetime.now().strftime('%a %b %d %H:%M:%S %Y')}\n")
        out_stream.write("\n")

    _replace_crop_flag(res_path)
    return True


def tsx_dump_data(source_data_path, work_dir):
    """Dump TSX COSAR data to image.raw and update slave.res."""
    target_data_path = os.path.join(work_dir, "image.raw")
    res_file = os.path.join(work_dir, "slave.res")
    l0, lN, p0, pN = tsx_to_data(source_data_path, target_data_path, res_file)
    tsx_to_res(res_file, l0, lN, p0, pN)
    print(f"TSX data dumped to: {target_data_path}")


if __name__ == "__main__":
    pass
