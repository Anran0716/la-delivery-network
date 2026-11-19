# Measured period-4 results

All figures are assumption-based planning results from independently checked
feasible incumbents. Solver bounds and actual elapsed times are retained.
Station counts are not proven minima. The fixed-network reference is the
frozen 38-station v2 baseline; the old 31-station network is a separate test.

Hard-service v1: **37 stations**, **990,938.45 USD/day**, **+125,301.38 USD/day** versus P=100.
Its 28 split cells become zero under v2. The two incumbent objectives differ
by 27,466.04 USD/day; this is not an exact optimal single-sourcing premium.

## Scenario comparison

| Scenario | Stations | Objective USD/day | Modeled unmet/day | Unmet % | Mean min | Gap % | Solve s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 38 | 1,018,404.49 | 0.00 | 0.0000 | 8.9769 | 4.2324 | 578.19 |
| peak_reoptimized | 49 | 1,370,016.63 | 0.00 | 0.0000 | 13.5935 | 7.0919 | 603.01 |
| peak_fixed | 38 | 8,022,547.02 | 69,924.39 | 9.8318 | 8.3279 | 0.0971 | 27.64 |
| outage | 37 | 993,442.71 | 0.00 | 0.0000 | 8.9819 | 0.5949 | 610.70 |
| capacity_15000 | 47 | 1,271,572.07 | 0.00 | 0.0000 | 12.6734 | 5.6122 | 603.49 |
| capacity_25000 | 38 | 1,018,404.49 | 0.00 | 0.0000 | 8.9769 | 17.1879 | 564.22 |
| fixed_cost_15000 | 38 | 638,404.49 | 0.00 | 0.0000 | 8.9769 | 4.0943 | 585.87 |
| fixed_cost_40000 | 38 | 1,588,404.49 | 0.00 | 0.0000 | 8.9769 | 4.3140 | 544.13 |
| legacy31_peak_fixed | 31 | 11,450,731.14 | 106,016.72 | 14.9067 | 8.1583 | 0.0349 | 18.78 |

Unmet percentages use the fixed 1,615-cell modeled universe. The same 250
structural exclusions add 350.56 parcels/day outside the model, or 490.78
during peak. Mean travel weights served parcels only. Objective includes
unmet penalties; penalties are not operating expense. Outage fixed cost
counts active sites and does not represent committed rent savings.

## Forecast check

The [original prediction record](period4-predictions.md) was committed before
these runs. The material fixed-cost threshold was a change of more than one site.

- Fixed fee 15,000: station change **+0**; locations added 0, removed 0. This is within the preregistered threshold.
- Fixed fee 40,000: station change **+0**; locations added 0, removed 0. This is within the preregistered threshold.
- Peak reoptimization needs at least 42 sites by aggregate capacity; the checked incumbent uses 49.
- Legacy 31-site peak: forecast lower bound 91,204.05 unmet/day; measured 106,016.72 (14.9067%).

Unchanged station counts alone do not establish fixed-cost insensitivity.
Sensitivity cases reuse the v2 baseline as their preferred start, and
time-limited search may retain it. Neither fixed-fee run improved that start.
The JSON audit records whether each start
was improved and cross-prices the three fixed-fee plans at each fee.
The 25,000-capacity case also retains its start, with a 17.1879% gap:
the capacity sensitivity is unresolved at this search limit.

## Capacity, geography and outage

For peak with the new fixed network, independent divisible-demand maximum flow leaves at least 69,849.59 parcels/day unmet. Total physical capacity exceeds demand; local coverage
and capacity bottlenecks explain most of the observed shortage.

Outage closes C027. Utilization is relaxed to 100% and eligibility to 45 minutes, so its change
from baseline combines three policy changes. The audit records changed
providers, positive and negative parcel-minute changes, and use of arcs
above 30 minutes. It is not an isolated causal estimate of station loss.

## Selection stability

**38 sites** appear in all six unique reoptimization incumbents. Capacity 20,000 and fixed fee 25,000 alias baseline and are not double-counted.
This is incumbent stability, not proof across all optimal solutions; shared
warm starts and unresolved gaps limit the inference.

`C003`, `C012`, `C014`, `C018`, `C020`, `C021`, `C023`, `C027`, `C030`, `C038`, `C048`, `C049`, `C051`, `C058`, `C059`, `C062`, `C063`, `C065`, `C069`, `C077`, `C081`, `C086`, `C087`, `C088`, `C089`, `C092`, `C093`, `C094`, `C097`, `C102`, `C103`, `C104`, `C105`, `C107`, `C109`, `C113`, `C114`, `C116`

Coverage alone forces the following 13 sites under the unchanged 30-minute
arcs and hard full-service rule (177 cells have exactly one candidate):

`C012`, `C030`, `C069`, `C081`, `C087`, `C093`, `C094`, `C103`, `C104`, `C105`, `C107`, `C109`, `C116`

Sites selected in only some profiles:

| Candidate | Selected / 6 |
| --- | ---: |
| C006 | 2 |
| C007 | 2 |
| C070 | 2 |
| C079 | 2 |
| C024 | 1 |
| C029 | 1 |
| C033 | 1 |
| C035 | 1 |
| C053 | 1 |
| C060 | 1 |
| C067 | 1 |
| C068 | 1 |
| C078 | 1 |
| C082 | 1 |
| C099 | 1 |
| C117 | 1 |

[All 117 candidates and coordinates](period4-station-frequency.csv), [scenario CSV](period4-scenarios.csv), and [full summaries, bounds, audit and hashes](period4-results.json).
