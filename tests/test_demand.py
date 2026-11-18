"""Offline geometric fixtures check H3 coordinates, allocation, and study boundaries."""

import geopandas as gpd
import h3
import pytest
from shapely.geometry import Point, box

from lanet.demand import allocate_households, cell_polygon, classify_centers, partition_mainland


def source_groups(geometries, households):
    return gpd.GeoDataFrame(
        {
            "GEOID": [str(i) for i in range(len(geometries))],
            "B11001_001E": households,
            "B11001_001M": [1] * len(geometries),
        },
        geometry=geometries,
        crs=3310,
    )


def test_allocation_conserves_total():
    source = source_groups([box(0, 0, 2, 1), box(2, 0, 4, 1)], [10, 30])
    cells = gpd.GeoDataFrame(
        {"h3": ["a", "b", "c", "d"]},
        geometry=[box(i, 0, i + 1, 1) for i in range(4)],
        crs=3310,
    )
    result, _, report = allocate_households(source, cells, 1e-8)
    assert result.households.sum() == pytest.approx(40)
    assert report["relative_household_error"] == pytest.approx(0)


def test_allocation_split():
    source = source_groups([box(0, 0, 2, 1)], [10])
    cells = gpd.GeoDataFrame(
        {"h3": ["a", "b"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=3310,
    )
    result, _, _ = allocate_households(source, cells, 1e-8)
    assert result.households.tolist() == pytest.approx([5, 5])


def test_allocation_rejects_coverage_gap():
    source = source_groups([box(0, 0, 2, 1)], [10])
    cells = gpd.GeoDataFrame({"h3": ["a"]}, geometry=[box(0, 0, 1, 1)], crs=3310)
    with pytest.raises(ValueError, match="Grid coverage error"):
        allocate_households(source, cells, 0.005)


def test_cell_polygon_contains_center():
    cell = h3.latlng_to_cell(34.05, -118.25, 7)
    lat, lng = h3.cell_to_latlng(cell)
    assert cell_polygon(cell).contains(Point(lng, lat))


def test_mainland_selection_precedes_water_clipping():
    raw = source_groups([box(0, 0, 2, 2), box(2, 0, 4, 2), box(10, 0, 11, 1)], [100, 200, 10])
    land = source_groups([box(0, 0, 1.9, 2), box(2.1, 0, 4, 2), box(10, 0, 11, 1)], [100, 200, 10])
    mainland, islands, _ = partition_mainland(raw, land)
    assert mainland.B11001_001E.sum() == 300
    assert islands.B11001_001E.sum() == 10


def test_outside_county_is_distinct_from_sea():
    cells = gpd.GeoDataFrame(
        {"h3": ["a", "b", "c"], "lat": [0.5, 0.0, 0.0], "lng": [0.5, 2.0, 4.0]},
        geometry=[Point(0.5, 0.5), Point(2, 0), Point(4, 0)],
        crs=4326,
    )
    water = gpd.GeoDataFrame(geometry=[box(10, 10, 11, 11)], crs=4326)
    sea = gpd.GeoDataFrame(geometry=[box(1.5, -1, 3, 1)], crs=4326)
    result = classify_centers(cells, box(0, 0, 1, 1), water, sea)
    assert result.center_outside_county.tolist() == [False, True, True]
    assert result.center_in_sea.tolist() == [False, True, False]
    assert result.center_in_perennial_water.tolist() == [False, True, False]
