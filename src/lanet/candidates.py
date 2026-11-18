"""Period 2: derive industrial candidates with station locations inside LA County.

The configured county-only scope excludes otherwise plausible Orange/Ventura
stations. Candidate generation must validate its final locations against the
county boundary before any travel-time or optimization step.
"""

import geopandas as gpd
import numpy as np


def select_industrial_candidates(
    industrial: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    min_area_hectares: float,
    min_spacing_m: float,
    max_candidates: int,
) -> tuple[gpd.GeoDataFrame, dict]:
    """Clip first, place interior points, then thin deterministically by area.

    Each polygon part must independently meet the usable-area threshold inside
    the study boundary. Spacing refers to physical station points, not graph nodes.
    """
    if not boundary.crs.is_projected or boundary.crs.axis_info[0].unit_name != "metre":
        raise ValueError("Candidate area and spacing require a projected CRS in meters")
    source = industrial.to_crs(boundary.crs)[["osm_id", "geometry"]].copy()
    source["osm_id"] = source.osm_id.astype(str)
    clipped = gpd.overlay(source, boundary[["geometry"]], how="intersection")
    clipped = clipped.explode(index_parts=False).reset_index(drop=True)
    clipped = clipped.loc[clipped.geom_type == "Polygon"].copy()
    clipped["source_part"] = clipped.groupby("osm_id").cumcount()
    clipped["area_m2"] = clipped.area
    eligible = clipped.loc[clipped.area_m2 >= min_area_hectares * 10000].copy()
    eligible = eligible.sort_values(
        ["area_m2", "osm_id", "source_part"], ascending=[False, True, True], kind="stable"
    )
    points = eligible.copy()
    points.geometry = points.geometry.representative_point()
    kept, xy = [], []
    for index, row in points.iterrows():
        point = np.array([row.geometry.x, row.geometry.y])
        if xy and np.linalg.norm(np.array(xy) - point, axis=1).min() < min_spacing_m:
            continue
        kept.append(index)
        xy.append(point)
        if len(kept) == max_candidates:
            break
    selected = points.loc[kept].reset_index(drop=True)
    selected["candidate_id"] = [f"C{i:03d}" for i in range(1, len(selected) + 1)]
    if not selected.geometry.covered_by(boundary.geometry.union_all()).all():
        raise ValueError("Candidate station outside study boundary")
    return selected, {
        "source_industrial_polygons": len(source),
        "clipped_polygon_parts": len(clipped),
        "eligible_polygon_parts": len(eligible),
        "selected_before_graph_deduplication": len(selected),
        "min_area_hectares": min_area_hectares,
        "min_spacing_m": min_spacing_m,
        "max_candidates": max_candidates,
        "selection": "Descending clipped area, OSM ID/part tie-break, greedy minimum spacing",
    }
