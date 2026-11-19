# Period 5, reduced scope: SQL metrics and a static map

Period 4 is frozen. This step reads its nine completed scenario outputs; it does
not rerun optimization or revisit solver conclusions. Tableau is deferred.

## Definitions

SQL source: [metrics.sql](../sql/metrics.sql). `assign_enriched` left-joins from
demand to actual served allocations and directed travel times, retaining fully
unserved cells. Travel times come from the existing `travel_times.parquet`
matrix, independently of the assignment table's cached time column.
`station_metrics` includes open stations, including unused ones.
`scenario_metrics` aggregates from the same enriched view.

| Metric | Numerator / denominator | Boundary behavior |
| --- | --- | --- |
| Station utilization | Served parcels / physical capacity Q | Closed sites excluded; unused open sites are 0. Above 85% is flagged, not rejected. Scenario utilization is total served / total open capacity. No open capacity gives NULL. |
| Weighted mean drive time | Sum(minutes × served parcels) / served parcels | Unmet demand excluded from denominator. No service gives NULL. |
| 20-minute coverage | Parcels served at <=20 minutes / total demand | Exactly 20 counts. Unserved demand counts as uncovered. Zero total demand gives NULL. |
| Cost per served parcel | (Open-site fixed cost + delivery cost) / served parcels | No unmet penalty included. Unused open sites still incur fixed costs. No service gives NULL. |
| Unmet rate | (Total demand − served parcels) / total demand | Full modeled baseline service gives 0. No service and positive demand gives 1. Zero demand gives NULL. Tiny negative residuals from floating-point summation are clamped to 0. |

These are node-to-node drive times, with the existing congestion multiplier.
No point-to-road connector time is added. Delivery cost is the frozen scenario's
rate × travel minutes × actual served volume. Fixed costs count active stations;
the outage scenario's lower active-site fixed cost is not savings on committed rent.

## Scope and input contracts

The exports include both `modeled` (the unchanged 1,615 cells) and `study_area`
(all 1,865 positive-demand mainland cells). The latter includes the same 250
structural exclusions as wholly unmet: 350.56 parcels/day, or 490.78 in peak.
Islands remain outside both scopes. The modeled baseline has zero unmet demand;
whole-mainland unmet is positive because of those explicit exclusions.

The five registered SQL inputs are demand, assignments, travel times, stations
and scenario parameters. Join keys must be unique. Missing road times, assignments
to closed sites, excess service and unknown keys stop metric generation.
Actual service uses the selected binary `w > 0.5` arcs. Unselected solver residuals
may be discarded only if their total absolute volume is <=0.01 parcel/scenario.
Genuinely tiny selected demand cells are retained; this is not low-demand pruning.

The script reconciles SQL service, unmet volume, fixed cost and delivery cost
against the frozen summaries within 0.01 in their respective units. Tests use
small in-memory DuckDB inputs, hand-calculated partial service, a fully unserved
cell, excluded demand, exact 20-minute/85% boundaries, unused and closed sites,
zero denominators, duplicate keys and missing references. No study data download
is needed to run tests.

## Outputs and reproduction

From the repository root, using the existing period-4 data:

```powershell
.venv\Scripts\python.exe -m pip install -e ".[plots]"
.venv\Scripts\python.exe -m pytest tests/test_metrics.py -q
.venv\Scripts\python.exe scripts/05_metrics.py
```

- [Scenario metrics, both scopes](metrics-scenarios.csv)
- [Readable modeled-scope result table](metrics-results.md)
- [Per-open-station utilization and 85% flags](metrics-stations.csv)
- [Static baseline station map](station-map.png)
- Local Parquet equivalents: `data/processed/metrics/`.
- [Setup, data assumptions and historical development](project-guide.md)

The map uses existing Census mainland land geometry in EPSG:3310, simplified
only for display. Blue circles show the frozen 37 selected sites, with marker
size reflecting served volume; gray crosses show other candidates. A minimum
marker area keeps low-volume sites visible. No site is labeled robust.
OSM candidate coordinates are representative points of
eligible industrial land, not verified available properties. No remote basemap
or additional data download is used.

Reliable planning findings remain conditional: normal-demand planning leaves
12.633% modeled demand unmet at a 40% peak. The modeled outage is absorbed after
utilization is relaxed to 100% and eligibility to 45 minutes. This does not imply
unconditional outage resilience or real-company operating performance.
