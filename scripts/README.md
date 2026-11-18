# Pipeline scripts

These entry points will be added in the corresponding implementation periods.
No data download or analysis is implemented in period 0.

| Script | Purpose | Period |
| --- | --- | --- |
| `01_download.py` | Download ACS households and TIGER boundaries | 1 |
| `02_demand.py` | Construct mainland H3 demand cells | 1 |
| `03_travel.py` | Generate candidates and directed travel times | 2 |
| `04_scenarios.py` | Solve, validate, and record scenario results | 3–4 |
| `05_metrics.py` | Run DuckDB metrics and export Tableau inputs | 5 |
