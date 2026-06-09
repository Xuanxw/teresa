#!/usr/bin/env python3

import os
import re
from contextlib import redirect_stdout
from datetime import datetime
from typing import Iterable, List, Union
from xml.etree import ElementTree


TSX_WAVELENGTH = 0.031


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_path_part(part: str):
    match = re.match(r'([^\[]+)\[@([^=]+)="([^"]+)"\]', part)
    if match:
        return match.group(1), (match.group(2), match.group(3))
    return part, None


def _iter_matching_descendants(node: ElementTree.Element, part: str) -> Iterable[ElementTree.Element]:
    tag, attr_filter = _parse_path_part(part)
    for elem in node.iter():
        if elem is node:
            continue
        if _local_name(elem.tag) != tag:
            continue
        if attr_filter is not None and elem.attrib.get(attr_filter[0]) != attr_filter[1]:
            continue
        yield elem


def find_all_text(root: ElementTree.Element, path: str) -> List[str]:
    """Find text values using local-name matching, tolerant of XML namespaces."""
    parts = [part for part in path.replace(".//", "").split("/") if part]
    candidates = [root]
    for part in parts:
        next_candidates: list[ElementTree.Element] = []
        for candidate in candidates:
            next_candidates.extend(_iter_matching_descendants(candidate, part))
        candidates = next_candidates
        if not candidates:
            break
    return [elem.text.strip() for elem in candidates if elem.text and elem.text.strip()]


def first_text(root: ElementTree.Element, path: str, default: str = "DUMMY") -> str:
    values = find_all_text(root, path)
    return values[0] if values else default


def tsx_time_to_doris(value: str) -> str:
    value = value.strip().rstrip("Z")
    if "." in value:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f")
        frac = f".{dt.microsecond:06d}"
    else:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        frac = ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{dt.day:02d}-{months[dt.month - 1]}-{dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}{frac}"


def hms2sec(value: str, convert_flag: str = "int") -> Union[int, float]:
    time_part = value.split("T")[-1].rstrip("Z")
    seconds = int(time_part[0:2]) * 3600 + int(time_part[3:5]) * 60 + float(time_part[6:])
    return seconds if convert_flag == "float" else int(seconds)


def _safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _decimal(value, precision: int = 12) -> str:
    text = f"{_safe_float(value):.{precision}f}".rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def extract_tsx_meta(xml_file: str) -> dict:
    """Extract TerraSAR-X/TanDEM-X/PAZ metadata for Doris readfiles output."""
    root = ElementTree.parse(xml_file).getroot()
    meta = {
        "mission": first_text(root, ".//generalHeader/mission", "TSX"),
        "imageData": first_text(root, ".//productComponents/imageData/file/location/filename"),
        "imageLines": first_text(root, ".//imageDataInfo/imageRaster/numberOfRows"),
        "imagePixels": first_text(root, ".//imageDataInfo/imageRaster/numberOfColumns"),
        "volFile": first_text(root, ".//productComponents/annotation/file/location/filename", os.path.basename(xml_file)),
        "volID": first_text(root, ".//generalHeader/itemName"),
        "volRef": first_text(root, ".//generalHeader/referenceDocument"),
        "productSpec": first_text(root, ".//generalHeader/referenceDocument", "TSX"),
        "productVolDate": first_text(root, ".//setup/IOCSAuxProductGenerationTimeUTC"),
        "productDate": first_text(root, ".//generalHeader/generationTime"),
        "productFacility": first_text(root, ".//productInfo/generationInfo/level1ProcessingFacility"),
        "sceneMode": first_text(root, ".//setup/orderInfo/imagingMode"),
        "sceneCenLat": first_text(root, ".//sceneInfo/sceneCenterCoord/lat", "0"),
        "sceneCenLon": first_text(root, ".//sceneInfo/sceneCenterCoord/lon", "0"),
        "sceneRecords": first_text(root, ".//imageDataInfo/imageRaster/numberOfRows"),
        "orbitABS": first_text(root, ".//productInfo/missionInfo/absOrbit"),
        "orbitDir": first_text(root, ".//productInfo/missionInfo/orbitDirection"),
        "orbitTime": find_all_text(root, ".//stateVec/timeUTC"),
        "orbitX": find_all_text(root, ".//stateVec/posX"),
        "orbitY": find_all_text(root, ".//stateVec/posY"),
        "orbitZ": find_all_text(root, ".//stateVec/posZ"),
        "orbitVX": find_all_text(root, ".//stateVec/velX"),
        "orbitVY": find_all_text(root, ".//stateVec/velY"),
        "orbitVZ": find_all_text(root, ".//stateVec/velZ"),
        "rangeRSR": first_text(root, ".//productSpecific/complexImageInfo/commonRSF", "0"),
        "rangeBW": first_text(root, ".//processingParameter/rangeLookBandwidth", "0"),
        "rangeWind": first_text(root, ".//processingParameter/rangeWindowID"),
        "rangeTimePix": first_text(root, ".//sceneInfo/rangeTime/firstPixel", "0"),
        "azimuthPRF": first_text(root, ".//productSpecific/complexImageInfo/commonPRF"),
        "azimuthBW": first_text(root, ".//processingParameter/azimuthLookBandwidth"),
        "azimuthWind": first_text(root, ".//processingParameter/azimuthWindowID"),
        "azimuthTimeStart": first_text(root, ".//sceneInfo/start/timeUTC"),
        "azimuthTimeStop": first_text(root, ".//sceneInfo/stop/timeUTC", ""),
        "heading": first_text(root, ".//sceneInfo/headingAngle", ""),
        "dopplerCoeff0": first_text(root, './/combinedDoppler/coefficient[@exponent="0"]', "0"),
        "dopplerCoeff1": first_text(root, './/combinedDoppler/coefficient[@exponent="1"]', "0"),
        "dopplerCoeff2": first_text(root, './/combinedDoppler/coefficient[@exponent="2"]', "0"),
    }
    return meta


def write_res_file(meta: dict) -> None:
    product_spec = str(meta["productSpec"]).split()[0] if str(meta["productSpec"]).split() else "TSX"
    range_bw_mhz = _safe_float(meta["rangeBW"]) / 1_000_000.0
    range_rsr_mhz = _safe_float(meta["rangeRSR"]) / 1_000_000.0
    range_time_ms = _safe_float(meta["rangeTimePix"]) * 1000.0

    print("===========================================================")
    print("           TERESA - SAR image registration tool (TSX)")
    print("===========================================================")
    print("File Generated  : ", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("File Type       : SAR Registration Metadata")
    print("Input Mission   : TSX")
    print("-----------------------------------------------------------")
    print("")
    print("**************************************************************")
    print("*Processing_Status_Flag:")
    print("**************************************************************")
    print("Start_process_control")
    print("readfiles:\t\t1")
    print("precise_orbits:\t\t0")
    print("modify_orbits:\t\t0")
    print("crop:\t\t0")
    print("sim_amplitude:\t\t0")
    print("master_timing:\t\t0")
    print("oversample:\t\t0")
    print("resample:\t\t0")
    print("filt_azi:\t\t0")
    print("filt_range:\t\t0")
    print("NOT_USED:\t\t0")
    print("End_process_control")
    print("")
    print("tsx_dump_header2doris.py v1.0, doris software, python3")
    print("*******************************************************************")
    print("*_Start_readfiles:")
    print("*******************************************************************")
    print(f"Volume file: \t\t\t\t\t{meta['volFile']}")
    print(f"Volume_ID: \t\t\t\t\t{meta['volID']}")
    print(f"Volume_identifier: \t\t\t\t{meta['volRef']}")
    print("Volume_set_identifier: \t\t\t\tDUMMY")
    print(f"(Check)Number of records in ref. file: \t\t{meta['sceneRecords']}")
    print(f"SAR_PROCESSOR:                                  {product_spec}")
    print(f"Product type specifier: \t                {meta['mission']}")
    print(f"Logical volume generating facility: \t\t{meta['productFacility']}")
    print(f"Logical volume creation date: \t\t\t{meta['productVolDate']}")
    print(f"Location and date/time of product creation: \t{meta['productDate']}")
    print(
        "Scene identification: \t\t\t\t"
        f"Orbit: {meta['orbitABS']} {meta['orbitDir']} Mode: {meta['sceneMode']}"
    )
    print(
        "Scene location: \t\t                "
        f"lat: {_decimal(meta['sceneCenLat'], 4)} lon: {_decimal(meta['sceneCenLon'], 4)}"
    )
    print(f"Leader file:                                 \t{meta['volFile']}")
    print(f"Sensor platform mission identifer:         \t{meta['mission']}")
    print(f"Scene_centre_latitude:                     \t{_decimal(meta['sceneCenLat'], 12)}")
    print(f"Scene_centre_longitude:                    \t{_decimal(meta['sceneCenLon'], 12)}")
    if meta.get("heading"):
        print(f"Scene_center_heading: \t                {_safe_float(meta['heading']):2.0f}")
    print(f"Radar_wavelength (m):                      \t{TSX_WAVELENGTH}")
    print(f"First_pixel_azimuth_time (UTC):\t\t\t{tsx_time_to_doris(meta['azimuthTimeStart'])}")
    if meta.get("azimuthTimeStop"):
        print(f"Last_pixel_azimuth_time (UTC):\t\t\t{tsx_time_to_doris(meta['azimuthTimeStop'])}")
    print(f"Pulse_Repetition_Frequency (computed, Hz): \t{_decimal(meta['azimuthPRF'], 12)}")
    print(f"Total_azimuth_band_width (Hz):             \t{_decimal(meta['azimuthBW'], 12)}")
    print(f"Weighting_azimuth:                         \t{str(meta['azimuthWind']).upper()}")
    print(f"Xtrack_f_DC_constant (Hz, early edge):     \t{_decimal(meta['dopplerCoeff0'], 12)}")
    print(f"Xtrack_f_DC_linear (Hz/s, early edge):     \t{_decimal(meta['dopplerCoeff1'], 12)}")
    print(f"Xtrack_f_DC_quadratic (Hz/s/s, early edge): \t{_decimal(meta['dopplerCoeff2'], 12)}")
    print(f"Range_time_to_first_pixel (2way) (ms):     \t{range_time_ms:0.15f}")
    print(f"Range_sampling_rate (computed, MHz):       \t{range_rsr_mhz:0.6f}")
    print(f"Total_range_band_width (MHz):              \t{range_bw_mhz}")
    print(f"Weighting_range:                           \t{str(meta['rangeWind']).upper()}")
    print("")
    print("*******************************************************************")
    print(f"Datafile: \t\t\t\t\t{meta['imageData']}")
    print("Dataformat: \t\t\t\tTSX_COSAR")
    print(f"Number_of_lines_original: \t\t\t{meta['imageLines']}")
    print(f"Number_of_pixels_original: \t                {meta['imagePixels']}")
    print("*******************************************************************")
    print("* End_readfiles:_NORMAL")
    print("*******************************************************************")
    print("")
    print("")
    print("*******************************************************************")
    print("*_Start_leader_datapoints")
    print("*******************************************************************")
    has_velocity = (
        len(meta["orbitVX"]) == len(meta["orbitTime"])
        and len(meta["orbitVY"]) == len(meta["orbitTime"])
        and len(meta["orbitVZ"]) == len(meta["orbitTime"])
    )
    if has_velocity:
        print(" t(s)\t\tX(m)\t\tY(m)\t\tZ(m)\t\tVX(m/s)\t\tVY(m/s)\t\tVZ(m/s)")
    else:
        print(" t(s)\t\tX(m)\t\tY(m)\t\tZ(m)")
    print(f"NUMBER_OF_DATAPOINTS: \t\t\t{len(meta['orbitTime'])}")
    print("")
    if has_velocity:
        for time_utc, x, y, z, vx, vy, vz in zip(
            meta["orbitTime"], meta["orbitX"], meta["orbitY"], meta["orbitZ"],
            meta["orbitVX"], meta["orbitVY"], meta["orbitVZ"]
        ):
            print(
                f" {hms2sec(time_utc)} {_decimal(x, 6)} {_decimal(y, 6)} {_decimal(z, 6)} "
                f"{_decimal(vx, 6)} {_decimal(vy, 6)} {_decimal(vz, 6)}"
            )
    else:
        for time_utc, x, y, z in zip(meta["orbitTime"], meta["orbitX"], meta["orbitY"], meta["orbitZ"]):
            print(f" {hms2sec(time_utc)} {_decimal(x, 6)} {_decimal(y, 6)} {_decimal(z, 6)}")
    print("")
    print("*******************************************************************")
    print("* End_leader_datapoints:_NORMAL")
    print("*******************************************************************")


def tsx_dump_header2doris(source_meta_path, work_dir):
    """Generate a Doris slave.res file from TSX/TDX/PAZ XML metadata."""
    result_file = os.path.join(work_dir, "slave.res")
    meta = extract_tsx_meta(source_meta_path)

    with open(result_file, "w", encoding="utf-8") as f:
        with redirect_stdout(f):
            write_res_file(meta)

    print(f"TSX header file generated: {result_file}")


if __name__ == "__main__":
    pass
