"""Select routing nodes from land points and audit original-center snap distances."""

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra


def largest_routing_component(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Use a view of the largest strongly connected component without copying it."""
    nodes = max(nx.strongly_connected_components(graph), key=len)
    return graph.subgraph(nodes)


def snap_demand_points(
    graph: nx.MultiDiGraph, cells: pd.DataFrame, warning_m: float
) -> pd.DataFrame:
    """Snap both point types to the same graph, selecting route nodes for modeling."""
    required = {"h3", "route_lat", "route_lng", "lat", "lng"}
    if not required.issubset(cells.columns):
        raise ValueError("Demand cells require route_lat/route_lng and original center coordinates")
    if cells.h3.duplicated().any():
        raise ValueError("Demand cells must have unique H3 indexes")
    coordinates = cells[["route_lat", "route_lng", "lat", "lng"]].to_numpy(dtype=float)
    if not np.isfinite(coordinates).all():
        raise ValueError("Snap coordinates must be finite")
    x = np.concatenate([cells.route_lng, cells.lng])
    y = np.concatenate([cells.route_lat, cells.lat])
    points = gpd.GeoSeries(gpd.points_from_xy(x, y), crs=4326).to_crs(graph.graph["crs"])
    if points.crs.is_projected and points.crs.axis_info[0].unit_name != "metre":
        raise ValueError("Projected routing graph must use meter units")
    nodes, distances = ox.distance.nearest_nodes(
        graph, X=points.x.to_numpy(), Y=points.y.to_numpy(), return_dist=True
    )
    count = len(cells)
    result = cells.copy()
    result["route_node"] = nodes[:count]
    result["center_node"] = nodes[count:]
    result["route_snap_m"] = distances[:count]
    result["center_snap_m"] = distances[count:]
    result["node_id"] = result.route_node
    result["snap_improvement_m"] = result.center_snap_m - result.route_snap_m
    result["route_snap_warning"] = result.route_snap_m > warning_m
    result["center_snap_warning"] = result.center_snap_m > warning_m
    return result


def summarize_snap_distances(snaps: pd.DataFrame) -> dict:
    """Describe paired snap distances, including cases where route points are farther."""
    report = {
        "cells": len(snaps),
        "route_closer_cells": int((snaps.snap_improvement_m > 0).sum()),
        "route_farther_cells": int((snaps.snap_improvement_m < 0).sum()),
        "equal_distance_cells": int((snaps.snap_improvement_m == 0).sum()),
    }
    prefixes = ["route", "center"]
    if "route_edge_snap_m" in snaps:
        prefixes += ["route_edge", "route_endpoint"]
    for prefix in prefixes:
        distance = snaps[f"{prefix}_snap_m"]
        demand = float(snaps.parcels.sum())
        warning_demand = float(snaps.loc[snaps[f"{prefix}_snap_warning"], "parcels"].sum())
        report[prefix] = {
            "median_m": float(distance.median()) if len(snaps) else None,
            "p95_m": float(distance.quantile(0.95)) if len(snaps) else None,
            "max_m": float(distance.max()) if len(snaps) else None,
            "demand_weighted_mean_m": float((distance * snaps.parcels).sum() / demand)
            if demand
            else None,
            "warning_cells": int(snaps[f"{prefix}_snap_warning"].sum()),
            "warning_parcels_per_day": warning_demand,
            "warning_parcel_share": warning_demand / demand if demand else 0.0,
        }
    return report


def snap_edge_endpoints(
    graph: nx.MultiDiGraph, snaps: pd.DataFrame, warning_m: float
) -> pd.DataFrame:
    """Select the nearer endpoint of the nearest edge without changing topology.

    Edge access distance and straight-line distance to the selected model node
    are distinct measurements. The existing route_snap_m remains the nearest-
    node audit; route_node and node_id become the edge-selected endpoint.
    """
    crs = gpd.GeoSeries([], crs=graph.graph["crs"]).crs
    if not crs.is_projected or crs.axis_info[0].unit_name != "metre":
        raise ValueError("Nearest-edge distances require a projected graph in meters")
    points = gpd.GeoSeries(gpd.points_from_xy(snaps.route_lng, snaps.route_lat), crs=4326).to_crs(
        crs
    )
    edges, distances = ox.distance.nearest_edges(
        graph, X=points.x.to_numpy(), Y=points.y.to_numpy(), return_dist=True
    )
    edges = np.asarray(list(edges), dtype=np.int64).reshape(-1, 3)
    result = snaps.copy()
    result["route_nearest_node"] = result.route_node
    result[["route_edge_u", "route_edge_v", "route_edge_key"]] = edges
    u_xy = np.array([[graph.nodes[int(u)]["x"], graph.nodes[int(u)]["y"]] for u in edges[:, 0]])
    v_xy = np.array([[graph.nodes[int(v)]["x"], graph.nodes[int(v)]["y"]] for v in edges[:, 1]])
    xy = np.column_stack([points.x, points.y])
    u_dist = np.linalg.norm(xy - u_xy, axis=1)
    v_dist = np.linalg.norm(xy - v_xy, axis=1)
    # A stable ID tie-break is independent of the orientation of reciprocal edges.
    use_u = (u_dist < v_dist) | ((u_dist == v_dist) & (edges[:, 0] <= edges[:, 1]))
    result["route_endpoint_node"] = np.where(use_u, edges[:, 0], edges[:, 1])
    result["route_edge_snap_m"] = distances
    result["route_endpoint_snap_m"] = np.where(use_u, u_dist, v_dist)
    result["route_edge_snap_warning"] = result.route_edge_snap_m > warning_m
    result["route_endpoint_snap_warning"] = result.route_endpoint_snap_m > warning_m
    result["route_node"] = result.route_endpoint_node
    result["node_id"] = result.route_endpoint_node
    return result


def directed_travel_times(
    graph: nx.MultiDiGraph,
    candidates: pd.DataFrame,
    demand: pd.DataFrame,
    congestion_multiplier: float,
    batch_size: int = 16,
) -> pd.DataFrame:
    """Station-to-demand shortest times; parallel edges use their minimum weight.

    Dijkstra runs on the directed graph with free-flow seconds, then applies the
    configured congestion multiplier. Full OD pairs are retained for auditing;
    the pipeline separately exports a model table within its 45-minute cutoff.
    """
    node_ids = list(graph.nodes)
    positions = {node: i for i, node in enumerate(node_ids)}
    rows, cols, weights = [], [], []
    for u, v, data in graph.edges(data=True):
        weight = float(data["travel_time"])
        if not np.isfinite(weight) or weight < 0:
            raise ValueError("Every directed edge requires finite nonnegative travel_time seconds")
        rows.append(positions[u])
        cols.append(positions[v])
        weights.append(weight)
    edges = pd.DataFrame({"u": rows, "v": cols, "seconds": weights})
    minimum = edges.groupby(["u", "v"], sort=False).seconds.min().reset_index()
    matrix = csr_matrix(
        (minimum.seconds, (minimum.u, minimum.v)), shape=(len(node_ids), len(node_ids))
    )
    targets = np.array([positions[node] for node in demand.node_id])
    chunks = []
    for start in range(0, len(candidates), batch_size):
        batch = candidates.iloc[start : start + batch_size]
        origins = np.array([positions[node] for node in batch.node_id])
        distances = dijkstra(matrix, directed=True, indices=origins)[:, targets]
        chunks.append(
            pd.DataFrame(
                {
                    "candidate_id": np.repeat(batch.candidate_id.to_numpy(), len(demand)),
                    "h3": np.tile(demand.h3.to_numpy(), len(batch)),
                    "from_node": np.repeat(batch.node_id.to_numpy(), len(demand)),
                    "to_node": np.tile(demand.node_id.to_numpy(), len(batch)),
                    "free_flow_time_min": distances.ravel() / 60,
                    "travel_time_min": distances.ravel() * congestion_multiplier / 60,
                }
            )
        )
        print(
            f"Travel times: {min(start + batch_size, len(candidates))}/{len(candidates)} stations",
            flush=True,
        )
    result = pd.concat(chunks, ignore_index=True)
    if result.duplicated(["candidate_id", "h3"]).any():
        raise ValueError("Duplicate candidate-demand OD pairs")
    return result
