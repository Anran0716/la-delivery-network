"""Compare both demand point types on the cached graph; select land-route nodes."""

import argparse
import json
import pickle
from pathlib import Path

import osmnx as ox
import pandas as pd

from lanet import load_config
from lanet.travel import (
    largest_routing_component,
    snap_demand_points,
    snap_edge_endpoints,
    summarize_snap_distances,
)


def main(config_path: str) -> None:
    path = Path(config_path).resolve()
    config = load_config(path)
    if config["travel"]["snap_point"] != "route":
        raise ValueError("Production snapping must use route_lat/route_lng")
    if config["travel"]["graph_component"] != "largest_strongly_connected":
        raise ValueError("Unsupported routing component policy")
    raw = path.parent / config["data"]["raw_dir"]
    processed = path.parent / config["data"]["processed_dir"]
    graph_path = raw / config["travel"]["graph_filename"]
    pickle_path = graph_path.with_suffix(".pickle")
    if pickle_path.exists():
        # This is the binary cache generated locally by download_drive_graph.py.
        with pickle_path.open("rb") as stream:
            graph = pickle.load(stream)
    else:
        graph = ox.load_graphml(graph_path)
    raw_nodes, raw_edges = len(graph), graph.number_of_edges()
    graph = largest_routing_component(graph)
    graph = ox.project_graph(graph, to_crs=config["study"]["projected_crs"])
    print(f"Routing component: {len(graph)} nodes, {graph.number_of_edges()} edges", flush=True)
    cells = pd.read_parquet(processed / "demand_cells.parquet")
    snaps = snap_demand_points(graph, cells, config["travel"]["snap_warning_m"])
    snaps = snap_edge_endpoints(graph, snaps, config["travel"]["snap_warning_m"])
    snaps.to_parquet(processed / "demand_snaps.parquet", index=False)
    snaps.to_csv(processed / "demand_snaps.csv", index=False)
    report = {
        "model_point": "route_lat/route_lng",
        "selected_node_column": "node_id = route_endpoint_node = route_node",
        "distance_definition": (
            "EPSG:3310 point-to-nearest-node, nearest-edge and selected-endpoint meters"
        ),
        "warning_threshold_m": config["travel"]["snap_warning_m"],
        "raw_graph_nodes": raw_nodes,
        "raw_graph_edges": raw_edges,
        "routing_component_nodes": len(graph),
        "routing_component_edges": graph.number_of_edges(),
        "all_cells": summarize_snap_distances(snaps),
        "marine_center_cells": summarize_snap_distances(snaps.loc[snaps.center_in_sea]),
        "low_demand_cells": summarize_snap_distances(snaps.loc[snaps.low_demand]),
    }
    warnings = snaps.loc[snaps.route_edge_snap_warning].copy()
    warnings["household_band"] = pd.cut(
        warnings.households,
        [0, 1, 1 / config["demand"]["parcels_per_household_per_day"], 100, 1000, float("inf")],
        right=False,
        labels=[
            "under_1",
            "1_to_low_demand_threshold",
            "threshold_to_100",
            "100_to_1000",
            "1000_plus",
        ],
    )
    groups = warnings.groupby("household_band", observed=False).agg(
        cells=("h3", "size"), households=("households", "sum"), parcels=("parcels", "sum")
    )
    groups.to_csv(processed / "edge_warning_household_groups.csv")
    warnings.to_csv(processed / "route_edge_warnings.csv", index=False)
    report["edge_warning_groups"] = groups.reset_index().to_dict("records")
    report["edge_warnings_low_demand_cells"] = int(warnings.low_demand.sum())
    report["edge_warning_household_share"] = float(
        warnings.households.sum() / snaps.households.sum()
    )
    manifest = json.loads((raw / "drive_graph_manifest.json").read_text(encoding="utf-8"))
    report["graph_source"] = manifest["source"]
    report["graph_file"] = manifest["graph"]
    if "pbf_sha256" in manifest:
        report["pbf_sha256"] = manifest["pbf_sha256"]
    if "pbf_replication_timestamp" in manifest:
        report["pbf_replication_timestamp"] = manifest["pbf_replication_timestamp"]
    (processed / "snap_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    main(parser.parse_args().config)
