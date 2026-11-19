# Period 4 solver-quality repair

The initial shared-start batch is historical evidence, not a robust-site
recommendation. Period 5 is on hold until the quality review is reported.

Run `python scripts/04_quality.py` after the offline tests pass. The runner writes
to `data/processed/quality_v2/`, preserving the first batch. Its protocol hashes
the input tables, model/checker/start sources and runner; changed inputs or code
stop cache reuse. Cached solutions are independently checked again.

1. Hard full-service models fix every single-provider coverage station to y=1.
   Stress models permitting unmet demand do not impose those openings.
2. Solve the baseline's own continuous v1 without an inherited start, round and
   repair it, and independently validate the resulting v2 start.
3. Compare CBC and HiGHS on exactly that same v2 model and checked start, using
   a 600-second limit, 0.5% relative target, seed 1 and serial execution.
4. If the selected baseline incumbent's dollar gap is at least 25,000 USD/day,
   allow the baseline HiGHS run 1,800 seconds with the best checked incumbent.
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
