"""Run checked single-source v2 and the preregistered period-4 scenarios."""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from lanet import load_config
from lanet.check import check_solution
from lanet.experiments import county_inputs, read_solution, write_solution
from lanet.model import solve_model
from lanet.scenarios import apply_scenario, scenario_definitions
from lanet.starts import single_source_start


def fingerprint(config, scenario, fixed):
    payload = {
        "config": config,
        "scenario": scenario.__dict__,
        "fixed": fixed,
        "formulation": "binary_w_continuous_x_partial_service_v1",
    }
    inputs = [
        Path(config["data"]["processed_dir"]) / name
        for name in ("demand_cells.parquet", "candidates.parquet", "travel_times.parquet")
    ]
    inputs += [
        Path(__file__).resolve().parents[1] / "src" / "lanet" / name
        for name in ("model.py", "problem.py", "check.py", "starts.py")
    ]
    payload["source_hashes"] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def combine_outputs(root, scenarios, candidates):
    rows, station_tables, assignment_tables, reoptimized = [], [], [], {}
    for scenario in scenarios:
        folder = root / scenario.name
        summary_path = folder / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        valid, solver = summary["validation"], summary["solver"]
        stations = pd.read_parquet(folder / "stations.parquet")
        stations["scenario"] = scenario.name
        station_tables.append(stations)
        flows = pd.read_parquet(folder / "assignments.parquet")
        unmet = pd.read_parquet(folder / "unmet.parquet")
        actual = flows.loc[flows.parcels > 0].copy()
        actual["demand_parcels"] = actual.h3.map(unmet.set_index("h3").parcels)
        actual["solver_s"] = actual.h3.map(unmet.set_index("h3").s)
        actual["unmet_parcels"] = actual.h3.map(unmet.set_index("h3").unmet_parcels)
        actual = actual.sort_values(["h3", "parcels"], ascending=[True, False])
        actual.loc[actual.h3.duplicated(), "unmet_parcels"] = 0.0
        unassigned = unmet.loc[~unmet.h3.isin(actual.h3)].copy()
        unassigned["candidate_id"] = None
        unassigned["demand_parcels"] = unassigned.parcels
        unassigned["fraction"] = 0.0
        unassigned["solver_s"] = unassigned.s
        unassigned["parcels"] = 0.0
        unassigned["travel_time_min"] = float("nan")
        actual = pd.concat([actual, unassigned], ignore_index=True)
        actual["in_model"] = True
        outside = pd.read_csv(folder / "structurally_uncovered.csv")
        outside["demand_parcels"] = outside.parcels
        outside["unmet_parcels"] = outside.parcels
        outside["candidate_id"] = None
        outside["parcels"] = outside["fraction"] = 0.0
        outside["solver_s"] = float("nan")
        outside["in_model"] = False
        actual = pd.concat([actual, outside], ignore_index=True)
        actual["served_parcels"] = actual.parcels
        actual["scenario"] = scenario.name
        assignment_tables.append(actual)
        opened = set(stations.loc[stations.opened > 0.5, "candidate_id"])
        if scenario.network == "reoptimize":
            reoptimized[scenario.name] = opened
        rows.append(
            {
                "scenario": scenario.name,
                "open_stations": valid["open_stations"],
                "objective": valid["objective"],
                "fixed_cost": valid["fixed_cost"],
                "delivery_cost": valid["delivery_cost"],
                "penalty_cost": valid["penalty_cost"],
                "modeled_parcels": valid["total_demand_parcels"],
                "served_parcels": valid["served_parcels"],
                "modeled_unmet_parcels": valid["unmet_parcels"],
                "modeled_unmet_share": valid["unmet_parcels"] / valid["total_demand_parcels"],
                "excluded_parcels": summary["excluded_parcels"],
                "study_area_unmet_parcels": summary["study_area_unmet_parcels"],
                "weighted_mean_travel_minutes": valid["weighted_mean_travel_minutes"],
                "all_s_zero": valid["all_s_zero"],
                "solve_seconds": solver["solve_wall_seconds"],
                "gap": solver["relative_gap"],
                "proven_optimal": solver["proven_optimal"],
                "termination_reason": solver["termination_reason"],
                "warm_start_checked": solver["warm_start_checked"],
                "split_cells": summary["split_cells"],
                "capacity_unmet_lower_bound": summary["capacity_unmet_lower_bound"],
            }
        )
    if not rows:
        return
    pd.DataFrame(rows).to_csv(root / "scenario_summary.csv", index=False)
    pd.DataFrame(rows).to_parquet(root / "scenario_summary.parquet", index=False)
    pd.concat(station_tables, ignore_index=True).to_parquet(
        root / "scenario_stations.parquet", index=False
    )
    pd.concat(assignment_tables, ignore_index=True).to_parquet(
        root / "scenario_assign.parquet", index=False
    )
    frequency = candidates.copy()
    frequency["selected_count"] = frequency.candidate_id.map(
        lambda i: sum(i in selection for selection in reoptimized.values())
    )
    frequency["reoptimized_scenarios"] = len(reoptimized)
    frequency["selected_in_all_solved_reoptimizations"] = frequency.selected_count == len(
        reoptimized
    )
    frequency.to_parquet(root / "station_selection_frequency.parquet", index=False)
    frequency.drop(columns=["geometry"], errors="ignore").to_csv(
        root / "station_selection_frequency.csv", index=False
    )
    planned = sum(s.network == "reoptimize" for s in scenarios)
    report = {
        "reoptimized_scenarios_solved": list(reoptimized),
        "planned_unique_reoptimizations": planned,
        "all_reoptimizations_completed": len(reoptimized) == planned,
        "selected_in_every_solved_reoptimization": frequency.loc[
            frequency.selected_in_all_solved_reoptimizations, "candidate_id"
        ].tolist(),
        "interpretation": (
            "Selection stability across checked incumbents, not proof across all optima"
        ),
        "control_aliases": {"capacity_20000": "baseline", "fixed_cost_25000": "baseline"},
    }
    (root / "robust_sites.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def main(only=None):
    base = load_config()
    root = Path(base["data"]["processed_dir"]) / "model_v2"
    root.mkdir(exist_ok=True)
    scenarios = scenario_definitions(base)
    v1_folder = Path(base["data"]["processed_dir"]) / "model_v1_full_service"
    if not (v1_folder / "summary.json").exists():
        raise FileNotFoundError("Complete the hard s=0 v1 baseline before running v2")
    legacy_folder = Path(base["data"]["processed_dir"]) / "model_v1" / "strong"
    for scenario in scenarios:
        if only is not None and scenario.name not in only:
            continue
        config = apply_scenario(base, scenario)
        data, frames = county_inputs(config, scenario.demand_multiplier, scenario.coverage_minutes)
        folder = root / scenario.name
        folder.mkdir(exist_ok=True)
        fixed, outage_info = None, {}
        if scenario.name == "baseline":
            preferred = read_solution(v1_folder)
        else:
            if not (root / "baseline" / "summary.json").exists():
                raise FileNotFoundError("Run the v2 baseline first")
            preferred = read_solution(root / "baseline")
        if scenario.network != "reoptimize":
            if scenario.network == "legacy31":
                preferred = read_solution(legacy_folder)
            fixed = {i: int(v > 0.5) for i, v in preferred["y"].items()}
            if scenario.network == "outage":
                stations = pd.read_parquet(root / "baseline" / "stations.parquet")
                stations = stations.loc[stations.opened > 0.5].copy()
                stations["rounded_load"] = stations.assigned_parcels.round(2)
                largest = stations.sort_values(
                    ["rounded_load", "candidate_id"], ascending=[False, True]
                ).iloc[0]
                fixed[largest.candidate_id] = 0
                outage_info = {
                    "closed_station": largest.candidate_id,
                    "closed_station_baseline_load": float(largest.assigned_parcels),
                    "largest_load_tie_break": (
                        "Loads rounded to 0.01 parcel; candidate ID ascending"
                    ),
                }
        signature = fingerprint(config, scenario, fixed)
        cached = folder / "summary.json"
        if cached.exists():
            old = json.loads(cached.read_text(encoding="utf-8"))
            if old.get("run_signature") != signature:
                raise ValueError(f"Cached scenario signature changed: {scenario.name}")
            result = read_solution(folder)
            check_solution(
                result["y"],
                result["x"],
                result["s"],
                data,
                w=result["w"],
                single_source=True,
                require_full_service=scenario.full_service,
                fixed_openings=fixed,
                objective=old["validation"]["objective"],
            )
            print(f"Reusing independently rechecked scenario {scenario.name}", flush=True)
            continue
        seed, audit = single_source_start(
            data, preferred, full_service=scenario.full_service, fixed_openings=fixed
        )
        (folder / "warm_start_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        print(
            f"Starting {scenario.name}: full_service={scenario.full_service}, "
            f"checked_start={seed is not None}",
            flush=True,
        )
        result = solve_model(
            data,
            "strong",
            folder,
            single_source=True,
            full_service=scenario.full_service,
            fixed_openings=fixed,
            warm_start=seed,
            time_limit_seconds=config["solver"]["time_limit_seconds"],
            relative_gap=config["solver"]["relative_gap"],
        )
        capacity = sum(
            data.capacity[i] * data.utilization_limit * value for i, value in result["y"].items()
        )
        floor = max(0.0, sum(data.demand.values()) - capacity)
        if result["validation"]["unmet_parcels"] + 0.01 < floor:
            raise ValueError("Scenario unmet demand violates aggregate capacity lower bound")
        extra = {
            "scenario": scenario.name,
            "run_signature": signature,
            "rounding_audit": audit,
            "network": scenario.network,
            "full_service": scenario.full_service,
            "demand_multiplier": scenario.demand_multiplier,
            "capacity_unmet_lower_bound": floor,
            "coverage_minutes": data.coverage_minutes,
            **outage_info,
        }
        summary = write_solution(folder, result, data, frames, extra)
        combine_outputs(root, scenarios, frames["candidates"])
        print(
            json.dumps(
                {
                    "scenario": scenario.name,
                    "validation": {
                        k: v for k, v in result["validation"].items() if k != "station_loads"
                    },
                    "solver": result["solver"],
                    "excluded_parcels": summary["excluded_parcels"],
                },
                indent=2,
            ),
            flush=True,
        )
    combine_outputs(root, scenarios, county_inputs(base)[1]["candidates"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+")
    main(parser.parse_args().only)
