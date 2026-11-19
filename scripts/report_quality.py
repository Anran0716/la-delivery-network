"""Independently audit the repaired runs and export their quality-qualified frequencies."""

import hashlib
import json
import subprocess
from pathlib import Path

import pandas as pd

from lanet import load_config
from lanet.check import check_solution
from lanet.experiments import county_inputs, read_solution
from lanet.scenarios import apply_scenario, scenario_definitions


def main():
    config = load_config()
    root = Path(config["data"]["processed_dir"]) / "quality_v2"
    protocol = json.loads((root / "protocol.json").read_text())
    revision_path = root / "cache_revision.json"
    revision = json.loads(revision_path.read_text()) if revision_path.exists() else {}
    assert protocol["config"] == config
    for p, h in protocol["sha256"].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest() == h:
            continue
        # Closeout clarified solver selection after this frozen batch completed.
        # Verify the recorded runner from Git; do not relabel it as current code.
        assert Path(p).resolve() == Path("scripts/04_quality.py").resolve()
        archived = subprocess.check_output(
            ["git", "show", revision["replay_runner_commit"] + ":scripts/04_quality.py"]
        )
        assert hashlib.sha256(archived).hexdigest() == h
    summaries = json.loads((root / "quality_results.json").read_text())
    definitions = scenario_definitions(config)
    assert set(summaries) == {s.name for s in definitions}
    baseline = read_solution(root / "baseline")
    checks, selections, quality_selections = {}, {}, {}
    for scenario in definitions:
        settings = apply_scenario(config, scenario)
        data, _ = county_inputs(settings, scenario.demand_multiplier, scenario.coverage_minutes)
        row = summaries[scenario.name]
        assert row["solver"]["solver_name"] == "HiGHS"
        result = read_solution(root / scenario.name)
        fixed = None
        if scenario.network != "reoptimize":
            source = (
                read_solution(Path(config["data"]["processed_dir"]) / "model_v1" / "strong")
                if scenario.network == "legacy31"
                else baseline
            )
            fixed = {i: int(v > 0.5) for i, v in source["y"].items()}
            if scenario.network == "outage":
                fixed[row["closed_station"]] = 0
        valid = check_solution(
            result["y"],
            result["x"],
            result["s"],
            data,
            w=result["w"],
            single_source=True,
            require_full_service=scenario.full_service,
            fixed_openings=fixed,
            objective=row["validation"]["objective"],
        )
        v1 = read_solution(root / "own_v1" / scenario.name)
        v1_summary = json.loads((root / "own_v1" / scenario.name / "summary.json").read_text())
        assert not v1_summary["solver"]["warm_start"]
        check_solution(
            v1["y"],
            v1["x"],
            v1["s"],
            data,
            require_full_service=scenario.full_service,
            fixed_openings=fixed,
        )
        assert row["own_v1_rounding"]["warm_start_checked"]
        assert row["solver"]["warm_start_checked"]
        assert (
            abs(
                valid["objective"] - row["solver"]["best_bound"] - row["solver"]["absolute_gap_usd"]
            )
            < 0.1
        )
        valid.pop("station_loads")
        checks[scenario.name] = valid
        if scenario.network == "reoptimize":
            opened = {i for i, v in result["y"].items() if v > 0.5}
            selections[scenario.name] = opened
            if row["solver"]["absolute_gap_usd"] < next(iter(data.fixed_cost.values())):
                quality_selections[scenario.name] = opened
    candidates = pd.read_parquet(Path(config["data"]["processed_dir"]) / "candidates.parquet")
    frequency = candidates[["candidate_id", "route_lat", "route_lng"]].copy()
    frequency["selected_all_profiles"] = frequency.candidate_id.map(
        lambda i: sum(i in s for s in selections.values())
    )
    frequency["all_profile_count"] = len(selections)
    frequency["selected_quality_profiles"] = frequency.candidate_id.map(
        lambda i: sum(i in s for s in quality_selections.values())
    )
    frequency["quality_profile_count"] = len(quality_selections)
    for name, ids in selections.items():
        frequency[name] = frequency.candidate_id.isin(ids)
    comparison = json.loads((root / "solver_comparison.json").read_text())
    if (root / "baseline1800" / "summary.json").exists():
        comparison["HiGHS1800_continuation"] = json.loads(
            (root / "baseline1800" / "summary.json").read_text()
        )
    execution_path = root / "execution_protocol.json"
    execution_protocol = (
        json.loads(execution_path.read_text()) if execution_path.exists() else protocol
    )
    if revision:
        executed_runner = subprocess.check_output(
            ["git", "show", revision["execution_runner_commit"] + ":scripts/04_quality.py"]
        )
        assert hashlib.sha256(executed_runner).hexdigest() == revision["execution_runner_sha256"]
        assert revision["fresh_solve_ast_unchanged"] and revision["model_and_inputs_unchanged"]
    public = {
        "protocol": {
            **protocol,
            "sha256": {
                Path(k).name if Path(k).is_absolute() else k: v
                for k, v in protocol["sha256"].items()
            },
        },
        "own_v1_summaries": {
            s.name: json.loads((root / "own_v1" / s.name / "summary.json").read_text())
            for s in definitions
        },
        "execution_protocol": {
            **execution_protocol,
            "sha256": {
                Path(k).name if Path(k).is_absolute() else k: v
                for k, v in execution_protocol["sha256"].items()
            },
        },
        "cache_only_revision": revision,
        "baseline_dollar_gate_passed": summaries["baseline"]["solver"]["absolute_gap_usd"] < 25000,
        "solver_policy_note": "All realized scenario solutions and final baseline used HiGHS. "
        "Fixed-HiGHS policy clarified at closeout, not claimed as preregistered. "
        "CBC comparison is one model/start/seed-1 experiment, not a solver-family ranking.",
        "comparison": comparison,
        "scenarios": summaries,
        "checks": checks,
        "quality_profiles": list(quality_selections),
        "frequency_definition": "Selection among independently initialized scenario incumbents; "
        "quality subset has absolute dollar gap below that profile's single-site fixed fee. "
        "Not statistical independence or proof across optimal solutions.",
    }
    output = Path("docs")
    (root / "final_audit.json").write_text(json.dumps(public, indent=2, allow_nan=False))
    frequency.to_csv(output / "quality-station-frequency.csv", index=False)
    table = pd.read_csv(root / "quality_summary.csv")
    fees = {
        s.name: apply_scenario(config, s)["facility"]["fixed_cost_usd_per_day"] for s in definitions
    }
    table["station_fixed_fee"] = table.scenario.map(fees)
    table["gap_in_station_fee_units"] = table.absolute_gap_usd / table.station_fixed_fee
    table["dollar_quality_pass"] = table.absolute_gap_usd < table.station_fixed_fee
    table.to_csv(output / "quality-scenarios.csv", index=False)
    lines = [
        "# Repaired solver-quality results",
        "",
        public["frequency_definition"],
        "",
        public["solver_policy_note"],
        "",
        "This is the final single complete quality batch. High gaps are retained; "
        "no second county-scale review or optimization round follows.",
        "",
        "## Baseline comparison and continuation",
        "",
        "Only the 600-second pair shares the same start. A possible 1,800-second run",
        "continues from the checked HiGHS 600-second incumbent.",
        "",
        "| Solver / limit | Stations | USD/day | Lower bound | Dollar gap | Gap % | Seconds |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, s in comparison.items():
        if name == "same_checked_seed":
            continue
        v, m = s["validation"], s["solver"]
        lines.append(
            f"| {name} | {v['open_stations']} | {v['objective']:,.2f} | "
            f"{m['best_bound']:,.2f} | {m['absolute_gap_usd']:,.2f} | "
            f"{100 * m['relative_gap']:.4f} | {m['solve_wall_seconds']:.2f} |"
        )
    lines += [
        "",
        "## Independently initialized scenarios",
        "",
        "| Scenario | Stations | Objective | Unmet/day | Mean min | Dollar gap | Gap % |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in table.itertuples():
        lines.append(
            f"| {r.scenario} | {r.stations} | {r.objective:,.2f} | {r.unmet:,.2f} | "
            f"{r.mean_minutes:.4f} | {r.absolute_gap_usd:,.2f} | {100 * r.gap:.4f} |"
        )
    common = set.intersection(*selections.values())
    lines += [
        "",
        "Baseline dollar gap below 25,000 USD/day: " + str(public["baseline_dollar_gate_passed"]),
        "",
        f"Common to all six profiles: {len(common)}.",
        ", ".join(sorted(common)),
        "",
        "Profiles passing the dollar-quality filter: " + ", ".join(quality_selections),
        "",
        f"Only {len(quality_selections)} of {len(selections)} reoptimization profiles pass "
        "the dollar-quality filter. Raw frequencies remain descriptive; "
        "no robust-station recommendation is made.",
        "",
        "Frequencies are conditional on these scenarios, solver budgets and independent v1 starts.",
        "The filter is a practical quality threshold, not a proof of an exact station count.",
        "The 250 structural exclusions remain outside the model (350.56/day; peak 490.78/day).",
        "Mean travel uses served demand. Penalties enter objective, not operating cost.",
        "",
        "[Protocol](quality-review.md), [site frequencies](quality-station-frequency.csv).",
        "Full audit retained locally at `data/processed/quality_v2/final_audit.json`.",
        "",
    ]
    (output / "quality-results.md").write_text("\n".join(lines))
    print(f"Audited {len(checks)} scenarios; quality profiles={len(quality_selections)}")


if __name__ == "__main__":
    main()
