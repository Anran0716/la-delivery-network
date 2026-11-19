"""Recompute feasibility and costs from dictionaries, independently of PuLP."""

from math import isfinite

from lanet.problem import FacilityData


def check_solution(
    y: dict[str, float],
    x: dict[tuple[str, str], float],
    s: dict[str, float],
    data: FacilityData,
    objective: float | None = None,
    fraction_tol: float = 1e-6,
    parcel_tol: float = 0.01,
) -> dict:
    """Reject invalid output and independently recompute served-demand metrics.

    Sparse x dictionaries may omit zero assignments; keys outside allowed arcs
    are rejected even if their value is zero. Tolerances allow CBC's text-output
    rounding: 1e-6 in fractions, 0.01 parcel/day in capacities, and 0.05 USD/day
    (or 1e-8 relative) in objective reconstruction.
    """
    data.validate()
    if y.keys() != data.capacity.keys() or s.keys() != data.demand.keys():
        raise ValueError("Solution station/cell keys do not match the input")
    if not x.keys() <= data.unit_cost.keys():
        raise ValueError("Assignment outside allowed coverage arcs")
    for name, values in (("y", y.values()), ("x", x.values()), ("s", s.values())):
        if any(not isfinite(v) or v < -fraction_tol or v > 1 + fraction_tol for v in values):
            raise ValueError(f"{name} contains nonfinite or out-of-bound fractions")
    if any(abs(value - round(value)) > fraction_tol for value in y.values()):
        raise ValueError("Station openings must be binary")
    balance = dict(s)
    loads = dict.fromkeys(data.capacity, 0.0)
    delivery_cost = travel_parcel_minutes = 0.0
    for (station, cell), fraction in x.items():
        if fraction > y[station] + fraction_tol:
            raise ValueError("Assignment to a closed station")
        balance[cell] += fraction
        parcels = data.demand[cell] * fraction
        loads[station] += parcels
        delivery_cost += parcels * data.unit_cost[station, cell]
        travel_parcel_minutes += parcels * data.travel_minutes[station, cell]
    residual = max(abs(value - 1) for value in balance.values())
    if residual > fraction_tol:
        raise ValueError("Assignment fractions plus unmet fraction do not sum to one")
    for station, load in loads.items():
        usable = data.utilization_limit * data.capacity[station] * y[station]
        if load > usable + parcel_tol:
            raise ValueError(f"Capacity exceeded at {station}: {load} > {usable}")
    fixed_cost = sum(data.fixed_cost[i] * value for i, value in y.items())
    unmet = sum(data.demand[j] * value for j, value in s.items())
    penalty = data.unmet_penalty * unmet
    total_cost = fixed_cost + delivery_cost + penalty
    if objective is not None:
        if not isfinite(objective) or abs(total_cost - objective) > max(
            0.05, abs(objective) * 1e-8
        ):
            raise ValueError("Reported objective differs from independently recomputed cost")
    served = sum(loads.values())
    return {
        "checks_passed": True,
        "open_stations": sum(round(value) for value in y.values()),
        "total_demand_parcels": sum(data.demand.values()),
        "served_parcels": served,
        "unmet_parcels": unmet,
        "all_s_zero": all(abs(value) <= fraction_tol for value in s.values())
        and unmet <= parcel_tol,
        "positive_s_cells": sum(value > fraction_tol for value in s.values()),
        "fixed_cost": fixed_cost,
        "delivery_cost": delivery_cost,
        "penalty_cost": penalty,
        "objective": total_cost,
        "weighted_mean_travel_minutes": travel_parcel_minutes / served if served else None,
        "maximum_balance_error": residual,
        "station_loads": loads,
    }
