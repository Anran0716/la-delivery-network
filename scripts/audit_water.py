"""Audit county water coverage and save land geometry before H3 allocation."""

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd

from lanet import load_config
from lanet.download import download_file
from lanet.geography import audit_water, prepare_land_geometry


def main(config_path: str) -> None:
    path = Path(config_path).resolve()
    config = load_config(path)
    if config["demand"]["allocation_geometry"] != "tiger_minus_perennial_water_faces":
        raise ValueError("Unsupported allocation geometry method")
    raw = path.parent / config["data"]["raw_dir"]
    processed = path.parent / config["data"]["processed_dir"]
    processed.mkdir(parents=True, exist_ok=True)
    year = config["data"]["acs_year"]
    county_id = config["study"]["state_fips"] + config["study"]["county_fips"]
    joined_path = raw / f"block_groups_{county_id}_acs{year}.gpkg"
    joined = gpd.read_file(joined_path, layer="block_groups")
    report = audit_water(joined)
    print("Water metadata audit:", json.dumps(report), flush=True)
    faces_path = download_file(config["data"]["tiger_faces_url"], raw)
    with ZipFile(faces_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("TIGER faces ZIP failed CRC validation")
    attributes = gpd.read_file(faces_path, columns=["LWFLAG", "ATOTAL"], ignore_geometry=True)
    area_by_flag = attributes.groupby("LWFLAG").ATOTAL.sum().to_dict()
    if set(area_by_flag) - {"G", "I", "L", "P", "S"}:
        raise ValueError("Unknown face land/water flag")
    face_water_area = int(area_by_flag.get("P", 0))
    face_land_area = int(sum(area for flag, area in area_by_flag.items() if flag != "P"))
    if (face_water_area, face_land_area) != (report["water_area_m2"], report["land_area_m2"]):
        raise ValueError(
            "Face areas do not match block-group ALAND/AWATER; inspect source vintages"
        )
    water = gpd.read_file(faces_path, columns=["LWFLAG", "ATOTAL"], where="LWFLAG = 'P'")
    print(f"Preparing land geometry with {len(water)} perennial-water faces", flush=True)
    land = prepare_land_geometry(joined, water)
    crs = config["study"]["projected_crs"]
    overlap = gpd.overlay(
        land[["geometry"]],
        water[["geometry"]],
        how="intersection",
        keep_geom_type=True,
        make_valid=False,
    )
    overlap_m2 = float(overlap.to_crs(crs).area.sum())
    if overlap_m2 > config["demand"]["geometry_overlap_tolerance_m2"]:
        raise ValueError(f"Land still overlaps perennial water by {overlap_m2} square meters")
    destination = processed / f"block_groups_land_{county_id}_{year}.gpkg"
    land.to_file(destination, layer="block_groups_land", driver="GPKG", index=False)
    with faces_path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    report.update(
        {
            "allocation_geometry": config["demand"]["allocation_geometry"],
            "faces_source_url": config["data"]["tiger_faces_url"],
            "faces_sha256": digest,
            "face_area_m2_by_flag": {str(key): int(value) for key, value in area_by_flag.items()},
            "perennial_water_faces": len(water),
            "land_block_groups": len(land),
            "households_before": int(joined.B11001_001E.sum()),
            "households_after": int(land.B11001_001E.sum()),
            "land_water_overlap_m2": overlap_m2,
            "output": destination.name,
            "includes_islands": True,
        }
    )
    (processed / "water_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    main(parser.parse_args().config)
