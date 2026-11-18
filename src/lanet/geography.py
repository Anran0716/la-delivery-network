"""Audit TIGER water coverage and prepare detailed land allocation geometries."""

import geopandas as gpd


def audit_water(joined: gpd.GeoDataFrame) -> dict:
    """Report county land/water metadata without assuming water implies coastline."""
    with_water = joined[joined.AWATER > 0]
    water_only = joined[joined.ALAND == 0]
    mixed = joined[(joined.ALAND > 0) & (joined.AWATER > 0)]
    total_area = joined.ALAND.add(joined.AWATER).sum()
    if total_area <= 0:
        raise ValueError("County total area must be positive")
    return {
        "block_groups": len(joined),
        "groups_with_water": len(with_water),
        "water_area_m2": int(joined.AWATER.sum()),
        "land_area_m2": int(joined.ALAND.sum()),
        "water_fraction": float(with_water.AWATER.sum() / total_area),
        "zero_land_groups": len(water_only),
        "zero_land_households": int(water_only.B11001_001E.sum()),
        "zero_land_geoids": sorted(water_only.GEOID.tolist()),
        "mixed_land_water_groups": len(mixed),
        "mixed_land_water_households": int(mixed.B11001_001E.sum()),
    }


def prepare_land_geometry(joined: gpd.GeoDataFrame, faces: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Remove perennial water faces, preserving all household and MOE attributes.

    Census counts intermittent water as ALAND, so only LWFLAG=P is removed.
    ALAND identifies zero-land groups; it cannot locate water inside a mixed group.
    Spatial-indexed overlay avoids subtracting a county-wide union from every row.
    """
    if joined.crs is None or faces.crs != joined.crs:
        raise ValueError("Block groups and faces must have the same defined CRS")
    if ((joined.ALAND == 0) & (joined.B11001_001E > 0)).any():
        raise ValueError("A zero-land block group has households; investigate before excluding it")
    land = joined[joined.ALAND > 0].copy()
    water = faces.loc[faces.LWFLAG == "P", ["geometry"]]
    if not land.geometry.is_valid.all() or not water.geometry.is_valid.all():
        raise ValueError("Invalid source geometry; inspect it before water removal")
    if not water.empty:
        land = gpd.overlay(land, water, how="difference", keep_geom_type=True, make_valid=False)
    expected_ids = set(joined.loc[joined.ALAND > 0, "GEOID"])
    if set(land.GEOID) != expected_ids or land.GEOID.duplicated().any():
        raise ValueError("Water removal changed the expected land block-group coverage")
    if land.geometry.is_empty.any() or not land.geometry.is_valid.all():
        raise ValueError("Water removal produced empty or invalid land geometry")
    if int(land.B11001_001E.sum()) != int(joined.B11001_001E.sum()):
        raise ValueError("Water removal changed the household total")
    return land
