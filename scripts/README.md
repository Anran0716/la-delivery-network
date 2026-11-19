# Pipeline scripts

`01_download.py` downloads and joins the county inputs. `02_demand.py` constructs
and audits mainland H3 demand. `03_travel.py` generates industrial candidates,
directed times, and a demand-weighted coverage-gap report. Model/scenario and SQL
entry points will be added in their corresponding implementation periods.

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
| `04_scenarios.py` | Solve, validate, and record scenario results | 3–4 |
| `05_metrics.py` | Run DuckDB metrics and export Tableau inputs | 5 |
