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


def write_markdown(output, snapshot, frequency):
    audit = snapshot["audit"]
    scenarios = snapshot["scenarios"]
    hard = snapshot["hard_full_service_v1"]
    lines = [
        "# Measured period-4 results",
        "",
        "All figures are assumption-based planning results from independently checked",
        "feasible incumbents. Solver bounds and actual elapsed times are retained.",
        "Station counts are not proven minima. The fixed-network reference is the",
        "frozen 38-station v2 baseline; the old 31-station network is a separate test.",
        "",
        f"Hard-service v1: **{hard['validation']['open_stations']} stations**, "
        f"**{hard['validation']['objective']:,.2f} USD/day**, "
        f"**+{hard['objective_delta_vs_P100']:,.2f} USD/day** versus P=100.",
        f"Its {hard['split_cells']} split cells become zero under v2. "
        "The two incumbent objectives differ",
        f"by {audit['v1_v2_comparison']['incumbent_objective_difference']:,.2f} USD/day; "
        "this is not an exact optimal single-sourcing premium.",
        "",
        "## Scenario comparison",
        "",
        "| Scenario | Stations | Objective USD/day | Modeled unmet/day | Unmet % | "
        "Mean min | Gap % | Solve s |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, summary in scenarios.items():
        v, solver = summary["validation"], summary["solver"]
        rate = 100 * v["unmet_parcels"] / v["total_demand_parcels"]
        lines.append(
            f"| {name} | {v['open_stations']} | {v['objective']:,.2f} | "
            f"{v['unmet_parcels']:,.2f} | {rate:.4f} | "
            f"{v['weighted_mean_travel_minutes']:.4f} | "
            f"{100 * solver['relative_gap']:.4f} | {solver['solve_wall_seconds']:.2f} |"
        )
    lines += [
        "",
        "Unmet percentages use the fixed 1,615-cell modeled universe. The same 250",
        "structural exclusions add 350.56 parcels/day outside the model, or 490.78",
        "during peak. Mean travel weights served parcels only. Objective includes",
        "unmet penalties; penalties are not operating expense. Outage fixed cost",
        "counts active sites and does not represent committed rent savings.",
        "",
        "## Forecast check",
        "",
        "The [original prediction record](period4-predictions.md) was committed before",
        "these runs. The material fixed-cost threshold was a change of more than one site.",
        "",
    ]
    for fee in (15000, 40000):
        p = audit["predictions"][f"fixed_cost_{fee}"]
        verdict = "within" if p["within_one_station_prediction"] else "outside"
        lines.append(
            f"- Fixed fee {fee:,}: station change **{p['station_change']:+d}**; "
            f"locations added {len(p['locations_added'])}, removed {len(p['locations_removed'])}. "
            f"This is {verdict} the preregistered threshold."
        )
    legacy = audit["predictions"]["legacy31_peak"]
    peak_count = scenarios["peak_reoptimized"]["validation"]["open_stations"]
    lines += [
        f"- Peak reoptimization needs at least 42 sites by aggregate capacity; "
        f"the checked incumbent uses {peak_count}.",
        f"- Legacy 31-site peak: forecast lower bound "
        f"{legacy['predicted_capacity_shortfall']:,.2f} unmet/day; measured "
        f"{legacy['observed_unmet_parcels']:,.2f} "
        f"({100 * legacy['observed_unmet_share']:.4f}%).",
        "",
        "Unchanged station counts alone do not establish fixed-cost insensitivity.",
        "Sensitivity cases reuse the v2 baseline as their preferred start, and",
        "time-limited search may retain it. Neither fixed-fee run improved that start.",
        "The JSON audit records whether each start",
        "was improved and cross-prices the three fixed-fee plans at each fee.",
        "The 25,000-capacity case also retains its start, with a 17.1879% gap:",
        "the capacity sensitivity is unresolved at this search limit.",
        "",
        "## Capacity, geography and outage",
        "",
        f"For peak with the new fixed network, independent divisible-demand maximum "
        f"flow leaves at least "
        f"{audit['scenarios']['peak_fixed']['continuous_maxflow_unmet_lower_bound']:,.2f} "
        "parcels/day unmet. Total physical capacity exceeds demand; local coverage",
        "and capacity bottlenecks explain most of the observed shortage.",
        "",
        f"Outage closes {scenarios['outage']['closed_station']}. "
        "Utilization is relaxed to 100% and eligibility to 45 minutes, so its change",
        "from baseline combines three policy changes. The audit records changed",
        "providers, positive and negative parcel-minute changes, and use of arcs",
        "above 30 minutes. It is not an isolated causal estimate of station loss.",
        "",
        "## Selection stability",
        "",
    ]
    stability = audit["selection_stability"]
    common = stability["selected_in_every_solved_reoptimization"]
    lines += [
        f"**{len(common)} sites** appear in all six unique reoptimization incumbents. "
        "Capacity 20,000 and fixed fee 25,000 alias baseline and are not double-counted.",
        "This is incumbent stability, not proof across all optimal solutions; shared",
        "warm starts and unresolved gaps limit the inference.",
        "",
        ", ".join(f"`{i}`" for i in common),
        "",
        "Coverage alone forces the following 13 sites under the unchanged 30-minute",
        "arcs and hard full-service rule (177 cells have exactly one candidate):",
        "",
        ", ".join(f"`{i}`" for i in audit["coverage_forced_sites"]["station_ids"]),
        "",
        "Sites selected in only some profiles:",
        "",
        "| Candidate | Selected / 6 |",
        "| --- | ---: |",
    ]
    mixed = frequency.loc[
        (frequency.selected_count > 0)
        & (frequency.selected_count < frequency.reoptimized_scenarios)
    ].sort_values(["selected_count", "candidate_id"], ascending=[False, True])
    lines += [f"| {r.candidate_id} | {r.selected_count} |" for r in mixed.itertuples()]
    lines += [
        "",
        "[All 117 candidates and coordinates](period4-station-frequency.csv), "
        "[scenario CSV](period4-scenarios.csv), and "
        "[full summaries, bounds, audit and hashes](period4-results.json).",
        "",
    ]
    (output / "period4-results.md").write_text("\n".join(lines), encoding="utf-8")


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
    artifacts += [
        Path("scripts") / name
        for name in ("04_scenarios.py", "audit_scenarios.py", "publish_scenario_report.py")
    ]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
    hashes["cbc_binary"] = hashlib.sha256(Path(pulp.PULP_CBC_CMD().path).read_bytes()).hexdigest()
    solver_artifacts = {
        name: {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root / name).iterdir()
            if path.suffix in {".log", ".mps", ".mst", ".sol"}
        }
        for name in names
    }
    unmet_samples = {}
    for name in names:
        unmet = pd.read_parquet(root / name / "unmet.parquet")
        sample = unmet.loc[unmet.unmet_parcels > 0.01].sort_values(
            ["unmet_parcels", "h3"], ascending=[False, True]
        )
        unmet_samples[name] = json.loads(
            sample[["h3", "lat", "lng", "households", "parcels", "unmet_parcels"]]
            .head(10)
            .to_json(orient="records")
        )
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
        "hard_full_service_v1": json.loads(
            (processed / "model_v1_full_service" / "summary.json").read_text(encoding="utf-8")
        ),
        "largest_modeled_unmet_cells": unmet_samples,
        "audit": audit,
    }
    output = Path("docs")
    (output / "period4-results.json").write_text(
        json.dumps(snapshot, indent=2, allow_nan=False), encoding="utf-8"
    )
    summary_table.to_csv(output / "period4-scenarios.csv", index=False)
    frequency.to_csv(output / "period4-station-frequency.csv", index=False)
    write_markdown(output, snapshot, frequency)
    print(f"Published {len(summaries)} audited cases and {len(frequency)} candidate frequencies")


if __name__ == "__main__":
    main()
