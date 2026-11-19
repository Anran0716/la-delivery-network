"""Independently verify saved OD results, station constraints, and demand retention."""

import json
import pickle
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import networkx as nx
import numpy as np
import osmium
import pandas as pd
from scipy.spatial.distance import pdist

from lanet import load_config


def main():
    config = load_config()
    processed = Path(config["data"]["processed_dir"])
    raw = Path(config["data"]["raw_dir"])
    original = pd.read_parquet(processed / "demand_cells.parquet")
    demand = pd.read_parquet(processed / "demand_snaps.parquet")
    candidates = gpd.read_parquet(processed / "candidates.parquet").to_crs(
        config["study"]["projected_crs"]
    )
    times = pd.read_parquet(processed / "travel_times_all.parquet")
    model_times = pd.read_parquet(processed / "travel_times.parquet")
    with (processed / "drive_time_graph.pickle").open("rb") as stream:
        graph = pickle.load(stream)  # Only the locally generated cache.
    edge_seconds = np.fromiter(
        (float(data["travel_time"]) for _, _, data in graph.edges(data=True)), dtype=float
    )
    zero_time_edges = int((edge_seconds == 0).sum())
    if zero_time_edges:
        raise ValueError(
            f"Zero-time edges require review before sparse conversion: {zero_time_edges}"
        )
    assert demand.h3.equals(original.h3)
    assert demand.households.equals(original.households)
    assert demand.parcels.equals(original.parcels)
    assert demand.node_id.equals(demand.route_endpoint_node)
    assert demand.low_demand.equals(demand.parcels < 1)
    assert np.isfinite(times.travel_time_min).all()
    assert (times.travel_time_min >= 0).all()
    assert len(times) == len(candidates) * len(demand)
    assert not times.duplicated(["candidate_id", "h3"]).any()
    assert set(times.candidate_id) == set(candidates.candidate_id)
    assert set(times.h3) == set(demand.h3)
    assert np.allclose(
        times.travel_time_min,
        times.free_flow_time_min * config["travel"]["congestion_multiplier"],
    )
    assert (
        len(model_times)
        == (times.travel_time_min <= config["travel"]["matrix_cutoff_minutes"]).sum()
    )
    boundary = gpd.read_parquet(processed / "mainland_block_groups.parquet").to_crs(candidates.crs)
    assert candidates.geometry.covered_by(boundary.geometry.union_all()).all()
    assert candidates.node_id.is_unique
    assert (candidates.area_m2 >= config["candidates"]["min_area_hectares"] * 10000).all()
    minimum_spacing = float(
        pdist(np.column_stack([candidates.geometry.x, candidates.geometry.y])).min()
    )
    assert minimum_spacing >= config["candidates"]["min_spacing_m"]
    assert len(candidates) <= config["candidates"]["max_candidates"]
    points = gpd.GeoSeries(gpd.points_from_xy(demand.route_lng, demand.route_lat), crs=4326).to_crs(
        candidates.crs
    )
    endpoint_distances = []
    for row, point in zip(demand.itertuples(), points, strict=True):
        assert row.node_id in (row.route_edge_u, row.route_edge_v)
        distances = [
            point.distance(gpd.points_from_xy([graph.nodes[n]["x"]], [graph.nodes[n]["y"]])[0])
            for n in (row.route_edge_u, row.route_edge_v)
        ]
        endpoint_distances.append(min(distances))
    assert np.allclose(endpoint_distances, demand.route_endpoint_snap_m, atol=1e-6)
    assert (demand.route_edge_snap_m <= demand.route_snap_m + 1e-6).all()
    assert (demand.route_snap_m <= demand.route_endpoint_snap_m + 1e-6).all()
    lookups = times.set_index(["candidate_id", "h3"])
    sample_stations = candidates.iloc[[0, len(candidates) // 2, -1]]
    sample_cells = demand.iloc[np.linspace(0, len(demand) - 1, 7, dtype=int)]
    checked = 0
    for station in sample_stations.itertuples():
        direct = nx.single_source_dijkstra_path_length(graph, station.node_id, weight="travel_time")
        for cell in sample_cells.itertuples():
            expected = direct[cell.node_id] / 60 * config["travel"]["congestion_multiplier"]
            actual = lookups.loc[(station.candidate_id, cell.h3), "travel_time_min"]
            assert np.isclose(actual, expected, rtol=1e-10, atol=1e-8)
            checked += 1
    reachable = set(times.loc[times.travel_time_min <= config["travel"]["coverage_minutes"], "h3"])
    uncovered = demand.loc[~demand.h3.isin(reachable)]
    report = {
        "checks_passed": True,
        "directed_edges_checked": len(edge_seconds),
        "zero_time_edges": zero_time_edges,
        "minimum_edge_seconds": float(edge_seconds.min()),
        "networkx_od_pairs_checked": checked,
        "minimum_station_spacing_m": minimum_spacing,
        "low_demand_cells_retained": int(demand.low_demand.sum()),
        "uncovered_cells": len(uncovered),
        "uncovered_household_share": float(uncovered.households.sum() / demand.households.sum()),
    }
    # Reuse the already downloaded archive for the geographic warning diagnostic.
    folder = raw / "osm_landuse"
    with ZipFile(raw / "socal-latest-free.shp.zip") as archive:
        for name in archive.namelist():
            if Path(name).name == name and "protected_areas" in name:
                (folder / name).write_bytes(archive.read(name))

    class ForestRelations(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.ids = set()

        def relation(self, relation):
            if relation.tags.get("name") == "Angeles National Forest":
                self.ids.add(str(relation.id))

    forest_relations = ForestRelations()
    forest_relations.apply_file(raw / "socal-latest.osm.pbf")
    if not forest_relations.ids:
        raise ValueError("Could not identify the named forest in the original OSM snapshot")
    identifiers = ",".join(f"'{identifier}'" for identifier in sorted(forest_relations.ids))
    forests = gpd.GeoDataFrame(
        pd.concat(
            [
                gpd.read_file(layer, where=f"osm_id IN ({identifiers})")
                for layer in sorted(folder.glob("*protected_areas*.shp"))
            ]
        ),
        crs=4326,
    ).to_crs(candidates.crs)
    if forests.empty:
        raise ValueError("Named forest relation is absent from the protected-area GIS layer")
    warning_cells = demand.loc[demand.route_edge_snap_warning].copy()
    warning_cells["in_osm_angeles_national_forest"] = (
        points.loc[warning_cells.index].covered_by(forests.geometry.union_all()).to_numpy()
    )
    warning_cells.to_csv(processed / "route_edge_warnings.csv", index=False)
    report["edge_warning_cells_in_osm_angeles_national_forest"] = int(
        warning_cells.in_osm_angeles_national_forest.sum()
    )
    report["forest_polygon_records"] = len(forests)
    report["forest_osm_relation_ids"] = sorted(forest_relations.ids)
    (processed / "travel_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
