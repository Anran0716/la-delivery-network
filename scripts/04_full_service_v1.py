"""Rerun the v1 baseline with a hard s=0 condition, retaining the P=100 result."""

import json
from pathlib import Path

from lanet import load_config
from lanet.experiments import (
    continuous_full_service_start,
    county_inputs,
    read_solution,
    write_solution,
)
from lanet.model import solve_model


def main():
    config = load_config()
    data, frames = county_inputs(config)
    previous_folder = Path(config["data"]["processed_dir"]) / "model_v1" / "strong"
    previous = json.loads((previous_folder / "summary.json").read_text(encoding="utf-8"))
    seed = continuous_full_service_start(data, read_solution(previous_folder))
    folder = Path(config["data"]["processed_dir"]) / "model_v1_full_service"
    print(f"Checked full-service warm start: {sum(seed['y'].values())} stations", flush=True)
    result = solve_model(
        data,
        "strong",
        folder,
        full_service=True,
        warm_start=seed,
        time_limit_seconds=config["solver"]["time_limit_seconds"],
        relative_gap=config["solver"]["relative_gap"],
    )
    old = previous["validation"]
    extra = {
        "comparison_P100_objective": old["objective"],
        "objective_delta_vs_P100": result["validation"]["objective"] - old["objective"],
        "operating_cost_delta_vs_P100": result["validation"]["fixed_cost"]
        + result["validation"]["delivery_cost"]
        - old["fixed_cost"]
        - old["delivery_cost"],
        "station_delta_vs_P100": result["validation"]["open_stations"] - old["open_stations"],
    }
    summary = write_solution(folder, result, data, frames, extra)
    print(
        json.dumps(
            {
                **{k: v for k, v in summary.items() if k != "validation"},
                "validation": {
                    k: v for k, v in result["validation"].items() if k != "station_loads"
                },
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
