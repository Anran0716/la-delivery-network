from dataclasses import replace

import pytest
from test_v2 import toy

from lanet.model import build_model, solve_model


def test_coverage_forced_bounds_apply_only_to_full_service():
    data = toy()
    arcs = {k: v for k, v in data.unit_cost.items() if k[1] != "0" or k[0] == "C"}
    data = replace(data, unit_cost=arcs, travel_minutes=arcs)
    _, y, *_ = build_model(data, full_service=True)
    assert y["C"].lowBound == y["C"].upBound == 1
    _, y, *_ = build_model(data, full_service=False)
    assert y["C"].lowBound == 0


def test_highs_receives_checked_seed_and_reports_bounds(tmp_path):
    data = toy()
    x = {("C", j): 1 for j in data.demand}
    seed = {"y": {"A": 0, "B": 0, "C": 1}, "x": x, "w": x, "s": dict.fromkeys(data.demand, 0)}
    result = solve_model(
        data,
        "strong",
        tmp_path,
        single_source=True,
        full_service=True,
        solver_name="HiGHS",
        warm_start=seed,
        time_limit_seconds=10,
        relative_gap=0,
    )
    assert result["validation"]["objective"] == pytest.approx(100)
    assert result["solver"]["absolute_gap_usd"] == pytest.approx(0)
    assert result["solver"]["warm_start_checked"]
