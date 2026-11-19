"""Evaluate SQL metrics against explicit, validated tabular input contracts."""

from pathlib import Path

import duckdb
import numpy as np


def selected_service(assignments):
    """Respect binary w; discard only solver dust on unselected arcs, not tiny cells."""
    unselected = assignments.w <= 0.5
    if assignments.loc[unselected, "parcels"].abs().sum() > 0.01:
        raise ValueError("Nontrivial volume on unselected arcs")
    return assignments.loc[~unselected & (assignments.parcels > 0)].copy()


def calculate_metrics(demand, assignments, travel, stations, parameters, sql_path=None):
    inputs = {
        "demand_input": demand,
        "assignment_input": assignments,
        "travel_input": travel,
        "station_input": stations,
        "parameter_input": parameters,
    }
    keys = {
        "demand_input": ["scenario", "h3"],
        "assignment_input": ["scenario", "h3"],
        "travel_input": ["scenario", "candidate_id", "h3"],
        "station_input": ["scenario", "candidate_id"],
        "parameter_input": ["scenario"],
    }
    numeric = {
        "demand_input": ["demand_parcels"],
        "assignment_input": ["served_parcels"],
        "travel_input": ["travel_time_min"],
        "station_input": ["capacity", "fixed_cost"],
        "parameter_input": ["coverage_minutes", "delivery_usd_per_parcel_minute"],
    }
    for name, frame in inputs.items():
        if frame[keys[name]].isna().any().any() or frame.duplicated(keys[name]).any():
            raise ValueError(f"Null or duplicate keys in {name}")
        values = frame[numeric[name]].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"Invalid nonnegative numeric values in {name}")
    if (stations.capacity <= 0).any():
        raise ValueError("Station capacity must be positive")
    if not stations.opened.isin([True, False, 0, 1]).all():
        raise ValueError("Station openings must be binary")
    if demand.in_model.isna().any() or not demand.in_model.isin([True, False]).all():
        raise ValueError("Demand must explicitly identify the modeled scope")
    names = set(demand.scenario)
    if names != set(parameters.scenario) or names != set(stations.scenario):
        raise ValueError("Scenario coverage differs between inputs")
    with duckdb.connect() as con:
        for name, frame in inputs.items():
            con.register(name, frame.astype(dict.fromkeys(numeric[name], float)))
        bad = con.execute("""
            SELECT count(*) FROM assignment_input a
            LEFT JOIN demand_input d USING (scenario, h3)
            LEFT JOIN station_input s USING (scenario, candidate_id)
            LEFT JOIN travel_input t USING (scenario, candidate_id, h3)
            WHERE d.h3 IS NULL OR s.candidate_id IS NULL OR NOT s.opened
               OR t.travel_time_min IS NULL OR a.served_parcels > d.demand_parcels + 0.01
               OR (NOT d.in_model AND a.served_parcels > 0)
        """).fetchone()[0]
        if bad:
            raise ValueError("Invalid assignment reference, closed station, or excess service")
        path = (
            Path(sql_path) if sql_path else Path(__file__).resolve().parents[2] / "sql/metrics.sql"
        )
        con.execute(path.read_text(encoding="utf-8"))
        return (
            con.execute("SELECT * FROM scenario_metrics ORDER BY scenario, scope").df(),
            con.execute("SELECT * FROM station_metrics ORDER BY scenario, candidate_id").df(),
        )
