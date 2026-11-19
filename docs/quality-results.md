# Repaired solver-quality results

Selection among independently initialized scenario incumbents; quality subset has absolute dollar gap below that profile's single-site fixed fee. Not statistical independence or proof across optimal solutions.

All realized scenario solutions and final baseline used HiGHS. Fixed-HiGHS policy clarified at closeout, not claimed as preregistered. CBC comparison is one model/start/seed-1 experiment, not a solver-family ranking.

This is the final single complete quality batch. High gaps are retained; no second county-scale review or optimization round follows.

## Baseline comparison and continuation

Only the 600-second pair shares the same start. A possible 1,800-second run
continues from the checked HiGHS 600-second incumbent.

| Solver / limit | Stations | USD/day | Lower bound | Dollar gap | Gap % | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CBC600 | 38 | 1,014,486.18 | 975,319.75 | 39,166.42 | 3.8607 | 623.04 |
| HiGHS600 | 38 | 1,014,486.18 | 975,384.76 | 39,101.41 | 3.8543 | 610.28 |
| HiGHS1800_continuation | 37 | 992,177.79 | 975,386.05 | 16,791.73 | 1.6924 | 1802.46 |

## Independently initialized scenarios

| Scenario | Stations | Objective | Unmet/day | Mean min | Dollar gap | Gap % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 37 | 992,177.79 | 0.00 | 8.8159 | 16,791.73 | 1.6924 |
| peak_reoptimized | 50 | 1,336,644.84 | 0.00 | 8.1219 | 63,618.62 | 4.7596 |
| peak_fixed | 37 | 9,986,226.90 | 89,849.59 | 8.1830 | 8.49 | 0.0001 |
| outage | 36 | 962,542.48 | 0.00 | 8.2076 | 1,336.44 | 0.1388 |
| capacity_15000 | 47 | 1,239,788.46 | 0.00 | 8.5024 | 39,493.05 | 3.1855 |
| capacity_25000 | 32 | 868,716.37 | 0.00 | 9.0178 | 25,305.33 | 2.9130 |
| fixed_cost_15000 | 38 | 634,531.19 | 0.00 | 8.4686 | 22,193.16 | 3.4976 |
| fixed_cost_40000 | 38 | 1,584,179.73 | 0.00 | 8.4225 | 64,233.37 | 4.0547 |
| legacy31_peak_fixed | 31 | 11,446,784.18 | 105,977.77 | 8.1520 | 16.16 | 0.0001 |

Baseline dollar gap below 25,000 USD/day: True

The 1,800-second run improves the baseline from 38 to 37 sites. Its 16,791.73
USD/day gap passes the requested practical gate; it does not prove an exact
optimal station count. In this single seed-1 experiment, HiGHS at 600 seconds
only improves CBC's lower bound by about 65 USD/day. There is no evidence here
for a general claim that HiGHS suits this problem class better.

The two fixed-fee incumbents each use 38 sites versus the final baseline's 37.
Both fail their dollar-quality filters; the higher-fee result must not be read
as evidence that higher rent causes more stations. The original prediction is
not decisively validated. The peak full-service incumbent uses 50 sites versus
the preregistered capacity lower bound of 42. The legacy-31 peak shortage of
105,977.77/day exceeds the preregistered 91,204.05/day lower bound.

Common to all six profiles: 26.
C012, C014, C018, C023, C030, C038, C063, C065, C069, C077, C081, C082, C086, C087, C088, C093, C094, C097, C102, C103, C104, C105, C107, C109, C114, C116

Profiles passing the dollar-quality filter: baseline

Only 1 of 6 reoptimization profiles passes the dollar-quality filter. Raw
frequencies remain descriptive; no robust-station recommendation is made.

Frequencies are conditional on these scenarios, solver budgets and independent v1 starts.
The filter is a practical quality threshold, not a proof of an exact station count.
The 250 structural exclusions remain outside the model (350.56/day; peak 490.78/day).
Mean travel uses served demand. Penalties enter objective, not operating cost.

[Protocol](quality-review.md), [site frequencies](quality-station-frequency.csv).
Full audit retained locally at `data/processed/quality_v2/final_audit.json`.
