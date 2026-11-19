"""A finite unmet penalty does not logically enforce zero unmet demand."""

from lanet.model import solve_model
from lanet.problem import FacilityData


def test_small_isolated_demand_can_be_cheaper_to_leave_unserved(tmp_path):
    # Hand calculation: serve one parcel for 25,000 fixed, or leave it for 100.
    data = FacilityData(
        demand={"tiny": 1},
        capacity={"A": 20000},
        fixed_cost={"A": 25000},
        unit_cost={("A", "tiny"): 0},
        travel_minutes={("A", "tiny"): 0},
        utilization_limit=0.85,
        unmet_penalty=100,
    )
    result = solve_model(data, "strong", tmp_path, time_limit_seconds=10, relative_gap=0)
    assert result["validation"]["objective"] == 100
    assert result["y"]["A"] == 0
    assert result["s"]["tiny"] == 1
