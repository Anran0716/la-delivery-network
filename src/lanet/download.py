"""Download official source files and validate the county block-group join."""

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import requests


def download_file(url: str, directory: Path) -> Path:
    """Cache a public source file; finish a streamed download before renaming it."""
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / Path(urlsplit(url).path).name
    if destination.exists():
        return destination
    partial = destination.with_name(destination.name + ".part")
    with requests.get(url, stream=True, timeout=(15, 180)) as response:
        response.raise_for_status()
        with partial.open("wb") as stream:
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)
    partial.replace(destination)
    return destination


def build_geoid(state: str, county: str, tract: str, block_group: str) -> str:
    """Concatenate fixed-width Census geography strings without losing zeros."""
    for name, value, width in (
        ("state", state, 2),
        ("county", county, 3),
        ("tract", tract, 6),
        ("block_group", block_group, 1),
    ):
        if (
            not isinstance(value, str)
            or len(value) != width
            or not value.isascii()
            or not value.isdigit()
        ):
            raise ValueError(f"{name} must be a {width}-digit string")
    return state + county + tract + block_group


def extract_households(path: Path, state: str, county: str) -> tuple[pd.DataFrame, int]:
    """Map Summary File columns to API names and build 12-character GEOIDs.

    Only standard block-group summary-level 150 records are retained. Geographic
    components stay strings so leading zeros survive the CSV and spatial join.
    """
    rows = []
    county_total = None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="|")
        required = {"GEO_ID", "B11001_E001", "B11001_M001"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Summary File is missing B11001 estimate or margin-of-error columns")
        for row in reader:
            source_id = row["GEO_ID"]
            if source_id == f"0500000US{state}{county}":
                county_total = int(row["B11001_E001"])
            if not source_id.startswith(f"1500000US{state}{county}"):
                continue
            geography = source_id.removeprefix("1500000US")
            if len(geography) != 12 or not geography.isdecimal():
                raise ValueError(f"Invalid block-group geography: {source_id}")
            components = {
                "state": geography[:2],
                "county": geography[2:5],
                "tract": geography[5:11],
                "block group": geography[11:],
            }
            geoid = build_geoid(
                components["state"],
                components["county"],
                components["tract"],
                components["block group"],
            )
            estimate = int(row["B11001_E001"])
            moe = int(row["B11001_M001"])
            if estimate < 0 or moe < 0:
                raise ValueError(
                    f"Missing/sentinel ACS value for {geoid}; review before allocation"
                )
            rows.append({**components, "GEOID": geoid, "B11001_001E": estimate, "B11001_001M": moe})
    if not rows or county_total is None:
        raise ValueError("Summary File has no requested county or block-group records")
    households = pd.DataFrame(rows)
    if households["GEOID"].duplicated().any():
        raise ValueError("ACS contains duplicate GEOIDs")
    if int(households["B11001_001E"].sum()) != county_total:
        raise ValueError("Block-group household sum differs from the county estimate")
    return households, county_total


def join_households(boundaries: gpd.GeoDataFrame, households: pd.DataFrame) -> gpd.GeoDataFrame:
    """Require complete one-to-one GEOID coverage before joining either input."""
    for name, frame in (("TIGER", boundaries), ("ACS", households)):
        ids = frame["GEOID"]
        if ids.isna().any() or not ids.str.fullmatch(r"[0-9]{12}").all():
            raise ValueError(f"{name} GEOID must be a 12-digit string")
        if ids.duplicated().any():
            raise ValueError(f"{name} contains duplicate GEOIDs")
    acs_only = sorted(set(households["GEOID"]) - set(boundaries["GEOID"]))
    tiger_only = sorted(set(boundaries["GEOID"]) - set(households["GEOID"]))
    if acs_only or tiger_only:
        raise ValueError(
            f"GEOID coverage mismatch: ACS-only={len(acs_only)} {acs_only[:5]}; "
            f"TIGER-only={len(tiger_only)} {tiger_only[:5]}"
        )
    return boundaries.merge(households, on="GEOID", how="left", validate="one_to_one")


def run_download(config_path: str | Path = "config.yaml") -> dict:
    """Download sources and write county CSV, joined GeoPackage, and provenance."""
    from lanet.config import load_config

    config_path = Path(config_path).resolve()
    config = load_config(config_path)
    raw = config_path.parent / config["data"]["raw_dir"]
    state = config["study"]["state_fips"]
    county = config["study"]["county_fips"]
    summary = download_file(config["data"]["acs_summary_url"], raw)
    tiger = download_file(config["data"]["tiger_bg_url"], raw)
    with ZipFile(tiger) as archive:
        if archive.testzip() is not None:
            raise ValueError("TIGER ZIP failed CRC validation")
    households, county_total = extract_households(summary, state, county)
    boundaries = gpd.read_file(tiger, where=f"COUNTYFP = '{county}'")
    if not boundaries["STATEFP"].eq(state).all() or not boundaries["COUNTYFP"].eq(county).all():
        raise ValueError("TIGER selection contains a different state or county")
    joined = join_households(boundaries, households)
    if joined.geometry.isna().any() or joined.geometry.is_empty.any():
        raise ValueError("TIGER contains missing or empty block-group geometries")

    year = config["data"]["acs_year"]
    csv_path = raw / f"acs{year}_{state}{county}_households.csv"
    gpkg_path = raw / f"block_groups_{state}{county}_acs{year}.gpkg"
    households.to_csv(csv_path, index=False)
    joined.to_file(gpkg_path, layer="block_groups", driver="GPKG", index=False)
    result = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "acs_source": "Official table-based Summary File; data API currently requires a key",
        "column_mapping": {"B11001_E001": "B11001_001E", "B11001_M001": "B11001_001M"},
        "sources": [],
        "state_fips": state,
        "county_fips": county,
        "includes_islands": True,
        "acs_block_groups": len(households),
        "tiger_block_groups": len(boundaries),
        "matched_block_groups": len(joined),
        "acs_only_geoids": [],
        "tiger_only_geoids": [],
        "households": int(households["B11001_001E"].sum()),
        "county_households": county_total,
        "crs": str(joined.crs),
        "csv": csv_path.name,
        "joined_geopackage": gpkg_path.name,
    }
    for source_path, url in (
        (summary, config["data"]["acs_summary_url"]),
        (tiger, config["data"]["tiger_bg_url"]),
    ):
        with source_path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        result["sources"].append(
            {
                "file": source_path.name,
                "url": url,
                "bytes": source_path.stat().st_size,
                "sha256": digest,
            }
        )
    (raw / "download_manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
