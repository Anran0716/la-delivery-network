# Project guide and historical development record

The completed reduced period 5 is documented in [SQL metrics and static map](metrics.md).

Current results: [final single-batch report](quality-results.md). Earlier numbers below are historical experiments; setup commands run from the repository root.

# LA delivery network

[![ci](https://github.com/Anran0716/la-delivery-network/actions/workflows/ci.yml/badge.svg)](https://github.com/Anran0716/la-delivery-network/actions/workflows/ci.yml)

An independent project to plan last-mile delivery stations in Los Angeles County.
**Period 4 quality review is in progress; do not use the earlier 38-site common
set as a robust-site recommendation. Period 5 is on hold.** The first scenario
batch below is retained as a historical benchmark, not an accepted sensitivity
conclusion. Its shared starts and dollar gaps leave station counts unresolved.
The checked single-source v2 planning incumbent opens **38 stations** at an
assumed objective of **1,018,404.49 USD/day**, with zero modeled unmet demand and
an **8.9769-minute** served-parcel-weighted drive time. Keeping those stations
under 40% peak demand leaves **69,924.39 parcels/day (9.8318%)** unmet even at
100% utilization. The baseline gap is 4.2324%, so its station count is not a proven
minimum. Another 250 structurally uncovered cells remain outside optimization.
Across six unique reoptimization incumbents, **38 sites** are common, including
13 required by coverage. Shared starts and unresolved gaps limit that stability
claim. **The data pipeline through period 4 is complete; optimization quality is
being repaired before DuckDB metrics or Tableau work.**

The pipeline uses ACS households, H3 demand cells, OSM industrial land, directed
driving times and capacitated facility-location models in PuLP. The next period
adds a tested DuckDB metrics layer feeding Tableau Public.

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
study data. Tested DuckDB metrics and Tableau exports remain for period 5.

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

## Routing access and model nodes

Production origins use **`route_lat` / `route_lng`** on the allocated demand land.
H3 centers remain audit coordinates. The same largest strongly connected directed
component is used for every point: **174,022 nodes / 460,060 edges**, from the cached
simplified graph's 175,463 nodes / 461,820 edges. Selected nodes are mutually
reachable; roads in disconnected fragments are excluded.

The model takes the **nearer endpoint of the nearest edge**, using straight-line
point-to-endpoint distance to choose between its endpoints. It does not split
edges or add nodes. `node_id = route_endpoint_node = route_node` is the production
key; `route_nearest_node` preserves the previous nearest-node choice. Missing land
coordinates stop the pipeline rather than falling back to an H3 center.

All three measurements use **EPSG:3310 meters**. Per the
[OSMnx nearest-edge API](https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.distance.nearest_edges),
both graph geometry and query points must be projected for accurate Euclidean
distances. The vectorized call returns `(edges, distances)`; each edge is `(u, v, key)`.

> Nearest-node distance on a simplified graph overstates access distance, so I measured distance to the nearest edge instead.

This diagnoses road proximity. Selecting an endpoint is a separate approximation:
the endpoint can be farther away than the globally nearest node. Long simplified
edges and one-way roads can affect the resulting origin/destination time. No
point-to-road connector or partial-edge travel time is added to the drive matrix.
Consequently, these are node-to-node planning times, not door-to-door delivery times.
A metric-layer access-time sensitivity at an assumed 20 km/h is deferred to period 5;
it does not change this model or the current matrix.

| Route-point distance check, 1,865 cells | Nearest node | Nearest edge | Selected endpoint |
| --- | ---: | ---: | ---: |
| Median, m | 433.69 | 213.83 | 473.09 |
| 95th percentile, m | 4,681.13 | 3,899.29 | 5,123.84 |
| Maximum, m | 7,997.85 | 7,666.27 | 10,632.69 |
| Parcel-weighted mean, m | 97.36 | 49.98 | 109.72 |
| Cells above 1,000 m | 625 | **462** | 659 |
| Share of parcel demand in warning cells | 0.473241% | **0.342956%** | 0.677874% |

The previous haversine nearest-node audit reported 627 warnings. Recomputing that
column in EPSG:3310 gives 625 because two borderline cases cross the threshold;
the consistent projected comparison is **625 to 462**, a 26.08% reduction. All
1,865 demand rows, household counts, and parcel totals are unchanged. The three
columns are `route_snap_m`, `route_edge_snap_m`, and `route_endpoint_snap_m` in
`demand_snaps.parquet` / `.csv`, with edge IDs, node IDs, and separate warning flags.
Original-center distances and paired comparisons also remain in the files.

The 462 edge warnings represent **11,622.87 households / 1,743.43 parcels per day**,
or 0.342956% of mainland demand. They are not all the low-demand cells:

| Households per edge-warning cell | Cells | Households | Parcels/day |
| --- | ---: | ---: | ---: |
| Less than 1 | 114 | 88.08 | 13.21 |
| 1 to less than 6.6666667 | 147 | 456.75 | 68.51 |
| 6.6666667 to less than 100 | 172 | 4,650.44 | 697.57 |
| 100 to less than 1,000 | 29 | 6,427.60 | 964.14 |
| 1,000 or more | 0 | 0 | 0 |

Only **261** of the 462 warnings are in the 538 low-demand cells; **201** have at
least one parcel/day. A spatial check places **322** warning points inside the OSM
Angeles National Forest boundary (relation 2786724). Its ID is resolved by name
from the original PBF and matched to the same-region protected-area polygons.
The other 140 are exported with coordinates for review; no unverified Antelope
Valley boundary classification is asserted. These are warnings against this
public driving graph, not proof that no road exists anywhere nearby. Forest,
private/service-road exclusions, and uniform area allocation all matter.

For the 30 original sea-center cells, the route-to-edge median is **79.74 m** and
one remains above 1 km. Land placement does not by itself establish public-road
access. Detailed exports are `snap_comparison.json`,
`edge_warning_household_groups.csv`, and `route_edge_warnings.csv`.

Public Overpass requests returned full-capacity errors or timed out during this
run. The graph is therefore built offline from the
[Geofabrik Southern California OSM extract](https://download.geofabrik.de/north-america/us/california/socal.html),
using a 500 m construction buffer, OSMnx simplification, and mainland truncation.
Original node IDs and one-way directions are retained. The offline filter records
OSMnx 2.1.2 `drive` exclusions, including private and service roads. Road data are
© OpenStreetMap contributors, supplied by Geofabrik under ODbL 1.0. The PBF header
identifies **2026-11-17 21:24:30 UTC**; SHA256 is
`294918282c23fde393c2e40bba6b91b2854ec117454a910604076d859d9853f1`.
The road snapshot is newer than ACS/TIGER 2023, so this is not a same-year reconstruction.

## Period 2 candidates and directed travel times

Reproduce from the existing demand layer:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[downloads]"
.venv\Scripts\python.exe scripts/audit_low_demand.py
.venv\Scripts\python.exe scripts/download_drive_graph.py
.venv\Scripts\python.exe scripts/compare_snaps.py
.venv\Scripts\python.exe scripts/download_landuse.py
.venv\Scripts\python.exe scripts/03_travel.py
.venv\Scripts\python.exe scripts/audit_travel.py
```

Industrial polygons come from `fclass='industrial'` in Geofabrik's regional land-use
GIS layer, corresponding to OSM `landuse=industrial` in the
[format specification](https://download.geofabrik.de/osm-data-in-gis-formats-free.pdf).
The downloaded GIS ZIP is retained locally, with component CRC checks and SHA256
`e674adbe81a73a5fa409531297d9a76ddc7303eac0c4fdc24b36d0c52578c554`.
The current ZIP has no published `.md5` sidecar (HTTP 404), so its manifest records
that separately rather than claiming an official checksum comparison.

Eligibility is measured **after clipping to county mainland land** in EPSG:3310.
Each polygon part must have at least 4 ha. An interior representative point is
chosen, then points are processed by descending clipped area, with OSM ID/part
as deterministic tie-breaks, retaining at least 3 km spacing up to 120 sites.
This prioritizes large mapped industrial areas; it is not an optimized site set.
The 6,756 regional industrial polygons produce 1,665 county-clipped parts,
557 eligible parts, and **117 candidates**. Their minimum spacing is **3,016.08 m**.
No duplicate model nodes occur. Final physical site points are checked against
the county mainland land boundary. Mapped industrial land alone does not prove vacancy,
lease availability, truck access, or permission to operate. Three candidate points
are over 1 km from a public graph edge and six from their selected endpoints;
those flags remain in `candidates.parquet` / `.csv` for site review.

Candidates use the same nearest-edge/nearer-endpoint policy as demand. OSMnx
[edge speed and travel-time functions](https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.routing.add_edge_speeds)
use OSM maxspeed tags, including mph conversion; missing speeds use the observed
mean for their highway type, with a **30 km/h** planning fallback. This is not
measured traffic speed. Directed shortest-path seconds are multiplied by **1.3**
and divided by 60 once. Parallel edges use their **minimum**, not summed, time.
SciPy batches directed Dijkstra searches; 21 real OD pairs were independently
checked against NetworkX. Synthetic tests cover direction, parallel edges,
congestion, disconnected destinations, boundary clipping, and spacing.

| Period 2 result | Value |
| --- | ---: |
| Candidate stations | **117** |
| Full directed station–cell pairs | **218,205** |
| Finite pairs | 218,205 |
| Pairs within 30 minutes, after congestion | **29,238** |
| Pairs within 45 minutes | **59,527** |
| Cells with no candidate within 30 minutes | **250 / 1,865** |
| Households in those cells | **2,337.04** |
| Share of mainland households | **0.068959%** |
| Parcels/day in those cells | 350.56 |
| Route points over 1 km from the nearest edge | **462** |

`travel_times_all.parquet` contains every candidate–cell pair.
`travel_times.parquet` / `.csv` contain the **45-minute** model superset, with
`within_30_min` flags. **Baseline feasible arcs must filter to 30 minutes**;
45-minute arcs are reserved for the outage scenario. `demand_coverage.parquet`
records candidate counts and minimum times; `uncovered_30min_cells.csv` lists
structural coverage gaps. `travel_report.json` and `travel_audit.json` retain
summary counts, household shares, assumptions, and verification results.

These are potential coverage counts with all candidates available. Station
selection and capacity can create further unmet demand in period 3. The 250 cells
have no baseline arc under this candidate set even before optimization, so they
must remain explicit in the unmet-demand accounting. Access offsets, site
suitability, OSM completeness, uniform demand allocation, and the county boundary
remain limitations. No cells or warning candidates are silently removed.

## Low-demand cells and model size

The threshold is **strictly fewer than 1 parcel/day**. At 0.15 parcels per household
this is fewer than **6.6666667 households** because allocated counts are fractional.
`households < 7` would flag 540 cells; two already exceed one parcel/day.

| Check | Result |
| --- | ---: |
| Low-demand cells | 538 / 1,865 (28.8472%) |
| Households in those cells | 1,326.313738 |
| Parcels/day in those cells | 198.947061 |
| Share of total parcel demand | 0.039136% |
| Cells retained | 1,865 |
| Total parcels/day retained | 508,353.45 |

**All 538 cells remain.** Consider merging in period 3 only if the solver reaches
its time limit. Potential variable savings depend on feasible station–cell arcs;
any aggregation must conserve demand and disclose its spatial/coverage effects.
`audit_low_demand.py` exports flags, `low_demand_cells.csv`, and
`low_demand_report.json`; `02_demand.py` also regenerates the flags.

## Hard full-service baseline update

The baseline now imposes **s=0** on all 1,615 modeled cells; the 250 structurally
uncovered cells remain separately reported. The [measured hard-service run](model-v1-full-service.json)
was completed before starting the county v2/scenarios.

| V1 comparison | P=100 penalized reference | Hard s=0 baseline |
| --- | ---: | ---: |
| Open stations | 31 | **37** |
| Objective, USD/day | 865,637.07 | **990,938.45** |
| Modeled unmet parcels/day | 219.43 | **0** |
| Weighted drive time, min | 9.0188 | 8.6533 |
| Split cells | 28 | **28** |

The hard-service incumbent adds **6 stations** and **125,301.38 USD/day** to the
objective. Operating cost rises by **147,244.41 USD/day**; the smaller objective
increase also reflects removal of 21,943.03 USD/day of unmet penalties. These are
incumbent comparisons, not an exact minimum cost of requiring full service.
The hard run stops on CBC's time limit with a **1.5855% gap** and 975,227.491 lower
bound; measured solve wall time is 653.95 seconds despite the configured soft
600-second limit. Every solution passes the independent checker.

This update illustrates why the aggregate 30-station capacity lower bound does
not determine the full-service optimum: coverage of small or remote cells can
require additional sites. The subsequent v2 reference uses the hard-service
policy, while peak/outage fixed-network scenarios permit partial unmet demand
at each cell's single selected station. The legacy 31-station peak remains a
separate comparison so its preregistered capacity prediction stays testable.

## Single-source v2 baseline and checked starts

V2 uses binary `w_ij` to choose at most one station for a cell, while continuous
`x_ij` is the fraction actually served. The constraints are `x_ij <= w_ij`,
`w_ij <= y_i`, and `sum_i w_ij <= 1`, alongside balance and capacity. A stress
scenario can therefore partially serve a cell at its one station, with the rest
recorded in s. This resolves the guide's indivisible-cell/unmet-demand conflict.
When `s=0`, these constraints imply `x=w`; the implementation eliminates the
duplicate continuous columns for hard-service runs without changing the model.

The [checked v2 baseline incumbent](model-v2-baseline.json) opens **38 sites**,
with objective **1,018,404.49 USD/day**, zero modeled unmet demand and **zero split
cells**. Its weighted drive time is **8.9769 min**. Relative to the hard-service v1
incumbent, this is **+1 station / +27,466.04 USD/day**. The v2 run stops on its time
limit with a **4.2324% gap**, so the incumbent difference is not a proven minimum
single-sourcing premium. Both problems retain the same demand universe and costs.

The naive maximum-fraction rounding of v1 was **rejected** by `check_solution()`:
C012 would receive **17,037.93 > 17,000** parcels/day. A deterministic capacity
repair produced a checked 38-station start. The solver only receives starts that
pass coverage, capacity, balance, opening and single-source checks; an invalid
start is rejected before CBC is invoked. Separate tests exercise that rejection,
capacity repair, station closure, and the exact six-parcel shortfall with two
25-capacity stations and four 14-demand cells. Directly corrupted w choices,
hard-service violations and fixed-network changes are also rejected. All
**87 offline tests pass**.

All nine period-4 scenarios have passed the independent audit. Reoptimization cases use
hard full service. Fixed-network peak and outage cases allow partial unmet demand.
Every scenario retains the same 1,615 modeled cells; the same 250 excluded cells
are reported outside optimization, scaled by the peak multiplier when applicable.
Outage extends travel eligibility to 45 minutes without changing that universe.
The main fixed network is the new v2 baseline; the legacy P=100 network of 31
stations is an additional peak comparison, not a replacement for the new baseline.

## Predictions registered before period 4

Recorded before running the hard-service baseline, v2, or any period-4 scenario
(UTC: 2026-11-19T03:01:26+00:00). These are
predictions to test, not measured scenario conclusions.

1. **Fixed costs 15,000 / 40,000 USD/day:** station counts should remain close to
   the new full-service v2 baseline, while locations may change. For this check,
   a change of more than one station is considered material and triggers review
   of geography, utilization, delivery-cost tradeoffs, and incumbent gaps.
   The capacity floor is necessary, rather than a proof of invariant site counts.
2. **Peak demand at 1.4 times baseline:** modeled demand becomes 711,204.05
   parcels/day. Reoptimization with full service, Q=20,000 and u=0.85 needs at
   least **42 stations**. Keeping the legacy **31-station** network and
   allowing u=1 gives capacity 620,000, hence an aggregate unmet lower bound of
   **91,204.05 parcels/day (12.824%)**, before geographic restrictions.

The unchanged model universe is 1,615 mainland cells. The 250 structural exclusions
remain outside optimization and are added separately to study-area unmet totals;
under peak demand their parcel volume is scaled by 1.4 too. The corresponding
whole-mainland demand is 711,694.83 parcels/day; its 31-station capacity shortfall
is at least 91,694.83 (12.884%). The new hard-service/v2 baseline may select more
than 31 stations. Main fixed-network scenarios will use that new baseline, with
an additional legacy-31 peak comparison to test the original conditional forecast.

The [original prediction record](period4-predictions.md) remains unchanged
from commit `a56fd6e`, made before these solves. Measured comparisons follow.

## Measured period-4 results

**Historical first batch, superseded for decision-making pending the quality
rerun.** Neither the common-site list nor the fixed-cost results below establish
robustness or cost insensitivity.

The [complete scenario report](period4-results.md) contains every station
count, objective, unmet volume, weighted drive time, elapsed solve time and gap,
plus the full common-site list and partial-selection frequencies. The
[audited JSON snapshot](period4-results.json) retains checks, bounds,
configuration, input/source/solver hashes and the largest modeled unmet cells.

| Scenario | Stations | Modeled unmet parcels/day | Modeled unmet rate | Gap |
| --- | ---: | ---: | ---: | ---: |
| V2 baseline, hard service | 38 | 0 | 0% | 4.2324% |
| Peak, reoptimized with hard service | 49 | 0 | 0% | 7.0919% |
| Peak, fixed new baseline and u=1 | 38 | 69,924.39 | 9.8318% | 0.0971% |
| Outage C027, u=1 and 45-minute eligibility | 37 active | 0 | 0% | 0.5949% |
| Capacity 15,000 | 47 | 0 | 0% | 5.6122% |
| Capacity 25,000 | 38 | 0 | 0% | 17.1879% |
| Fixed fee 15,000 | 38 | 0 | 0% | 4.0943% |
| Fixed fee 40,000 | 38 | 0 | 0% | 4.3140% |
| Peak, fixed legacy 31 stations and u=1 | 31 | 106,016.72 | 14.9067% | 0.0349% |

These are feasible incumbents, with no exact optimality proof. Structural exclusions
add 350.56 unmet parcels/day outside the model, or 490.78 under peak demand.
Objectives include unmet penalties; penalties are not actual operating expense.

The fixed-cost forecast is **consistent with the observed station counts**, but
is not strongly validated: all three fees keep the same 38 sites and assignments,
and neither sensitivity run improves its checked start. Cross-pricing all three
plans at each fee finds the same cost. The shared starts and 4.09–4.31% gaps mean
that genuine changes in optimal locations or counts remain unresolved.
Similarly, the unchanged 25,000-capacity incumbent has a 17.19% gap and does not
establish that larger stations cannot reduce the required network.

The peak capacity forecast holds as a lower bound: a 49-site full-service plan
is found versus the aggregate minimum of 42. The legacy 31-site network leaves
106,016.72 parcels/day unmet (14.9067%), exceeding the preregistered minimum of
91,204.05 (12.824%). Its independent divisible-demand flow lower bound is
105,977.77, confirming that geographic bottlenecks explain most of that excess.
The main fixed-network case uses the new 38-site reference;
its 69,924.39 unmet parcels/day are close to an independently computed divisible
maximum-flow lower bound of 69,849.59. Although total capacity is 760,000, local
coverage and capacity bottlenecks prevent that total from being fully usable.

Outage closes C027, carrying 16,998.35 baseline parcels/day. The remaining 37
stations serve all modeled demand at a mean of 8.9819 minutes, **+0.0050 minutes**
from baseline. Seventeen cells change provider; positive and negative changes
largely offset. No served arc exceeds 30 minutes in this incumbent. Utilization
also increases from 85% to 100%, so the small change is not an isolated effect of
losing one station. The outage objective counts active-site fixed costs and must
not be interpreted as a saving on committed rent.

The common set has **38 sites across six unique reoptimizations**; baseline also
serves as the Q=20,000 and f=25,000 control. This is selection stability among
checked incumbents, not a proof of robust optimal sites. None of the six
reoptimizations improves its checked start's objective. Separately, 177 cells
have exactly one 30-minute candidate, making **13 sites necessary for any full-service solution** under these
arcs: C012, C030, C069, C081, C087, C093, C094, C103, C104, C105, C107, C109, C116.
C093 and C116 serve only 88.98 and 75.74 parcels/day in baseline, illustrating how
coverage and the hard-service policy can require low-utilization stations.
The [candidate frequency CSV](period4-station-frequency.csv) lists every
site's coordinates, per-profile decisions and count; the report lists all common
and partially selected sites.

## Period 3 continuous-allocation CFLP v1

The [four hand calculations](toy-model-hand-calculations.md) were completed
before implementation or county optimization. The tests reproduce objectives
**100, 180, 140, and 220**, under both strong and weak linking. The coverage case
accepts either tied optimum, A alone or B alone. The final serial-profile gate:

```text
tests/test_model_toys.py::test_toy_base PASSED
tests/test_model_toys.py::test_toy_high_fixed_cost PASSED
tests/test_model_toys.py::test_toy_capacity_binds PASSED
tests/test_model_toys.py::test_toy_coverage PASSED
4 passed in 2.09s
```

With daily parcels `d_j`, opening variables `y_i`, allocation fractions `x_ij`,
and unmet fractions `s_j`, the objective is:

```text
min sum_i f_i*y_i + sum_(i,j in A) 0.015*t_ij*d_j*x_ij + 100*sum_j d_j*s_j
sum_i x_ij + s_j = 1                       for each modeled cell
sum_j d_j*x_ij <= 0.85*20,000*y_i           for each candidate station
x_ij <= y_i                               strong linking only
y binary; x and s continuous in [0,1]
```

Only **29,238 arcs at or below 30 minutes** enter either model. It has 117
candidate openings and 1,615 demand cells, representing **508,002.89 parcels/day**.
The 250 structurally uncovered cells (350.56 parcels/day) are exported separately,
outside model variables and the objective. Their demand is still included in
county-wide unserved totals. Per-station usable capacity is **17,000 parcels/day**,
so full modeled service needs at least **30 stations**. The independently checked
station count and station loads enforce this scale check.

Strong linking adds the per-arc `x_ij <= y_i` rows. They are redundant for integer
openings when all demand is positive, but strengthen the fractional relaxation.
Both models retain exactly the same candidate set, arcs, costs, demand and capacity.

`check_solution()` imports no PuLP and accepts `y`, `x`, `s`, and raw input data.
It recomputes balance, binary openings, bounds, capacity, coverage, closed-station
links, objective components and the served-parcel-weighted mean travel time.
It rejects deliberately corrupted solutions, including a capacity violation.
CBC text-rounding tolerances are 1e-6 for fractions, 0.01 parcel/day for capacity,
and 0.05 USD/day (or 1e-8 relative) for objective reconstruction. Unmet parcels
are excluded from the mean-travel denominator.

Reproduce **in this order** from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_model_toys.py tests/test_solution_check.py -v
# Continue only after every offline model/checker test passes:
.venv\Scripts\python.exe scripts/04_model_v1.py
.venv\Scripts\python.exe scripts/diagnose_v1_unmet.py
```

The county script runs strong then weak with a 600-second elapsed-time limit,
0.005 requested relative gap, seed 1, no warm start, and CBC native serial mode
(`threads=0`). An initial Windows CBC 2.10.3 trial using `threads=1` stalled in
thread waits; it was archived and excluded from this comparison, then both cases
were rerun with the same serial profile. See the [compatibility notes](guide-review.md).
Elapsed solve time includes MPS writing/solver invocation, while model-build time
and CBC's own wall time are recorded separately. These are individual local runs,
not repeated controlled performance measurements.

A finite penalty does **not** guarantee all `s_j=0`. The regression counterexample
is one parcel with a 25,000 fixed opening cost versus a 100 unmet penalty: leaving
it unmet is optimal. Full baseline service would require an explicit condition
or a priority objective. Existing assumptions are retained so the benchmark does
not hide any unmet demand. CBC termination reasons and numeric bounds determine
whether a result is proven optimal; PuLP's coarse `Optimal` label is insufficient.
The reported gap is `(incumbent - lower_bound) / abs(incumbent)`; CBC's rounded
printed `Gap: 0.00` is not treated as proof of a zero gap.

All inputs, raw CBC logs, MPS/solution files, full allocations, station loads,
unmet fractions, independent checks and summaries are retained locally under
`data/processed/model_v1/`. `structurally_uncovered.csv` is separate from model
`unmet.parquet`; `comparison.json` and `unmet_diagnostic.json` keep their scopes explicit.

### Measured baseline and linking comparison

The following [benchmark snapshot](model-v1-benchmark.json) preserves the
input hashes, binary hash, settings, numerical checks, bounds and outcomes. Both
models pass `check_solution()` and the quantity scale check. The strong-linking
incumbent has the lower independently recomputed objective and is retained as the
v1 baseline for later comparison; it is **not a proven exact optimum**.

| Check | Strong linking | Weak linking |
| --- | ---: | ---: |
| Open stations | 31 | 31 |
| Objective, USD/day including penalty | 865,637.07 | 866,747.11 |
| Parcel-weighted mean drive time, min | 9.0188 | 9.1457 |
| Positive s cells | 146 | 158 |
| Modeled unmet parcels/day | 219.43 | 220.87 |
| Elapsed solve time, seconds | 263.76 | 601.35 |
| CBC wall time, seconds | 262.37 | 600.55 |
| Initial LP lower bound, USD/day | 862,764 | 793,977 |
| Final lower bound, USD/day | 862,763.727 | 861,935.517 |
| Final gap | 0.3319% | 0.5551% |
| Stop condition | Within gap tolerance | Time limit |
| Proven exact optimum | No | No |

The stronger initial relaxation raises the bound from 793,977 to 862,764. It also
requires 30,970 rows versus 1,732, with 30,970 variables in both formulations.
For these individual serial runs, strong linking reaches the requested 0.5% gap
in 263.76 seconds; weak linking uses its time
limit and stops at 0.5551%. This is evidence for
using the stronger formulation here, rather than a universal speed guarantee.

**The baseline s values are not all zero.** All 146 positive s values are 1;
those cells have no open station within 30 minutes in the selected 31-station
network. They account for 219.43 parcels/day, of which 94 cells are low-demand.
Their penalty is **21,943.03 USD/day**, compared with **25,000 USD/day** per new
station. This is consistent with the finite-penalty tradeoff; it does not prove
that this incumbent's particular station set is globally optimal.

An independent maximum-flow diagnostic shows that opening all 117 candidates
can serve all **508,002.89** modeled parcels/day. The selected strong network's
maximum-flow shortfall is **219.43**, matching its unmet demand. The maximum
station load is 17,000.000015 parcels/day, within CBC text-rounding tolerance of
17,000. Neither the number of stations nor capacity units fail the scale check.
The model's finite penalty permits a network with some unserved cells; a business
requirement for zero modeled unmet demand would need an explicit baseline rule.
No penalties or constraints were silently changed to force the reported s values.

The **250 structural exclusions / 350.56 parcels/day** remain outside this
objective. Including them, the strong baseline leaves **569.99
parcels/day** unserved in the mainland study area. The weighted drive-time
calculation uses served parcels only and excludes both types of unserved demand.

The source road graph has **460,060 directed edges and zero explicit zero-time
edges**; its shortest edge is 0.026532 seconds. CSR conversion now rejects any
explicit zero-time edge, and a synthetic test exercises that guard. Zero OD time
for identical origin/destination nodes is a separate valid case.

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
| Fixed cost | USD 25,000 per station per day | Assumed rent and fixed labor; sensitivity measured with reported gaps |
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
scripts/                   Reproducible pipeline and audit entry points
tests/                     Offline geometry, routing, model and checker tests
data/raw/                  Local downloads, ignored by Git
data/processed/            Local outputs, ignored by Git
.github/workflows/ci.yml    Ruff, pytest, and CBC verification
```

## Implementation plan

- [x] Period 0: configuration, package structure, offline tests, pre-commit hooks, CI.
- [x] Period 1: county downloads, join checks, water audit, mainland geometry, H3 allocation.
- [x] Period 2: industrial candidates, nearest-edge/endpoints, directed times, coverage-gap report.
- [x] Period 3: CFLP v1, hand-checked cases, independent checks, linking benchmark and unmet diagnosis.
- [ ] Period 4: pipeline complete; solver-quality repair and independently initialized reruns in progress.
- [ ] Period 5: tested DuckDB metrics and Tableau exports/dashboard.
- [ ] Period 6: measured results, design decisions, limitations, reproducibility review.

See [guide review notes](guide-review.md) for compatibility and modeling issues
to resolve before implementing later periods.

## Results and limitations

### The cost of the last 0.04% of demand

In the historical continuous incumbents, enforcing full service adds six sites
to serve the final 219.43 modeled parcels/day (about 0.0432% of demand). The
objective increases by 125,301.38 USD/day, approximately **571 USD per additional
parcel**. Because the P=100 objective already includes an unmet penalty, the
increase in operating cost is actually 147,244.41 USD/day, approximately **671 USD
per additional parcel**. These are incumbent comparisons, not exact marginal-cost
proofs, and neither number is a quote for an outside carrier.

This exposes a business choice: obtain a real USPS or partner-carrier service
quote for that tail and compare outsourcing with dedicated stations. The model
should disclose this cost and let the business set service policy rather than
automatically demand a dedicated facility for every remote cell.

The aggregate capacity floor explains the rough scale of the P=100 network, but
does not explain the hard-service network. Thirteen sites are individually
forced by single-candidate coverage. A site can satisfy both coverage and
capacity needs, so those 13 cannot simply be subtracted from total station count.
County-only candidates and a hard 30-minute limit together raise the pressure
to open sites; relaxing either would require a separate, disclosed scenario.

The v1/v2 benchmarks, stress cases and sensitivity incumbents are reported above.
Tested SQL metrics and Tableau outputs remain for period 5.
These are assumption-based planning results, not measured operating performance.

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
