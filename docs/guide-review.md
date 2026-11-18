# P2 guide review

The repository foundation and mainland demand layer are complete. The following
notes record compatibility decisions and remaining modeling issues. Measured
county and H3 results are reported in the README; scenario results are pending.

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

Before implementing period 4, choose and document the operating rule: either keep
whole-cell service and revise that test, or use a binary station-assignment variable
plus continuous served quantities so each cell can be partially served by its one
assigned station. The latter preserves single-sourcing while permitting exact
unmet quantities. A rounded v1 solution must also pass capacity checks before it
is used as a warm start.
