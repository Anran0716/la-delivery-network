"""Report numbers must follow configuration and data, not baseline literals."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def reporter():
    path = Path(__file__).resolve().parents[1] / "scripts/outage_control.py"
    spec = importlib.util.spec_from_file_location("outage_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.report_facts


@pytest.mark.parametrize("fee,control_sites,outage_sites", [(123.0, 5, 3), (40000.0, 37, 36)])
def test_report_uses_config_counts_and_actual_exclusions(fee, control_sites, outage_sites):
    control = {"validation": {"open_stations": control_sites, "fixed_cost": fee * control_sites}}
    outage = {"validation": {"open_stations": outage_sites, "fixed_cost": fee * outage_sites}}
    frames = {
        "demand": pd.DataFrame({"h3": ["a", "b", "c"]}),
        "excluded": pd.DataFrame({"parcels": [1.25, 7.5]}),
    }
    facts = reporter()({"facility": {"fixed_cost_usd_per_day": fee}}, control, outage, frames)
    assert facts == {
        "fixed_cost_difference": fee * (control_sites - outage_sites),
        "modeled_cells": 3,
        "excluded_cells": 2,
        "excluded_parcels": 8.75,
    }


def test_report_rejects_changed_config_with_old_costs():
    cached = {"validation": {"open_stations": 5, "fixed_cost": 615.0}}
    with pytest.raises(ValueError, match="disagree"):
        reporter()({"facility": {"fixed_cost_usd_per_day": 999.0}}, cached, cached, {})
