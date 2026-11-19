"""Shared county input/output and checked feasible starts for model experiments."""

import json
from pathlib import Path

import networkx as nx
import pandas as pd

from lanet.check import check_solution
from lanet.problem import FacilityData


def county_inputs(config, demand_multiplier=1.0, coverage_minutes=None):
    processed = Path(config["data"]["processed_dir"])
    candidates = pd.read_parquet(processed / "candidates.parquet")
    demand = pd.read_parquet(processed / "demand_cells.parquet").copy()
    demand["parcels"] *= demand_multiplier
    travel = pd.read_parquet(processed / "travel_times.parquet")
    # Keep the baseline's 1,615-cell universe across every scenario, including outage.
    modeled = set(travel.loc[travel.travel_time_min <= config["travel"]["coverage_minutes"], "h3"])
    excluded = demand.loc[~demand.h3.isin(modeled)].copy()
    demand = demand.loc[demand.h3.isin(modeled)].copy()
    cutoff = (
        coverage_minutes if coverage_minutes is not None else config["travel"]["coverage_minutes"]
    )
    travel = travel.loc[travel.h3.isin(modeled) & (travel.travel_time_min <= cutoff)].copy()
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
        coverage_minutes=cutoff,
    )
    return data, {"candidates": candidates, "demand": demand, "excluded": excluded}


def read_solution(folder):
    folder = Path(folder)
    stations = pd.read_parquet(folder / "stations.parquet")
    assignments = pd.read_parquet(folder / "assignments.parquet")
    unmet = pd.read_parquet(folder / "unmet.parquet")
    return {
        "y": stations.set_index("candidate_id").opened.to_dict(),
        "x": assignments.set_index(["candidate_id", "h3"]).fraction.to_dict(),
        "s": unmet.set_index("h3").s.to_dict(),
        "w": assignments.set_index(["candidate_id", "h3"]).w.to_dict()
        if "w" in assignments
        else {},
    }


def write_solution(folder, result, data, frames, extra=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    summary = {"validation": result["validation"], "solver": result["solver"], **(extra or {})}
    stations = frames["candidates"].copy()
    stations["opened"] = stations.candidate_id.map(result["y"])
    stations["assigned_parcels"] = stations.candidate_id.map(result["validation"]["station_loads"])
    stations["capacity"] = stations.candidate_id.map(data.capacity)
    stations["utilization"] = stations.assigned_parcels / stations.capacity
    stations.to_parquet(folder / "stations.parquet", index=False)
    assignments = pd.DataFrame(
        [
            {
                "candidate_id": i,
                "h3": j,
                "fraction": fraction,
                "parcels": data.demand[j] * fraction,
                "travel_time_min": data.travel_minutes[i, j],
                **({"w": result["w"].get((i, j), 0)} if result.get("w") else {}),
            }
            for (i, j), fraction in result["x"].items()
        ]
    )
    assignments.to_parquet(folder / "assignments.parquet", index=False)
    unmet = frames["demand"].copy()
    unmet["s"] = unmet.h3.map(result["s"])
    unmet["unmet_parcels"] = unmet.parcels * unmet.s
    unmet.to_parquet(folder / "unmet.parquet", index=False)
    frames["excluded"].to_csv(folder / "structurally_uncovered.csv", index=False)
    summary["excluded_cells"] = len(frames["excluded"])
    summary["excluded_parcels"] = float(frames["excluded"].parcels.sum())
    summary["study_area_unmet_parcels"] = (
        summary["excluded_parcels"] + result["validation"]["unmet_parcels"]
    )
    summary["split_cells"] = int(
        assignments.loc[assignments.fraction > 1e-6].groupby("h3").size().gt(1).sum()
    )
    (folder / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def continuous_full_service_start(data, preferred):
    """Repair the penalized v1 network with additional sites and a feasible flow."""
    opened = {i for i, value in preferred["y"].items() if value > 0.5}
    by_station = {i: [] for i in data.capacity}
    for i, j in data.unit_cost:
        by_station[i].append(j)
    while True:
        source, sink = ("source",), ("sink",)
        graph = nx.DiGraph()
        for i in opened:
            graph.add_edge(source, ("i", i), capacity=data.capacity[i] * data.utilization_limit)
            for j in by_station[i]:
                graph.add_edge(("i", i), ("j", j), capacity=data.demand[j])
        for j, demand in data.demand.items():
            graph.add_edge(("j", j), sink, capacity=demand)
        _, flow = nx.maximum_flow(graph, source, sink)
        short = {j: max(0, demand - flow[("j", j)][sink]) for j, demand in data.demand.items()}
        if all(short[j] <= max(1e-10, data.demand[j] * 1e-7) for j in data.demand):
            x = {
                (i, j): flow.get(("i", i), {}).get(("j", j), 0) / data.demand[j]
                for i, j in data.unit_cost
            }
            seed = {
                "y": {i: int(i in opened) for i in data.capacity},
                "x": x,
                "s": dict.fromkeys(data.demand, 0),
            }
            check_solution(seed["y"], seed["x"], seed["s"], data, require_full_service=True)
            return seed
        closed = [i for i in data.capacity if i not in opened]
        if not closed:
            raise ValueError("All-candidate flow cannot meet hard full-service demand")
        closed.sort(key=lambda i: (-sum(short[j] for j in by_station[i]) / data.fixed_cost[i], i))
        opened.add(closed[0])
