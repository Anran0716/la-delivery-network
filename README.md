An independent project to plan LA County delivery stations and test peak demand and outages.

| Scenario | Stations | Modeled unmet/day | Dollar gap/day |
| --- | ---: | ---: | ---: |
| Baseline | 37 | 0 | USD 16,791.73 |
| Peak: reoptimize | 50 | 0 | USD 63,618.62 |
| Peak: fixed network | 37 | 89,849.59 | USD 8.49 |
| Station outage | 36 | 0 | USD 1,336.44 |
| Capacity 15k / 25k | 47 / 32 | 0 / 0 | USD 39,493 / 25,305 |
| Fixed fee 15k / 40k | 38 / 38 | 0 / 0 | USD 22,193 / 64,233 |
| Peak: earlier 31-site network | 31 | 105,977.77 | USD 16.16 |

- Planning for normal demand leaves 12.6% unmet at a 40% peak; the modeled single-station outage is absorbed.
- Hard coverage is costly: serving the last ~219 parcels/day had a historical objective premium of ~USD 571 each.
- The 37-site baseline meets the dollar-gap gate; high-gap cases remain uncertain. [Results](docs/quality-results.md) · [Metrics](docs/metrics.md).

![Baseline station locations; circle size shows daily parcel volume](docs/station-map.png)

The outage scenario allows 100% utilization and up to 45 minutes of driving. Above results use modeled demand; exclusions and all five SQL metric definitions are in [metrics and limitations](docs/metrics.md).

Under matched 100% / 45-minute conditions, closing one station adds about 26 seconds to mean drive time, with zero modeled unmet demand in both checked solutions. [Outage control](docs/outage-control.md).
