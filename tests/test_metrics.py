"""Hand-computed metrics, denominator boundaries and unsafe joins; no downloads."""

import pandas as pd
import pytest

from lanet.metrics import calculate_metrics, selected_service


@pytest.fixture
def tables():
    demand = pd.DataFrame(
        [
            ["s", "a", 10.0, True],
            ["s", "b", 10.0, True],
            ["s", "c", 10.0, True],
            ["s", "outside", 10.0, False],
        ],
        columns=["scenario", "h3", "demand_parcels", "in_model"],
    )
    assignments = pd.DataFrame(
        [
            ["s", "a", "A", 10.0],
            ["s", "b", "A", 5.0],
        ],
        columns=["scenario", "h3", "candidate_id", "served_parcels"],
    )
    travel = pd.DataFrame(
        [
            ["s", "a", "A", 20.0],
            ["s", "b", "A", 30.0],
        ],
        columns=["scenario", "h3", "candidate_id", "travel_time_min"],
    )
    stations = pd.DataFrame(
        [
            ["s", "A", True, 16.0, 30.0],
            ["s", "unused", True, 20.0, 10.0],
            ["s", "closed", False, 20.0, 9999.0],
        ],
        columns=["scenario", "candidate_id", "opened", "capacity", "fixed_cost"],
    )
    params = pd.DataFrame(
        [["s", 20.0, 0.1]],
        columns=["scenario", "coverage_minutes", "delivery_usd_per_parcel_minute"],
    )
    return demand, assignments, travel, stations, params


def test_five_metrics_match_hand_calculation_and_scope(tables):
    scenarios, sites = calculate_metrics(*tables)
    modeled = scenarios.set_index("scope").loc["modeled"]
    whole = scenarios.set_index("scope").loc["study_area"]
    # 15 served, 15 modeled unmet; (10*20+5*30)/15; exactly 20 is covered.
    assert modeled.total_demand == 30
    assert modeled.served_parcels == 15
    assert modeled.network_utilization == pytest.approx(15 / 36)
    assert modeled.weighted_mean_travel_minutes == pytest.approx(350 / 15)
    assert modeled.coverage_20min == pytest.approx(10 / 30)
    assert modeled.unmet_rate == pytest.approx(15 / 30)
    # Operating cost = 40 fixed + 35 delivery. No 100*15 unmet penalty.
    assert modeled.fixed_cost == 40
    assert modeled.delivery_cost == 35
    assert modeled.cost_per_served_parcel == 5
    assert whole.total_demand == 40
    assert whole.unmet_rate == pytest.approx(25 / 40)
    assert whole.coverage_20min == pytest.approx(10 / 40)
    assert whole.weighted_mean_travel_minutes == modeled.weighted_mean_travel_minutes
    assert whole.cost_per_served_parcel == modeled.cost_per_served_parcel
    assert set(sites.candidate_id) == {"A", "unused"}
    indexed = sites.set_index("candidate_id")
    assert indexed.loc["A", "utilization"] == pytest.approx(15 / 16)
    assert indexed.loc["A", "above_baseline_headroom"]
    assert indexed.loc["unused", "utilization"] == 0


def test_selected_service_keeps_tiny_demand_but_removes_unselected_solver_dust():
    frame = pd.DataFrame(
        {"h3": ["a", "a", "tiny"], "w": [1.0, 0.0, 1.0], "parcels": [10.0, 1e-10, 1e-10]}
    )
    assert selected_service(frame).h3.tolist() == ["a", "tiny"]
    frame.loc[1, "parcels"] = 1
    with pytest.raises(ValueError, match="unselected"):
        selected_service(frame)


@pytest.mark.parametrize("zero_demand", [False, True])
def test_zero_served_and_zero_total_denominators(tables, zero_demand):
    demand, assign, travel, stations, params = tables
    if zero_demand:
        demand["demand_parcels"] = 0.0
    scenarios, _ = calculate_metrics(demand, assign.iloc[:0], travel, stations, params)
    assert scenarios.weighted_mean_travel_minutes.isna().all()
    assert scenarios.cost_per_served_parcel.isna().all()
    assert scenarios.fixed_cost.eq(40).all()
    if zero_demand:
        assert scenarios.unmet_rate.isna().all()
        assert scenarios.coverage_20min.isna().all()
    else:
        assert scenarios.unmet_rate.eq(1).all()
        assert scenarios.coverage_20min.eq(0).all()


def test_closed_network_still_reports_unserved_demand(tables):
    demand, assign, travel, stations, params = tables
    stations["opened"] = False
    scenarios, sites = calculate_metrics(demand, assign.iloc[:0], travel, stations, params)
    assert sites.empty
    assert scenarios.open_stations.eq(0).all()
    assert scenarios.fixed_cost.eq(0).all()
    assert scenarios.network_utilization.isna().all()
    assert scenarios.unmet_rate.eq(1).all()


def test_full_service_and_exact_85_percent_boundary(tables):
    demand, assign, travel, stations, params = tables
    demand = demand.iloc[:1].copy()
    demand["demand_parcels"] = 13.6
    assign = assign.iloc[:1].copy()
    assign["served_parcels"] = 13.6
    scenarios, sites = calculate_metrics(demand, assign, travel, stations, params)
    assert scenarios.unmet_rate.eq(0).all()
    assert scenarios.coverage_20min.eq(1).all()
    assert not sites.set_index("candidate_id").loc["A", "above_baseline_headroom"]


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate_demand",
        "duplicate_travel",
        "duplicate_assignment",
        "missing_time",
        "unknown_cell",
        "closed_site",
        "over_served",
    ],
)
def test_reject_unsafe_joins_and_invalid_service(tables, failure):
    demand, assign, travel, stations, params = tables
    if failure == "duplicate_demand":
        demand = pd.concat([demand, demand.iloc[:1]])
    elif failure == "duplicate_travel":
        travel = pd.concat([travel, travel.iloc[:1]])
    elif failure == "duplicate_assignment":
        assign = pd.concat([assign, assign.iloc[:1]])
    elif failure == "missing_time":
        travel = travel.iloc[:0]
    elif failure == "unknown_cell":
        assign.loc[0, "h3"] = "unknown"
    elif failure == "closed_site":
        stations["opened"] = False
    else:
        assign.loc[0, "served_parcels"] = 11
    with pytest.raises(ValueError):
        calculate_metrics(demand, assign, travel, stations, params)
