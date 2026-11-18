"""Generate county industrial candidates and directed station-to-demand times."""

import argparse
import json
import pickle
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd

from lanet import load_config
from lanet.candidates import select_industrial_candidates
from lanet.travel import directed_travel_times, largest_routing_component, snap_edge_endpoints


def main(config_path: str) -> None:
    path = Path(config_path).resolve()
    config = load_config(path)
    if config["candidates"]["boundary_scope"] != "county":
        raise ValueError("Candidates must stay inside the county")
    if config["travel"]["snap_method"] != "nearest_edge_endpoint":
        raise ValueError("Model nodes must use the nearest edge's nearer endpoint")
    if config["travel"]["speed_imputation"] != "highway_mean":
        raise ValueError("Unsupported speed imputation policy")
    raw = path.parent / config["data"]["raw_dir"]
    processed = path.parent / config["data"]["processed_dir"]
    demand = pd.read_parquet(processed / "demand_snaps.parquet")
    if not demand.node_id.equals(demand.route_endpoint_node):
        raise ValueError("Rerun compare_snaps.py to select edge-endpoint demand nodes")
    mainland = gpd.read_parquet(processed / "mainland_block_groups.parquet").to_crs(
        config["study"]["projected_crs"]
    )
    boundary = gpd.GeoDataFrame(geometry=[mainland.geometry.union_all()], crs=mainland.crs)
    layers = sorted((raw / "osm_landuse").glob("*landuse*.shp"))
    if not layers:
        raise FileNotFoundError("Run scripts/download_landuse.py first")
    industrial = gpd.GeoDataFrame(
        pd.concat([gpd.read_file(layer, where="fclass = 'industrial'") for layer in layers]),
        crs=4326,
    )
    points, candidate_report = select_industrial_candidates(
        industrial,
        boundary,
        config["candidates"]["min_area_hectares"],
        config["candidates"]["min_spacing_m"],
        config["candidates"]["max_candidates"],
    )
    if points.empty:
        raise ValueError("No eligible industrial candidates; inspect source coverage")
    graph_path = raw / config["travel"]["graph_filename"]
    with graph_path.with_suffix(".pickle").open("rb") as stream:
        graph = pickle.load(stream)  # Only the locally generated raw graph cache.
    graph = largest_routing_component(graph)
    graph = ox.project_graph(graph, to_crs=config["study"]["projected_crs"])
    print(f"Routing graph: {len(graph)} nodes; {len(points)} spatial candidates", flush=True)
    points = points.reset_index(drop=True)
    points["candidate_id"] = [f"C{i + 1:03d}" for i in range(len(points))]
    geographic = points.to_crs(4326)
    points["route_lat"] = geographic.geometry.y.to_numpy()
    points["route_lng"] = geographic.geometry.x.to_numpy()
    nodes, distance = ox.distance.nearest_nodes(
        graph, X=points.geometry.x, Y=points.geometry.y, return_dist=True
    )
    points["route_node"] = nodes
    points["route_snap_m"] = distance
    points["route_snap_warning"] = points.route_snap_m > config["travel"]["snap_warning_m"]
    points = snap_edge_endpoints(graph, points, config["travel"]["snap_warning_m"])
    duplicate_nodes = int(points.node_id.duplicated().sum())
    points = points.drop_duplicates("node_id").reset_index(drop=True)
    if not points.geometry.covered_by(boundary.geometry.iloc[0]).all():
        raise ValueError("A candidate location escaped the county mainland land boundary")
    points.to_crs(4326).to_parquet(processed / "candidates.parquet", index=False)
    points.drop(columns="geometry").to_csv(processed / "candidates.csv", index=False)
    before_nodes, before_edges = len(graph), graph.number_of_edges()
    graph = ox.routing.add_edge_speeds(graph, fallback=config["travel"]["speed_fallback_kph"])
    graph = ox.routing.add_edge_travel_times(graph)
    if (len(graph), graph.number_of_edges()) != (before_nodes, before_edges):
        raise ValueError("Travel-time preparation changed graph topology")
    times = directed_travel_times(graph, points, demand, config["travel"]["congestion_multiplier"])
    times["within_30_min"] = times.travel_time_min <= config["travel"]["coverage_minutes"]
    all_path = processed / "travel_times_all.parquet"
    times.to_parquet(all_path, index=False)
    cutoff = config["travel"]["matrix_cutoff_minutes"]
    model_times = times.loc[times.travel_time_min <= cutoff].copy()
    model_times.to_parquet(processed / "travel_times.parquet", index=False)
    model_times.to_csv(processed / "travel_times.csv", index=False)
    reachable = times.loc[times.within_30_min].groupby("h3").candidate_id.nunique()
    coverage = demand.copy()
    coverage["candidates_within_30_min"] = coverage.h3.map(reachable).fillna(0).astype(int)
    coverage["minimum_travel_time_min"] = coverage.h3.map(times.groupby("h3").travel_time_min.min())
    coverage.to_parquet(processed / "demand_coverage.parquet", index=False)
    uncovered = coverage.loc[coverage.candidates_within_30_min == 0]
    uncovered.to_csv(processed / "uncovered_30min_cells.csv", index=False)
    edge_data = pd.DataFrame([data for _, _, data in graph.edges(data=True)])
    report = {
        "candidate_selection": {
            **candidate_report,
            "duplicate_routing_nodes_removed": duplicate_nodes,
        },
        "candidate_count": len(points),
        "demand_cells": len(demand),
        "low_demand_cells_retained": int(demand.low_demand.sum()),
        "mainland_households": float(demand.households.sum()),
        "daily_parcels": float(demand.parcels.sum()),
        "rows_all_pairs": len(times),
        "rows_finite": int(np.isfinite(times.travel_time_min).sum()),
        "rows_within_30_min": int(times.within_30_min.sum()),
        "rows_within_45_min": len(model_times),
        "uncovered_30_min_cells": len(uncovered),
        "uncovered_30_min_households": float(uncovered.households.sum()),
        "uncovered_30_min_household_share": float(
            uncovered.households.sum() / demand.households.sum()
        ),
        "uncovered_30_min_parcels": float(uncovered.parcels.sum()),
        "route_edge_warning_cells": int(demand.route_edge_snap_warning.sum()),
        "routing_nodes": len(graph),
        "routing_edges": graph.number_of_edges(),
        "congestion_multiplier": config["travel"]["congestion_multiplier"],
        "time_definition": (
            "Directed station-to-demand road seconds / 60 * congestion; no access leg"
        ),
        "speed_policy": (
            "OSM maxspeed; missing values imputed by highway mean, fallback from config"
        ),
        "speed_fallback_kph": config["travel"]["speed_fallback_kph"],
        "speed_kph_min": float(edge_data.speed_kph.min()),
        "speed_kph_max": float(edge_data.speed_kph.max()),
        "candidate_edge_warning_cells": int(points.route_edge_snap_warning.sum()),
        "candidate_endpoint_warning_cells": int(points.route_endpoint_snap_warning.sum()),
    }
    (processed / "travel_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (processed / "drive_time_graph.pickle").open("wb") as stream:
        pickle.dump(graph, stream, protocol=pickle.HIGHEST_PROTOCOL)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    main(parser.parse_args().config)
