"""Build mainland demand and report buffering, conservation, and original-center diagnostics."""

import argparse
import csv
import json
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd

from lanet import load_config
from lanet.demand import (
    allocate_households,
    classify_centers,
    demand_land_geometry,
    generate_cells,
    mark_low_demand,
    partition_mainland,
    summarize_centers,
)
from lanet.download import download_file


def main(config_path: str) -> None:
    path = Path(config_path).resolve()
    config = load_config(path)
    raw_dir = path.parent / config["data"]["raw_dir"]
    processed = path.parent / config["data"]["processed_dir"]
    year = config["data"]["acs_year"]
    county_id = config["study"]["state_fips"] + config["study"]["county_fips"]
    crs = config["study"]["projected_crs"]
    raw = gpd.read_file(raw_dir / f"block_groups_{county_id}_acs{year}.gpkg").to_crs(crs)
    land = gpd.read_file(processed / f"block_groups_land_{county_id}_{year}.gpkg").to_crs(crs)
    if config["study"]["mainland_method"] != "largest_contiguous_polygon":
        raise ValueError("Unsupported mainland-selection method")
    mainland, islands, _ = partition_mainland(raw, land)
    print(f"Mainland: {len(mainland)} groups; islands: {len(islands)} groups", flush=True)
    grid = generate_cells(
        mainland, config["demand"]["h3_resolution"], config["demand"]["grid_buffer_m"]
    )
    print(f"Generated grid: {len(grid)} cells", flush=True)
    cells, overlaps, report = allocate_households(
        mainland, grid, config["demand"]["conservation_relative_tolerance"]
    )
    print(f"Allocated demand: {len(cells)} positive-demand cells", flush=True)
    marine_urls = [
        config["data"][key]
        for key in ("tiger_area_water_url", "orange_area_water_url", "ventura_area_water_url")
    ]
    marine_parts = []
    for url in marine_urls:
        water_path = download_file(url, raw_dir)
        with ZipFile(water_path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Area-water ZIP failed CRC validation")
        part = gpd.read_file(
            water_path, where="MTFCC IN ('H2051', 'H2053')", columns=["MTFCC", "ALAND"]
        )
        if (part.ALAND > 0).any():
            raise ValueError("A marine feature mixes land and water; review its geometry")
        marine_parts.append(part)
    water = gpd.read_file(
        raw_dir / Path(config["data"]["tiger_faces_url"]).name,
        where="LWFLAG = 'P'",
        columns=["LWFLAG"],
    )
    sea = pd.concat(marine_parts, ignore_index=True)
    grid = classify_centers(grid, raw.geometry.union_all(), water, sea)
    flags = grid.drop(columns="geometry").drop(columns=["lat", "lng"])
    cells = cells.merge(flags, on="h3", validate="one_to_one")
    served_land = demand_land_geometry(overlaps, cells.h3)
    cells = cells.merge(
        served_land[["h3", "route_lat", "route_lng"]], on="h3", validate="one_to_one"
    )
    cells["parcels"] = cells.households * config["demand"]["parcels_per_household_per_day"]
    cells, low_report = mark_low_demand(
        cells,
        config["demand"]["low_demand_parcels_per_day"],
        config["demand"]["parcels_per_household_per_day"],
    )
    cells.drop(columns="geometry").to_parquet(processed / "demand_cells.parquet", index=False)
    cells.loc[cells.center_in_sea].drop(columns="geometry").to_csv(
        processed / "sea_center_demand_cells.csv", index=False
    )
    served_land.to_parquet(processed / "demand_land.parquet", index=False)
    overlaps.drop(columns="geometry").to_parquet(
        processed / "block_group_allocation.parquet", index=False
    )
    grid.to_parquet(processed / "generated_h3_grid.parquet", index=False)
    mainland.to_parquet(processed / "mainland_block_groups.parquet", index=False)
    islands.drop(columns="geometry").to_csv(
        processed / "excluded_island_block_groups.csv", index=False
    )
    report.update(
        {
            "h3_resolution": config["demand"]["h3_resolution"],
            "buffer_m": config["demand"]["grid_buffer_m"],
            "county_households": int(raw.B11001_001E.sum()),
            "island_households": int(islands.B11001_001E.sum()),
            "island_block_groups": len(islands),
            "generated_grid_centers": summarize_centers(grid),
            "positive_demand_centers": summarize_centers(cells),
            "marine_source_urls": marine_urls,
            "daily_parcels": float(cells.parcels.sum()),
            "low_demand": low_report,
            "top_five": cells.nlargest(5, "households")[["h3", "lat", "lng", "households"]].to_dict(
                "records"
            ),
        }
    )
    summary_path = raw_dir / Path(config["data"]["acs_summary_url"]).name
    with summary_path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="|"):
            if row["GEO_ID"] == "1600000US" + config["data"]["reference_place_geoid"]:
                report["reference_place"] = {
                    "name": config["data"]["reference_place_name"],
                    "geoid": row["GEO_ID"],
                    "households": int(row["B11001_E001"]),
                    "moe": int(row["B11001_M001"]),
                }
                break
        else:
            raise ValueError("Reference place was not found in the ACS summary")
    (processed / "demand_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    main(parser.parse_args().config)
