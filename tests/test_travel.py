"""Synthetic graph fixtures keep snapping tests independent of Overpass."""

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from shapely.geometry import Point

from lanet.travel import (
    directed_travel_times,
    largest_routing_component,
    snap_demand_points,
    snap_edge_endpoints,
)


def toy_graph(crs=4326):
    graph = nx.MultiDiGraph(crs=crs)
    graph.add_node(10, x=-118.0, y=34.0)
    graph.add_node(20, x=-117.99, y=34.0)
    graph.add_edge(10, 20)
    graph.add_edge(20, 10)
    return graph


def demand_row():
    return pd.DataFrame(
        {
            "h3": ["toy"],
            "route_lat": [34.0],
            "route_lng": [-117.99],
            "lat": [34.0],
            "lng": [-118.0],
            "parcels": [1.0],
        }
    )


def test_snapping_selects_route_node_and_retains_center_audit():
    result = snap_demand_points(toy_graph(), demand_row(), 1000)
    assert result.node_id.tolist() == result.route_node.tolist() == [20]
    assert result.center_node.tolist() == [10]
    assert result.route_snap_m.iloc[0] == pytest.approx(0)
    assert result.center_snap_m.iloc[0] == pytest.approx(0)


def test_projected_snapping_reports_meters_and_can_be_farther():
    graph = nx.MultiDiGraph(crs="EPSG:3310")
    graph.add_node(10, x=0, y=0)
    graph.add_node(20, x=1000, y=0)
    graph.add_edge(10, 20)
    graph.add_edge(20, 10)
    points = gpd.GeoSeries([Point(1100, 0), Point(10, 0)], crs=3310).to_crs(4326)
    cells = demand_row()
    cells.loc[0, ["route_lng", "route_lat"]] = [points.iloc[0].x, points.iloc[0].y]
    cells.loc[0, ["lng", "lat"]] = [points.iloc[1].x, points.iloc[1].y]
    result = snap_demand_points(graph, cells, 50)
    assert result.route_snap_m.iloc[0] == pytest.approx(100, abs=0.001)
    assert result.center_snap_m.iloc[0] == pytest.approx(10, abs=0.001)
    assert result.snap_improvement_m.iloc[0] == pytest.approx(-90, abs=0.001)
    assert result.route_snap_warning.iloc[0]
    assert not result.center_snap_warning.iloc[0]


def test_largest_routing_component_excludes_isolated_nodes():
    graph = toy_graph()
    graph.add_node(30, x=-117.98, y=34.0)
    assert set(largest_routing_component(graph)) == {10, 20}


def test_snapping_requires_route_coordinates_without_center_fallback():
    with pytest.raises(ValueError, match="route_lat/route_lng"):
        snap_demand_points(toy_graph(), demand_row().drop(columns="route_lat"), 1000)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf")])
def test_snapping_rejects_nonfinite_coordinates(invalid):
    cells = demand_row()
    cells.loc[0, "route_lat"] = invalid
    with pytest.raises(ValueError, match="finite"):
        snap_demand_points(toy_graph(), cells, 1000)


def test_directed_times_choose_fastest_parallel_edge_and_apply_congestion_once():
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=60)
    graph.add_edge(1, 2, travel_time=600)
    graph.add_edge(2, 3, travel_time=120)
    graph.add_edge(3, 1, travel_time=600)
    graph.add_node(4)
    origins = pd.DataFrame({"candidate_id": ["A", "B"], "node_id": [1, 3]})
    demand = pd.DataFrame({"h3": ["connected", "isolated"], "node_id": [2, 4]})
    result = directed_travel_times(graph, origins, demand, 1.3, batch_size=1)
    a = result.loc[(result.candidate_id == "A") & (result.h3 == "connected")].iloc[0]
    b = result.loc[(result.candidate_id == "B") & (result.h3 == "connected")].iloc[0]
    assert a.free_flow_time_min == pytest.approx(1)
    assert a.travel_time_min == pytest.approx(1.3)
    assert b.travel_time_min == pytest.approx(14.3)
    assert result.loc[result.h3 == "isolated", "travel_time_min"].eq(float("inf")).all()
    assert len(result) == 4


@pytest.mark.parametrize("weight", [-1, float("nan"), float("inf")])
def test_directed_times_reject_invalid_edge_weights(weight):
    graph = nx.MultiDiGraph()
    graph.add_edge(1, 2, travel_time=weight)
    origins = pd.DataFrame({"candidate_id": ["A"], "node_id": [1]})
    demand = pd.DataFrame({"h3": ["toy"], "node_id": [2]})
    with pytest.raises(ValueError, match="finite nonnegative"):
        directed_travel_times(graph, origins, demand, 1.3)


def test_nearest_edge_selects_its_endpoint_instead_of_unrelated_nearest_node():
    graph = nx.MultiDiGraph(crs="EPSG:3310", simplified=True)
    for node, x, y in [(1, 0, 0), (2, 10000, 0), (3, 4500, 100), (4, 4500, 200)]:
        graph.add_node(node, x=x, y=y)
    graph.add_edge(1, 2)
    graph.add_edge(3, 4)
    point = gpd.GeoSeries([Point(4500, 10)], crs=3310).to_crs(4326).iloc[0]
    cells = demand_row()
    cells.loc[0, ["route_lng", "route_lat"]] = [point.x, point.y]
    nodes_before, edges_before = set(graph.nodes), set(graph.edges)
    audit = snap_demand_points(graph, cells, 1000)
    result = snap_edge_endpoints(graph, audit, 1000)
    assert result.route_nearest_node.iloc[0] == 3
    assert result.route_edge_snap_m.iloc[0] == pytest.approx(10, abs=0.001)
    assert result.route_snap_m.iloc[0] == pytest.approx(90, abs=0.001)
    assert result.node_id.iloc[0] == result.route_endpoint_node.iloc[0] == 1
    assert result.route_endpoint_snap_m.iloc[0] == pytest.approx(4500.011111, abs=0.001)
    assert set(graph.nodes) == nodes_before
    assert set(graph.edges) == edges_before


def test_nearest_edge_rejects_degrees_as_distance_units():
    with pytest.raises(ValueError, match="projected graph in meters"):
        snap_edge_endpoints(toy_graph(), demand_row(), 1000)
