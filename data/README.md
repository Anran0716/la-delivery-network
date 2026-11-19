# Local data

Create `raw/` for downloaded ACS, TIGER, and OSM data, and `processed/` for
derived Parquet tables and dashboard exports. Both directories are ignored by Git.
Road-network GraphML files are also ignored. No input data is needed for the tests.

Period-4 outputs under `processed/model_v2/` include one subdirectory per case,
the combined `scenario_summary.csv` / `.parquet`, `scenario_stations.parquet`,
and `scenario_assign.parquet`. Small audited snapshots are exported to `docs/`
for review without publishing raw data or solver MPS files.

`scenario_stations` retains all 117 candidates per scenario. `opened` is the
opening decision, `assigned_parcels` is actual daily served volume, and
`utilization = assigned_parcels / capacity` uses physical Q. Closed stations
have zero load and should be filtered from operating utilization metrics.

`scenario_assign` retains all 1,865 positive-demand mainland cells per scenario:

| Column | Meaning |
| --- | --- |
| `h3`, `scenario` | Unique cell/scenario pair in single-source v2 |
| `candidate_id` | Actual serving station; null when no volume is served |
| `demand_parcels` | Daily demand after the scenario multiplier |
| `served_parcels` | Actual daily volume served; `parcels` is the same legacy alias |
| `unmet_parcels` | Daily demand not served, including explicit structural exclusions |
| `fraction` | Served fraction, zero for an excluded or entirely unmet cell |
| `travel_time_min` | Directed, congestion-adjusted node-to-node time; null without service |
| `in_model` | True for the fixed 1,615-cell universe, false for the 250 exclusions |
| `solver_s` | Solver slack fraction for modeled cells; null for structural exclusions |

Each row must satisfy `served_parcels + unmet_parcels = demand_parcels` within
numerical tolerance. The excluded cells have zero served volume and their full
demand recorded as unmet; they are not solver variables and must not be silently
converted to `s=0`. Household estimates are not multiplied in peak cases, while
parcel demand and both forms of unmet volume are. Mean travel uses served parcels
only. Study-area unmet rates use the total mainland demand, including exclusions.

`scenario_summary.objective` includes `penalty_cost`; the penalty is an optimization
device, not actual operating expense. Operating cost is `fixed_cost + delivery_cost`.
The outage optimization charges fixed cost for the remaining active stations;
it does not represent committed rent or an outage-related financial saving.
