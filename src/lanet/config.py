"""Read and validate the shared planning configuration without network access."""

from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import Any

import yaml

# Validation rules only; planning values belong in config.yaml.
POSITIVE_FIELDS = {
    "data": ("acs_year",),
    "demand": (
        "h3_resolution",
        "grid_buffer_m",
        "parcels_per_household_per_day",
        "conservation_relative_tolerance",
        "geometry_overlap_tolerance_m2",
        "low_demand_parcels_per_day",
    ),
    "candidates": ("min_area_hectares", "min_spacing_m", "max_candidates"),
    "travel": (
        "congestion_multiplier",
        "coverage_minutes",
        "matrix_cutoff_minutes",
        "snap_warning_m",
        "request_timeout_seconds",
        "graph_query_buffer_m",
    ),
    "facility": ("capacity_parcels_per_day", "utilization_limit", "fixed_cost_usd_per_day"),
    "cost": ("delivery_usd_per_parcel_minute", "unmet_penalty_usd_per_parcel"),
    "solver": ("time_limit_seconds", "relative_gap"),
    "scenarios": (
        "peak_demand_multiplier",
        "stress_utilization_limit",
        "outage_coverage_minutes",
    ),
    "metrics": ("coverage_threshold_minutes",),
}

TEXT_FIELDS = {
    "study": (
        "name",
        "state_fips",
        "county_fips",
        "mainland_method",
        "projected_crs",
        "geographic_crs",
    ),
    "data": (
        "acs_dataset",
        "household_variable",
        "household_moe_variable",
        "census_api_base",
        "acs_summary_url",
        "tiger_bg_url",
        "tiger_faces_url",
        "tiger_area_water_url",
        "orange_area_water_url",
        "ventura_area_water_url",
        "reference_place_geoid",
        "reference_place_name",
        "osm_extract_url",
        "raw_dir",
        "processed_dir",
    ),
    "demand": ("allocation_method", "allocation_geometry"),
    "candidates": ("landuse", "boundary_scope"),
    "travel": (
        "network_type",
        "graph_filename",
        "graph_component",
        "snap_point",
        "overpass_url",
        "http_user_agent",
        "network_source",
    ),
    "solver": ("name",),
    "assumptions": (
        "demand_proxy",
        "parcel_rate",
        "capacity",
        "fixed_cost",
        "delivery_cost",
        "congestion",
        "coverage",
    ),
}


def _positive(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load a fresh configuration; relative paths resolve from the working directory.

    Raises FileNotFoundError for a missing file, or ValueError for an invalid
    configuration. This function never downloads data or creates directories.
    """
    with Path(path).open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a mapping")

    for section in POSITIVE_FIELDS.keys() | TEXT_FIELDS.keys():
        if not isinstance(config.get(section), Mapping):
            raise ValueError(f"Missing or invalid section: {section}")
    for section, fields in POSITIVE_FIELDS.items():
        for field in fields:
            _positive(config[section].get(field), f"{section}.{field}")
    for section, fields in TEXT_FIELDS.items():
        for field in fields:
            value = config[section].get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{section}.{field} must be a nonempty string")

    for field in ("capacity_values", "fixed_cost_values"):
        values = config["scenarios"].get(field)
        if not isinstance(values, list) or not values:
            raise ValueError(f"scenarios.{field} must be a nonempty list")
        for value in values:
            _positive(value, f"scenarios.{field}")

    for section, field in (
        ("facility", "utilization_limit"),
        ("scenarios", "stress_utilization_limit"),
        ("solver", "relative_gap"),
        ("demand", "conservation_relative_tolerance"),
    ):
        if config[section][field] > 1:
            raise ValueError(f"{section}.{field} must be at most 1")
    for field, width in (("state_fips", 2), ("county_fips", 3)):
        value = config["study"][field]
        if len(value) != width or not value.isdecimal():
            raise ValueError(f"study.{field} must be a {width}-digit string")
    for section, field in (
        ("data", "acs_year"),
        ("demand", "h3_resolution"),
        ("candidates", "max_candidates"),
    ):
        if not isinstance(config[section][field], int):
            raise ValueError(f"{section}.{field} must be an integer")
    if config["demand"]["h3_resolution"] > 15:
        raise ValueError("demand.h3_resolution must be at most 15")
    if config["travel"]["matrix_cutoff_minutes"] < max(
        config["travel"]["coverage_minutes"], config["scenarios"]["outage_coverage_minutes"]
    ):
        raise ValueError("travel.matrix_cutoff_minutes must cover baseline and outage limits")
    return config
