"""Synthetic graph fixtures keep snapping tests independent of Overpass."""

import geopandas as gpd
import networkx as nx
import pandas as pd
import pytest
from shapely.geometry import Point

from lanet.travel import largest_routing_component, snap_demand_points


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
