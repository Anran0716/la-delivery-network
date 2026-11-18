"""Synthetic land and water fixtures check geometry without downloading data."""

import geopandas as gpd
import pytest
from shapely.geometry import box

from lanet.geography import prepare_land_geometry


def test_land_geometry_removes_water_and_preserves_households():
    joined = gpd.GeoDataFrame(
        {
            "GEOID": ["060370001001", "060379901000"],
            "ALAND": [2, 0],
            "B11001_001E": [100, 0],
            "B11001_001M": [12, 3],
        },
        geometry=[box(0, 0, 2, 2), box(2, 0, 3, 2)],
        crs="EPSG:3310",
    )
    faces = gpd.GeoDataFrame(
        {"LWFLAG": ["P", "I"]},
        geometry=[box(1, 0, 3, 2), box(0, 0, 0.5, 2)],
        crs=joined.crs,
    )
    land = prepare_land_geometry(joined, faces)
    assert land.GEOID.tolist() == ["060370001001"]
    assert land.B11001_001E.tolist() == [100]
    assert land.B11001_001M.tolist() == [12]
    assert land.area.sum() == pytest.approx(2)
    assert land.intersection(faces.geometry.iloc[0]).area.sum() == pytest.approx(0)
    assert land.intersection(faces.geometry.iloc[1]).area.sum() == pytest.approx(1)


def test_land_geometry_rejects_households_on_zero_land():
    joined = gpd.GeoDataFrame(
        {"GEOID": ["060379901000"], "ALAND": [0], "B11001_001E": [1]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:3310",
    )
    faces = gpd.GeoDataFrame({"LWFLAG": ["P"]}, geometry=joined.geometry, crs=joined.crs)
    with pytest.raises(ValueError, match="zero-land block group has households"):
        prepare_land_geometry(joined, faces)
