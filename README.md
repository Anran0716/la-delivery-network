# LA delivery network

[![ci](https://github.com/Anran0716/la-delivery-network/actions/workflows/ci.yml/badge.svg)](https://github.com/Anran0716/la-delivery-network/actions/workflows/ci.yml)

An independent project to plan the location and capacity of last-mile delivery
stations in Los Angeles County. The intended decision is how many stations to open,
where to put them, and how the network performs under a 40% demand peak or a station
outage. **Periods 0 and 1 are complete: the repository foundation, county inputs,
land geometry, and mainland H3 demand layer have been validated. No station
recommendations or location-model results have been computed yet.**

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

Tests use repository configuration, temporary files, synthetic geometries/graphs,
and a tiny local MILP.
CI installs software dependencies but does not download ACS, TIGER, OSM, or other
study data. Candidate selection, travel-time matrices, optimization, and SQL
metrics are reserved for later periods.

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

## Water audit and allocation geometry

Before constructing H3 demand, run:

```powershell
.venv\Scripts\python.exe scripts/audit_water.py
```

The requested metadata check on the joined TIGER inputs is:

```python
coastal = joined[joined.AWATER > 0]
print(len(coastal), coastal.AWATER.sum() / joined.AWATER.add(joined.ALAND).sum())
# 958 0.14511052006243513
```

`AWATER > 0` includes inland water as well as coastal water. The county-wide audit,
before removing islands, finds:

| Check | Result |
| --- | ---: |
| Block groups with water | 958 |
| Water area / total land and water area | 14.5111% |
| Zero-land block groups | 4 |
| Households in zero-land groups | 0 |
| Mixed land/water groups | 954 |
| Households in mixed groups | 513,663 |
| Land groups retained after water removal | 6,587 |
| Households retained | 3,390,254 |
| Remaining overlap with perennial-water faces | 0 m² |

The zero-land GEOIDs are `060375766020`, `060379901000`, `060379902000`, and
`060379903000`. Classification uses `ALAND`, not tract-number or final-digit rules.
Filtering these four records alone leaves the mixed polygons' water geometry intact.
Changing an area denominator to `ALAND` cannot locate or remove that water.

The allocation geometry therefore retains detailed TIGER block groups and subtracts
the same-year county topological faces with `LWFLAG="P"` (perennial water). Census
counts intermittent water as land for area measurement; its land/water flag
[documentation](https://www.census.gov/programs-surveys/geography/technical-documentation/user-note/tiger-geo-line.2009.html)
explains this classification. In the actual 2023 faces, `L + I` totals
10,515,988,121 m², exactly matching block-group `ALAND`; `P` totals 1,785,003,256 m²,
exactly matching `AWATER`. This also avoids removing the land portions of mixed
river features in the coarser area-hydrography layer.

`cb_2023_06_bg_500k` is a useful display layer. It uses generalized outlines and can
omit small areas; Census explicitly excludes area/perimeter analysis from its
[intended uses](https://www.census.gov/programs-surveys/geography/technical-documentation/naming-convention/cartographic-boundary-file.html).
The detailed TIGER faces provide the land geometry for area-weighted allocation.
Both intersection areas and their denominator will use that geometry in EPSG:3310.

The audit writes `data/processed/water_audit.json` and
`data/processed/block_groups_land_06037_2023.gpkg`, preserving household and MOE
values. It stops if source area totals disagree, positive demand has zero land,
land groups disappear, or residual water overlap exceeds the configured 1 m²
numerical tolerance. Islands remain in this output; mainland selection comes next.
`ALAND` and `AWATER` remain the original source attributes; the residual-water check
uses geometry, so it does not mistake retained metadata for unremoved water.
This mask represents Census land classification, not residential land use: uniform
household density within the retained land remains an assumption.

A coastal H3 cell can intersect land while its center lies offshore. The next demand
step retains the land intersection and stores a point on its retained mainland
portion for routing. Actual road-snap distances are compared below.

## Mainland demand results

After the water audit, run:

```powershell
.venv\Scripts\python.exe scripts/02_demand.py
```

The largest contiguous component is selected from the original county geometry,
before water removal. This retains mainland land separated by rivers. The prepared
land block groups are then partitioned against that component; a group spanning
mainland and island components causes an explicit error instead of a centroid-based
assignment. This dataset has no such spanning groups.

The retained land footprint is buffered by **2,000 meters in EPSG:3310**, converted
to WGS84, and filled with resolution-7 H3 cells. Allocation uses the unbuffered
land: each block group's households are multiplied by its cell-intersection area
divided by its complete retained land area. Buffering creates coverage candidates;
it does not create demand outside the study area. Per-group area coverage and
household conservation are checked without renormalizing missing intersections.

Area weighting distributes a block group's households across all intersecting cells.
Assigning its entire total to the centroid's cell would concentrate a large rural
block group's demand in one cell and leave its other cells artificially empty.
The chosen method assumes uniform household density within each block group's
retained land; the ACS data do not reveal household locations inside the group.

The four requested stage-1 tests use synthetic inputs without data downloads:
`test_allocation_conserves_total`, `test_allocation_split`,
`test_cell_polygon_contains_center`, and the parameterized `test_geoid_build`.

| Check | Computed result |
| --- | ---: |
| County household total | 3,390,254 |
| Excluded island households, six block groups | 1,231 |
| Mainland households, 6,581 block groups | 3,389,023 |
| Generated cells after the 2 km buffer | 1,965 |
| Cells intersecting mainland land | 1,902 |
| Positive-demand cells | 1,865 |
| Allocated household total | 3,389,023 |
| Absolute / relative household conservation error | 0 households / 0% |
| Largest per-group relative area coverage error | 9.004 × 10⁻¹⁴ |
| Original H3 centers in marine water, positive-demand cells | 30 / 1,865 |
| Original H3 centers in marine water, complete generated grid | 44 / 1,965 |
| Original centers outside the county, positive-demand cells | 72 / 1,865 |
| Assumption-based parcels per day | 508,353.45 |

For a scale check, the separately published 2023 ACS Avalon city household estimate
is **1,200**, with MOE **177**. It is a different geographic estimate from the island
block-group sum and is not used to force that sum to reconcile. The place GEOID
`0603274` is identified as Avalon city in the [2023 Census
Gazetteer](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_place_06.txt).

The five highest-demand cells are:

| H3 cell | Households | Center latitude | Center longitude |
| --- | ---: | ---: | ---: |
| `8729a1d63ffffff` | 42,431.58 | 34.065431 | -118.293267 |
| `8729a1d62ffffff` | 32,666.82 | 34.054670 | -118.268798 |
| `8729a1d6affffff` | 23,119.19 | 34.099363 | -118.318181 |
| `8729a5616ffffff` | 22,144.79 | 33.779439 | -118.166830 |
| `8729a1d75ffffff` | 21,682.88 | 34.043903 | -118.244331 |

Fractional households reflect area-weighted allocation. Positive demand extends
across the full retained mainland, including sparsely populated Antelope Valley;
zero-demand cells are removed after allocation.

Marine-center flags use TIGER ocean and bay/estuary polygons (`H2053`, `H2051`),
including Orange and Ventura county context for the buffered border. One positive
cell's sea center lies outside LA County. A center outside the county is not
automatically a sea center, and marine water is distinguished from inland water.
The original H3 `lat` and `lng` remain unchanged for this audit. Period 2 routing
must use the separate `route_lat` and `route_lng` on the largest retained,
positive-demand land part; this does not establish road accessibility by itself.

Outputs in `data/processed/` include `demand_cells.parquet`, `demand_land.parquet`,
`block_group_allocation.parquet`, `generated_h3_grid.parquet`,
`excluded_island_block_groups.csv`, `sea_center_demand_cells.csv`, and
`demand_report.json`. The source-to-cell crosswalk retains source MOEs and allocation
shares so later uncertainty analysis can account for shared source estimates.

## Preparation for routing and model size

Production demand-node selection uses **`route_lat` / `route_lng`**. The original
H3 `lat` / `lng` are retained as audit coordinates. Both point types are snapped
to the same largest strongly connected driving component. The selected model
column is `node_id = route_node`; there is no fallback to the H3 center when route
coordinates are missing.

The common strongly connected component makes its selected nodes mutually
reachable on the directed graph. This removes disconnected fragments, so its snap
distances can exceed distances to any road fragment. Long snaps remain flagged
for inspection; neither point type nor low demand is used to hide those cases.

```powershell
.venv\Scripts\python.exe -m pip install -e ".[downloads]"
.venv\Scripts\python.exe scripts/download_drive_graph.py
.venv\Scripts\python.exe scripts/compare_snaps.py
```

`demand_snaps.parquet` and its CSV companion retain `route_node`, `center_node`,
`route_snap_m`, `center_snap_m`, `snap_improvement_m`, both >1,000 m warning flags,
and the selected `node_id`. Positive improvement means the route point is closer.
These are point-to-nearest-node distances, not distance along the road or drive
times. The [OSMnx distance API](https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.distance.nearest_nodes)
returns distances in meters for the unprojected graph. The report includes median,
95th percentile, maximum, demand-weighted mean, warning counts, and both better and
worse paired outcomes for all cells, marine-center cells, and low-demand cells.

The source is configured explicitly. Public Overpass requests returned full-capacity
errors or timed out during this run, so the driving graph is built offline from the
[Geofabrik Southern California OSM extract](https://download.geofabrik.de/north-america/us/california/socal.html).
The extract is clipped to the county mainland with a 500 m construction buffer;
OSMnx simplifies the directed graph and truncates it to the mainland boundary.
Original OSM node IDs, road tags, and one-way directions are retained. The offline
way filter records the OSMnx 2.1.2 `drive` exclusions. GraphML, a locally generated
binary reload cache, and source/version/SHA256 metadata remain in ignored raw data.
Road data are © OpenStreetMap contributors, supplied by Geofabrik under ODbL 1.0.
This run's PBF header identifies the snapshot as **2026-11-17 21:24:30 UTC**;
its SHA256 is `294918282c23fde393c2e40bba6b91b2854ec117454a910604076d859d9853f1`.
The road snapshot is newer than the ACS and TIGER 2023 inputs, so this is not a
same-year reconstruction of demand and infrastructure.

The cached simplified graph contains **175,463 nodes / 461,820 directed edges**;
the common routing component contains **174,022 nodes / 460,060 edges**. The actual
comparison across all **1,865** positive-demand cells is:

| Point-to-node distance check | Original H3 center | Land route point |
| --- | ---: | ---: |
| Median, m | 493.35 | 433.15 |
| 95th percentile, m | 4,746.48 | 4,684.02 |
| Maximum, m | 8,002.69 | 8,002.71 |
| Parcel-weighted mean, m | 106.29 | 97.37 |
| Cells above 1,000 m | 661 | 627 |
| Total parcel demand in those warning cells | 0.611142% | 0.499512% |

Route points are closer in **1,037** paired cases and farther in **828**. Their
purpose is to place the origin on its allocated demand land, not to guarantee a
shorter road snap. The **30 cells whose original centers lie in the sea** show:

| Marine-center subset | Original H3 center | Land route point |
| --- | ---: | ---: |
| Median, m | 954.95 | 135.81 |
| 95th percentile, m | 1,780.70 | 767.05 |
| Parcel-weighted mean, m | 641.32 | 83.16 |
| Cells above 1,000 m | 13 | 1 |

Of these 30 cells, **28 improve and 2 worsen**. For example,
`8729a578dffffff` retains a 2,287.82 m route snap versus 2,103.42 m from its sea
center; its 11.80 parcels/day remain flagged. Land placement alone does not prove
public-road access. Across all cells, the 627 route warnings carry 2,539.28
parcels/day. The longest snaps occur at about 34.26°N, 117.96°W and nearby mountain
cells, with less than one allocated household per cell. This is consistent with
the uniform-within-block-group allocation limitation, rather than evidence of
households observed at those remote points. Long snaps still need review before
interpreting a travel-time matrix as coverage. No warning cells are discarded.

Both distance columns and node IDs are saved in `demand_snaps.parquet` / `.csv`;
`snap_comparison.json` records all-cell, marine-center, and low-demand summaries,
including warning demand shares. Read-back checks confirm unchanged H3 order,
households, parcels, and cell count, finite distances, and `node_id == route_node`
for every row.

The small-demand threshold is **strictly fewer than 1 parcel/day**. At 0.15 parcels
per household this is fewer than **6.6666667 households**, since allocated household
counts are fractional. Using `households < 7` would flag 540 cells; two of them
already exceed one parcel/day. The actual strict threshold identifies:

| Check | Result |
| --- | ---: |
| Low-demand cells | 538 / 1,865 (28.8472%) |
| Households in those cells | 1,326.313738 |
| Parcels per day in those cells | 198.947061 |
| Share of total parcel demand | 0.039136% |
| Cells retained in the demand layer | 1,865 |
| Total parcels per day retained | 508,353.45 |

The 538 low-demand cells have a route-snap median of 1,646.96 m, and 358 exceed
1,000 m. Their original-center median is 1,745.53 m, with 364 exceeding 1,000 m.

`audit_low_demand.py` adds `low_demand` flags and exports `low_demand_cells.csv` and
`low_demand_report.json`; the H3 generation script also regenerates these flags.
It does not delete or merge cells. A merging decision is deferred to period 3:
fewer demand units could reduce assignment variables and per-cell constraints,
while actual variable savings depend on feasible station–cell arcs. Any aggregation
must conserve demand and disclose its spatial and coverage effects.

## Download and join design decisions

Downloads first write to `.part` so an interrupted stream does not leave a final
filename that a later run would mistake for a completed download. Renaming within
the same directory publishes the finished stream in one filesystem operation.
This guards against partial visibility; ZIP CRC and table-schema checks separately
validate the downloaded content.

GEOID coverage checks compare which keys exist in each input. They do not establish
join cardinality: two tables can contain the same key set and still have repeated
rows. The explicit duplicate checks give source-specific diagnostics;
`validate="one_to_one"` also enforces the contract at the merge itself. That final
guard remains useful if preprocessing changes during a later refactor and prevents
duplicate matches from multiplying household counts.

ACS MOEs are confidence-interval half-widths, not counts. Variances add with covariance
terms; MOEs do not add directly. At a common confidence level, ignoring covariance
gives the approximation `MOE(sum) = sqrt(sum(MOE_i**2))`: MOEs of 3 and 4 give 5,
not 7. Census's [2023 worked examples](https://www2.census.gov/programs-surveys/acs/tech_docs/accuracy/2023_ACS_Accuracy_Document_Worked_Examples.pdf)
describe this approximation and its covariance limitation. Use a published county
MOE when available. H3 cells split from the same source block group share sampling
error and cannot be treated as independent when recombining their MOEs. These
sampling MOEs also exclude uncertainty in the assumed parcel rate and within-group
household distribution.

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
- [x] Period 1: county downloads, join checks, water audit, mainland geometry, H3 allocation.
- [ ] Period 2: industrial candidates, directed times, infeasibility report;
      road-graph cache and paired snapping audit are complete.
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
capacities, and congestion are assumptions. Area-weighted allocation assumes
uniform household density within each block group. Industrial land alone does not
establish vacancy or leasing suitability. This project does not optimize vehicle routes
and does not represent the operations of any real company.

Candidate stations are restricted to LA County (`candidates.boundary_scope: county`).
Demand near the county boundary could in reality be served by stations in Orange or
Ventura County. Excluding those alternatives can change selected sites, border
coverage, capacity needs, and cost; model results are conditional on this study-area
restriction. Road-graph truncation also excludes cross-boundary route alternatives.
