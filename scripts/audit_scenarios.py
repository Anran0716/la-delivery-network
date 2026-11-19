"""Recheck scenario exports and compare actual outcomes to prior predictions."""

import argparse
import json
import math
from pathlib import Path

import networkx as nx
import pandas as pd

from lanet import load_config
from lanet.check import check_solution
from lanet.experiments import county_inputs, read_solution
from lanet.scenarios import apply_scenario, scenario_definitions


def flow_shortfall(data, openings):
    graph = nx.DiGraph()
    source, sink = ("source",), ("sink",)
    for i, value in openings.items():
        if value > 0.5:
            graph.add_edge(source, ("i", i), capacity=data.capacity[i] * data.utilization_limit)
    for j, demand in data.demand.items():
        graph.add_edge(("j", j), sink, capacity=demand)
    for i, j in data.unit_cost:
        if openings[i] > 0.5:
            graph.add_edge(("i", i), ("j", j), capacity=data.demand[j])
    return max(0.0, sum(data.demand.values()) - nx.maximum_flow_value(graph, source, sink))


def main(allow_partial=False):
    base = load_config()
    processed = Path(base["data"]["processed_dir"])
    root = processed / "model_v2"
    baseline = read_solution(root / "baseline")
    legacy = read_solution(processed / "model_v1" / "strong")
    report = {"checks_passed": True, "scenarios": {}, "predictions": {}}
    definitions = scenario_definitions(base)
    for scenario in definitions:
        folder = root / scenario.name
        if not (folder / "summary.json").exists() and allow_partial:
            continue
        summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        config = apply_scenario(base, scenario)
        data, frames = county_inputs(config, scenario.demand_multiplier, scenario.coverage_minutes)
        result = read_solution(folder)
        fixed = None
        if scenario.network != "reoptimize":
            source = legacy if scenario.network == "legacy31" else baseline
            fixed = {i: int(v > 0.5) for i, v in source["y"].items()}
            if scenario.network == "outage":
                fixed[summary["closed_station"]] = 0
        checked = check_solution(
            result["y"],
            result["x"],
            result["s"],
            data,
            w=result["w"],
            single_source=True,
            require_full_service=scenario.full_service,
            fixed_openings=fixed,
            objective=summary["validation"]["objective"],
        )
        detail = {k: v for k, v in checked.items() if k != "station_loads"}
        log = (folder / "cbc.log").read_text(encoding="utf-8")
        detail["warm_start_values_read"] = "MIPStart values read for" in log
        detail["warm_start_accepted_by_cbc"] = "MIPStart provided solution with cost" in log
        warm_cost = summary["solver"]["warm_start_objective"]
        detail["improvement_over_checked_start"] = (
            warm_cost - checked["objective"] if warm_cost is not None else None
        )
        detail["improved_checked_start"] = (
            detail["improvement_over_checked_start"] > 0.05 if warm_cost is not None else None
        )
        if fixed is not None:
            detail["continuous_maxflow_unmet_lower_bound"] = flow_shortfall(data, fixed)
            assert checked["unmet_parcels"] + 0.01 >= detail["continuous_maxflow_unmet_lower_bound"]
        else:
            lower = math.ceil(
                sum(data.demand.values())
                / (next(iter(data.capacity.values())) * data.utilization_limit)
            )
            assert checked["open_stations"] >= lower
            detail["capacity_station_lower_bound"] = lower
        assert len(frames["demand"]) == 1615 and len(frames["excluded"]) == 250
        assert summary["split_cells"] == 0
        report["scenarios"][scenario.name] = detail
    assignments = pd.read_parquet(root / "scenario_assign.parquet")
    station_tables = pd.read_parquet(root / "scenario_stations.parquet")
    assert set(assignments.scenario) == set(report["scenarios"])
    assert set(station_tables.scenario) == set(report["scenarios"])
    report["combined_exports"] = {}
    for name, checked in report["scenarios"].items():
        cells = assignments.loc[assignments.scenario == name]
        stations = station_tables.loc[station_tables.scenario == name]
        assert len(cells) == cells.h3.nunique() == 1865
        assert len(stations) == stations.candidate_id.nunique() == 117
        assert cells.in_model.sum() == 1615
        assert cells.loc[~cells.in_model, "solver_s"].isna().all()
        assert cells.loc[cells.in_model, "solver_s"].notna().all()
        assert (cells.served_parcels >= -0.01).all()
        assert (cells.unmet_parcels >= -0.01).all()
        residual = (cells.served_parcels + cells.unmet_parcels - cells.demand_parcels).abs()
        assert residual.max() <= 0.01
        assert abs(cells.served_parcels.sum() - checked["served_parcels"]) <= 0.01
        modeled = cells.loc[cells.in_model]
        assert abs(modeled.unmet_parcels.sum() - checked["unmet_parcels"]) <= 0.01
        assigned_load = cells.groupby("candidate_id").served_parcels.sum()
        differences = stations.set_index("candidate_id").assigned_parcels - assigned_load.reindex(
            stations.candidate_id, fill_value=0
        )
        assert differences.abs().max() <= 0.01
        report["combined_exports"][name] = {
            "unique_cells": len(cells),
            "modeled_cells": int(cells.in_model.sum()),
            "structural_exclusions": int((~cells.in_model).sum()),
            "maximum_cell_balance_error": float(residual.max()),
            "maximum_station_load_error": float(differences.abs().max()),
            "study_area_unmet_parcels": float(cells.unmet_parcels.sum()),
        }
    if "outage" in report["scenarios"]:
        columns = ["h3", "candidate_id", "served_parcels", "travel_time_min"]
        before = assignments.loc[
            (assignments.scenario == "baseline") & assignments.in_model, columns
        ]
        after = assignments.loc[(assignments.scenario == "outage") & assignments.in_model, columns]
        paired = before.merge(after, on="h3", suffixes=("_base", "_outage"), validate="one_to_one")
        changed = paired.loc[paired.candidate_id_base != paired.candidate_id_outage]
        delta = (
            changed.served_parcels_outage * changed.travel_time_min_outage
            - changed.served_parcels_base * changed.travel_time_min_base
        )
        report["outage_diagnostic"] = {
            "changed_provider_cells": len(changed),
            "changed_provider_baseline_parcels": float(changed.served_parcels_base.sum()),
            "positive_parcel_minute_change": float(delta.loc[delta > 0].sum()),
            "negative_parcel_minute_change": float(delta.loc[delta < 0].sum()),
            "served_arcs_above_30_minutes": int(
                ((after.travel_time_min > 30) & (after.served_parcels > 0)).sum()
            ),
            "interpretation": "Outage also relaxes utilization and coverage; effects are combined",
        }
    b = report["scenarios"]["baseline"]
    baseline_ids = {i for i, value in baseline["y"].items() if value > 0.5}
    base_data, _ = county_inputs(base)
    providers = {j: [] for j in base_data.demand}
    for i, j in base_data.unit_cost:
        providers[j].append(i)
    single_provider_cells = {j: options[0] for j, options in providers.items() if len(options) == 1}
    forced_sites = set(single_provider_cells.values())
    legacy_ids = {i for i, value in legacy["y"].items() if value > 0.5}
    report["coverage_forced_sites"] = {
        "single_candidate_cells": len(single_provider_cells),
        "station_ids": sorted(forced_sites),
        "not_open_in_old_penalized_network": sorted(forced_sites - legacy_ids),
        "interpretation": "Required for every full-service solution under the same 30-minute arcs",
    }
    for cost in (15000, 40000):
        if f"fixed_cost_{cost}" not in report["scenarios"]:
            continue
        row = report["scenarios"][f"fixed_cost_{cost}"]
        change = row["open_stations"] - b["open_stations"]
        transferred = b["open_stations"] * cost + b["delivery_cost"]
        alternative = read_solution(root / f"fixed_cost_{cost}")
        alternative_ids = {i for i, value in alternative["y"].items() if value > 0.5}
        base_data, _ = county_inputs(base)
        transferred_check = check_solution(
            alternative["y"],
            alternative["x"],
            alternative["s"],
            base_data,
            w=alternative["w"],
            single_source=True,
            require_full_service=True,
        )
        report["predictions"][f"fixed_cost_{cost}"] = {
            "station_change": change,
            "within_one_station_prediction": abs(change) <= 1,
            "baseline_plan_cost_at_new_fee": transferred,
            "scenario_plan_cost_at_baseline_fee": transferred_check["objective"],
            "alternative_improves_baseline_incumbent": transferred_check["objective"]
            < b["objective"] - 0.05,
            "locations_added": sorted(alternative_ids - baseline_ids),
            "locations_removed": sorted(baseline_ids - alternative_ids),
            "fixed_cost_change_component": change * cost,
            "delivery_cost_change_component": row["delivery_cost"] - b["delivery_cost"],
            "objective_change_vs_transferred_baseline": row["objective"] - transferred,
            "material_change_review": (
                "Same demand, coverage, capacity and hard service; "
                "assess cost components and solver gaps"
                if abs(change) > 1
                else "No material station-count change under preregistered threshold"
            ),
        }
    if "peak_reoptimized" in report["scenarios"]:
        peak = report["scenarios"]["peak_reoptimized"]
        report["predictions"]["peak_reoptimization"] = {
            "minimum_stations": 42,
            "observed_stations": peak["open_stations"],
            "capacity_prediction_satisfied": peak["open_stations"] >= 42,
        }
    if "legacy31_peak_fixed" in report["scenarios"]:
        old_peak = report["scenarios"]["legacy31_peak_fixed"]
        predicted_gap = old_peak["total_demand_parcels"] - 620000
        report["predictions"]["legacy31_peak"] = {
            "predicted_capacity_shortfall": predicted_gap,
            "observed_unmet_parcels": old_peak["unmet_parcels"],
            "observed_unmet_share": old_peak["unmet_parcels"] / old_peak["total_demand_parcels"],
            "lower_bound_satisfied": old_peak["unmet_parcels"] + 0.01 >= predicted_gap,
        }
    v1 = json.loads(
        (processed / "model_v1_full_service" / "summary.json").read_text(encoding="utf-8")
    )
    v2 = json.loads((root / "baseline" / "summary.json").read_text(encoding="utf-8"))
    # The v2 incumbent is also feasible for v1. Bound comparisons avoid claiming
    # a negative operational premium when incumbents have different quality.
    report["v1_v2_comparison"] = {
        "v1_split_cells": v1["split_cells"],
        "v2_split_cells": v2["split_cells"],
        "incumbent_objective_difference": b["objective"] - v1["validation"]["objective"],
        "incumbent_station_difference": b["open_stations"] - v1["validation"]["open_stations"],
        "premium_lower_bound": max(
            0.0, v2["solver"]["best_bound"] - min(b["objective"], v1["validation"]["objective"])
        ),
        "premium_upper_bound": b["objective"] - v1["solver"]["best_bound"],
        "interpretation": "Incumbent differences are not exact optimal-policy premiums",
    }
    report["all_scenarios_completed"] = len(report["scenarios"]) == len(definitions)
    stability = json.loads((root / "robust_sites.json").read_text(encoding="utf-8"))
    frequency = pd.read_parquet(root / "station_selection_frequency.parquet")
    solved_reoptimizations = [
        s.name for s in definitions if s.network == "reoptimize" and s.name in report["scenarios"]
    ]
    assert stability["reoptimized_scenarios_solved"] == solved_reoptimizations
    for row in frequency.itertuples():
        observed = (
            station_tables.loc[
                station_tables.scenario.isin(solved_reoptimizations)
                & (station_tables.candidate_id == row.candidate_id),
                "opened",
            ]
            .gt(0.5)
            .sum()
        )
        assert observed == row.selected_count
        assert row.reoptimized_scenarios == len(solved_reoptimizations)
        assert row.selected_in_all_solved_reoptimizations == (
            observed == len(solved_reoptimizations)
        )
    stable_ids = set(
        frequency.loc[frequency.selected_count == len(solved_reoptimizations), "candidate_id"]
    )
    assert stable_ids == set(stability["selected_in_every_solved_reoptimization"])
    assert forced_sites <= stable_ids
    report["selection_stability"] = stability
    name = "scenario_audit_partial.json" if allow_partial else "scenario_audit.json"
    (root / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-partial", action="store_true")
    main(parser.parse_args().allow_partial)
