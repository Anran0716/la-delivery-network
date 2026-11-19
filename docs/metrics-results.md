# Frozen-solution SQL metrics

Modeled scope (1,615 cells); utilization is capacity-weighted across open sites.
No optimization was rerun. High-gap scenario results remain provisional.

| Scenario | Network utilization | Mean min | <=20 min | USD/served parcel | Unmet |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 68.65% | 8.816 | 96.06% | 1.953 | 0.000% |
| capacity_15000 | 72.06% | 8.502 | 95.62% | 2.441 | 0.000% |
| capacity_25000 | 63.50% | 9.018 | 96.20% | 1.710 | 0.000% |
| fixed_cost_15000 | 66.84% | 8.469 | 99.08% | 1.249 | 0.000% |
| fixed_cost_40000 | 66.84% | 8.422 | 96.68% | 3.118 | 0.000% |
| legacy31_peak_fixed | 97.62% | 8.152 | 79.15% | 1.403 | 14.901% |
| outage | 70.56% | 8.208 | 99.32% | 1.895 | 0.000% |
| peak_fixed | 83.97% | 8.183 | 83.27% | 1.611 | 12.633% |
| peak_reoptimized | 71.12% | 8.122 | 96.82% | 1.879 | 0.000% |

[Definitions, scope and boundary cases](metrics.md).
[Both scopes](metrics-scenarios.csv); [station utilization](metrics-stations.csv).
Study-area scope also counts 250 structural exclusions as unmet demand.
Lower mean time or per-served cost does not offset a larger unmet share.
