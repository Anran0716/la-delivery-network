"""Recheck scenario exports and compare actual outcomes to prior predictions."""

import json
import math
from pathlib import Path

import networkx as nx

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


def main():
    base = load_config()
    processed = Path(base["data"]["processed_dir"])
    root = processed / "model_v2"
    baseline = read_solution(root / "baseline")
    legacy = read_solution(processed / "model_v1" / "strong")
    report = {"checks_passed": True, "scenarios": {}, "predictions": {}}
    for scenario in scenario_definitions(base):
        folder = root / scenario.name
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
        report["scenarios"][scenario.name] = detail
    b = report["scenarios"]["baseline"]
    for cost in (15000, 40000):
        row = report["scenarios"][f"fixed_cost_{cost}"]
        change = row["open_stations"] - b["open_stations"]
        transferred = b["open_stations"] * cost + b["delivery_cost"]
        report["predictions"][f"fixed_cost_{cost}"] = {
            "station_change": change,
            "within_one_station_prediction": abs(change) <= 1,
            "baseline_plan_cost_at_new_fee": transferred,
            "scenario_plan_cost_at_baseline_fee": row["open_stations"] * 25000
            + row["delivery_cost"],
            "fixed_cost_change_component": change * cost,
            "delivery_cost_change_component": row["delivery_cost"] - b["delivery_cost"],
            "objective_change_vs_transferred_baseline": row["objective"] - transferred,
        }
    peak = report["scenarios"]["peak_reoptimized"]
    old_peak = report["scenarios"]["legacy31_peak_fixed"]
    report["predictions"]["peak_reoptimization"] = {
        "minimum_stations": 42,
        "observed_stations": peak["open_stations"],
        "capacity_prediction_satisfied": peak["open_stations"] >= 42,
    }
    predicted_gap = peak["total_demand_parcels"] - 620000
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
    (root / "scenario_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
