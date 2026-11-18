# Pipeline scripts

`01_download.py` downloads and joins the county inputs. `02_demand.py` constructs
and audits the mainland H3 demand layer. The remaining entry points will be added
in their corresponding implementation periods.

Run `audit_water.py` after `01_download.py` and before H3 allocation. It audits
ALAND/AWATER, checks the same-year TIGER topological-face area totals, and saves
land geometry plus a verification report under `data/processed/`.
Then run `02_demand.py` for the 2 km buffered grid, island ledger, demand allocation,
conservation checks, marine-center diagnostics, and land routing points.

Before directed travel times, run `audit_low_demand.py` to flag cells below one
parcel/day without deleting them. Install the `downloads` extra and run
`download_drive_graph.py` to cache the driving graph from the configured source;
`compare_snaps.py` snaps both land-route points and original H3 centers to the same
largest strongly connected component. It exports both distance sets and selects
only `route_node` as the model's `node_id`. All downloaded and processed files stay
under ignored data directories. `03_travel.py` remains a later implementation step.

| Script | Purpose | Period |
| --- | --- | --- |
| `01_download.py` | Download ACS households and TIGER boundaries | 1 |
| `02_demand.py` | Construct mainland H3 demand cells | 1 |
| `audit_low_demand.py` | Flag and report small demand; retain all cells | 2 preparation |
| `download_drive_graph.py` | Cache the mainland directed OSM drive graph | 2 preparation |
| `compare_snaps.py` | Compare both point types; select route-point nodes | 2 preparation |
| `03_travel.py` | Generate candidates and directed travel times | 2 |
| `04_scenarios.py` | Solve, validate, and record scenario results | 3–4 |
| `05_metrics.py` | Run DuckDB metrics and export Tableau inputs | 5 |
