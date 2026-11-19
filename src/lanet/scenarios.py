"""Period 4: baseline, peak, outage, and sensitivity scenario definitions."""

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    name: str
    overrides: dict = field(default_factory=dict)
    demand_multiplier: float = 1.0
    full_service: bool = True
    network: str = "reoptimize"
    coverage_minutes: float | None = None


def apply_scenario(config, scenario):
    result = deepcopy(config)
    for section, values in scenario.overrides.items():
        result[section].update(deepcopy(values))
    return result


def scenario_definitions(config):
    settings = config["scenarios"]
    scenarios = [
        Scenario("baseline"),
        Scenario("peak_reoptimized", demand_multiplier=settings["peak_demand_multiplier"]),
        Scenario(
            "peak_fixed",
            {"facility": {"utilization_limit": settings["stress_utilization_limit"]}},
            demand_multiplier=settings["peak_demand_multiplier"],
            full_service=False,
            network="baseline",
        ),
        Scenario(
            "outage",
            {"facility": {"utilization_limit": settings["stress_utilization_limit"]}},
            full_service=False,
            network="outage",
            coverage_minutes=settings["outage_coverage_minutes"],
        ),
    ]
    for capacity in settings["capacity_values"]:
        if capacity != config["facility"]["capacity_parcels_per_day"]:
            scenarios.append(
                Scenario(
                    f"capacity_{capacity}", {"facility": {"capacity_parcels_per_day": capacity}}
                )
            )
    for fixed_cost in settings["fixed_cost_values"]:
        if fixed_cost != config["facility"]["fixed_cost_usd_per_day"]:
            scenarios.append(
                Scenario(
                    f"fixed_cost_{fixed_cost}", {"facility": {"fixed_cost_usd_per_day": fixed_cost}}
                )
            )
    scenarios.append(
        Scenario(
            "legacy31_peak_fixed",
            {"facility": {"utilization_limit": settings["stress_utilization_limit"]}},
            demand_multiplier=settings["peak_demand_multiplier"],
            full_service=False,
            network="legacy31",
        )
    )
    return scenarios
