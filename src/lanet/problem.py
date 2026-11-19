"""Solver-independent inputs: parcels/day, minutes, and daily USD costs."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FacilityData:
    demand: dict[str, float]
    capacity: dict[str, float]
    fixed_cost: dict[str, float]
    unit_cost: dict[tuple[str, str], float]
    travel_minutes: dict[tuple[str, str], float]
    utilization_limit: float
    unmet_penalty: float
    coverage_minutes: float = 30.0

    def validate(self) -> None:
        if not self.demand or not self.capacity:
            raise ValueError("Model requires demand cells and candidate stations")
        if self.capacity.keys() != self.fixed_cost.keys():
            raise ValueError("Capacity and fixed-cost station keys differ")
        for label, values in (
            ("demand", self.demand.values()),
            ("capacity", self.capacity.values()),
            ("fixed cost", self.fixed_cost.values()),
        ):
            if any(not isfinite(v) or v <= 0 for v in values):
                raise ValueError(f"Every {label} must be finite and strictly positive")
        if not 0 < self.utilization_limit <= 1 or not isfinite(self.unmet_penalty):
            raise ValueError("Invalid utilization or unmet penalty")
        if self.unmet_penalty <= 0 or not 0 < self.coverage_minutes < float("inf"):
            raise ValueError("Penalty and coverage must be positive and finite")
        if self.unit_cost.keys() != self.travel_minutes.keys():
            raise ValueError("Delivery-cost and travel-time allowed arcs differ")
        reached = set()
        for (station, cell), cost in self.unit_cost.items():
            if station not in self.capacity or cell not in self.demand:
                raise ValueError("Arc references an unknown station or demand cell")
            minutes = self.travel_minutes[station, cell]
            if not isfinite(cost) or cost < 0 or not isfinite(minutes) or minutes < 0:
                raise ValueError("Arc costs and minutes must be finite and nonnegative")
            if minutes > self.coverage_minutes + 1e-9:
                raise ValueError("Allowed arc exceeds coverage limit")
            reached.add(cell)
        if reached != set(self.demand):
            raise ValueError("Exclude structurally uncovered demand before building the model")
