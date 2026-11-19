"""Four cases derived on paper in docs/toy-model-hand-calculations.md."""

import pytest

from lanet.check import check_solution
from lanet.model import solve_model
from lanet.problem import FacilityData


def toy_data(fixed_cost, capacity, remove_c4=False):
    rows = {"A": [1, 1, 5, 5], "B": [5, 5, 1, 1], "C": [2, 2, 2, 2]}
    costs = {(i, str(j + 1)): value for i, row in rows.items() for j, value in enumerate(row)}
    if remove_c4:
        costs.pop(("C", "4"))
    return FacilityData(
        demand={str(j): 10.0 for j in range(1, 5)},
        capacity=dict.fromkeys(rows, capacity),
        fixed_cost=dict.fromkeys(rows, fixed_cost),
        unit_cost=costs,
        travel_minutes=dict(costs),
        utilization_limit=1.0,
        unmet_penalty=100.0,
    )


def check_case(data, objective, stations, tmp_path):
    solutions = []
    for linking in ("strong", "weak"):
        result = solve_model(
            data, linking, tmp_path / linking, time_limit_seconds=10, relative_gap=0
        )
        checked = check_solution(
            result["y"], result["x"], result["s"], data, objective=result["validation"]["objective"]
        )
        assert checked["objective"] == pytest.approx(objective)
        assert checked["all_s_zero"]
        assert checked["open_stations"] == stations
        assert result["solver"]["proven_optimal"]
        solutions.append(result)
    return solutions


def test_toy_base(tmp_path):
    for result in check_case(toy_data(30, 40), 100, 2, tmp_path):
        assert {i for i, value in result["y"].items() if value > 0.5} == {"A", "B"}


def test_toy_high_fixed_cost(tmp_path):
    for result in check_case(toy_data(100, 40), 180, 1, tmp_path):
        assert {i for i, value in result["y"].items() if value > 0.5} == {"C"}


def test_toy_capacity_binds(tmp_path):
    for result in check_case(toy_data(30, 15), 140, 3, tmp_path):
        loads = result["validation"]["station_loads"]
        assert loads == pytest.approx({"A": 15, "B": 15, "C": 10})


def test_toy_coverage(tmp_path):
    for result in check_case(toy_data(100, 40, remove_c4=True), 220, 1, tmp_path):
        assert result["y"]["C"] == 0
        assert ("C", "4") not in result["x"]
