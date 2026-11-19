# P2 guide review

Periods 0–4 are complete. The following notes record compatibility decisions,
modeling choices and remaining metric-layer work. Measured county, routing,
v1/v2 and scenario results are reported in the README and `period4-results.md`.

## Directed travel and access resolved in period 2

Nearest-node distance on a simplified graph measures proximity to its retained
endpoints, so it can overstate road-access distance. The production audit now
measures projected EPSG:3310 distance to the nearest edge and selects the nearer
endpoint of that edge as the model node. All node, edge, and selected-endpoint
distances remain distinct. The graph is not split; connector and partial-edge
times remain outside the matrix, which limits door-to-door coverage interpretation.

The complete matrix retains all 117 × 1,865 directed OD pairs. The model export
keeps the 45-minute superset for outage analysis, while baseline feasible arcs
must filter `within_30_min`. Speeds use OSM maxspeed, observed highway-type means
for missing speeds, and a configured 30 km/h fallback. Congestion is applied once.
Sparse-matrix construction takes the fastest parallel edge rather than adding
parallel-edge times. Synthetic tests and 21 independent NetworkX OD checks verify
these contracts. The 250 demand cells with no baseline candidate remain explicit
for unmet-demand accounting in period 3.

## PuLP compatibility resolved in period 0

The guide's Python 3.11 and `PULP_CBC_CMD` examples require PuLP 3.x. This project
pins 3.3.0 and tests a real CBC solve. Upgrading to PuLP 4 would require the new
solver installation and API described in the upstream migration guide.

PuLP 3.x also splits temporary CBC file paths on whitespace. On Windows, a
temporary directory beneath this workspace contains spaces and can make solver
discovery succeed while the actual solve fails. The smoke test changes into its
isolated pytest directory and uses `keepFiles=True`, which gives CBC relative
filenames. Apply the same working-directory discipline to later model runs or
use a writable solver temporary path without spaces.

## V1 validation and finite penalties in period 3

The four guide cases were calculated by hand before implementation; see
`toy-model-hand-calculations.md`. Each is solved under both strong and weak linking.
`check_solution()` imports no PuLP code and independently checks dictionary keys,
bounds, binary openings, balance, capacity, allowed arcs, closed stations, costs,
and served-demand-weighted travel time. Corrupted-solution tests exercise rejection.

The guide's claim that a high per-parcel penalty guarantees baseline `s=0` does
not follow mathematically. A one-parcel cell with a 25,000 fixed opening cost and
100 unmet penalty is optimally left unmet. This counterexample is a regression
test. Keep finite-penalty output honest; requiring full service would need a hard
baseline condition or an explicit priority objective. Do not change parameters
silently to make a reported baseline appear fully served.

CBC's final result line and objective lower bound determine termination and gap.
PuLP 3.3 can label a stopped feasible solution `Optimal`, and CBC can also report
"Optimal solution found (within gap tolerance)". Neither is evidence of an exact
proof. The benchmark reports `(incumbent-lower_bound)/abs(incumbent)` from the
numeric bounds, rather than CBC's two-decimal printed gap.

The bundled Windows CBC is 2.10.3. An initial `threads=1` weak-link run stalled:
both coordination threads waited in `UserRequest` while CPU time stopped growing.
It was aborted and archived locally, and both formulations were restarted under
the same native serial `threads=0` profile. This is consistent with CBC's
[thread-mode documentation](https://www.coin-or.org/Doxygen/Cbc/classCbcModel.html),
which distinguishes parallel mode 0 (off) from mode 1 (testing). The abandoned
trial is excluded from timing comparisons; exact cause of its wait was not proven.

The 250 cells without any 30-minute candidate are outside the v1 optimization and
its objective. Model-selected-network unmet demand and that structural exclusion
must be reported separately, then combined for a county-wide unserved total.

## Access-time decision deferred to period 5

The v1 matrix and objective remain node-to-node. A metric-layer sensitivity could
add `route_edge_snap_m / (20_000 / 60)` minutes at an assumed 20 km/h. Whether to
add that diagnostic, and how to label its assumptions, is deferred to period 5.
It would not alter graph topology or silently change this baseline benchmark.

## Demand conservation boundary in period 1

Compare allocated demand against the same mainland population retained by the
study-area filter. Report excluded island households separately. H3's default
center-based polygon filling can omit boundary slivers; verify that the cell union
covers the allocation geometry before asserting conservation. Area weighting must
not silently lose households at the coast or county boundary.

## Single-sourcing and unmet demand in period 4

The guide changes allocation fractions to binary variables while retaining
`sum(x_ij) + s_j = 1`. Under those constraints, a cell is either fully served or
fully unmet. It cannot be partially served.

This conflicts with the proposed test requiring exactly 6 unmet parcels from four
cells of 14 parcels, with two fixed stations of capacity 25 each. Under strict
binary allocation, each station can serve only one cell, so at least 28 parcels
remain unmet, even if every station can reach every cell. The 6-parcel expectation
is an aggregate-capacity lower bound achievable with divisible demand, not with
that binary model.

Period 4 resolves this with binary station assignment `w_ij` and continuous served
fraction `x_ij`: `x_ij <= w_ij`, `w_ij <= y_i`, and `sum_i w_ij <= 1`. A cell can
be partially served at its one selected station. The remaining demand is `s_j`.
The synthetic fixed-network test now attains exactly six unmet parcels. With hard
`s=0`, balance forces `x=w`, allowing duplicate continuous columns to be eliminated.

The naive maximum-fraction rounding of the hard-service v1 incumbent violates
C012's 17,000-parcel usable capacity (17,037.93 assigned). It is rejected by the
independent checker. A deterministic repair supplies a feasible 38-station start,
which is checked again before any initial values reach CBC. Tests verify rejection
before solver invocation as well as the capacity repair. The incumbent comparison
and solver bounds are reported separately; a difference between two time-limited
incumbents is not an exact optimal single-sourcing premium.
