"""Distinguish selected-network gaps from all-candidate capacity infeasibility."""

import json
from pathlib import Path

import networkx as nx
import pandas as pd

from lanet import load_config


def maximum_served(demand, arcs, station_ids, usable_capacity):
    graph = nx.DiGraph()
    source, sink = ("source",), ("sink",)
    for station in station_ids:
        graph.add_edge(source, ("station", station), capacity=usable_capacity)
    for cell, parcels in demand.items():
        graph.add_edge(("cell", cell), sink, capacity=parcels)
    for row in arcs.loc[arcs.candidate_id.isin(station_ids)].itertuples():
        graph.add_edge(("station", row.candidate_id), ("cell", row.h3), capacity=demand[row.h3])
    return nx.maximum_flow_value(graph, source, sink)


def main():
    config = load_config()
    processed = Path(config["data"]["processed_dir"])
    folder = processed / "model_v1"
    demand_table = pd.read_parquet(processed / "demand_cells.parquet")
    arcs = pd.read_parquet(processed / "travel_times.parquet")
    arcs = arcs.loc[arcs.travel_time_min <= config["travel"]["coverage_minutes"]]
    demand = demand_table.loc[demand_table.h3.isin(arcs.h3)].set_index("h3").parcels.to_dict()
    station_ids = pd.read_parquet(processed / "candidates.parquet").candidate_id.tolist()
    usable = (
        config["facility"]["capacity_parcels_per_day"] * config["facility"]["utilization_limit"]
    )
    total = sum(demand.values())
    served_all = maximum_served(demand, arcs, station_ids, usable)
    report = {
        "modeled_demand_parcels": total,
        "maxflow_served_with_all_candidates": served_all,
        "all_candidate_capacity_shortfall": max(0, total - served_all),
        "all_candidate_full_service_feasible": total - served_all <= 0.01,
        "linkings": {},
    }
    for linking in ("strong", "weak"):
        stations = pd.read_parquet(folder / linking / "stations.parquet")
        cells = pd.read_parquet(folder / linking / "unmet.parquet")
        opened = stations.loc[stations.opened > 0.5].candidate_id.tolist()
        reached = set(arcs.loc[arcs.candidate_id.isin(opened), "h3"])
        positive = cells.loc[cells.s > 1e-6]
        served_open = maximum_served(demand, arcs, opened, usable)
        detail = {
            "positive_s_cells": len(positive),
            "positive_s_cells_without_open_candidate": int((~positive.h3.isin(reached)).sum()),
            "all_positive_s_are_one": bool(positive.s.eq(1).all()),
            "positive_s_low_demand_cells": int(positive.low_demand.sum()),
            "unmet_parcels": float(positive.unmet_parcels.sum()),
            "unmet_penalty_cost": float(
                positive.unmet_parcels.sum() * config["cost"]["unmet_penalty_usd_per_parcel"]
            ),
            "maxflow_shortfall_of_selected_network": max(0, total - served_open),
            "maximum_station_load": float(stations.assigned_parcels.max()),
        }
        report["linkings"][linking] = detail
        positive.to_csv(folder / linking / "positive_s_diagnostic.csv", index=False)
    (folder / "unmet_diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
