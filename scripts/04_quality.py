"""Independent scenario starts and controlled CBC/HiGHS quality experiments."""

import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import pulp

from lanet import load_config
from lanet.check import check_solution
from lanet.experiments import county_inputs, read_solution, write_solution
from lanet.model import solve_model
from lanet.scenarios import apply_scenario, scenario_definitions
from lanet.starts import single_source_start

SCENARIO_SOLVER = "HiGHS"


def run(folder, data, frames, *, single, full, fixed=None, start=None, seconds=600, solver="HiGHS"):
    if (folder / "summary.json").exists():
        result = read_solution(folder)
        summary = json.loads((folder / "summary.json").read_text())
        metadata = summary["solver"]
        if (
            metadata["solver_name"] != solver
            or metadata["time_limit_seconds"] != seconds
            or metadata["single_source"] != single
            or metadata["full_service"] != full
        ):
            raise ValueError("Cached solver settings differ from requested run")
        check_solution(
            result["y"],
            result["x"],
            result["s"],
            data,
            w=result["w"] if single else None,
            single_source=single,
            require_full_service=full,
            fixed_openings=fixed,
            objective=summary["validation"]["objective"],
        )
        result["validation"] = summary["validation"]
        result["solver"] = metadata
        return result, summary
    print(f"START {folder}: {solver} {seconds}s", flush=True)
    result = solve_model(
        data,
        "strong",
        folder,
        time_limit_seconds=seconds,
        relative_gap=0.005,
        single_source=single,
        full_service=full,
        fixed_openings=fixed,
        warm_start=start,
        solver_name=solver,
    )
    summary = write_solution(folder, result, data, frames)
    print(
        json.dumps(
            {
                "folder": str(folder),
                "stations": summary["validation"]["open_stations"],
                "objective": summary["validation"]["objective"],
                "solver": summary["solver"],
            }
        ),
        flush=True,
    )
    return result, summary


def main():
    config = load_config()
    root = Path(config["data"]["processed_dir"]) / "quality_v2"
    root.mkdir(exist_ok=True)
    sources = list(Path("src/lanet").glob("*.py")) + [Path(__file__)]
    sources += [
        Path(config["data"]["processed_dir"]) / n
        for n in ("demand_cells.parquet", "candidates.parquet", "travel_times.parquet")
    ]
    protocol = {
        "config": config,
        "sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    protocol_path = root / "protocol.json"
    if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
        raise ValueError("Quality-run inputs/source/config changed; preserve prior runs separately")
    protocol_path.write_text(json.dumps(protocol, indent=2))
    print(pulp.listSolvers(onlyAvailable=True), flush=True)
    definitions = scenario_definitions(config)
    summaries = {}
    for scenario in definitions:
        settings = apply_scenario(config, scenario)
        data, frames = county_inputs(
            settings, scenario.demand_multiplier, scenario.coverage_minutes
        )
        fixed = None
        closed = None
        if scenario.network != "reoptimize":
            source = read_solution(
                Path(config["data"]["processed_dir"]) / "model_v1" / "strong"
                if scenario.network == "legacy31"
                else root / "baseline"
            )
            fixed = {i: int(v > 0.5) for i, v in source["y"].items()}
            if scenario.network == "outage":
                stations = pd.read_parquet(root / "baseline" / "stations.parquet")
                stations = stations.loc[stations.opened > 0.5].copy()
                stations["rounded"] = stations.assigned_parcels.round(2)
                closed = (
                    stations.sort_values(["rounded", "candidate_id"], ascending=[False, True])
                    .iloc[0]
                    .candidate_id
                )
                fixed[closed] = 0
        v1, _ = run(
            root / "own_v1" / scenario.name,
            data,
            frames,
            single=False,
            full=scenario.full_service,
            fixed=fixed,
            solver=SCENARIO_SOLVER,
        )
        seed, audit = single_source_start(
            data, v1, full_service=scenario.full_service, fixed_openings=fixed
        )
        if seed is None:
            raise ValueError("Scenario-specific v1 failed to produce a checked v2 seed")
        if scenario.name == "baseline":
            _, cbc = run(
                root / "benchmark_cbc600",
                data,
                frames,
                single=True,
                full=True,
                start=seed,
                solver="CBC",
            )
            high, highs = run(
                root / "benchmark_highs600", data, frames, single=True, full=True, start=seed
            )
            comparison = {"CBC600": cbc, "HiGHS600": highs, "same_checked_seed": audit}
            (root / "solver_comparison.json").write_text(json.dumps(comparison, indent=2))
            result, summary = high, highs
            # The comparison is descriptive; it never selects the scenario solver.
            if summary["solver"]["absolute_gap_usd"] >= 25000:
                result, summary = run(
                    root / "baseline1800",
                    data,
                    frames,
                    single=True,
                    full=True,
                    start=result,
                    seconds=1800,
                    solver=SCENARIO_SOLVER,
                )
            summary = write_solution(
                root / "baseline",
                result,
                data,
                frames,
                {"own_v1_rounding": audit, "closed_station": closed},
            )
        else:
            result, summary = run(
                root / scenario.name,
                data,
                frames,
                single=True,
                full=scenario.full_service,
                fixed=fixed,
                start=seed,
                solver=SCENARIO_SOLVER,
            )
        summary["own_v1_rounding"] = audit
        summary["closed_station"] = closed
        summary["capacity_station_lower_bound"] = math.ceil(
            sum(data.demand.values())
            / (next(iter(data.capacity.values())) * data.utilization_limit)
        )
        summaries[scenario.name] = summary
        (root / "quality_results.json").write_text(json.dumps(summaries, indent=2))
        pd.DataFrame(
            [
                {
                    "scenario": n,
                    "stations": s["validation"]["open_stations"],
                    "objective": s["validation"]["objective"],
                    "unmet": s["validation"]["unmet_parcels"],
                    "mean_minutes": s["validation"]["weighted_mean_travel_minutes"],
                    "gap": s["solver"]["relative_gap"],
                    "absolute_gap_usd": s["solver"]["absolute_gap_usd"],
                    "seconds": s["solver"]["solve_wall_seconds"],
                }
                for n, s in summaries.items()
            ]
        ).to_csv(root / "quality_summary.csv", index=False)


if __name__ == "__main__":
    main()
