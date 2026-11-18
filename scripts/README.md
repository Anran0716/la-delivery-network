# Pipeline scripts

`01_download.py` downloads and joins the county inputs. The remaining entry points
will be added in their corresponding implementation periods.

Run `audit_water.py` after `01_download.py` and before H3 allocation. It audits
ALAND/AWATER, checks the same-year TIGER topological-face area totals, and saves
land geometry plus a verification report under `data/processed/`.

| Script | Purpose | Period |
| --- | --- | --- |
| `01_download.py` | Download ACS households and TIGER boundaries | 1 |
| `02_demand.py` | Construct mainland H3 demand cells | 1 |
| `03_travel.py` | Generate candidates and directed travel times | 2 |
| `04_scenarios.py` | Solve, validate, and record scenario results | 3–4 |
| `05_metrics.py` | Run DuckDB metrics and export Tableau inputs | 5 |
