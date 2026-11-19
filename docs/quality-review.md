# Period 4 solver-quality repair

The single complete quality batch is finished. Its [final results](quality-results.md)
retain every gap, including failures of the quality filter. No second county-scale
review or optimization round follows; period 5 has not been started.

## Solver rule and scope

All scenarios use **HiGHS**, including baseline and its extended run. The reason
is the explicitly checked `setSolution` path for initial values. The CBC comparison
is descriptive and never selects the scenario solver. `SCENARIO_SOLVER` in the
runner makes this rule explicit.

This policy clarification was made at closeout, after the completed batch; it
is **not** a preregistered solver-choice rule. The realized baseline and all nine
scenario results already used HiGHS, so the code correction changes none of the
reported numbers and triggers no rerun. Original execution hashes remain in the
result snapshot; the edited runner is the clarified implementation.

CBC and HiGHS were compared **once**, on this model and this checked start, seed 1,
serial execution, with 600 seconds requested. The result supports a statement
about this experiment only, not that HiGHS is better for this problem class.

The completed `python scripts/04_quality.py` invocation followed offline tests and wrote
to `data/processed/quality_v2/`, preserving the first batch. Its protocol hashes
the input tables, model/checker/start sources and runner; changed inputs or code
stop cache reuse. Cached solutions are independently checked again.

1. Hard full-service models fix every single-provider coverage station to y=1.
   Stress models permitting unmet demand do not impose those openings.
   These bounds are already implied by full service and the strong links, even
   in the LP relaxation; explicit fixing does not change the feasible region or
   theoretical LP bound. A presolver may already infer them, so performance gains
   cannot be attributed to fixing alone without a separate controlled experiment.
2. Solve the baseline's own continuous v1 without an inherited start, round and
   repair it, and independently validate the resulting v2 start.
3. Compare CBC and HiGHS on exactly that same v2 model and checked start, using
   a 600-second limit, 0.5% relative target, seed 1 and serial execution.
4. If the HiGHS baseline incumbent's dollar gap is at least 25,000 USD/day,
   allow the baseline HiGHS run 1,800 seconds with its checked 600-second incumbent.
5. Every other scenario first solves its own continuous v1 cold, then generates
   and validates its own v2 start. Each phase has a 600-second limit. Fixed-network
   stress cases use the repaired baseline network; legacy31 remains a separate
   conditional forecast check. No scenario borrows another scenario's allocation.

The HiGHS PuLP interface does not automatically submit `setInitialValue` values.
`CheckedHiGHS` explicitly calls `setSolution` after the independent checker has
accepted the start. Bounds and gap come from the native solver info, not PuLP's
coarse status. See the official [Python interface examples](https://ergo-code.github.io/HiGHS/stable/interfaces/python/example-py/).

Report both relative and dollar gaps. A dollar gap smaller than one station's
fixed fee is the requested practical quality gate; it is not a mathematical proof
of an exact station count, because delivery costs and opening costs can trade off.
Any remaining frequency analysis must be described as selection frequency among
independently initialized, approximately optimal checked solutions, with each
solution's bound and quality retained. High-gap cases must be visibly separated.

The frequency export includes all six unique reoptimization profiles and a
separate quality-filtered count. The filter is an absolute gap below the profile's
own one-site fixed fee (15,000 / 25,000 / 40,000 USD/day), defined before those
scenario reruns complete. No profile is removed from the main scenario table.
A filtered subset does not support a robustness claim across excluded profiles.
