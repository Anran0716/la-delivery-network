"""After offline toy/checker tests pass, compare county strong and weak CFLP v1."""

import json
from math import ceil
from pathlib import Path

import pandas as pd

from lanet import load_config
from lanet.model import solve_model
from lanet.problem import FacilityData


def main():
    config = load_config()
    processed = Path(config["data"]["processed_dir"])
    destination = processed / "model_v1"
    destination.mkdir(exist_ok=True)
    candidates = pd.read_parquet(processed / "candidates.parquet")
    all_demand = pd.read_parquet(processed / "demand_cells.parquet")
    travel = pd.read_parquet(processed / "travel_times.parquet")
    travel = travel.loc[travel.travel_time_min <= config["travel"]["coverage_minutes"]].copy()
    if travel.duplicated(["candidate_id", "h3"]).any():
        raise ValueError("Duplicate model arcs")
    demand = all_demand.loc[all_demand.h3.isin(travel.h3)].copy()
    excluded = all_demand.loc[~all_demand.h3.isin(travel.h3)].copy()
    excluded["exclusion_reason"] = "No candidate within baseline 30-minute driving limit"
    excluded.to_csv(destination / "structurally_uncovered.csv", index=False)
    times = travel.set_index(["candidate_id", "h3"]).travel_time_min.to_dict()
    data = FacilityData(
        demand=demand.set_index("h3").parcels.to_dict(),
        capacity=dict.fromkeys(
            candidates.candidate_id, config["facility"]["capacity_parcels_per_day"]
        ),
        fixed_cost=dict.fromkeys(
            candidates.candidate_id, config["facility"]["fixed_cost_usd_per_day"]
        ),
        unit_cost={
            arc: minutes * config["cost"]["delivery_usd_per_parcel_minute"]
            for arc, minutes in times.items()
        },
        travel_minutes=times,
        utilization_limit=config["facility"]["utilization_limit"],
        unmet_penalty=config["cost"]["unmet_penalty_usd_per_parcel"],
        coverage_minutes=config["travel"]["coverage_minutes"],
    )
    comparison = {
        "modeled_cells": len(demand),
        "model_arcs_within_30_minutes": len(travel),
        "candidates": len(candidates),
        "modeled_parcels_per_day": float(demand.parcels.sum()),
        "structurally_uncovered_cells": len(excluded),
        "structurally_uncovered_households": float(excluded.households.sum()),
        "structurally_uncovered_parcels": float(excluded.parcels.sum()),
        "excluded_cells_outside_objective": True,
        "usable_capacity_per_station": config["facility"]["capacity_parcels_per_day"]
        * config["facility"]["utilization_limit"],
        "capacity_lower_bound_for_full_modeled_service": ceil(
            demand.parcels.sum()
            / (
                config["facility"]["capacity_parcels_per_day"]
                * config["facility"]["utilization_limit"]
            )
        ),
        "solutions": {},
    }
    print(
        json.dumps({k: v for k, v in comparison.items() if k != "solutions"}, indent=2), flush=True
    )
    for linking in ("strong", "weak"):
        print(f"Starting {linking} linking", flush=True)
        folder = destination / linking
        result = solve_model(
            data,
            linking,
            folder,
            time_limit_seconds=config["solver"]["time_limit_seconds"],
            relative_gap=config["solver"]["relative_gap"],
        )
        summary = {"validation": result["validation"], "solver": result["solver"]}
        loads = result["validation"]["station_loads"]
        station_table = candidates.copy()
        station_table["opened"] = station_table.candidate_id.map(result["y"])
        station_table["assigned_parcels"] = station_table.candidate_id.map(loads)
        station_table["utilization"] = (
            station_table.assigned_parcels / config["facility"]["capacity_parcels_per_day"]
        )
        station_table.to_parquet(folder / "stations.parquet", index=False)
        assignments = pd.DataFrame(
            [
                {
                    "candidate_id": i,
                    "h3": j,
                    "fraction": fraction,
                    "parcels": data.demand[j] * fraction,
                    "travel_time_min": data.travel_minutes[i, j],
                }
                for (i, j), fraction in result["x"].items()
            ]
        )
        assignments.to_parquet(folder / "assignments.parquet", index=False)
        unmet = demand.copy()
        unmet["s"] = unmet.h3.map(result["s"])
        unmet["unmet_parcels"] = unmet.parcels * unmet.s
        unmet.to_parquet(folder / "unmet.parquet", index=False)
        summary["county_unserved_parcels_including_excluded"] = result["validation"][
            "unmet_parcels"
        ] + float(excluded.parcels.sum())
        summary["split_cells"] = int(
            assignments.loc[assignments.fraction > 1e-6].groupby("h3").size().gt(1).sum()
        )
        minimum_stations = ceil(
            (result["validation"]["served_parcels"] - 0.01)
            / comparison["usable_capacity_per_station"]
        )
        if result["validation"]["open_stations"] < minimum_stations:
            raise ValueError("Station-count scale check failed; inspect capacity units")
        if result["validation"]["all_s_zero"] and result["validation"]["open_stations"] < 30:
            raise ValueError("Full modeled service requires at least 30 stations")
        (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        comparison["solutions"][linking] = summary
        (destination / "comparison.json").write_text(
            json.dumps(comparison, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "linking": linking,
                    **{k: v for k, v in result["validation"].items() if k != "station_loads"},
                    "solver": result["solver"],
                },
                indent=2,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
