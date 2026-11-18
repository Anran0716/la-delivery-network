# LA delivery network

[![ci](https://github.com/Anran0716/la-delivery-network/actions/workflows/ci.yml/badge.svg)](https://github.com/Anran0716/la-delivery-network/actions/workflows/ci.yml)

An independent project to plan the location and capacity of last-mile delivery
stations in Los Angeles County. The intended decision is how many stations to open,
where to put them, and how the network performs under a 40% demand peak or a station
outage. **The period 0 foundation is complete, and the period 1 county inputs have
been downloaded and joined. No station recommendations or location-model results
have been computed yet.**

The planned pipeline uses ACS households, H3 demand cells, OSM industrial land and
directed driving times, a capacitated facility-location model in PuLP, and a tested
DuckDB metrics layer feeding Tableau Public.

## Setup and checks

Use Python 3.11 (the guide's target) or 3.12. CI checks both versions on Linux.
From the repository root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pre_commit install
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -c "import pulp; print(pulp.listSolvers(onlyAvailable=True))"
```

Run `pre-commit run --all-files` **before the first commit**. The pinned Gitleaks
hook uses pre-commit's managed Go environment; its first run needs network access
to install the tool. To scan the full history separately, install
[Gitleaks v8.30.1](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)
from its official release and run `gitleaks git --redact .`
(the current equivalent of `gitleaks detect`).
The Ruff hooks and development dependency use the same version.

PuLP is pinned to **3.3.0**, which retains the bundled CBC binary and
`PULP_CBC_CMD` API used in the guide. [PuLP 4 changes that API and solver
installation](https://github.com/coin-or/pulp/blob/master/doc/source/guides/how_to_migrate_to_v4.rst).
The solver smoke test checks actual execution, in addition to solver discovery.

Tests use only repository configuration, temporary files, and a tiny local MILP.
CI installs software dependencies but does not download ACS, TIGER, OSM, or other
study data. Analytical modules and SQL beyond the county input join are reserved
for later periods.

## Download the county inputs

```powershell
.venv\Scripts\python.exe scripts/01_download.py
```

Sources and outputs are saved under `data/raw/` and stay out of Git. Existing
downloads are reused. The script validates the TIGER ZIP, retains only
`COUNTYFP == "037"`, builds the 12-digit GEOID from string geography components,
and requires zero unmatched GEOIDs in both directions before joining.

The guide's keyless API example no longer works: [Census now requires a key for
data queries](https://www.census.gov/library/video/2026/adrm/requesting-a-census-data-api-key.html).
The downloader uses the [official 2023 ACS five-year Summary
File](https://www.census.gov/programs-surveys/acs/data/summary-file.2023.html),
which contains the same Detailed Table estimates and margins of error. It maps
`B11001_E001` to API field `B11001_001E`, and `B11001_M001` to `B11001_001M`.

The county CSV and joined GeoPackage retain both fields. CSV geography columns
must be read as strings to preserve leading zeros; the GeoPackage stores them as
text. The manifest records source URLs, file sizes, SHA256 hashes, and join counts.
This step includes the county's islands; mainland selection comes next. Margins
of error describe uncertainty in the household estimates and must not simply be
added together or interpreted as parcel-demand uncertainty.

The downloaded inputs contain **6,591 block groups** in both ACS and TIGER, with
**zero unmatched GEOIDs** in either direction. Their household estimates sum to
**3,390,254**, exactly matching the county record in the same Summary File.

## Configuration and assumptions

`config.yaml` is the source of planning parameters. `load_config()` validates required
fields, positive finite numbers, utilization bounds, FIPS strings, and travel cutoffs.
Run Python from the repository root or pass an explicit configuration path:

```python
from lanet import load_config

config = load_config("config.yaml")
```

| Parameter | Baseline | Basis |
| --- | --- | --- |
| Study area | LA County mainland; retain Antelope Valley | Largest contiguous county polygon; exclude islands |
| Households | ACS 2023 five-year block groups, B11001_001E and margin of error | [Census variable definition](https://api.census.gov/data/2023/acs/acs5/groups/B11001.html) |
| Demand cells | H3 resolution 7 | Guide assumption for tractable model size |
| Parcel rate | 0.15 parcels per household per day | Planning assumption; external volume and market-share sources still need verification |
| Capacity and baseline utilization | 20,000 parcels per day; 85% | Assumed capacity with operating headroom |
| Fixed cost | USD 25,000 per station per day | Assumed rent and fixed labor; sensitivity planned |
| Delivery cost | USD 0.015 per parcel per minute | Assumed USD 1.5 vehicle-minute × 2 / 200 parcels |
| Congestion | Free-flow driving time × 1.3 | Uniform planning assumption |
| Coverage | 30 minutes; outage allowance 45 minutes | Assumed operating limits after congestion adjustment |
| Candidate selection | Industrial land ≥4 ha; spacing ≥3 km; maximum 120 | Guide assumptions |
| Unmet demand penalty | USD 100 per parcel | Optimization penalty, excluded from operating-cost metrics |
| Solver | CBC; 600-second limit; relative gap 0.005 | Guide settings; report feasible solutions separately from proven optima |

An illustrative scale check from the guide is 3.4 million households × 0.15 =
510,000 parcels per day; at 17,000 usable parcels per station this requires at least
30 stations. **This is an assumption-based check, not a computed ACS total or a
location-model result.**

## Repository layout

```text
config.yaml                 Shared assumptions and scenario settings
pyproject.toml              Dependencies, Ruff, and pytest configuration
src/lanet/config.py         Configuration loading and validation
src/lanet/demand.py         Period 1: ACS to H3
src/lanet/candidates.py     Period 2: candidate stations
src/lanet/travel.py         Period 2: directed drive-time matrix
src/lanet/model.py          Period 3: facility-location model
src/lanet/check.py          Period 3: independent solution checks
src/lanet/scenarios.py      Period 4: scenario analysis
sql/metrics.sql             Period 5: metric definitions; SQL implementation pending
scripts/                   Pipeline entry-point plan
tests/                     Offline configuration and CBC smoke tests
data/raw/                  Local downloads, ignored by Git
data/processed/            Local outputs, ignored by Git
.github/workflows/ci.yml    Ruff, pytest, and CBC verification
```

## Implementation plan

- [x] Period 0: configuration, package structure, offline tests, pre-commit hooks, CI.
- [ ] Period 1: county downloads and join checks complete; mainland geometry and H3 pending.
- [ ] Period 2: industrial candidates, road graph, directed times, infeasibility report.
- [ ] Period 3: CFLP v1, four hand-checked toy cases, independent solution checker.
- [ ] Period 4: single-sourcing, peak/outage stress tests, sensitivities, robust sites.
- [ ] Period 5: tested DuckDB metrics and Tableau exports/dashboard.
- [ ] Period 6: measured results, design decisions, limitations, reproducibility review.

See [guide review notes](docs/guide-review.md) for compatibility and modeling issues
to resolve before implementing later periods.

## Results and limitations

No operational results are available yet. Results will include selected stations,
utilization, served-weighted driving time, coverage, cost per served parcel, and
unmet demand for each scenario. Do not interpret placeholder modules as completed analyses.

Households are a demand proxy rather than observed orders. Parcel rates, costs,
capacities, and congestion are assumptions. Planned area-weighted allocation assumes
uniform household density within each block group. Industrial land alone does not
establish vacancy or leasing suitability. This project does not optimize vehicle routes
and does not represent the operations of any real company.
