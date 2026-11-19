"""Read frozen period-4 solutions; export tested metrics and one static baseline map."""

import json
import os
from pathlib import Path

import pandas as pd

from lanet import load_config
from lanet.metrics import calculate_metrics, selected_service
from lanet.scenarios import apply_scenario, scenario_definitions


def station_map(processed, folder, output):
    cache = Path(".cache/matplotlib").resolve()
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    import geopandas as gpd
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    land = gpd.read_parquet(processed / "mainland_block_groups.parquet").to_crs(3310)
    sites = pd.read_parquet(folder / "stations.parquet")
    points = gpd.GeoDataFrame(
        sites, geometry=gpd.points_from_xy(sites.route_lng, sites.route_lat), crs=4326
    ).to_crs(3310)
    opened = points.loc[points.opened > 0.5]
    fig, ax = plt.subplots(figsize=(9, 8.4), facecolor="#fafaf7")
    fig.subplots_adjust(left=0.04, right=0.76, bottom=0.10, top=0.88)
    ax.set_facecolor("#fafaf7")
    land.geometry.simplify(100).plot(ax=ax, color="#e5e8e3", linewidth=0)
    points.loc[points.opened < 0.5].plot(
        ax=ax, color="#a9b1b7", markersize=10, marker="x", linewidth=0.6, alpha=0.7
    )
    ax.scatter(
        opened.geometry.x,
        opened.geometry.y,
        s=25 + opened.assigned_parcels / 90,
        c="#176885",
        edgecolors="white",
        linewidths=0.65,
    )
    ax.set_aspect("equal")
    ax.set_axis_off()
    xmin, ymin, xmax, ymax = land.total_bounds
    x, y = xmin + 5000, ymin + 4500
    ax.plot([x, x + 20000], [y, y], color="#333f47", linewidth=2)
    ax.text(x + 10000, y + 2000, "20 km", ha="center", fontsize=9, color="#333f47")
    ax.annotate(
        "N",
        xy=(0.94, 0.93),
        xytext=(0.94, 0.84),
        xycoords="axes fraction",
        ha="center",
        fontsize=10,
        arrowprops={"arrowstyle": "->", "color": "#333f47"},
    )
    fig.text(
        0.06, 0.955, "LA County delivery stations", fontsize=22, weight="bold", color="#183341"
    )
    fig.text(
        0.06,
        0.915,
        f"Frozen baseline • {len(opened)} selected sites • mainland only",
        fontsize=12,
        color="#536570",
    )
    fig.text(0.78, 0.77, "SELECTED SITES", fontsize=10, weight="bold", color="#176885")
    fig.text(
        0.78, 0.72, "Circle area reflects\nparcels served per day.", fontsize=10, color="#536570"
    )
    handles = [
        ax.scatter([], [], s=25 + v / 90, c="#176885", edgecolors="white", label=f"{v:,}")
        for v in (2000, 10000, 17000)
    ]
    fig.legend(
        handles=handles,
        loc="center left",
        bbox_to_anchor=(0.77, 0.59),
        frameon=False,
        labelspacing=1.6,
        fontsize=10,
    )
    fig.text(0.78, 0.39, "×  Other candidates", fontsize=10, color="#6c7a83")
    fig.text(0.78, 0.32, "No robust-site\nclassification shown.", fontsize=10, color="#536570")
    fig.text(
        0.06,
        0.055,
        "Context: Census TIGER 2023 land geometry • Candidate sites: © OpenStreetMap contributors",
        fontsize=8,
        color="#536570",
    )
    fig.text(
        0.06,
        0.03,
        "EPSG:3310 • Assumption-based independent project; not a company operating network",
        fontsize=8,
        color="#536570",
    )
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    processed = Path(load_config()["data"]["processed_dir"])
    root = processed / "quality_v2"
    frozen = json.loads((root / "protocol.json").read_text())["config"]
    summaries = json.loads((root / "quality_results.json").read_text())
    travel_source = pd.read_parquet(processed / "travel_times.parquet")[
        ["candidate_id", "h3", "travel_time_min"]
    ]
    demands, assignments, times, stations, params = [], [], [], [], []
    for case in scenario_definitions(frozen):
        folder = root / case.name
        config = apply_scenario(frozen, case)
        d = pd.read_parquet(folder / "unmet.parquet")[["h3", "parcels"]]
        d["in_model"] = True
        excluded = pd.read_csv(folder / "structurally_uncovered.csv")[["h3", "parcels"]]
        excluded["in_model"] = False
        d = pd.concat([d, excluded], ignore_index=True).rename(
            columns={"parcels": "demand_parcels"}
        )
        d["scenario"] = case.name
        a = pd.read_parquet(folder / "assignments.parquet")
        # Join the independent frozen road-time matrix, not a copied assignment field.
        t = travel_source.copy()
        t["scenario"] = case.name
        a = selected_service(a)[["h3", "candidate_id", "parcels"]]
        a = a.rename(columns={"parcels": "served_parcels"})
        a["scenario"] = case.name
        s = pd.read_parquet(folder / "stations.parquet")[["candidate_id", "opened", "capacity"]]
        s["opened"] = s.opened > 0.5
        s["fixed_cost"] = config["facility"]["fixed_cost_usd_per_day"]
        s["scenario"] = case.name
        demands.append(d)
        assignments.append(a)
        times.append(t)
        stations.append(s)
        params.append(
            {
                "scenario": case.name,
                "coverage_minutes": 20.0,
                "delivery_usd_per_parcel_minute": config["cost"]["delivery_usd_per_parcel_minute"],
            }
        )
    metrics, site_metrics = calculate_metrics(
        pd.concat(demands),
        pd.concat(assignments),
        pd.concat(times),
        pd.concat(stations),
        pd.DataFrame(params),
    )
    for row in metrics.loc[metrics.scope == "modeled"].itertuples():
        expected = summaries[row.scenario]["validation"]
        for column, key in [
            ("served_parcels", "served_parcels"),
            ("unmet_parcels", "unmet_parcels"),
            ("fixed_cost", "fixed_cost"),
            ("delivery_cost", "delivery_cost"),
        ]:
            if abs(getattr(row, column) - expected[key]) > 0.01:
                raise ValueError(
                    f"SQL metric does not reconcile with frozen output: {row.scenario}/{column}"
                )
    output = processed / "metrics"
    output.mkdir(exist_ok=True)
    metrics.to_parquet(output / "scenario_metrics.parquet", index=False)
    site_metrics.to_parquet(output / "station_metrics.parquet", index=False)
    metrics.to_csv("docs/metrics-scenarios.csv", index=False)
    site_metrics.to_csv("docs/metrics-stations.csv", index=False)
    lines = [
        "# Frozen-solution SQL metrics",
        "",
        "Modeled scope (1,615 cells); utilization is capacity-weighted across open sites.",
        "No optimization was rerun. High-gap scenario results remain provisional.",
        "",
        "| Scenario | Network utilization | Mean min | <=20 min | USD/served parcel | Unmet |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in metrics.loc[metrics.scope == "modeled"].itertuples():
        lines.append(
            f"| {r.scenario} | {100 * r.network_utilization:.2f}% | "
            f"{r.weighted_mean_travel_minutes:.3f} | {100 * r.coverage_20min:.2f}% | "
            f"{r.cost_per_served_parcel:.3f} | {100 * r.unmet_rate:.3f}% |"
        )
    lines += [
        "",
        "[Definitions, scope and boundary cases](metrics.md).",
        "[Both scopes](metrics-scenarios.csv); [station utilization](metrics-stations.csv).",
        "Study-area scope also counts 250 structural exclusions as unmet demand.",
        "Lower mean time or per-served cost does not offset a larger unmet share.",
        "",
    ]
    Path("docs/metrics-results.md").write_text("\n".join(lines), encoding="utf-8")
    station_map(processed, root / "baseline", Path("docs/station-map.png"))
    print(metrics.loc[metrics.scope == "modeled"].to_string(index=False))


if __name__ == "__main__":
    main()
