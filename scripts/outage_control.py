"""One fixed-network reassignment control; preserve the frozen nine-case batch."""

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from lanet.check import check_solution
from lanet.experiments import county_inputs, read_solution, write_solution
from lanet.model import solve_model


def report_facts(config, control, outage, frames):
    """Derive report quantities; reject changed fees paired with stale solutions."""
    fee = config["facility"]["fixed_cost_usd_per_day"]
    for summary in (control, outage):
        values = summary["validation"]
        expected = fee * values["open_stations"]
        if abs(expected - values["fixed_cost"]) > 0.01:
            raise ValueError("Frozen config fee and recorded station costs disagree")
    return {
        "fixed_cost_difference": fee
        * (control["validation"]["open_stations"] - outage["validation"]["open_stations"]),
        "modeled_cells": len(frames["demand"]),
        "excluded_cells": len(frames["excluded"]),
        "excluded_parcels": float(frames["excluded"].parcels.sum()),
    }


def main():
    root = Path("data/processed/quality_v2")
    frozen = json.loads((root / "protocol.json").read_text())["config"]
    settings = deepcopy(frozen)
    utilization = frozen["scenarios"]["stress_utilization_limit"]
    coverage = frozen["scenarios"]["outage_coverage_minutes"]
    settings["facility"]["utilization_limit"] = utilization
    data, frames = county_inputs(settings, coverage_minutes=coverage)
    start = read_solution(root / "baseline")
    fixed = {i: int(v > 0.5) for i, v in start["y"].items()}
    station_count = sum(fixed.values())
    folder = root / "outage_control"
    path = folder / "summary.json"
    if path.exists():
        summary = json.loads(path.read_text())
        if (
            summary.get("coverage_minutes") != coverage
            or summary.get("utilization_limit") != utilization
        ):
            raise ValueError("Cached control policy differs from frozen config")
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
                "description": f"{station_count} frozen baseline sites; no closure; "
                f"u={utilization:g}; {coverage:g}-minute eligibility",
                "coverage_minutes": coverage,
                "utilization_limit": utilization,
                "baseline_start_checked": True,
            },
        )
    frozen_results = json.loads((root / "quality_results.json").read_text())
    facts = report_facts(frozen, summary, frozen_results["outage"], frames)
    cases = {
        f"Baseline ({100 * frozen['facility']['utilization_limit']:g}%, "
        f"{frozen['travel']['coverage_minutes']:g} min)": frozen_results["baseline"],
        f"No closure ({100 * utilization:g}%, {coverage:g} min)": summary,
        f"Outage ({100 * utilization:g}%, {coverage:g} min)": frozen_results["outage"],
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
        f"All {station_count:,} baseline sites remain open; utilization is "
        f"{100 * utilization:g}%, eligibility {coverage:g} minutes.",
        f"The same {facts['modeled_cells']:,} modeled cells and "
        f"{facts['excluded_cells']:,} structural exclusions are retained.",
        f"{summary['solver']['solver_name']}, seed {summary['solver']['random_seed']}, serial, "
        f"{summary['solver']['time_limit_seconds']:g}-second limit and "
        f"{100 * summary['solver']['requested_relative_gap']:g}% gap target; the checked",
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
        f"Active-site fixed cost (no closure minus outage): "
        f"{facts['fixed_cost_difference']:,.2f} USD/day; that is not committed-rent savings.",
        f"Structural exclusions add {facts['excluded_parcels']:,.2f} unmet parcels/day "
        "outside the modeled totals.",
        f"Original {len(frozen_results)}-case batch, predictions, metrics and map remain frozen.",
        "",
    ]
    Path("docs/outage-control.md").write_text("\n".join(report), encoding="utf-8")
    print(table.to_string(index=False), flush=True)
    print(f"Matched outage delta: {delta:+.6f} minutes", flush=True)


if __name__ == "__main__":
    main()
