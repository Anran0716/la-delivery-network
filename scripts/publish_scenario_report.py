"""Export small reviewable period-4 snapshots after the complete independent audit."""

import hashlib
import importlib.metadata
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pulp

from lanet import load_config
from lanet.scenarios import scenario_definitions


def main():
    config = load_config()
    processed = Path(config["data"]["processed_dir"])
    root = processed / "model_v2"
    audit = json.loads((root / "scenario_audit.json").read_text(encoding="utf-8"))
    definitions = scenario_definitions(config)
    names = [s.name for s in definitions]
    if not audit["checks_passed"] or not audit["all_scenarios_completed"]:
        raise ValueError("Complete audit required before publishing a period-4 snapshot")
    if set(audit["scenarios"]) != set(names):
        raise ValueError("Audited scenario set differs from current configuration")
    summaries = {
        name: json.loads((root / name / "summary.json").read_text(encoding="utf-8"))
        for name in names
    }
    summary_table = pd.read_csv(root / "scenario_summary.csv")
    if set(summary_table.scenario) != set(names):
        raise ValueError("Combined summary is incomplete")
    frequency = pd.read_parquet(root / "station_selection_frequency.parquet")
    columns = [
        "candidate_id",
        "osm_id",
        "route_lat",
        "route_lng",
        "selected_count",
        "reoptimized_scenarios",
        "selected_in_all_solved_reoptimizations",
    ]
    frequency = frequency[columns].copy()
    frequency["coverage_forced"] = frequency.candidate_id.isin(
        audit["coverage_forced_sites"]["station_ids"]
    )
    stations = pd.read_parquet(root / "scenario_stations.parquet")
    for scenario in definitions:
        if scenario.network == "reoptimize":
            case = stations.loc[stations.scenario == scenario.name].set_index("candidate_id")
            frequency[f"selected_{scenario.name}"] = frequency.candidate_id.map(case.opened).gt(0.5)

    artifacts = [
        processed / name
        for name in ("demand_cells.parquet", "candidates.parquet", "travel_times.parquet")
    ]
    artifacts += [
        Path("src/lanet") / name
        for name in (
            "model.py",
            "problem.py",
            "check.py",
            "starts.py",
            "experiments.py",
            "scenarios.py",
        )
    ]
    artifacts += [Path(pulp.PULP_CBC_CMD().path)]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
    solver_artifacts = {
        name: {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root / name).iterdir()
            if path.suffix in {".log", ".mps", ".mst", ".sol"}
        }
        for name in names
    }
    snapshot = {
        "generated_utc": datetime.now(UTC).isoformat(),
        "interpretation": "Planning assumptions; checked feasible incumbents and solver bounds",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "package_versions": {
            name: importlib.metadata.version(name)
            for name in ("pulp", "pandas", "networkx", "geopandas", "pyarrow")
        },
        "config": config,
        "scenario_definitions": [scenario.__dict__ for scenario in definitions],
        "prediction_record": {
            "path": "docs/period4-predictions.md",
            "preregistered_commit": "a56fd6e",
            "sha256": hashlib.sha256(Path("docs/period4-predictions.md").read_bytes()).hexdigest(),
        },
        "source_sha256": hashes,
        "solver_artifact_sha256": solver_artifacts,
        "scenarios": summaries,
        "audit": audit,
    }
    output = Path("docs")
    (output / "period4-results.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    summary_table.to_csv(output / "period4-scenarios.csv", index=False)
    frequency.to_csv(output / "period4-station-frequency.csv", index=False)
    print(f"Published {len(summaries)} audited cases and {len(frequency)} candidate frequencies")


if __name__ == "__main__":
    main()
