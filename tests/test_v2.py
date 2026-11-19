"""Single-source w permits partial service by its one selected station."""

from dataclasses import replace

import pytest

from lanet import load_config
from lanet.check import check_solution
from lanet.model import solve_model
from lanet.problem import FacilityData
from lanet.scenarios import Scenario, apply_scenario
from lanet.starts import single_source_start


def toy():
    rows = {"A": [1, 1, 5, 5], "B": [5, 5, 1, 1], "C": [2, 2, 2, 2]}
    costs = {(i, str(j)): v for i, row in rows.items() for j, v in enumerate(row)}
    return FacilityData(
        demand=dict.fromkeys([str(j) for j in range(4)], 10),
        capacity=dict.fromkeys(rows, 40),
        fixed_cost=dict.fromkeys(rows, 30),
        unit_cost=costs,
        travel_minutes=dict(costs),
        utilization_limit=1,
        unmet_penalty=100,
    )


def test_single_source_no_split(tmp_path):
    result = solve_model(
        toy(),
        "strong",
        tmp_path,
        single_source=True,
        full_service=True,
        time_limit_seconds=10,
        relative_gap=0,
    )
    assert result["validation"]["objective"] == pytest.approx(100)
    assert result["x"] == result["w"]
    for j in toy().demand:
        assert sum(v > 1e-6 for (i, cell), v in result["x"].items() if cell == j) == 1


def test_fixed_network_reports_exact_six_unmet(tmp_path):
    data = replace(
        toy(), demand=dict.fromkeys(toy().demand, 14), capacity=dict.fromkeys(toy().capacity, 25)
    )
    fixed = {"A": 1, "B": 1, "C": 0}
    result = solve_model(
        data,
        "strong",
        tmp_path,
        single_source=True,
        fixed_openings=fixed,
        time_limit_seconds=10,
        relative_gap=0,
    )
    assert result["validation"]["unmet_parcels"] == pytest.approx(6, abs=1e-5)
    assert result["validation"]["objective"] == pytest.approx(710, abs=1e-4)
    assert result["solver"]["proven_optimal"]


def test_outage_closes_station(tmp_path):
    result = solve_model(
        toy(),
        "strong",
        tmp_path,
        single_source=True,
        fixed_openings={"A": 0, "B": 1, "C": 1},
        time_limit_seconds=10,
        relative_gap=0,
    )
    assert result["y"]["A"] == 0
    assert all(v == 0 for (i, _), v in result["x"].items() if i == "A")
    assert all(v == 0 for (i, _), v in result["w"].items() if i == "A")


def test_scenario_overrides_do_not_mutate_config():
    config = load_config()
    scenario = Scenario("changed", {"facility": {"capacity_parcels_per_day": 1}})
    changed = apply_scenario(config, scenario)
    changed["scenarios"]["capacity_values"].append(1)
    assert config["facility"]["capacity_parcels_per_day"] == 20000
    assert 1 not in config["scenarios"]["capacity_values"]


def test_rounding_capacity_failure_is_repaired_and_checked():
    costs = {(i, j): 1 for i in ["A", "B", "C"] for j in ["1", "2", "3"]}
    data = FacilityData(
        demand={"1": 10, "2": 10, "3": 10},
        capacity={"A": 20, "B": 20, "C": 20},
        fixed_cost={"A": 1, "B": 1, "C": 1},
        unit_cost=costs,
        travel_minutes=costs,
        utilization_limit=1,
        unmet_penalty=100,
    )
    preferred = {
        "y": dict.fromkeys(data.capacity, 1),
        "x": {(i, j): 0.5 if i in ["A", "B"] else 0 for i, j in costs},
        "s": dict.fromkeys(data.demand, 0),
    }
    seed, audit = single_source_start(data, preferred, full_service=True)
    assert not audit["naive_rounding_passed"]
    assert audit["warm_start_checked"]
    check_solution(
        seed["y"],
        seed["x"],
        seed["s"],
        data,
        w=seed["w"],
        single_source=True,
        require_full_service=True,
    )


def test_invalid_warm_start_is_rejected_before_solver(tmp_path, monkeypatch):
    import pulp

    def forbidden(*args, **kwargs):
        pytest.fail("Solver must not receive an unchecked invalid warm start")

    monkeypatch.setattr(pulp.LpProblem, "solve", forbidden)
    data = toy()
    seed = {
        "y": dict.fromkeys(data.capacity, 0),
        "x": {("A", "0"): 1},
        "s": dict.fromkeys(data.demand, 1),
        "w": {("A", "0"): 1},
    }
    with pytest.raises(ValueError):
        solve_model(data, "strong", tmp_path, single_source=True, warm_start=seed)


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("second_source", "more than one station"),
        ("unlinked_service", "exceeds its single-source"),
        ("fractional_w", "w must be binary"),
        ("closed_source", "w selects a closed station"),
        ("unknown_arc", "valid w keys"),
        ("missing_w", "valid w keys"),
    ],
)
def test_checker_rejects_corrupt_single_source_choices(failure, message):
    data = toy()
    y = {"A": 0, "B": 0, "C": 1}
    x = {("C", j): 1 for j in data.demand}
    w = dict(x)
    s = dict.fromkeys(data.demand, 0)
    if failure == "second_source":
        y["A"] = 1
        w["A", "0"] = 1
    elif failure == "unlinked_service":
        w["C", "0"] = 0
    elif failure == "fractional_w":
        w["C", "0"] = 0.5
    elif failure == "closed_source":
        w["A", "0"] = 1
    elif failure == "unknown_arc":
        w["unknown", "0"] = 0
    else:
        w = None
    with pytest.raises(ValueError, match=message):
        check_solution(y, x, s, data, w=w, single_source=True)


def test_checker_distinguishes_partial_service_from_hard_service():
    data = toy()
    y = {"A": 0, "B": 0, "C": 1}
    x = {("C", j): 1 for j in data.demand}
    w = dict(x)
    s = dict.fromkeys(data.demand, 0)
    x["C", "0"] = s["0"] = 0.5
    result = check_solution(y, x, s, data, w=w, single_source=True)
    assert result["unmet_parcels"] == 5
    with pytest.raises(ValueError, match="Full-service baseline requires s=0"):
        check_solution(y, x, s, data, w=w, single_source=True, require_full_service=True)


def test_checker_rejects_fixed_network_change():
    data = toy()
    y = {"A": 0, "B": 0, "C": 1}
    x = {("C", j): 1 for j in data.demand}
    s = dict.fromkeys(data.demand, 0)
    with pytest.raises(ValueError, match="fixed station openings"):
        check_solution(y, x, s, data, fixed_openings={"A": 1, "B": 0, "C": 0})
