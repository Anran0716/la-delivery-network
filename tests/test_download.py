"""Small synthetic inputs validate geography and join behavior offline."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from lanet.download import extract_households, join_households


def test_summary_preserves_moe_and_builds_geoid(tmp_path):
    source = tmp_path / "households.dat"
    source.write_text(
        "GEO_ID|B11001_E001|B11001_M001\n"
        "0500000US06037|30|9\n"
        "1500000US060370001001|10|3\n"
        "1500000US060370001002|20|4\n"
        "1500000US060590001001|999|5\n",
        encoding="utf-8",
    )
    households, county_total = extract_households(source, "06", "037")
    assert households["GEOID"].tolist() == ["060370001001", "060370001002"]
    assert households["tract"].tolist() == ["000100", "000100"]
    assert households["B11001_001M"].tolist() == [3, 4]
    assert households["B11001_001E"].sum() == county_total == 30


@pytest.mark.parametrize("field", ["B11001_E001", "B11001_M001"])
def test_summary_rejects_negative_sentinel(tmp_path, field):
    values = {"B11001_E001": "10", "B11001_M001": "3"}
    values[field] = "-666666666"
    source = tmp_path / "sentinel.dat"
    source.write_text(
        "GEO_ID|B11001_E001|B11001_M001\n"
        "0500000US06037|10|3\n"
        f"1500000US060370001001|{values['B11001_E001']}|{values['B11001_M001']}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing/sentinel ACS value for 060370001001"):
        extract_households(source, "06", "037")


def test_summary_rejects_missing_county_record(tmp_path):
    source = tmp_path / "missing_county.dat"
    source.write_text(
        "GEO_ID|B11001_E001|B11001_M001\n1500000US060370001001|10|3\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no requested county or block-group records"):
        extract_households(source, "06", "037")


@pytest.mark.parametrize("missing_from", ["ACS", "TIGER"])
def test_join_rejects_unmatched_geographies(missing_from):
    ids = ["060370001001", "060370001002"]
    boundaries = gpd.GeoDataFrame(
        {"GEOID": ids}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4269"
    )
    households = pd.DataFrame({"GEOID": ids, "B11001_001E": [10, 20], "B11001_001M": [3, 4]})
    if missing_from == "ACS":
        households = households.iloc[:1]
    else:
        boundaries = boundaries.iloc[:1]
    with pytest.raises(ValueError, match="GEOID coverage mismatch"):
        join_households(boundaries, households)


def test_join_uses_geoid_instead_of_row_position():
    boundaries = gpd.GeoDataFrame(
        {"GEOID": ["060370001002", "060370001001"]},
        geometry=[box(1, 0, 2, 1), box(0, 0, 1, 1)],
        crs="EPSG:4269",
    )
    households = pd.DataFrame(
        {"GEOID": ["060370001001", "060370001002"], "B11001_001E": [10, 20], "B11001_001M": [3, 4]}
    )
    joined = join_households(boundaries, households)
    assert joined["B11001_001E"].tolist() == [20, 10]
    assert joined["B11001_001M"].tolist() == [4, 3]
