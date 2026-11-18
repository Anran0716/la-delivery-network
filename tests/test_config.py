"""Offline validation of configuration, including invalid-input behavior."""

from pathlib import Path

import pytest
import yaml

from lanet import load_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"


def test_config_contains_guide_parameters():
    config = load_config(CONFIG_PATH)
    assert config["study"]["state_fips"] == "06"
    assert config["study"]["county_fips"] == "037"
    assert config["data"]["acs_year"] == 2023
    assert config["data"]["household_variable"] == "B11001_001E"
    assert config["data"]["household_moe_variable"] == "B11001_001M"
    assert config["demand"]["h3_resolution"] == 7
    assert config["demand"]["parcels_per_household_per_day"] == 0.15
    assert config["facility"]["capacity_parcels_per_day"] == 20000
    assert config["facility"]["utilization_limit"] == 0.85
    assert config["facility"]["fixed_cost_usd_per_day"] == 25000
    assert config["cost"]["delivery_usd_per_parcel_minute"] == 0.015
    assert config["travel"]["congestion_multiplier"] == 1.3
    assert config["travel"]["coverage_minutes"] == 30


@pytest.mark.parametrize("bad_value", [0, -1, True, "0.15", float("inf"), float("nan")])
def test_config_rejects_invalid_positive_parameter(tmp_path, bad_value):
    config = load_config(CONFIG_PATH)
    config["demand"]["parcels_per_household_per_day"] = bad_value
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=r"demand\.parcels_per_household_per_day"):
        load_config(path)


def test_config_rejects_missing_parameter(tmp_path):
    config = load_config(CONFIG_PATH)
    del config["facility"]["capacity_parcels_per_day"]
    path = tmp_path / "missing.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=r"facility\.capacity_parcels_per_day"):
        load_config(path)


def test_config_rejects_utilization_over_one(tmp_path):
    config = load_config(CONFIG_PATH)
    config["facility"]["utilization_limit"] = 1.1
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=r"facility\.utilization_limit"):
        load_config(path)


def test_config_rejects_insufficient_matrix_cutoff(tmp_path):
    config = load_config(CONFIG_PATH)
    config["travel"]["matrix_cutoff_minutes"] = 35
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=r"travel\.matrix_cutoff_minutes"):
        load_config(path)


def test_config_reloads_without_shared_state():
    first = load_config(CONFIG_PATH)
    first["scenarios"]["capacity_values"].append(1)
    assert load_config(CONFIG_PATH)["scenarios"]["capacity_values"] == [15000, 20000, 25000]
