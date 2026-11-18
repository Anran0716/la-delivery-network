"""Small artificial industrial parcels exercise boundary, area and spacing rules."""

import geopandas as gpd
from shapely.geometry import box

from lanet.candidates import select_industrial_candidates


def test_candidate_area_is_measured_after_county_clipping():
    industrial = gpd.GeoDataFrame(
        {"osm_id": ["partial", "too_small", "outside"]},
        geometry=[box(-100, 0, 200, 300), box(900, 0, 1200, 300), box(2000, 0, 2400, 400)],
        crs=3310,
    )
    county = gpd.GeoDataFrame(geometry=[box(0, 0, 1000, 1000)], crs=3310)
    candidates, report = select_industrial_candidates(industrial, county, 4, 1, 120)
    assert candidates.osm_id.tolist() == ["partial"]
    assert candidates.area_m2.tolist() == [60000]
    assert candidates.geometry.covered_by(county.geometry.iloc[0]).all()
    assert report["eligible_polygon_parts"] == 1


def test_candidate_spacing_and_cap_are_deterministic():
    industrial = gpd.GeoDataFrame(
        {"osm_id": ["small_nearby", "largest", "distant", "more_distant"]},
        geometry=[
            box(0, 0, 210, 210),
            box(300, 0, 700, 400),
            box(6000, 0, 6300, 300),
            box(12000, 0, 12250, 250),
        ],
        crs=3310,
    )
    county = gpd.GeoDataFrame(geometry=[box(-100, -100, 15000, 1000)], crs=3310)
    first, _ = select_industrial_candidates(industrial, county, 4, 3000, 2)
    shuffled, _ = select_industrial_candidates(industrial.iloc[::-1], county, 4, 3000, 2)
    assert first.osm_id.tolist() == shuffled.osm_id.tolist() == ["largest", "distant"]
    assert first.geometry.iloc[0].distance(first.geometry.iloc[1]) >= 3000
