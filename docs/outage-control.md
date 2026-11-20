# Outage reassignment control

One additional fixed-network solve, explicitly requested after the frozen batch.
All 37 baseline sites remain open; utilization is 100%, eligibility 45 minutes.
The same 1,615 modeled cells and 250 structural exclusions are retained.
HiGHS, seed 1, serial, 600-second limit and 0.5% gap target; the checked
baseline allocation is the feasible start. Slack and single-sourcing match outage.

| Case | Sites | Mean min | Modeled unmet/day | Delivery USD/day | Dollar gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline (85%, 30 min) | 37 | 8.8159 | 0.00 | 67,177.79 | 16,791.73 |
| No closure (100%, 45 min) | 37 | 7.7746 | 0.00 | 59,242.95 | 77.57 |
| Outage (100%, 45 min) | 36 | 8.2076 | 0.00 | 62,542.48 | 1,336.44 |

Outage minus matched no-closure control: **+0.4330 minutes**.
This compares checked incumbents, not exact optima or a measured real-world causal effect.
Active-site fixed costs differ by 25,000 USD/day; that is not committed-rent savings.
Structural exclusions add 350.56 unmet parcels/day outside the modeled totals.
The original nine scenarios, predictions, metrics and map remain frozen.
