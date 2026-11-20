"""One fixed-network reassignment control; preserve the frozen nine-case batch."""

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from lanet.check import check_solution
from lanet.experiments import county_inputs, read_solution, write_solution
from lanet.model import solve_model


def main():
    root = Path("data/processed/quality_v2")
    frozen = json.loads((root / "protocol.json").read_text())["config"]
    settings = deepcopy(frozen)
    settings["facility"]["utilization_limit"] = 1.0
    data, frames = county_inputs(settings, coverage_minutes=45)
    start = read_solution(root / "baseline")
    fixed = {i: int(v > 0.5) for i, v in start["y"].items()}
    assert sum(fixed.values()) == 37
    folder = root / "outage_control"
    path = folder / "summary.json"
    if path.exists():
        summary = json.loads(path.read_text())
        result = read_solution(folder)
        check_solution(
            result["y"],
            result["x"],
            result["s"],
            data,
            w=result["w"],
            single_source=True,
            fixed_openings=fixed,
            objective=summary["validation"]["objective"],
        )
        print("Reused existing control; no second solve", flush=True)
    else:
        result = solve_model(
            data,
            "strong",
            folder,
            single_source=True,
            full_service=False,
            fixed_openings=fixed,
            warm_start=start,
            solver_name="HiGHS",
            time_limit_seconds=600,
            relative_gap=0.005,
        )
        summary = write_solution(
            folder,
            result,
            data,
            frames,
            {
                "description": "37 frozen baseline sites; no closure; u=1; 45-minute eligibility",
                "coverage_minutes": 45,
                "utilization_limit": 1.0,
                "baseline_start_checked": True,
            },
        )
    frozen_results = json.loads((root / "quality_results.json").read_text())
    cases = {
        "Baseline (85%, 30 min)": frozen_results["baseline"],
        "No closure (100%, 45 min)": summary,
        "Outage (100%, 45 min)": frozen_results["outage"],
    }
    rows = []
    for name, s in cases.items():
        v, m = s["validation"], s["solver"]
        rows.append(
            {
                "case": name,
                "stations": v["open_stations"],
                "mean_minutes": v["weighted_mean_travel_minutes"],
                "unmet_parcels": v["unmet_parcels"],
                "delivery_cost": v["delivery_cost"],
                "objective": v["objective"],
                "dollar_gap": m["absolute_gap_usd"],
                "relative_gap": m["relative_gap"],
                "seconds": m["solve_wall_seconds"],
            }
        )
    table = pd.DataFrame(rows)
    table.to_csv("docs/outage-control.csv", index=False)
    delta = rows[2]["mean_minutes"] - rows[1]["mean_minutes"]
    report = [
        "# Outage reassignment control",
        "",
        "One additional fixed-network solve, explicitly requested after the frozen batch.",
        "All 37 baseline sites remain open; utilization is 100%, eligibility 45 minutes.",
        "The same 1,615 modeled cells and 250 structural exclusions are retained.",
        "HiGHS, seed 1, serial, 600-second limit and 0.5% gap target; the checked",
        "baseline allocation is the feasible start. Slack and single-sourcing match outage.",
        "",
        "| Case | Sites | Mean min | Modeled unmet/day | Delivery USD/day | Dollar gap |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in rows:
        report.append(
            f"| {r['case']} | {r['stations']} | {r['mean_minutes']:.4f} | "
            f"{r['unmet_parcels']:.2f} | {r['delivery_cost']:,.2f} | {r['dollar_gap']:,.2f} |"
        )
    report += [
        "",
        f"Outage minus matched no-closure control: **{delta:+.4f} minutes**.",
        "Checked incumbent comparison only; no exact-optimality or real-world causal claim.",
        "Active-site fixed costs differ by 25,000 USD/day; that is not committed-rent savings.",
        "Structural exclusions add 350.56 unmet parcels/day outside the modeled totals.",
        "The original nine scenarios, predictions, metrics and map remain frozen.",
        "",
    ]
    Path("docs/outage-control.md").write_text("\n".join(report), encoding="utf-8")
    print(table.to_string(index=False), flush=True)
    print(f"Matched outage delta: {delta:+.6f} minutes", flush=True)


if __name__ == "__main__":
    main()
