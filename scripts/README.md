# Pipeline scripts

`outage_control.py` performs the separately requested single no-closure control
with 37 frozen baseline sites, 100% utilization and 45-minute eligibility. It
uses a new output folder and reuses an existing checked result rather than
solving a second time. Report: `docs/outage-control.md`.

Reduced period 5 is implemented by `05_metrics.py`: frozen solutions to DuckDB
views, scenario/station metrics and a static baseline map. Install the `plots`
extra for rendering. Definitions, boundary cases and result links are in
`docs/metrics.md`. It never invokes a solver; Tableau is deferred.

The current period-4 quality repair uses `04_quality.py`, followed by
`report_quality.py` after all nine cases finish. See `docs/quality-review.md`.
The earlier `04_scenarios.py` outputs are historical shared-start experiments.
Their fingerprint guard intentionally prevents reusing them after model-source
changes; the quality runner preserves them and uses a separate output directory.

`01_download.py` downloads and joins the county inputs. `02_demand.py` constructs
and audits mainland H3 demand. `03_travel.py` generates industrial candidates,
directed times, and a demand-weighted coverage-gap report. Periods 3–4 implement
the checked facility-location models and scenario runner. SQL metrics remain for
period 5.

Run `audit_water.py` after `01_download.py` and before H3 allocation. It audits
ALAND/AWATER, checks the same-year TIGER topological-face area totals, and saves
land geometry plus a verification report under `data/processed/`.
Then run `02_demand.py` for the 2 km buffered grid, island ledger, demand allocation,
conservation checks, marine-center diagnostics, and land routing points.

Before directed travel times, run `audit_low_demand.py` to flag cells below one
parcel/day without deleting them. Install the `downloads` extra and run
`download_drive_graph.py` to cache the driving graph from the configured source;
`compare_snaps.py` snaps both land-route points and original H3 centers to the same
largest strongly connected component in EPSG:3310. It exports distance to the
nearest node, nearest edge, and the nearer endpoint of that edge. The endpoint is
the model's `node_id`; H3-center distances remain as a separate audit.

Run `download_landuse.py` for the Geofabrik land-use archive, then `03_travel.py`
for county-clipped candidates (4 ha, 3 km spacing, up to 120) and directed shortest
times after the 1.3 congestion multiplier. `travel_times_all.parquet` contains all
OD pairs; `travel_times.parquet` / `.csv` retain the 45-minute superset. Baseline
model arcs must use its `within_30_min` flag. Run `audit_travel.py` for independent
NetworkX OD checks, county/spacing checks, demand retention, and the geographic
edge-warning diagnostic. This audit requires the `downloads` extra for PBF metadata.
All downloaded and processed files stay under ignored data directories.

For period 3, first run `pytest tests/test_model_toys.py tests/test_solution_check.py -v`.
Their hand calculations are in `docs/toy-model-hand-calculations.md`. Only after
they pass, run `04_model_v1.py` for sequential strong/weak CBC solves, followed by
`diagnose_v1_unmet.py` for independent maximum-flow checks of capacity and coverage.
The 250 structurally uncovered cells stay outside the optimization objective and
are exported separately. `model_v1/strong` and `model_v1/weak` retain solver logs,
MPS/solution files, station/assignment/unmet tables, independent checks and bounds.
`model_v1/comparison.json` records the benchmark and `unmet_diagnostic.json`
distinguishes selected-network shortfalls from all-candidate infeasibility.

For period 4, run the offline single-source and warm-start tests first:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_v2.py tests/test_solution_check.py -v
.venv\Scripts\python.exe scripts/04_full_service_v1.py
.venv\Scripts\python.exe scripts/04_scenarios.py
.venv\Scripts\python.exe scripts/audit_scenarios.py
.venv\Scripts\python.exe scripts/publish_scenario_report.py
```

`04_full_service_v1.py` preserves the P=100 reference and writes a separate hard
`s=0` continuous run. Its output is required before v2. `04_scenarios.py` runs
sequential CBC solves for v2 baseline, peak reoptimization, fixed-network peak,
outage, capacity and fixed-cost sensitivities, and a separate legacy-31 peak test.
The default capacity and fixed-cost controls both reuse baseline, so selection
frequency counts six unique reoptimization profiles. All hard-service runs use
`x=w`; fixed-network stress runs retain partial service at one selected station.

Every warm start must pass `check_solution()` before reaching CBC. Cache reuse
also rechecks feasibility and requires a matching configuration, fixed network,
input-data hashes and formulation-source hashes. Changed fingerprints raise an
error instead of silently mixing experiments. `--only baseline` or a list of
scenario names can run a subset, provided its baseline dependencies exist. CBC's
600-second limit is soft; actual wall times, bounds and termination reasons are
retained, including overruns and feasible runs without exact optimality proofs.

Each case saves solver artifacts, rounding/repair audit, station/assignment/unmet
tables and structural exclusions under `data/processed/model_v2/<scenario>/`.
Combined `scenario_stations.parquet` and `scenario_assign.parquet` include all
cases; the latter retains the 250 out-of-model cells with `in_model=False` and
null `solver_s`. They are counted as unserved study-area demand separately from
model slack. The audit rechecks all nine cases, combined-table conservation,
station loads, fixed-network maximum-flow lower bounds, selection frequencies,
and the preregistered predictions. `audit_scenarios.py --allow-partial` provides
an explicitly incomplete audit while solves are running.

After the complete audit, `publish_scenario_report.py` writes small Git-tracked
snapshots under `docs/`: a measured Markdown report, all scenario summaries and
audit evidence in JSON, a scenario comparison CSV, and all 117 candidates'
coordinates and selection frequencies in CSV. It records configuration, package versions and SHA256 hashes
for the model inputs, source and solver artifacts. The original prediction file
is preserved separately; publishing results does not rewrite the forecast.

| Script | Purpose | Period |
| --- | --- | --- |
| `01_download.py` | Download ACS households and TIGER boundaries | 1 |
| `02_demand.py` | Construct mainland H3 demand cells | 1 |
| `audit_low_demand.py` | Flag and report small demand; retain all cells | 2 preparation |
| `download_drive_graph.py` | Cache the mainland directed OSM drive graph | 2 preparation |
| `compare_snaps.py` | Compare node/edge/endpoint distances; select endpoint nodes | 2 |
| `download_landuse.py` | Cache Geofabrik industrial land-use source | 2 |
| `03_travel.py` | Generate candidates and directed travel times | 2 |
| `audit_travel.py` | Independently verify OD results and spatial constraints | 2 |
| `04_model_v1.py` | Compare strong/weak continuous-allocation CFLP v1 | 3 |
| `diagnose_v1_unmet.py` | Independently diagnose modeled unmet demand with maximum flow | 3 |
| `04_full_service_v1.py` | Rerun continuous v1 with hard s=0 | 4 preparation |
| `04_scenarios.py` | Solve single-source v2 and all scenario profiles | 4 |
| `audit_scenarios.py` | Independently check saved cases, exports and predictions | 4 |
| `publish_scenario_report.py` | Export audited summaries, candidate frequencies and hashes | 4 |
| `05_metrics.py` | Run DuckDB metrics and export Tableau inputs | 5 |
