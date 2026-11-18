"""Select routing nodes from land points and audit original-center snap distances."""

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd


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
    for prefix in ("route", "center"):
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
