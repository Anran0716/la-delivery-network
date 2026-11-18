"""Allocate mainland ACS households to a buffered H3 grid on land geometry."""

import geopandas as gpd
import h3
import pandas as pd
import shapely
from shapely.geometry import Polygon


def cell_polygon(cell: str) -> Polygon:
    """Convert H3's (latitude, longitude) boundary into a Shapely polygon."""
    return Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])


def partition_mainland(
    raw: gpd.GeoDataFrame, land: gpd.GeoDataFrame
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, object]:
    """Choose the largest raw county component, then retain its prepared land.

    Choosing after water removal could mistake river-separated mainland pieces
    for islands. A source group spanning components requires an explicit policy;
    it is never silently assigned by its centroid.
    """
    if raw.crs is None or raw.crs != land.crs or not raw.crs.is_projected:
        raise ValueError("County and land inputs need the same projected CRS")
    boundary = raw.geometry.union_all()
    mainland = max(shapely.get_parts(boundary), key=lambda part: part.area)
    shapely.prepare(mainland)
    inside = shapely.covers(mainland, land.geometry.array)
    intersects = shapely.intersects(mainland, land.geometry.array)
    if (intersects & ~inside).any():
        raise ValueError("A land block group spans mainland components; review its apportionment")
    return land.loc[inside].copy(), land.loc[~inside].copy(), mainland


def generate_cells(
    mainland: gpd.GeoDataFrame, resolution: int, buffer_m: float
) -> gpd.GeoDataFrame:
    """Fill a buffered land footprint; retain full H3 polygons and original centers."""
    if mainland.crs is None or not mainland.crs.is_projected:
        raise ValueError("Buffering requires a projected CRS in meters")
    if mainland.crs.axis_info[0].unit_name != "metre":
        raise ValueError("Buffering requires meter units")
    if buffer_m <= 0:
        raise ValueError("Grid buffer must be positive")
    outline = mainland.geometry.union_all().buffer(buffer_m)
    outline_wgs84 = gpd.GeoSeries([outline], crs=mainland.crs).to_crs(4326).iloc[0]
    cells = sorted(h3.geo_to_cells(outline_wgs84.__geo_interface__, resolution))
    coordinates = [h3.cell_to_latlng(cell) for cell in cells]
    return gpd.GeoDataFrame(
        {"h3": cells, "lat": [p[0] for p in coordinates], "lng": [p[1] for p in coordinates]},
        geometry=[cell_polygon(cell) for cell in cells],
        crs="EPSG:4326",
    ).to_crs(mainland.crs)


def allocate_households(
    mainland: gpd.GeoDataFrame, cells: gpd.GeoDataFrame, relative_tolerance: float
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, dict]:
    """Allocate on land intersections; reject uncovered land without renormalizing."""
    if mainland.crs != cells.crs or mainland.crs is None or not mainland.crs.is_projected:
        raise ValueError("Area allocation requires the same projected CRS")
    source = mainland[["GEOID", "B11001_001E", "B11001_001M", "geometry"]].copy()
    source["source_area_m2"] = source.area
    if (source.source_area_m2 <= 0).any():
        raise ValueError("Every mainland source group needs positive land area")
    if source.GEOID.duplicated().any() or cells.h3.duplicated().any():
        raise ValueError("Source GEOIDs and H3 indexes must be unique")
    overlaps = gpd.overlay(
        source,
        cells[["h3", "geometry"]],
        how="intersection",
        keep_geom_type=True,
        make_valid=False,
    )
    overlaps["overlap_area_m2"] = overlaps.area
    covered = overlaps.groupby("GEOID").overlap_area_m2.sum()
    fractions = covered.reindex(source.GEOID, fill_value=0).to_numpy() / source.source_area_m2
    max_area_error = float(abs(fractions - 1).max())
    if max_area_error > relative_tolerance:
        raise ValueError(f"Grid coverage error exceeds tolerance: {max_area_error}")
    overlaps["area_share"] = overlaps.overlap_area_m2 / overlaps.source_area_m2
    overlaps["households_allocated"] = overlaps.B11001_001E * overlaps.area_share
    totals = overlaps.groupby("h3", as_index=False).households_allocated.sum()
    totals = totals.rename(columns={"households_allocated": "households"})
    result = cells.merge(totals, on="h3", how="left", validate="one_to_one")
    result["households"] = result.households.fillna(0)
    result = result[result.households > 0].copy()
    expected = float(source.B11001_001E.sum())
    observed = float(result.households.sum())
    error = abs(observed - expected)
    relative_error = error / expected if expected else 0.0
    if relative_error > relative_tolerance:
        raise ValueError(f"Household conservation error exceeds tolerance: {relative_error}")
    report = {
        "generated_cells": len(cells),
        "land_intersecting_cells": int(overlaps.h3.nunique()),
        "positive_demand_cells": len(result),
        "mainland_households": expected,
        "allocated_households": observed,
        "absolute_household_error": error,
        "relative_household_error": relative_error,
        "max_block_group_area_coverage_error": max_area_error,
    }
    return result, overlaps, report


def summarize_centers(cells: gpd.GeoDataFrame) -> dict:
    """Report original-center flags with an explicit grid denominator."""
    return {
        "cells": len(cells),
        "centers_in_sea": int(cells.center_in_sea.sum()),
        "centers_in_perennial_water": int(cells.center_in_perennial_water.sum()),
        "centers_outside_county": int(cells.center_outside_county.sum()),
    }


def classify_centers(
    cells: gpd.GeoDataFrame, county_boundary, water: gpd.GeoDataFrame, sea: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Distinguish marine water, inland water, and centers outside the county."""
    result = cells.copy()
    points = gpd.GeoSeries(gpd.points_from_xy(result.lng, result.lat), crs=4326).to_crs(cells.crs)
    sea_mask = sea.to_crs(cells.crs).geometry.union_all()
    water_mask = water.to_crs(cells.crs).geometry.union_all()
    for mask in (county_boundary, sea_mask, water_mask):
        shapely.prepare(mask)
    result["center_in_sea"] = shapely.covers(sea_mask, points.array)
    result["center_in_perennial_water"] = (
        shapely.covers(water_mask, points.array) | result.center_in_sea.to_numpy()
    )
    result["center_outside_county"] = ~shapely.covers(county_boundary, points.array)
    return result


def demand_land_geometry(overlaps: gpd.GeoDataFrame, active_cells: pd.Series) -> gpd.GeoDataFrame:
    """Keep the served land footprint and choose an on-land point for later routing."""
    pieces = overlaps.loc[
        overlaps.h3.isin(active_cells) & (overlaps.B11001_001E > 0), ["h3", "geometry"]
    ]
    land = pieces.dissolve(by="h3", as_index=False)
    largest = [
        max(shapely.get_parts(geometry), key=lambda part: part.area) for geometry in land.geometry
    ]
    points = gpd.GeoSeries(largest, crs=land.crs).representative_point().to_crs(4326)
    land["route_lat"] = points.y.to_numpy()
    land["route_lng"] = points.x.to_numpy()
    return land
