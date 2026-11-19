"""The checker must reject plausible but incorrect output, without solving it."""

from dataclasses import replace

import pytest

from lanet.check import check_solution
from lanet.model import parse_cbc_log
from lanet.problem import FacilityData


@pytest.fixture
def inputs():
    data = FacilityData(
        demand={"1": 10, "2": 10},
        capacity={"A": 20, "B": 20},
        fixed_cost={"A": 30, "B": 30},
        unit_cost={("A", "1"): 1, ("B", "2"): 1},
        travel_minutes={("A", "1"): 5, ("B", "2"): 5},
        utilization_limit=1,
        unmet_penalty=100,
    )
    return data, {"A": 1, "B": 1}, {("A", "1"): 1, ("B", "2"): 1}, {"1": 0, "2": 0}


def test_checker_rejects_capacity_excess(inputs):
    data, y, x, s = inputs
    with pytest.raises(ValueError, match="Capacity exceeded"):
        check_solution(y, x, s, replace(data, capacity={"A": 5, "B": 20}))


@pytest.mark.parametrize("failure", ["balance", "coverage", "closed", "binary", "bounds", "nan"])
def test_checker_rejects_corrupt_assignments(inputs, failure):
    data, y, x, s = inputs
    if failure == "balance":
        x["A", "1"] = 0.9
    elif failure == "coverage":
        x["A", "2"] = 0
    elif failure == "closed":
        y["A"] = 0
    elif failure == "binary":
        y["A"] = 0.5
    elif failure == "bounds":
        s["1"] = -0.1
    else:
        x["A", "1"] = float("nan")
    with pytest.raises(ValueError):
        check_solution(y, x, s, data)


def test_checker_rejects_wrong_objective(inputs):
    data, y, x, s = inputs
    with pytest.raises(ValueError, match="Reported objective"):
        check_solution(y, x, s, data, objective=1)


def test_checker_rejects_arc_beyond_driving_limit(inputs):
    data, y, x, s = inputs
    data = replace(data, travel_minutes={("A", "1"): 5, ("B", "2"): 30.01})
    with pytest.raises(ValueError, match="coverage limit"):
        check_solution(y, x, s, data)


def test_checker_weights_travel_by_served_parcels(inputs):
    data, y, x, s = inputs
    data = replace(data, travel_minutes={("A", "1"): 5, ("B", "2"): 15})
    x["B", "2"] = 0.5
    s["2"] = 0.5
    # 15 served parcels: (10*5 + 5*15)/15; five unmet parcels stay out.
    result = check_solution(y, x, s, data, objective=575)
    assert result["served_parcels"] == 15
    assert result["unmet_parcels"] == 5
    assert result["weighted_mean_travel_minutes"] == pytest.approx(125 / 15)


def test_log_parser_does_not_call_gap_termination_proven_optimal():
    log = (
        "Continuous objective value is 90 - 0.00 seconds\n"
        "Result - Optimal solution found (within gap tolerance)\n"
        "Objective value: 100\nLower bound: 99.6\nGap: 0.00\n"
    )
    result = parse_cbc_log(log)
    assert not result["proven_optimal"]
    assert result["relative_gap"] == pytest.approx(0.004)
    assert result["initial_lp_objective"] == 90


def test_log_parser_preserves_time_limit_and_nonzero_gap():
    result = parse_cbc_log(
        "Result - Stopped on time limit\nObjective value: 100\nLower bound: 80\n"
    )
    assert not result["proven_optimal"]
    assert result["relative_gap"] == pytest.approx(0.2)
    assert result["termination_reason"] == "Stopped on time limit"
